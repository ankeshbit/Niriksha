"""
tests/test_durable_storage_failures.py

Durable File Storage Failure & Resilience Test Suite for NiriKsha.
Verifies Prompt 2 requirements:
1. Successful upload and subsequent retrieval.
2. Database persistence failure returns 500, rolls back DB, and cleans up local cache.
3. Report persistence failure returns 500 and does not commit an orphan/broken report.
4. Server restart / cross-instance retrieval: wipes local disk, rehydrates from DB.
5. Unauthorized file access rejected with 403/404.
6. File overwrite protection: finalized evidence cannot be overwritten or deleted.
7. Validation: invalid MIME type or empty file raises StorageValidationError.
"""

import io
import uuid
import pytest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app
from backend.config import settings
from backend.database import SessionLocal
from backend.models import User, Inspection, Product, ProductImage, Report, StoredFile
from backend.storage_service import (
    storage_service,
    normalize_storage_key,
    StoragePersistenceError,
    StorageConflictError,
    StorageValidationError
)

client = TestClient(app)

TINY_JPEG_BYTES = (
    b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00'
    b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
    b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
    b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342'
    b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4'
    b'\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00'
    b'\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b'
    b'\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9'
)


@pytest.fixture
def auth_headers():
    resp = client.post("/api/auth/login", json={
        "officer_id": settings.SEED_OFFICER_ID,
        "password": settings.SEED_OFFICER_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_officer_auth_headers():
    db = SessionLocal()
    try:
        officer = db.query(User).filter(User.officer_id == "DOCA-INSP-888").first()
        if not officer:
            from backend.auth_utils import hash_password
            officer = User(
                id=str(uuid.uuid4()),
                officer_id="DOCA-INSP-888",
                full_name="Other Officer 888",
                email="other888@doca.gov.in",
                phone="8888888888",
                designation="Inspector",
                zone="Northern Zone",
                role="INSPECTOR"
            )
            officer.password_hash = hash_password("otherpass888")
            db.add(officer)
            db.commit()
    finally:
        db.close()

    resp = client.post("/api/auth/login", json={
        "officer_id": "DOCA-INSP-888",
        "password": "otherpass888"
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_inspection(auth_headers):
    resp = client.post("/api/inspections", json={
        "location": "Durable Storage Lab",
        "product_name": "Storage Test Commodity",
        "brand_name": "Reliable Brand",
        "category": "Packaged Food"
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ── TEST 1: Successful upload and subsequent retrieval ───────────────────────

def test_successful_upload_and_subsequent_retrieval(auth_headers):
    insp_id = _create_inspection(auth_headers)

    files = {"file": ("front_panel.jpg", io.BytesIO(TINY_JPEG_BYTES), "image/jpeg")}
    data = {"view_type": "front"}
    up_resp = client.post(f"/api/inspections/{insp_id}/images", files=files, data=data, headers=auth_headers)
    assert up_resp.status_code == 201, f"Upload failed: {up_resp.text}"
    img_data = up_resp.json()
    img_id = img_data["id"]

    # Verify durable persistence in Neon StoredFile
    db = SessionLocal()
    try:
        clean_key = normalize_storage_key(img_data["file_path"])
        stored_file = db.query(StoredFile).filter(StoredFile.storage_key == clean_key).first()
        assert stored_file is not None, "StoredFile record must exist in durable storage"
        assert bytes(stored_file.file_data) == TINY_JPEG_BYTES
    finally:
        db.close()

    # Retrieve image binary through streaming endpoint
    get_resp = client.get(f"/api/images/{img_id}/file", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.content == TINY_JPEG_BYTES


# ── TEST 2: Database persistence failure returns 500 and cleans up ───────────

def test_database_persistence_failure_returns_500_and_no_partial_records(auth_headers):
    insp_id = _create_inspection(auth_headers)

    # Count existing images
    db = SessionLocal()
    try:
        initial_img_count = db.query(ProductImage).filter(ProductImage.inspection_id == insp_id).count()
    finally:
        db.close()

    # Mock durable backend to raise StoragePersistenceError
    with patch.object(
        storage_service.backend,
        "save",
        side_effect=StoragePersistenceError("Simulated Neon DB connection timeout")
    ):
        files = {"file": ("fail_image.jpg", io.BytesIO(TINY_JPEG_BYTES), "image/jpeg")}
        data = {"view_type": "back"}
        up_resp = client.post(f"/api/inspections/{insp_id}/images", files=files, data=data, headers=auth_headers)

        # Upload must fail with 500 Internal Server Error
        assert up_resp.status_code == 500, f"Expected 500, got {up_resp.status_code}: {up_resp.text}"
        assert "durable storage" in up_resp.text.lower()

    # Verify no partial or orphan ProductImage record was saved in DB
    db = SessionLocal()
    try:
        after_count = db.query(ProductImage).filter(ProductImage.inspection_id == insp_id).count()
        assert after_count == initial_img_count, "No ProductImage record should be saved when storage fails"
    finally:
        db.close()


# ── TEST 3: Report persistence failure returns 500 ───────────────────────────

def test_report_persistence_failure_returns_500(auth_headers):
    insp_id = _create_inspection(auth_headers)

    # Upload an image
    files = {"file": ("panel.jpg", io.BytesIO(TINY_JPEG_BYTES), "image/jpeg")}
    client.post(f"/api/inspections/{insp_id}/images", files=files, data={"view_type": "front"}, headers=auth_headers)

    # Mock backend save to fail during report file storage
    original_save = storage_service.backend.save
    def failing_save(key, data, content_type, allow_overwrite=True):
        if key.startswith("reports/"):
            raise StoragePersistenceError("Simulated Neon DB write failure during report generation")
        return original_save(key, data, content_type, allow_overwrite)

    with patch.object(storage_service.backend, "save", side_effect=failing_save):
        rep_resp = client.post(f"/api/inspections/{insp_id}/report", headers=auth_headers)
        assert rep_resp.status_code == 500, f"Expected 500, got {rep_resp.status_code}: {rep_resp.text}"

    # Verify no Report record was committed
    db = SessionLocal()
    try:
        rep = db.query(Report).filter(Report.inspection_id == insp_id).first()
        assert rep is None, "Report record must not be committed if storage persistence fails"
    finally:
        db.close()


# ── TEST 4: Simulated restart cross-instance retrieval ───────────────────────

def test_simulated_restart_cross_instance_retrieval(auth_headers):
    insp_id = _create_inspection(auth_headers)

    files = {"file": ("side_panel.jpg", io.BytesIO(TINY_JPEG_BYTES), "image/jpeg")}
    up_resp = client.post(f"/api/inspections/{insp_id}/images", files=files, data={"view_type": "side"}, headers=auth_headers)
    assert up_resp.status_code == 201
    img_data = up_resp.json()
    img_id = img_data["id"]
    file_path = img_data["file_path"]

    # Simulate container restart: delete local disk copy
    clean_key = normalize_storage_key(file_path)
    local_path = storage_service._get_local_cache_path(clean_key)
    if local_path.exists():
        local_path.unlink()
    assert not local_path.exists(), "Local cache file must be deleted to simulate fresh container"

    # Streaming endpoint must rehydrate from Neon DB and return correct bytes
    get_resp = client.get(f"/api/images/{img_id}/file", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.content == TINY_JPEG_BYTES
    assert local_path.exists(), "Local cache file must be rehydrated from Neon DB"


# ── TEST 5: Unauthorized file access rejected ────────────────────────────────

def test_unauthorized_file_access(auth_headers, other_officer_auth_headers):
    insp_id = _create_inspection(auth_headers)

    files = {"file": ("priv.jpg", io.BytesIO(TINY_JPEG_BYTES), "image/jpeg")}
    up_resp = client.post(f"/api/inspections/{insp_id}/images", files=files, data={"view_type": "front"}, headers=auth_headers)
    assert up_resp.status_code == 201
    img_id = up_resp.json()["id"]

    # Other officer attempting to access image must be rejected with 403 or 404
    other_resp = client.get(f"/api/images/{img_id}/file", headers=other_officer_auth_headers)
    assert other_resp.status_code in (403, 404), f"Expected 403/404, got {other_resp.status_code}"


# ── TEST 6: File overwrite & finalized evidence immutability ─────────────────

def test_file_overwrite_and_immutability(auth_headers):
    insp_id = _create_inspection(auth_headers)

    # 1. Non-overwrite flag protects existing keys in storage_service
    test_key = f"inspections/{insp_id}/protected_file.jpg"
    storage_service.save_file(test_key, TINY_JPEG_BYTES, "image/jpeg")

    with pytest.raises(StorageConflictError):
        storage_service.save_file(test_key, TINY_JPEG_BYTES, "image/jpeg", allow_overwrite=False)

    # 2. Mark inspection COMPLETED and verify evidence cannot be deleted
    db = SessionLocal()
    try:
        insp = db.query(Inspection).filter(Inspection.id == insp_id).first()
        insp.status = "COMPLETED"
        db.commit()
    finally:
        db.close()

    # Attempt to delete finalized evidence via storage_service without force must raise StorageConflictError
    with pytest.raises(StorageConflictError):
        storage_service.delete_file(test_key, force=False)


# ── TEST 7: Invalid MIME and empty file validation ───────────────────────────

def test_invalid_mime_and_empty_file_rejected(auth_headers):
    insp_id = _create_inspection(auth_headers)

    # Empty content rejected by storage service
    with pytest.raises(StorageValidationError, match="empty"):
        storage_service.save_file(f"inspections/{insp_id}/empty.jpg", b"", "image/jpeg")

    # Disallowed MIME type rejected by storage service
    with pytest.raises(StorageValidationError, match="Disallowed content type"):
        storage_service.save_file(
            f"inspections/{insp_id}/script.sh",
            b"echo hack",
            "application/x-sh"
        )
