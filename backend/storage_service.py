"""
backend/storage_service.py

Durable Image & Report Storage Service for NiriKsha.
Provides crash-resilient and restart-resilient persistence across Render container lifecycles.

Architecture:
1. Object Storage Tier (Supabase Storage):
   - Active if SUPABASE_URL and SUPABASE_KEY are provided.
   - Synchronizes blobs to cloud buckets via authenticated REST API.
2. PostgreSQL Blob Tier (Neon Database):
   - Always active as zero-dependency persistent storage in table `stored_files`.
   - Guarantees images survive all Render restarts/redeployments even on Render Free tier.
3. Ephemeral Disk Cache:
   - Maintains working copies on local filesystem for PaddleOCR, OpenCV, and ReportLab.
   - Transparently rehydrates from persistent tiers whenever local files are missing.
"""

import os
import re
import logging
from pathlib import Path
from typing import Optional, Union, Tuple
from datetime import datetime

from backend.config import settings, BACKEND_DIR

logger = logging.getLogger("backend.storage")

# Maximum permitted key length and characters
MAX_KEY_LENGTH = 500
SAFE_KEY_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\./]+$')


def normalize_storage_key(raw_path_or_key: str) -> str:
    """
    Normalizes and validates a storage key or filesystem path.
    Prevents directory traversal and sanitizes separators.

    Examples:
        '/uploads/inspections/123/front.jpg' -> 'inspections/123/front.jpg'
        'uploads\\inspections\\123\\front.jpg' -> 'inspections/123/front.jpg'
        'inspections/123/front.jpg'          -> 'inspections/123/front.jpg'
    """
    if not raw_path_or_key or not isinstance(raw_path_or_key, str):
        raise ValueError("Storage key must be a non-empty string.")

    # Remove drive letters if present (e.g. C:)
    cleaned = re.sub(r'^[a-zA-Z]:', '', raw_path_or_key.strip())
    # Normalize backslashes to forward slashes
    cleaned = cleaned.replace('\\', '/')
    # Strip leading slashes
    cleaned = cleaned.lstrip('/')

    # Strip standard prefix aliases
    if cleaned.startswith('uploads/'):
        cleaned = cleaned[len('uploads/'):]
    elif cleaned.startswith('generated_reports/'):
        cleaned = cleaned[len('generated_reports/'):]

    # Guard against directory traversal attacks
    parts = cleaned.split('/')
    if '..' in parts or '.' in parts:
        raise ValueError(f"Directory traversal sequences are forbidden in storage keys: {raw_path_or_key!r}")

    if len(cleaned) > MAX_KEY_LENGTH or not SAFE_KEY_PATTERN.match(cleaned):
        raise ValueError(f"Invalid characters or excessive length in storage key: {raw_path_or_key!r}")

    return cleaned


class DurableStorageService:
    """
    Unified persistent storage provider with automatic multi-tier fallback:
    Local Disk Cache <-> PostgreSQL StoredFiles <-> Supabase Storage Bucket
    """

    def __init__(self):
        self.supabase_url = (getattr(settings, "SUPABASE_URL", None) or "").strip()
        self.supabase_key = (getattr(settings, "SUPABASE_KEY", None) or "").strip()
        self.bucket_images = getattr(settings, "SUPABASE_BUCKET_IMAGES", "inspection-images")
        self.bucket_reports = getattr(settings, "SUPABASE_BUCKET_REPORTS", "inspection-reports")
        self.is_supabase_configured = bool(self.supabase_url and self.supabase_key)

        _cfg_uploads = Path(settings.UPLOAD_DIR)
        self.base_uploads_dir = _cfg_uploads if _cfg_uploads.is_absolute() else (BACKEND_DIR.parent / _cfg_uploads)
        self.base_uploads_dir.mkdir(parents=True, exist_ok=True)

        if self.is_supabase_configured:
            logger.info(f"[STORAGE_INIT] Supabase Storage configured: {self.supabase_url}")
        else:
            logger.info("[STORAGE_INIT] Supabase not configured. Using Neon PostgreSQL StoredFile persistent tier.")

    # ── Tier 1: Local Disk Cache Helpers ─────────────────────────────────────

    def _get_local_cache_path(self, key: str) -> Path:
        """Resolves the safe local cache path for a key."""
        clean_key = normalize_storage_key(key)
        return self.base_uploads_dir / clean_key

    # ── Tier 2: Database Blob Storage (Neon PostgreSQL) ──────────────────────

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
            logger.error(f"[STORAGE_DB_SAVE_ERR] Failed to persist key '{key}' to DB: {e}", exc_info=True)
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
                return None
            finally:
                db.close()
        except Exception as e:
            logger.error(f"[STORAGE_DB_GET_ERR] Failed to read key '{key}' from DB: {e}", exc_info=True)
            return None

    def _db_delete_blob(self, key: str) -> bool:
        """Deletes binary payload from PostgreSQL stored_files table."""
        try:
            from backend.database import SessionLocal
            from backend.models import StoredFile

            db = SessionLocal()
            try:
                db.query(StoredFile).filter(StoredFile.storage_key == key).delete()
                db.commit()
                return True
            finally:
                db.close()
        except Exception as e:
            logger.error(f"[STORAGE_DB_DEL_ERR] Failed to delete key '{key}' from DB: {e}", exc_info=True)
            return False

    # ── Tier 3: Supabase Object Storage ──────────────────────────────────────

    def _supabase_upload(self, key: str, data: bytes, content_type: str) -> bool:
        """Uploads file to Supabase Storage bucket via REST API."""
        if not self.is_supabase_configured:
            return False
        try:
            import httpx
            bucket = self.bucket_reports if key.startswith("reports/") else self.bucket_images
            url = f"{self.supabase_url}/storage/v1/object/{bucket}/{key}"
            headers = {
                "Authorization": f"Bearer {self.supabase_key}",
                "Content-Type": content_type,
                "x-upsert": "true"
            }
            resp = httpx.post(url, headers=headers, content=data, timeout=15.0)
            if resp.status_code in (200, 201):
                logger.info(f"[SUPABASE_UPLOAD_OK] Synced '{key}' to Supabase bucket '{bucket}'")
                return True
            else:
                logger.warning(f"[SUPABASE_UPLOAD_WARN] Status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            logger.warning(f"[SUPABASE_UPLOAD_FAIL] Failed to sync to Supabase: {e}")
            return False

    def _supabase_download(self, key: str) -> Optional[bytes]:
        """Downloads file from Supabase Storage bucket via REST API."""
        if not self.is_supabase_configured:
            return None
        try:
            import httpx
            bucket = self.bucket_reports if key.startswith("reports/") else self.bucket_images
            url = f"{self.supabase_url}/storage/v1/object/{bucket}/{key}"
            headers = {
                "Authorization": f"Bearer {self.supabase_key}"
            }
            resp = httpx.get(url, headers=headers, timeout=15.0)
            if resp.status_code == 200:
                return resp.content
            return None
        except Exception as e:
            logger.warning(f"[SUPABASE_DOWNLOAD_FAIL] Failed to download '{key}': {e}")
            return None

    # ── Public Storage API ───────────────────────────────────────────────────

    def save_file(
        self,
        raw_key: str,
        content: bytes,
        content_type: str = "image/jpeg"
    ) -> str:
        """
        Persists a file across durable storage tiers and updates the local disk cache.
        Returns the standard relative URL path (e.g. '/uploads/inspections/...').
        """
        clean_key = normalize_storage_key(raw_key)

        # 1. Update local filesystem cache
        local_path = self._get_local_cache_path(clean_key)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(content)

        # 2. Persist to Neon PostgreSQL
        self._db_save_blob(clean_key, content, content_type)

        # 3. Persist to Supabase if configured
        if self.is_supabase_configured:
            self._supabase_upload(clean_key, content, content_type)

        return f"/uploads/{clean_key}"

    def get_file(self, raw_key: str) -> Optional[bytes]:
        """
        Retrieves file bytes from local disk cache, DB stored_files, or Supabase.
        Rehydrates local disk cache automatically if found in persistent storage.
        """
        clean_key = normalize_storage_key(raw_key)
        local_path = self._get_local_cache_path(clean_key)

        # Fast path: local disk cache hit
        if local_path.exists() and local_path.is_file():
            try:
                return local_path.read_bytes()
            except Exception as e:
                logger.warning(f"[STORAGE_LOCAL_READ_FAIL] Failed to read {local_path}: {e}")

        # Persistent path 1: Neon DB stored_files
        db_res = self._db_get_blob(clean_key)
        if db_res:
            data, _ = db_res
            # Rehydrate local cache
            try:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                local_path.write_bytes(data)
                logger.info(f"[STORAGE_REHYDRATED] Rehydrated local cache for '{clean_key}' from DB")
            except Exception as e:
                logger.warning(f"[STORAGE_CACHE_WRITE_FAIL] {e}")
            return data

        # Persistent path 2: Supabase Storage
        if self.is_supabase_configured:
            sb_data = self._supabase_download(clean_key)
            if sb_data:
                try:
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    local_path.write_bytes(sb_data)
                    # Also write to DB for faster future access
                    self._db_save_blob(clean_key, sb_data, "image/jpeg")
                    logger.info(f"[STORAGE_REHYDRATED] Rehydrated local cache for '{clean_key}' from Supabase")
                except Exception as e:
                    logger.warning(f"[STORAGE_CACHE_WRITE_FAIL] {e}")
                return sb_data

        return None

    def get_local_working_copy(self, raw_path_or_key: str) -> Optional[Path]:
        """
        Ensures a valid local file exists on disk for inference / processing.
        If the file was lost due to container restart, rehydrates it from durable storage.
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

        # Attempt to pull from durable storage
        data = self.get_file(clean_key)
        if data is not None and local_path.exists() and local_path.is_file():
            return local_path

        return None

    def file_exists(self, raw_key: str) -> bool:
        """Returns True if the file exists in any storage tier."""
        try:
            clean_key = normalize_storage_key(raw_key)
        except ValueError:
            return False

        local_path = self._get_local_cache_path(clean_key)
        if local_path.exists() and local_path.is_file():
            return True

        if self._db_get_blob(clean_key) is not None:
            return True

        if self.is_supabase_configured and self._supabase_download(clean_key) is not None:
            return True

        return False

    def delete_file(self, raw_key: str) -> bool:
        """Deletes file from local cache, PostgreSQL stored_files, and Supabase."""
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

        # 3. Supabase
        if self.is_supabase_configured:
            try:
                import httpx
                bucket = self.bucket_reports if clean_key.startswith("reports/") else self.bucket_images
                url = f"{self.supabase_url}/storage/v1/object/{bucket}/{clean_key}"
                headers = {"Authorization": f"Bearer {self.supabase_key}"}
                httpx.delete(url, headers=headers, timeout=10.0)
            except Exception:
                pass

        return True


# Global singleton instance
storage_service = DurableStorageService()
