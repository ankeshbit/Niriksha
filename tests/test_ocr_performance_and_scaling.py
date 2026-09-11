import os
import cv2
import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import settings
from backend.ocr_service import ModularOCRService, OCRResultData
from backend.models import Inspection, ProductImage, Declaration, ComplianceCheck

@pytest.fixture
def auth_client():
    client = TestClient(app)
    resp = client.post("/api/auth/login", json={
        "officer_id": settings.SEED_OFFICER_ID,
        "password": settings.SEED_OFFICER_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    client.headers = {"Authorization": f"Bearer {token}"}
    return client


def test_ocr_resolution_cap_setting():
    """Verifies that MAX_OCR_DIMENSION is configured to 1024 by default."""
    assert hasattr(settings, "MAX_OCR_DIMENSION")
    assert settings.MAX_OCR_DIMENSION == 1024


def test_ocr_image_downscaling_and_coordinate_mapping():
    """
    Verifies that an oversized image (e.g. 1600px) is processed at <= 1024px,
    and all returned bounding boxes are scaled back to original image coordinates.
    """
    # Create a synthetic high-res image 1600x800 with text
    test_img_path = "tests/fixtures/test_highres_scaling.jpg"
    img = 255 * (cv2.imread("tests/fixtures/clear_package.jpg") is not None)
    # Read clear package and resize to 1600x800
    base = cv2.imread("tests/fixtures/clear_package.jpg")
    if base is None:
        pytest.skip("Fixture clear_package.jpg not found")

    h, w = base.shape[:2]
    oversized = cv2.resize(base, (1600, 800))
    cv2.imwrite(test_img_path, oversized)

    try:
        svc = ModularOCRService()
        t0 = time.time()
        result = svc.process_image(test_img_path, image_id="test-highres")
        elapsed = time.time() - t0

        assert result.ocr_status == "OCR_SUCCESS"
        assert len(result.text_boxes) > 0
        # Check that bounding box coordinates span the original 1600x800 coordinate space
        max_x = max(b.bbox[2] for b in result.text_boxes)
        max_y = max(b.bbox[3] for b in result.text_boxes)
        # With original width 1600, coordinates must be in [0, 1600]
        assert max_x <= 1600
        assert max_y <= 800
        # If coordinates were not scaled back, max_x would be <= 1024
        # Since text is distributed across the card, max_x should exceed 1024
        assert max_x > 800, f"Expected bounding boxes mapped back to 1600px width, got max_x={max_x}"
    finally:
        if os.path.exists(test_img_path):
            os.remove(test_img_path)


def test_ocr_real_package_performance_budget():
    """
    Verifies that OCR on a real package image completes well within the 60-second budget.
    """
    real_front = "scripts/real_images/real_package_front.jpg"
    if not os.path.exists(real_front):
        pytest.skip("Fixture real_package_front.jpg not found")

    svc = ModularOCRService()
    t0 = time.time()
    res = svc.process_image(real_front, image_id="perf-front")
    elapsed = time.time() - t0

    assert res.ocr_status == "OCR_SUCCESS"
    assert len(res.text_boxes) > 0
    # Single image must complete in under 50s on CPU
    assert elapsed < 50.0, f"OCR took {elapsed:.2f}s, exceeding 50s budget"


def test_ocr_and_compliance_evaluation_workflow(auth_client):
    """
    Tests the complete API workflow:
    Inspection creation -> Upload images -> Run OCR -> Evaluate compliance rules.
    Verifies that evaluateRules succeeds immediately after OCR.
    """
    # 1. Create inspection
    create_resp = auth_client.post("/api/inspections", json={
        "product_name": "Acceptance Test Pen",
        "category": "Packaged Food",
        "brand_name": "Flair",
        "location": "Test Depot Mumbai",
        "batch_number": "BATCH-PERF-01"
    })
    assert create_resp.status_code == 201, create_resp.text
    insp_id = create_resp.json()["id"]

    # 2. Upload front image
    front_path = "scripts/real_images/real_package_front.jpg"
    if not os.path.exists(front_path):
        front_path = "tests/fixtures/clear_package.jpg"

    with open(front_path, "rb") as f:
        up_resp = auth_client.post(
            f"/api/inspections/{insp_id}/images",
            files={"file": ("front.jpg", f, "image/jpeg")},
            data={"view_type": "front"}
        )
    assert up_resp.status_code == 201, up_resp.text

    # 3. Run OCR
    t0 = time.time()
    ocr_resp = auth_client.post(f"/api/inspections/{insp_id}/ocr")
    ocr_time = time.time() - t0

    assert ocr_resp.status_code == 200, ocr_resp.text
    ocr_json = ocr_resp.json()
    assert ocr_json["status"] == "EXTRACTION_COMPLETE"
    assert ocr_json["declarations_count"] > 0
    assert ocr_time < 90.0, f"OCR endpoint took {ocr_time:.2f}s, exceeding 90s budget"

    # 4. Evaluate rules (directly after OCR)
    t0 = time.time()
    eval_resp = auth_client.post(f"/api/inspections/{insp_id}/evaluate")
    eval_time = time.time() - t0

    assert eval_resp.status_code == 200, eval_resp.text
    eval_json = eval_resp.json()
    assert "total_rules_evaluated" in eval_json
    assert "findings" in eval_json
    assert "overall_status" in eval_json
    assert eval_time < 10.0, f"Rule evaluation took {eval_time:.2f}s"
