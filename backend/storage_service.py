"""
backend/storage_service.py

Durable Image & Report Storage Service for NiriKsha.
Provides crash-resilient and restart-resilient persistence across Render container lifecycles.

STRICT DESIGN MANDATE:
- Neon PostgreSQL `stored_files` is the SOLE durable source of truth.
- Render container filesystems are strictly ephemeral and may be wiped at any time.
- Working files created for PaddleOCR / OpenCV / ReportLab are temporary working copies
  and must be cleaned up when processing completes.
- NO external object-storage dependencies (no Supabase, S3, R2, Firebase).
"""

import os
import re
import io
import tempfile
import logging
from pathlib import Path
from typing import Optional, Union, Tuple, BinaryIO
from datetime import datetime

from backend.config import settings, BACKEND_DIR

logger = logging.getLogger("backend.storage")

# Maximum permitted key length and characters
MAX_KEY_LENGTH = 500
SAFE_KEY_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\./]+$')


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


class DurableStorageService:
    """
    Unified persistent storage provider using Neon PostgreSQL StoredFile exclusively.
    Local working files are strictly ephemeral and used only for active processing.
    """

    def __init__(self):
        _cfg_uploads = Path(settings.UPLOAD_DIR)
        self.base_uploads_dir = _cfg_uploads if _cfg_uploads.is_absolute() else (BACKEND_DIR.parent / _cfg_uploads)
        self.base_uploads_dir.mkdir(parents=True, exist_ok=True)

        # Ephemeral temp directory for OCR & inference working copies
        self.temp_working_dir = Path(tempfile.gettempdir()) / "niriksha_working"
        self.temp_working_dir.mkdir(parents=True, exist_ok=True)

        logger.info("[STORAGE_INIT] DurableStorageService initialized with Neon PostgreSQL StoredFile tier.")

    # ── Local Cache / Temp Paths ─────────────────────────────────────────────

    def _get_local_cache_path(self, key: str) -> Path:
        """Resolves the local path for a key."""
        clean_key = normalize_storage_key(key)
        return self.base_uploads_dir / clean_key

    # ── Database Blob Storage (Neon PostgreSQL StoredFile) ────────────────────

    def _db_save_blob(self, key: str, data: bytes, content_type: str) -> bool:
        """Stores binary payload in PostgreSQL stored_files table."""
        try:
            from backend.database import SessionLocal
            from backend.models import StoredFile

            db = SessionLocal()
            try:
                existing = db.query(StoredFile).filter(StoredFile.storage_key == key).first()
                if existing:
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
                return True
            finally:
                db.close()
        except Exception as e:
            logger.error(f"[STORAGE_DB_SAVE_ERR] Failed to persist key '{key}' to Neon DB: {e}", exc_info=True)
            return False

    def _db_get_blob(self, key: str) -> Optional[Tuple[bytes, str]]:
        """Retrieves binary payload and content_type from PostgreSQL stored_files table."""
        try:
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
            finally:
                db.close()
        except Exception as e:
            logger.error(f"[STORAGE_DB_GET_ERR] Failed to read key '{key}' from Neon DB: {e}", exc_info=True)
            return None

    def _db_delete_blob(self, key: str) -> bool:
        """Deletes binary payload from PostgreSQL stored_files table."""
        try:
            from backend.database import SessionLocal
            from backend.models import StoredFile

            db = SessionLocal()
            try:
                db.query(StoredFile).filter(StoredFile.storage_key == key).delete()
                # Also delete alt key if any
                alt_key = f"reports/{key}" if not key.startswith("reports/") else key[len("reports/"):]
                db.query(StoredFile).filter(StoredFile.storage_key == alt_key).delete()
                db.commit()
                return True
            finally:
                db.close()
        except Exception as e:
            logger.error(f"[STORAGE_DB_DEL_ERR] Failed to delete key '{key}' from Neon DB: {e}", exc_info=True)
            return False

    # ── Public Storage API ───────────────────────────────────────────────────

    def save_file(
        self,
        raw_key: str,
        content: bytes,
        content_type: str = "image/jpeg"
    ) -> str:
        """
        Persists a file to Neon PostgreSQL StoredFile and maintains local cache copy.
        Returns the standard relative URL path (e.g. '/uploads/inspections/...').
        """
        clean_key = normalize_storage_key(raw_key)

        # 1. Update local filesystem cache
        local_path = self._get_local_cache_path(clean_key)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(content)

        # 2. Persist durably to Neon PostgreSQL
        saved_db = self._db_save_blob(clean_key, content, content_type)
        if not saved_db:
            logger.warning(f"[STORAGE_WARN] Could not persist '{clean_key}' to Neon StoredFile table.")

        return f"/uploads/{clean_key}"

    def get_file(self, raw_key: str) -> Optional[bytes]:
        """
        Retrieves file bytes from local cache or directly from Neon DB stored_files.
        Rehydrates local disk cache automatically if found in Neon.
        """
        clean_key = normalize_storage_key(raw_key)
        local_path = self._get_local_cache_path(clean_key)

        # Fast path: local cache hit
        if local_path.exists() and local_path.is_file():
            try:
                return local_path.read_bytes()
            except Exception as e:
                logger.warning(f"[STORAGE_LOCAL_READ_FAIL] Failed to read {local_path}: {e}")

        # Durable path: Neon DB stored_files
        db_res = self._db_get_blob(clean_key)
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
        if local_path.exists() and local_path.is_file():
            return local_path

        # Pull from Neon DB durable storage
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
                # Only delete if inside temp_working_dir
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
        if local_path.exists() and local_path.is_file():
            return True

        if self._db_get_blob(clean_key) is not None:
            return True

        return False

    def delete_file(self, raw_key: str) -> bool:
        """Deletes file from local cache and Neon PostgreSQL stored_files."""
        try:
            clean_key = normalize_storage_key(raw_key)
        except ValueError:
            return False

        # 1. Local disk
        local_path = self._get_local_cache_path(clean_key)
        if local_path.exists():
            try:
                local_path.unlink()
            except Exception:
                pass

        # 2. Database
        self._db_delete_blob(clean_key)

        return True


# Global singleton instance
storage_service = DurableStorageService()
