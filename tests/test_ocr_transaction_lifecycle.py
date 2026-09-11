"""
Regression Test: OCR Session Lifecycle & Transaction Non-Idle Verification
Ensures that during long PaddleOCR inference:
1. The initial database transaction is committed and closed before inference begins.
2. No SQLAlchemy session remains idle or holds an active checked-out connection.
3. If the session/connection is left open during inference, this test fails.

Database is managed by tests/conftest.py (PostgreSQL test database).
Do NOT set DATABASE_URL here — conftest.py configures the test engine before this module loads.
"""

import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

# Note: DATABASE_URL is configured by tests/conftest.py to point to the PostgreSQL test database.
from backend.main import app
from backend.config import settings
from backend.database import SessionLocal, get_db
from backend.models import User, Inspection, Product, ProductImage
from backend.ocr_service import OCRResultData, OCRTextBox

client = TestClient(app)


@pytest.fixture(scope="module")
def auth_headers():
    resp = client.post("/api/auth/login", json={
        "officer_id": settings.SEED_OFFICER_ID,
        "password": settings.SEED_OFFICER_PASSWORD
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_ocr_transaction_closed_during_inference(auth_headers):
    # 1. Create inspection
    insp_resp = client.post("/api/inspections", json={
        "product_name": "Lifecycle Test Biscuit",
        "category": "Packaged Food",
        "brand_name": "LifecycleBrand",
        "location": "Test Lab",
        "batch_number": "LC-001"
    }, headers=auth_headers)
    assert insp_resp.status_code == 201
    inspection_id = insp_resp.json()["id"]

    # 2. Upload dummy image
    from PIL import Image
    import io
    img = Image.new("RGB", (100, 100), color=(200, 50, 50))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    upload_resp = client.post(
        f"/api/inspections/{inspection_id}/images",
        files={"file": ("front.jpg", img_bytes, "image/jpeg")},
        data={"view_type": "front"},
        headers=auth_headers
    )
    assert upload_resp.status_code == 201

    inference_executed = False
    transaction_held_during_inference = None

    def mock_process_image(image_path, image_id=None):
        nonlocal inference_executed, transaction_held_during_inference
        inference_executed = True
        
        # FORENSIC CHECK DURING INFERENCE:
        # Check whether any connections are currently checked out from the pool
        # or if the engine pool has active connections.
        # In SQLite/Postgres with SQLAlchemy QueuePool/NullPool/SingletonThreadPool:
        # If db.close() was called, no transaction is active.
        checked_out = engine.pool.checkedout()
        transaction_held_during_inference = (checked_out > 0)
        
        return OCRResultData(
            raw_text="Net Wt 100g MRP Rs 50.00 incl of all taxes",
            mean_confidence=0.98,
            text_boxes=[
                OCRTextBox(text="Net Wt 100g", confidence=0.98, bbox=[10, 10, 50, 20]),
                OCRTextBox(text="MRP Rs 50.00 incl of all taxes", confidence=0.98, bbox=[10, 30, 90, 40])
            ],
            processing_time_ms=50.0,
            engine_used="PaddleOCR",
            ocr_status="OCR_SUCCESS"
        )

    with patch("backend.main.ocr_service.process_image", side_effect=mock_process_image):
        ocr_resp = client.post(f"/api/inspections/{inspection_id}/ocr", headers=auth_headers)
        assert ocr_resp.status_code == 200, f"OCR endpoint failed: {ocr_resp.text}"

    assert inference_executed is True, "Inference mock was not called"
    assert transaction_held_during_inference is False, (
        "CRITICAL REGRESSION: Database connection/transaction was held open during OCR inference! "
        "The session must be released (db.close()) before long PaddleOCR inference to prevent "
        "Neon pooler timeouts."
    )
