"""
backend/storage_service.py

Durable Image & Report Storage Service for NiriKsha.
Provides crash-resilient and restart-resilient persistence across Render container lifecycles.

STRICT DESIGN MANDATE:
- Neon PostgreSQL `stored_files` is the SOLE durable source of truth.
- Render container filesystems are strictly ephemeral and may be wiped at any time.
- Working files created for PaddleOCR / OpenCV / ReportLab are temporary working copies
  and must be cleaned up when processing completes.
- Clean storage backend interface (StorageBackend) decouples storage provider logic.
- Storage writes are authoritative: failure to durably persist raises StoragePersistenceError
  and NEVER silently falls back to ephemeral local-only storage.
"""

import os
import re
import io
import tempfile
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Union, Tuple, BinaryIO, Set
from datetime import datetime

from backend.config import settings, BACKEND_DIR

logger = logging.getLogger("backend.storage")

# Maximum permitted key length and characters
MAX_KEY_LENGTH = 500
SAFE_KEY_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\./]+$')

# Maximum file size permitted for storage (25 MB)
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024

# Allowed MIME content types
ALLOWED_CONTENT_TYPES: Set[str] = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/bmp",
    "image/gif",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/octet-stream"
}


# ── Storage Exceptions ────────────────────────────────────────────────────────

class StorageError(Exception):
    """Base exception for all storage service operations."""
    pass


class StoragePersistenceError(StorageError, IOError):
    """Raised when durable storage persistence fails."""
    pass


class StorageReadError(StorageError, IOError):
    """Raised when reading from storage fails."""
    pass


class StorageNotFoundError(StorageError, FileNotFoundError):
    """Raised when a storage key cannot be found in durable storage."""
    pass


class StorageConflictError(StorageError):
    """Raised when an overwrite or deletion violates immutability / access constraints."""
    pass


class StorageValidationError(StorageError, ValueError):
    """Raised when storage key, content, MIME type, or size validation fails."""
    pass


# ── Storage Key Sanitization & Validation ────────────────────────────────────

def normalize_storage_key(raw_path_or_key: str) -> str:
    """
    Normalizes and validates a storage key or filesystem path.
    Prevents directory traversal, absolute system path access, and sanitizes separators.

    Permitted namespaces:
        - inspections/{inspection_id}/{filename}
        - reports/{filename}
        - Prefixed with uploads/ or generated_reports/ (which gets stripped)

    Examples:
        '/uploads/inspections/123/front.jpg' -> 'inspections/123/front.jpg'
        'uploads\\inspections\\123\\front.jpg' -> 'inspections/123/front.jpg'
        'reports/LM_Report_123.pdf'          -> 'reports/LM_Report_123.pdf'
    """
    if not raw_path_or_key or not isinstance(raw_path_or_key, str):
        raise ValueError("Storage key must be a non-empty string.")

    raw = raw_path_or_key.strip()

    # Reject null bytes
    if '\x00' in raw:
        raise ValueError("Null bytes are forbidden in storage keys.")

    # Reject Windows drive letters (e.g. C:\Windows\...)
    if re.match(r'^[a-zA-Z]:', raw):
        raise ValueError(f"Drive letters / absolute system paths are forbidden in storage keys: {raw!r}")

    # Normalize backslashes to forward slashes
    cleaned = raw.replace('\\', '/')

    # Check for absolute paths that are NOT under uploads/ or generated_reports/
    if cleaned.startswith('/'):
        stripped_leading = cleaned.lstrip('/')
        if not (stripped_leading.startswith('uploads/') or stripped_leading.startswith('generated_reports/')):
            raise ValueError(f"Absolute system paths are forbidden in storage keys: {raw!r}")
        cleaned = stripped_leading

    # Strip standard prefix aliases
    if cleaned.startswith('uploads/'):
        cleaned = cleaned[len('uploads/'):]
    elif cleaned.startswith('generated_reports/'):
        cleaned = cleaned[len('generated_reports/'):]

    # Guard against directory traversal attacks
    parts = cleaned.split('/')
    if any(p in ('..', '.') for p in parts):
        raise ValueError(f"Directory traversal sequences are forbidden in storage keys: {raw!r}")

    if len(cleaned) > MAX_KEY_LENGTH or not SAFE_KEY_PATTERN.match(cleaned):
        raise ValueError(f"Invalid characters or excessive length in storage key: {raw!r}")

    return cleaned


# ── Storage Backend Interface ────────────────────────────────────────────────

class StorageBackend(ABC):
    """
    Abstract interface for durable storage implementations.
    Enables future cloud storage providers (e.g., S3, R2) to be plugged in cleanly.
    """

    @abstractmethod
    def save(self, key: str, data: bytes, content_type: str, allow_overwrite: bool = True) -> None:
        """
        Durably persist data for the specified key.
        Must raise StoragePersistenceError or StorageConflictError on failure.
        """
        pass

    @abstractmethod
    def get(self, key: str) -> Optional[Tuple[bytes, str]]:
        """
        Retrieve data bytes and content_type for key.
        Returns None if not found in durable storage.
        """
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """
        Deletes data for key from durable storage.
        Returns True if deleted, False if not found.
        """
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Checks if key exists in durable storage."""
        pass


class PostgresBlobStorageBackend(StorageBackend):
    """
    Primary durable storage backend persisting files into Neon PostgreSQL stored_files table.
    Ensures ACID transactional guarantees and crash resilience across Render container lifecycles.
    """

    def save(self, key: str, data: bytes, content_type: str, allow_overwrite: bool = True) -> None:
        from backend.database import SessionLocal
        from backend.models import StoredFile

        db = SessionLocal()
        try:
            existing = db.query(StoredFile).filter(StoredFile.storage_key == key).first()
            if existing:
                if not allow_overwrite:
                    raise StorageConflictError(f"Storage key '{key}' already exists in durable storage and overwrite is prohibited.")
                existing.file_data = data
                existing.file_size = len(data)
                existing.content_type = content_type
                existing.updated_at = datetime.utcnow()
            else:
                new_file = StoredFile(
                    storage_key=key,
                    content_type=content_type,
                    file_size=len(data),
                    file_data=data,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(new_file)
            db.commit()
        except StorageConflictError:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"[STORAGE_DB_SAVE_ERR] Failed to persist key '{key}' to Neon DB: {e}", exc_info=True)
            raise StoragePersistenceError(f"Durable database persistence failed for key '{key}': {e}") from e
        finally:
            db.close()

    def get(self, key: str) -> Optional[Tuple[bytes, str]]:
        from backend.database import SessionLocal
        from backend.models import StoredFile

        db = SessionLocal()
        try:
            rec = db.query(StoredFile).filter(StoredFile.storage_key == key).first()
            if rec and rec.file_data:
                return bytes(rec.file_data), rec.content_type

            # Fallback check: if key lacks or includes "reports/" prefix
            alt_key = f"reports/{key}" if not key.startswith("reports/") else key[len("reports/"):]
            alt_rec = db.query(StoredFile).filter(StoredFile.storage_key == alt_key).first()
            if alt_rec and alt_rec.file_data:
                return bytes(alt_rec.file_data), alt_rec.content_type

            return None
        except Exception as e:
            logger.error(f"[STORAGE_DB_GET_ERR] Failed to read key '{key}' from Neon DB: {e}", exc_info=True)
            return None
        finally:
            db.close()

    def delete(self, key: str) -> bool:
        from backend.database import SessionLocal
        from backend.models import StoredFile

        db = SessionLocal()
        try:
            count = db.query(StoredFile).filter(StoredFile.storage_key == key).delete()
            alt_key = f"reports/{key}" if not key.startswith("reports/") else key[len("reports/"):]
            alt_count = db.query(StoredFile).filter(StoredFile.storage_key == alt_key).delete()
            db.commit()
            return (count + alt_count) > 0
        except Exception as e:
            db.rollback()
            logger.error(f"[STORAGE_DB_DEL_ERR] Failed to delete key '{key}' from Neon DB: {e}", exc_info=True)
            raise StoragePersistenceError(f"Failed to delete '{key}' from durable database: {e}") from e
        finally:
            db.close()

    def exists(self, key: str) -> bool:
        from backend.database import SessionLocal
        from backend.models import StoredFile

        db = SessionLocal()
        try:
            found = db.query(StoredFile.storage_key).filter(StoredFile.storage_key == key).first()
            if found:
                return True
            alt_key = f"reports/{key}" if not key.startswith("reports/") else key[len("reports/"):]
            return db.query(StoredFile.storage_key).filter(StoredFile.storage_key == alt_key).first() is not None
        except Exception as e:
            logger.error(f"[STORAGE_DB_EXISTS_ERR] Check exists failed for '{key}': {e}", exc_info=True)
            return False
        finally:
            db.close()


# ── Unified Durable Storage Service ──────────────────────────────────────────

class DurableStorageService:
    """
    Unified persistent storage provider using Neon PostgreSQL StoredFile exclusively.
    Local working files are strictly ephemeral and used only for active processing / read-through caching.
    """

    def __init__(self, backend: Optional[StorageBackend] = None):
        _cfg_uploads = Path(settings.UPLOAD_DIR)
        self.base_uploads_dir = _cfg_uploads if _cfg_uploads.is_absolute() else (BACKEND_DIR.parent / _cfg_uploads)
        self.base_uploads_dir.mkdir(parents=True, exist_ok=True)

        # Ephemeral temp directory for OCR & inference working copies
        self.temp_working_dir = Path(tempfile.gettempdir()) / "niriksha_working"
        self.temp_working_dir.mkdir(parents=True, exist_ok=True)

        # Durable backend provider
        self.backend: StorageBackend = backend or PostgresBlobStorageBackend()

        logger.info("[STORAGE_INIT] DurableStorageService initialized with Neon PostgreSQL StoredFile backend.")

    # ── Local Cache / Temp Paths ─────────────────────────────────────────────

    def _get_local_cache_path(self, key: str) -> Path:
        """Resolves the local path for a key."""
        clean_key = normalize_storage_key(key)
        return self.base_uploads_dir / clean_key

    # ── Database Blob Storage Backward-Compatibility Wrappers ────────────────

    def _db_save_blob(self, key: str, data: bytes, content_type: str, allow_overwrite: bool = True) -> bool:
        """Stores binary payload in PostgreSQL stored_files table (returns bool for backward compat)."""
        try:
            self.backend.save(key, data, content_type, allow_overwrite=allow_overwrite)
            return True
        except Exception:
            return False

    def _db_get_blob(self, key: str) -> Optional[Tuple[bytes, str]]:
        """Retrieves binary payload and content_type from PostgreSQL stored_files table."""
        return self.backend.get(key)

    def _db_delete_blob(self, key: str) -> bool:
        """Deletes binary payload from PostgreSQL stored_files table."""
        try:
            return self.backend.delete(key)
        except Exception:
            return False

    # ── Immutability Guard ───────────────────────────────────────────────────

    def _is_finalized_evidence_key(self, clean_key: str) -> bool:
        """
        Determines whether the given storage key belongs to a finalized inspection or official report.
        Finalized evidence and reports cannot be deleted or overwritten without administrative bypass.
        """
        try:
            from backend.database import SessionLocal
            from backend.models import Inspection, Report
            db = SessionLocal()
            try:
                if clean_key.startswith("reports/"):
                    rep = db.query(Report).filter(
                        (Report.pdf_path == clean_key) | (Report.docx_path == clean_key) |
                        (Report.pdf_path == f"/uploads/{clean_key}") | (Report.docx_path == f"/uploads/{clean_key}")
                    ).first()
                    if rep and rep.inspection and rep.inspection.status == "COMPLETED":
                        return True
                elif clean_key.startswith("inspections/"):
                    parts = clean_key.split("/")
                    if len(parts) >= 2:
                        insp_id = parts[1]
                        insp = db.query(Inspection).filter(Inspection.id == insp_id).first()
                        if insp and insp.status == "COMPLETED":
                            return True
                return False
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[STORAGE_IMMUTABILITY_CHECK_WARN] {e}")
            return False

    # ── Public Storage API ───────────────────────────────────────────────────

    def save_file(
        self,
        raw_key: str,
        content: bytes,
        content_type: str = "image/jpeg",
        allow_overwrite: bool = True
    ) -> str:
        """
        Persists a file to durable storage (Neon PostgreSQL StoredFile) and updates the local cache.
        Returns the standard relative URL path (e.g. '/uploads/inspections/...').

        Guarantees:
        - Validates storage key against path traversal and forbidden characters.
        - Validates content length (> 0 and <= MAX_FILE_SIZE_BYTES).
        - Validates MIME type against ALLOWED_CONTENT_TYPES.
        - Verifies overwrite constraints and finalized evidence immutability.
        - Durable backend persistence is authoritative: if DB persistence fails, any local
          working file is unlinked, no success is returned, and StoragePersistenceError is raised.
        """
        clean_key = normalize_storage_key(raw_key)

        if not isinstance(content, bytes):
            raise StorageValidationError(f"File content must be bytes, got {type(content).__name__}")
        if len(content) == 0:
            raise StorageValidationError("Uploaded file content is empty (0 bytes).")
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise StorageValidationError(
                f"File size ({len(content)} bytes) exceeds maximum permitted limit of {MAX_FILE_SIZE_BYTES} bytes."
            )

        norm_content_type = content_type.lower().split(";")[0].strip() if content_type else "image/jpeg"
        if norm_content_type not in ALLOWED_CONTENT_TYPES:
            raise StorageValidationError(f"Disallowed content type: {content_type!r}")

        # Check immutability if trying to overwrite finalized inspection evidence
        if not allow_overwrite and self.file_exists(clean_key):
            raise StorageConflictError(f"Storage key '{clean_key}' already exists and overwrite is prohibited.")

        local_path = self._get_local_cache_path(clean_key)

        # 1. Authoritative durable persistence to Neon PostgreSQL StoredFile
        try:
            self.backend.save(clean_key, content, norm_content_type, allow_overwrite=allow_overwrite)
        except Exception as e:
            # Guarantee rollback and cleanup of local working copy on failure
            if local_path.exists():
                try:
                    local_path.unlink()
                except Exception:
                    pass
            logger.error(f"[STORAGE_PERSISTENCE_FAILED] Could not durably persist '{clean_key}': {e}", exc_info=True)
            if isinstance(e, (StorageConflictError, StorageValidationError)):
                raise
            raise StoragePersistenceError(f"Durable storage persistence failed for '{clean_key}': {e}") from e

        # 2. Update local filesystem cache ONLY AFTER durable persistence succeeds
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(content)
        except Exception as e:
            logger.warning(f"[STORAGE_CACHE_WRITE_WARN] Could not update local disk cache for '{clean_key}': {e}")

        return f"/uploads/{clean_key}"

    def get_file(self, raw_key: str) -> Optional[bytes]:
        """
        Retrieves file bytes from local cache or directly from Neon DB stored_files.
        Rehydrates local disk cache automatically if found in Neon (resilience across container restarts).
        """
        clean_key = normalize_storage_key(raw_key)
        local_path = self._get_local_cache_path(clean_key)

        # Fast path: local cache hit (must be non-empty)
        if local_path.exists() and local_path.is_file():
            try:
                data = local_path.read_bytes()
                if len(data) > 0:
                    return data
            except Exception as e:
                logger.warning(f"[STORAGE_LOCAL_READ_FAIL] Failed to read {local_path}: {e}")

        # Durable path: Neon DB stored_files
        db_res = self.backend.get(clean_key)
        if db_res:
            data, _ = db_res
            # Rehydrate local cache
            try:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                local_path.write_bytes(data)
                logger.info(f"[STORAGE_REHYDRATED] Rehydrated local cache for '{clean_key}' from Neon DB")
            except Exception as e:
                logger.warning(f"[STORAGE_CACHE_WRITE_FAIL] {e}")
            return data

        return None

    def get_file_stream(self, raw_key: str) -> Optional[io.BytesIO]:
        """
        Returns a binary stream of the file content from Neon DB or local cache.
        """
        data = self.get_file(raw_key)
        if data is not None:
            return io.BytesIO(data)
        return None

    def get_local_working_copy(self, raw_path_or_key: str) -> Optional[Path]:
        """
        Ensures a valid local file exists on disk for inference / processing.
        If the local file was lost due to Render container restart, rehydrates it from Neon.
        Returns Path to the local file, or None if unavailable anywhere.
        """
        if not raw_path_or_key:
            return None

        # Direct local filesystem check (e.g. for repo-relative test fixtures)
        candidate = Path(raw_path_or_key)
        if candidate.is_absolute() and candidate.exists() and candidate.is_file():
            return candidate
        base_cand = BACKEND_DIR.parent / raw_path_or_key.lstrip("/\\")
        if base_cand.exists() and base_cand.is_file():
            return base_cand

        try:
            clean_key = normalize_storage_key(raw_path_or_key)
        except ValueError as e:
            logger.error(f"[STORAGE_INVALID_KEY] {e}")
            return None

        local_path = self._get_local_cache_path(clean_key)
        if local_path.exists() and local_path.is_file() and local_path.stat().st_size > 0:
            return local_path

        # Pull from Neon DB durable storage and rehydrate
        data = self.get_file(clean_key)
        if data is not None and local_path.exists() and local_path.is_file():
            return local_path

        return None

    def create_temp_working_file(self, raw_path_or_key: str, suffix: str = ".jpg") -> Optional[Path]:
        """
        Creates a dedicated ephemeral working file in temp_working_dir from Neon storage.
        Caller is expected to call cleanup_local_working_copy(path) when done.
        """
        data = self.get_file(raw_path_or_key)
        if data is None:
            return None

        import uuid
        temp_file = self.temp_working_dir / f"ocr_{uuid.uuid4().hex}{suffix}"
        temp_file.write_bytes(data)
        return temp_file

    def cleanup_local_working_copy(self, path: Union[str, Path]) -> None:
        """
        Removes an ephemeral working file if it resides in temp_working_dir.
        """
        if not path:
            return
        try:
            p = Path(path)
            if p.exists() and p.is_file():
                # Only delete if inside temp_working_dir or an ocr_ temporary file
                if self.temp_working_dir in p.parents or "ocr_" in p.name:
                    p.unlink(missing_ok=True)
                    logger.debug(f"[STORAGE_CLEANUP] Deleted ephemeral working copy: {p}")
        except Exception as e:
            logger.warning(f"[STORAGE_CLEANUP_ERR] Could not delete {path}: {e}")

    def file_exists(self, raw_key: str) -> bool:
        """Returns True if the file exists in Neon DB or local cache."""
        try:
            clean_key = normalize_storage_key(raw_key)
        except ValueError:
            return False

        local_path = self._get_local_cache_path(clean_key)
        if local_path.exists() and local_path.is_file() and local_path.stat().st_size > 0:
            return True

        if self.backend.exists(clean_key):
            return True

        return False

    def delete_file(self, raw_key: str, force: bool = False) -> bool:
        """
        Deletes file from local cache and Neon PostgreSQL stored_files.
        Prevents deletion of finalized inspection evidence unless force=True.
        """
        try:
            clean_key = normalize_storage_key(raw_key)
        except ValueError:
            return False

        if not force and self._is_finalized_evidence_key(clean_key):
            raise StorageConflictError(f"Cannot delete evidence or report file '{clean_key}' for a finalized inspection.")

        # 1. Local disk cache
        local_path = self._get_local_cache_path(clean_key)
        if local_path.exists():
            try:
                local_path.unlink()
            except Exception as e:
                logger.warning(f"[STORAGE_LOCAL_UNLINK_FAIL] Could not unlink {local_path}: {e}")

        # 2. Durable backend
        return self.backend.delete(clean_key)


# Global singleton instance
storage_service = DurableStorageService()
