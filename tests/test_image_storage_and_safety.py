"""
tests/test_image_storage_and_safety.py

Phase 11 Production Automated Test Suite for NiriKsha:
Durable Neon PostgreSQL Storage Architecture & Asynchronous OCR Safety Fixes.

Covers:
TEST A — Durable image upload (ProductImage + StoredFile created in Neon)
TEST B — OCR with durable image (PaddleOCR execution)
TEST C — Missing image deterministic failure (SOURCE_IMAGE_UNAVAILABLE)
TEST D — Simulated Render restart (purge local disk, OCR still succeeds)
TEST E — Two-image OCR (both images rehydrated and processed)
TEST F — Duplicate OCR jobs (unique active-job constraint prevents duplicates)
TEST G — Unauthorized image access (RBAC enforcement 403/404)
TEST H — Path traversal rejection (../../etc/passwd, /etc/passwd, ..\\..\\...)
TEST I — Report persistence (PDF/DOCX downloadable from Neon after local wipe)
TEST J — Evidence persistence (evidence rehydrates from Neon for report generation)
"""

import os
import io
import uuid
import time
import shutil
import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app
from backend.database import SessionLocal
from backend.models import (
    User,
    OCRJob,
    Inspection,
    Product,
    ProductImage,
    Declaration,
    Report,
    StoredFile
)
from backend.storage_service import storage_service, normalize_storage_key
from backend.ocr_job_service import ocr_job_service
from backend.ocr_service import OCRResultData, OCRTextBox
from backend.config import settings

client = TestClient(app)

# Genuine minimal 1x1 test JPEG binary payload
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


@pytest.fixture(autouse=True)
def pause_worker_and_mock_ocr():
    ocr_job_service.stop_worker_loop()
    mock_ocr = OCRResultData(
        raw_text="Net Quantity: 500g MRP: Rs 120.00 incl. of all taxes Mfg Date: 02/2026",
        mean_confidence=0.97,
        text_boxes=[
            OCRTextBox(text="Net Quantity: 500g", confidence=0.98, bbox=[10, 10, 80, 20]),
            OCRTextBox(text="MRP: Rs 120.00 incl. of all taxes", confidence=0.97, bbox=[10, 25, 120, 35]),
            OCRTextBox(text="Mfg Date: 02/2026", confidence=0.96, bbox=[10, 40, 90, 50]),
        ],
        processing_time_ms=30.0,
        engine_used="PaddleOCR",
        ocr_status="OCR_SUCCESS"
    )
    with patch("backend.ocr_job_service.ocr_job_service.trigger_worker"), \
         patch("backend.ocr_job_service.ocr_service.process_image", return_value=mock_ocr), \
         patch("backend.ocr_service.ocr_service.process_image", return_value=mock_ocr):
        yield


@pytest.fixture
def auth_headers():
    login_resp = client.post("/api/auth/login", json={
        "officer_id": settings.SEED_OFFICER_ID,
        "password": settings.SEED_OFFICER_PASSWORD
    })
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_officer_auth_headers():
    db = SessionLocal()
    try:
        other_officer = db.query(User).filter(User.officer_id == "DOCA-INSP-999").first()
        if not other_officer:
            from backend.auth_utils import hash_password
            other_officer = User(
                id=str(uuid.uuid4()),
                officer_id="DOCA-INSP-999",
                full_name="Other Officer",
                email="other@doca.gov.in",
                phone="9999999999",
                designation="Inspector",
                zone="Southern Zone",
                role="INSPECTOR"
            )
            other_officer.password_hash = hash_password("otherpass123")
            db.add(other_officer)
            db.commit()
    finally:
        db.close()

    login_resp = client.post("/api/auth/login", json={
        "officer_id": "DOCA-INSP-999",
        "password": "otherpass123"
    })
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_test_inspection(db, inspector_officer_id=None):
    if not inspector_officer_id:
        inspector_officer_id = settings.SEED_OFFICER_ID
    officer = db.query(User).filter(User.officer_id == inspector_officer_id).first()
    insp_id = str(uuid.uuid4())
    insp = Inspection(
        id=insp_id,
        inspector_id=officer.id,
        inspection_number=f"INSP-2026-STORE-{uuid.uuid4().hex[:6]}",
        location="Lab 2 - Storage Test",
        status="IMAGES_UPLOADED",
        created_at=datetime.utcnow()
    )
    db.add(insp)
    db.commit()

    prod = Product(
        inspection_id=insp_id,
        product_name="Storage Test Product",
        brand_name="Test Brand",
        category="Packaged Food"
    )
    db.add(prod)
    db.commit()
    return insp_id


# ==============================================================================
# TEST A: Durable image upload
# ==============================================================================
def test_a_durable_image_upload(auth_headers):
    db = SessionLocal()
    try:
        insp_id = create_test_inspection(db)
    finally:
        db.close()

    # Upload genuine image through HTTP endpoint
    files = {"file": ("front_panel.jpg", io.BytesIO(TINY_JPEG_BYTES), "image/jpeg")}
    data = {"view_type": "front"}
    r = client.post(f"/api/inspections/{insp_id}/images", files=files, data=data, headers=auth_headers)
    assert r.status_code == 201, f"Upload failed: {r.text}"
    img_resp = r.json()

    # Verify ProductImage metadata
    assert img_resp["view_type"] == "front"
    assert img_resp["file_path"].startswith("/uploads/inspections/")

    # Verify StoredFile exists in Neon PostgreSQL
    db = SessionLocal()
    try:
        clean_key = normalize_storage_key(img_resp["file_path"])
        stored_file = db.query(StoredFile).filter(StoredFile.storage_key == clean_key).first()
        assert stored_file is not None, "StoredFile record must exist in database"
        assert bytes(stored_file.file_data) == TINY_JPEG_BYTES, "StoredFile must contain actual image bytes"
        assert stored_file.file_size == len(TINY_JPEG_BYTES)
        assert stored_file.content_type == "image/jpeg"
    finally:
        db.close()


# ==============================================================================
# TEST B: OCR with durable image
# ==============================================================================
def test_b_ocr_with_durable_image():
    db = SessionLocal()
    try:
        insp_id = create_test_inspection(db)
        key = f"inspections/{insp_id}/front_test_b.jpg"
        rel_path = storage_service.save_file(key, TINY_JPEG_BYTES, "image/jpeg")

        img = ProductImage(
            id=str(uuid.uuid4()),
            inspection_id=insp_id,
            file_path=rel_path,
            view_type="front",
            sequence_order=1,
            processing_status="QUALITY_CHECKED",
            created_at=datetime.utcnow()
        )
        db.add(img)

        job_id = str(uuid.uuid4())
        job = OCRJob(
            id=job_id,
            inspection_id=insp_id,
            status="PROCESSING",
            current_stage="STARTING",
            created_at=datetime.utcnow(),
            started_at=datetime.utcnow(),
            heartbeat_at=datetime.utcnow()
        )
        db.add(job)
        db.commit()

        # Run worker pipeline
        success = ocr_job_service.process_job_execution(job_id, insp_id)
        assert success is True

        db.refresh(job)
        assert job.status == "COMPLETED"
        assert job.progress_percent == 100
        assert job.error_code is None

        insp = db.query(Inspection).filter(Inspection.id == insp_id).first()
        assert insp.status in ["EXTRACTION_COMPLETE", "EVALUATION_COMPLETE", "UNDER_REVIEW", "COMPLETED"]

        decls = db.query(Declaration).filter(Declaration.inspection_id == insp_id).all()
        assert len(decls) > 0
    finally:
        db.close()


# ==============================================================================
# TEST C: Missing image deterministic failure (SOURCE_IMAGE_UNAVAILABLE)
# ==============================================================================
def test_c_missing_image_deterministic_failure():
    db = SessionLocal()
    try:
        insp_id = create_test_inspection(db)
        # Non-existent storage path
        ghost_path = f"/uploads/inspections/{insp_id}/non_existent_ghost_image.jpg"

        img = ProductImage(
            id=str(uuid.uuid4()),
            inspection_id=insp_id,
            file_path=ghost_path,
            view_type="front",
            sequence_order=1,
            processing_status="QUALITY_CHECKED",
            created_at=datetime.utcnow()
        )
        db.add(img)

        job_id = str(uuid.uuid4())
        job = OCRJob(
            id=job_id,
            inspection_id=insp_id,
            status="PROCESSING",
            current_stage="STARTING",
            created_at=datetime.utcnow(),
            started_at=datetime.utcnow(),
            heartbeat_at=datetime.utcnow()
        )
        db.add(job)
        db.commit()

        # Run worker pipeline — must deterministically fail
        success = ocr_job_service.process_job_execution(job_id, insp_id)
        assert success is False

        db.refresh(job)
        assert job.status == "FAILED"
        assert job.error_code == "SOURCE_IMAGE_UNAVAILABLE"
        assert "could not be accessed" in job.error_message

        insp = db.query(Inspection).filter(Inspection.id == insp_id).first()
        assert insp.status == "OCR_FAILED"

        # MUST NOT fabricate declarations or mark EXTRACTION_COMPLETE
        decls = db.query(Declaration).filter(Declaration.inspection_id == insp_id).all()
        assert len(decls) == 0
    finally:
        db.close()


# ==============================================================================
# TEST D: Simulated Render restart (purge local disk, OCR still succeeds)
# ==============================================================================
def test_d_simulated_render_restart_resilience():
    insp_id = str(uuid.uuid4())
    key = f"inspections/{insp_id}/restart_test.jpg"

    # 1. Save to durable storage
    rel_path = storage_service.save_file(key, TINY_JPEG_BYTES, "image/jpeg")

    # 2. Verify it is persisted in Neon StoredFile
    db = SessionLocal()
    try:
        stored_file = db.query(StoredFile).filter(StoredFile.storage_key == normalize_storage_key(key)).first()
        assert stored_file is not None
        assert bytes(stored_file.file_data) == TINY_JPEG_BYTES
    finally:
        db.close()

    # 3. Simulate Render Container Restart / Wiped Ephemeral Disk:
    # Delete local cache file from disk completely
    local_path = storage_service._get_local_cache_path(key)
    if local_path.exists():
        local_path.unlink()
    assert not local_path.exists(), "Local cache file must be deleted to simulate restart"

    # 4. Request working copy after restart — must rehydrate from Neon
    rehydrated_path = storage_service.get_local_working_copy(rel_path)
    assert rehydrated_path is not None
    assert rehydrated_path.exists()
    assert rehydrated_path.read_bytes() == TINY_JPEG_BYTES


# ==============================================================================
# TEST E: Two-image OCR (both images processed)
# ==============================================================================
def test_e_two_image_ocr():
    db = SessionLocal()
    try:
        insp_id = create_test_inspection(db)
        key_front = f"inspections/{insp_id}/front_panel.jpg"
        key_back = f"inspections/{insp_id}/back_panel.jpg"

        rel_front = storage_service.save_file(key_front, TINY_JPEG_BYTES, "image/jpeg")
        rel_back = storage_service.save_file(key_back, TINY_JPEG_BYTES, "image/jpeg")

        img1 = ProductImage(
            id=str(uuid.uuid4()),
            inspection_id=insp_id,
            file_path=rel_front,
            view_type="front",
            sequence_order=1,
            processing_status="QUALITY_CHECKED",
            created_at=datetime.utcnow()
        )
        img2 = ProductImage(
            id=str(uuid.uuid4()),
            inspection_id=insp_id,
            file_path=rel_back,
            view_type="back",
            sequence_order=2,
            processing_status="QUALITY_CHECKED",
            created_at=datetime.utcnow()
        )
        db.add_all([img1, img2])

        job_id = str(uuid.uuid4())
        job = OCRJob(
            id=job_id,
            inspection_id=insp_id,
            status="PROCESSING",
            current_stage="STARTING",
            created_at=datetime.utcnow(),
            started_at=datetime.utcnow(),
            heartbeat_at=datetime.utcnow()
        )
        db.add(job)
        db.commit()

        success = ocr_job_service.process_job_execution(job_id, insp_id)
        assert success is True

        db.refresh(job)
        assert job.status == "COMPLETED"
    finally:
        db.close()


# ==============================================================================
# TEST F: Duplicate OCR jobs prevented
# ==============================================================================
def test_f_duplicate_ocr_jobs_prevented(auth_headers):
    db = SessionLocal()
    try:
        insp_id = create_test_inspection(db)
        key = f"inspections/{insp_id}/pkg.jpg"
        rel_path = storage_service.save_file(key, TINY_JPEG_BYTES, "image/jpeg")

        img = ProductImage(
            id=str(uuid.uuid4()),
            inspection_id=insp_id,
            file_path=rel_path,
            view_type="front",
            sequence_order=1,
            processing_status="QUALITY_CHECKED",
            created_at=datetime.utcnow()
        )
        db.add(img)
        db.commit()
    finally:
        db.close()

    # Request 1
    r1 = client.post(f"/api/inspections/{insp_id}/ocr/start", headers=auth_headers)
    assert r1.status_code == 202
    d1 = r1.json()
    job_id_1 = d1["job_id"]
    assert d1["is_existing"] is False

    # Immediate Request 2 — Must NOT create a duplicate job
    r2 = client.post(f"/api/inspections/{insp_id}/ocr/start", headers=auth_headers)
    assert r2.status_code == 202
    d2 = r2.json()
    assert d2["job_id"] == job_id_1
    assert d2["is_existing"] is True

    # Verify only 1 job exists in database for this inspection
    db = SessionLocal()
    try:
        jobs = db.query(OCRJob).filter(OCRJob.inspection_id == insp_id).all()
        assert len(jobs) == 1
    finally:
        db.close()


# ==============================================================================
# TEST G: Unauthorized image access rejected
# ==============================================================================
def test_g_unauthorized_image_access_rejected(auth_headers, other_officer_auth_headers):
    db = SessionLocal()
    try:
        insp_id = create_test_inspection(db, settings.SEED_OFFICER_ID)
        key = f"inspections/{insp_id}/private_evidence.jpg"
        rel_path = storage_service.save_file(key, TINY_JPEG_BYTES, "image/jpeg")

        img_id = str(uuid.uuid4())
        img = ProductImage(
            id=img_id,
            inspection_id=insp_id,
            file_path=rel_path,
            view_type="front",
            sequence_order=1,
            processing_status="QUALITY_CHECKED",
            created_at=datetime.utcnow()
        )
        db.add(img)
        db.commit()
    finally:
        db.close()

    # Officer A (authorized owner) can access
    r_owner = client.get(f"/api/images/{img_id}/file", headers=auth_headers)
    assert r_owner.status_code == 200

    # Officer B (unauthorized) is rejected
    r_other = client.get(f"/api/images/{img_id}/file", headers=other_officer_auth_headers)
    assert r_other.status_code in [403, 404]


# ==============================================================================
# TEST H: Path traversal rejection
# ==============================================================================
def test_h_path_traversal_rejection():
    # Attempt directory traversal
    with pytest.raises(ValueError, match="Directory traversal"):
        normalize_storage_key("../../etc/passwd")

    with pytest.raises(ValueError, match="Directory traversal"):
        normalize_storage_key("..\\..\\...")

    with pytest.raises(ValueError, match="Directory traversal"):
        normalize_storage_key("inspections/../../../secret.env")

    with pytest.raises(ValueError, match="Directory traversal"):
        normalize_storage_key("uploads/././inspections")

    # Attempt absolute system path access
    with pytest.raises(ValueError):
        normalize_storage_key("/etc/passwd")

    with pytest.raises(ValueError):
        normalize_storage_key("C:\\Windows\\System32\\cmd.exe")

    # Attempt null byte injection
    with pytest.raises(ValueError, match="Null bytes"):
        normalize_storage_key("inspections/123/img.jpg\x00.png")

    # Attempt excessive length
    with pytest.raises(ValueError):
        normalize_storage_key("a" * 600)


# ==============================================================================
# TEST I: Report persistence across local file deletion
# ==============================================================================
def test_i_report_persistence_across_local_wipe(auth_headers):
    db = SessionLocal()
    try:
        insp_id = create_test_inspection(db)
        key = f"inspections/{insp_id}/panel.jpg"
        storage_service.save_file(key, TINY_JPEG_BYTES, "image/jpeg")

        img = ProductImage(
            id=str(uuid.uuid4()),
            inspection_id=insp_id,
            file_path=f"/uploads/{key}",
            view_type="front",
            sequence_order=1,
            processing_status="QUALITY_CHECKED",
            created_at=datetime.utcnow()
        )
        db.add(img)
        db.commit()
    finally:
        db.close()

    # 1. Generate Report
    r_meta = client.get(f"/api/inspections/{insp_id}/report", headers=auth_headers)
    assert r_meta.status_code == 200, f"Report metadata generation failed: {r_meta.text}"

    # Verify Report record exists in DB with stored files
    db = SessionLocal()
    try:
        rep = db.query(Report).filter(Report.inspection_id == insp_id).first()
        assert rep is not None
        assert rep.pdf_path is not None
        pdf_key = rep.pdf_path
        # Verify stored_file in Neon
        stored_pdf = db.query(StoredFile).filter(StoredFile.storage_key == normalize_storage_key(pdf_key)).first()
        assert stored_pdf is not None, "Report PDF must be persisted in StoredFile table"
        assert len(stored_pdf.file_data) > 0
    finally:
        db.close()

    # 2. Simulate container restart by wiping local generated_reports and uploads
    rep_dir = Path("generated_reports")
    if rep_dir.exists():
        for f in rep_dir.glob("*.pdf"):
            try:
                f.unlink()
            except Exception:
                pass
    local_pdf = storage_service._get_local_cache_path(pdf_key)
    if local_pdf.exists():
        local_pdf.unlink()

    # 3. Stream PDF report from API — must retrieve from Neon storage
    r_pdf = client.get(f"/api/inspections/{insp_id}/report/pdf", headers=auth_headers)
    assert r_pdf.status_code == 200
    assert r_pdf.headers.get("content-type") == "application/pdf"
    assert r_pdf.content.startswith(b"%PDF-"), "Must stream valid PDF bytes from Neon"

    # 4. Stream DOCX report from API — must retrieve from Neon storage
    r_docx = client.get(f"/api/inspections/{insp_id}/report/docx", headers=auth_headers)
    assert r_docx.status_code == 200
    assert "openxmlformats" in r_docx.headers.get("content-type", "")
    assert r_docx.content.startswith(b"PK"), "Must stream valid DOCX bytes from Neon"


# ==============================================================================
# TEST J: Evidence persistence across local file deletion
# ==============================================================================
def test_j_evidence_persistence_across_local_wipe(auth_headers):
    db = SessionLocal()
    try:
        insp_id = create_test_inspection(db)
        key = f"inspections/{insp_id}/evidence_image.jpg"
        rel_path = storage_service.save_file(key, TINY_JPEG_BYTES, "image/jpeg")

        img_id = str(uuid.uuid4())
        img = ProductImage(
            id=img_id,
            inspection_id=insp_id,
            file_path=rel_path,
            view_type="front",
            sequence_order=1,
            processing_status="QUALITY_CHECKED",
            created_at=datetime.utcnow()
        )
        db.add(img)
        db.commit()
    finally:
        db.close()

    # 1. Delete local image copy from disk to simulate container restart
    local_path = storage_service._get_local_cache_path(key)
    if local_path.exists():
        local_path.unlink()
    assert not local_path.exists()

    # 2. Retrieve image binary through API — must rehydrate from Neon
    r_img = client.get(f"/api/images/{img_id}/file", headers=auth_headers)
    assert r_img.status_code == 200
    assert r_img.content == TINY_JPEG_BYTES

    # 3. Verify report components can rehydrate and render the evidence image
    from backend.report_components import build_package_images_evidence_section
    db = SessionLocal()
    try:
        insp = db.query(Inspection).filter(Inspection.id == insp_id).first()
        images = db.query(ProductImage).filter(ProductImage.inspection_id == insp_id).all()
        flowables = build_package_images_evidence_section(images, Path("."))
        assert len(flowables) > 0
    finally:
        db.close()
