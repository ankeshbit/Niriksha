"""
backend/supabase_storage.py

Supabase Storage Integration Layer with local filesystem fallback.
Provides clean methods to upload and retrieve inspection images and report PDFs.
"""

import os
from pathlib import Path
from typing import Optional
from backend.config import settings

class SupabaseStorageService:
    def __init__(self):
        self.supabase_url = settings.SUPABASE_URL
        self.supabase_key = settings.SUPABASE_KEY
        self.bucket_images = settings.SUPABASE_BUCKET_IMAGES
        self.bucket_reports = settings.SUPABASE_BUCKET_REPORTS
        self.is_configured = bool(self.supabase_url and self.supabase_key)
        
        # Ensure local fallback directories exist
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        os.makedirs(settings.REPORTS_DIR, exist_ok=True)

    def upload_image(self, inspection_id: str, filename: str, file_bytes: bytes, content_type: str = "image/jpeg") -> str:
        """
        Saves image to local storage and Supabase Storage bucket.
        Returns the relative file path.
        """
        # Always write to local storage path for OCR processing efficiency
        dest_dir = Path(settings.UPLOAD_DIR) / "inspections" / inspection_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        local_path = dest_dir / filename
        with open(local_path, "wb") as f:
            f.write(file_bytes)

        if self.is_configured:
            try:
                # Upload to Supabase Storage via REST API (POST)
                url = f"{self.supabase_url}/storage/v1/object/{self.bucket_images}/inspections/{inspection_id}/{filename}"
                headers = {
                    "Authorization": f"Bearer {self.supabase_key}",
                    "Content-Type": content_type
                }
                import httpx
                response = httpx.post(url, headers=headers, content=file_bytes, timeout=10.0)
                if response.status_code in [200, 201]:
                    print(f"[SupabaseStorage] Successfully synced inspections/{inspection_id}/{filename} to Supabase")
                else:
                    print(f"[SupabaseStorage] Warning: Supabase upload failed with status {response.status_code}: {response.text}")
            except Exception as e:
                print(f"[SupabaseStorage] Warning: Failed to sync image to Supabase: {e}")

        # Return standard relative API path for local routing/serving
        return f"/uploads/inspections/{inspection_id}/{filename}"

    def upload_report_pdf(self, inspection_id: str, version: int, pdf_bytes: bytes) -> str:
        """
        Saves PDF report to reports directory and Supabase Storage bucket.
        Returns the relative file path.
        """
        dest_dir = Path(settings.REPORTS_DIR)
        dest_dir.mkdir(parents=True, exist_ok=True)
        filename = f"Report_{inspection_id}_v{version}.pdf"
        local_path = dest_dir / filename
        with open(local_path, "wb") as f:
            f.write(pdf_bytes)

        if self.is_configured:
            try:
                # Upload report to Supabase Storage bucket
                url = f"{self.supabase_url}/storage/v1/object/{self.bucket_reports}/{filename}"
                headers = {
                    "Authorization": f"Bearer {self.supabase_key}",
                    "Content-Type": "application/pdf"
                }
                import httpx
                response = httpx.post(url, headers=headers, content=pdf_bytes, timeout=10.0)
                if response.status_code in [200, 201]:
                    print(f"[SupabaseStorage] Successfully synced PDF report {filename} to Supabase")
                else:
                    print(f"[SupabaseStorage] Warning: Supabase report upload failed with status {response.status_code}: {response.text}")
            except Exception as e:
                print(f"[SupabaseStorage] Warning: Failed to sync report to Supabase: {e}")

        return str(local_path)

storage_service = SupabaseStorageService()
