"""
tests/test_blur_detection2_integration.py

Comprehensive test suite for BlurDetection2 integration into NiriKsha image quality pipeline:
1. Clear image accepted (ACCEPTABLE, engine="BlurDetection2", QUALITY_ACCEPTED).
2. Blurry image rejected (BLURRY, engine="BlurDetection2", QUALITY_REJECTED).
3. Extremely dark image handled safely.
4. Very small image handled safely without crash.
5. Corrupted image handled safely (proper validation, no unhandled 500).
6. Anti-fabrication: score derived strictly from pixel data, different pixels produce distinct scores.
7. Dedicated /api/quality-check endpoint verification.
8. Direct assess_blur_blur_detection2 contract verification.
"""
import io
import os
import cv2
import numpy as np
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app
from backend.image_quality import assess_image_quality, assess_blur_blur_detection2
from backend.blur_detection import fix_image_size, estimate_blur, pretty_blur_map

BASE_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = BASE_DIR / "tests" / "fixtures"
CLEAR_IMG = FIXTURES_DIR / "clear_package.jpg"
BLURRY_IMG = FIXTURES_DIR / "blurry_package.jpg"
DARK_IMG = FIXTURES_DIR / "dark_package.jpg"
LOW_RES_IMG = FIXTURES_DIR / "low_res_package.jpg"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    resp = client.post(
        "/api/auth/login",
        json={"officer_id": "DOCA-INSP-842", "password": "admin123"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# 1. Clear image accepted
def test_01_clear_image_accepted_by_blur_detection2():
    res = assess_image_quality(str(CLEAR_IMG))
    assert res.engine == "BlurDetection2"
    assert res.status == "ACCEPTABLE"
    assert res.blur_ok is True
    assert res.blur_score > 100.0
    assert res.quality_status in ["GOOD", "EXCELLENT"]
    assert res.quality_decision == "QUALITY_ACCEPTED"

    blur_dict = res.to_blur_result()
    assert blur_dict["engine"] == "BlurDetection2"
    assert blur_dict["status"] == "ACCEPTABLE"
    assert blur_dict["blur_score"] > 100.0
    assert "clear_package.jpg" in blur_dict["image_id"]


# 2. Blurry image rejected
def test_02_blurry_image_rejected_by_blur_detection2():
    res = assess_image_quality(str(BLURRY_IMG))
    assert res.engine == "BlurDetection2"
    assert res.status == "BLURRY"
    assert res.blur_ok is False
    assert res.blur_score < 70.0
    assert res.quality_status in ["POOR", "WARNING"]
    assert res.quality_decision == "QUALITY_REJECTED"

    blur_dict = res.to_blur_result()
    assert blur_dict["engine"] == "BlurDetection2"
    assert blur_dict["status"] == "BLURRY"
    assert blur_dict["blur_score"] < 70.0


# 3. Extremely dark image handled safely
def test_03_extremely_dark_image_handled_safely():
    res = assess_image_quality(str(DARK_IMG))
    assert res.brightness_ok is False
    assert any("dark" in w.lower() or "underexposed" in w.lower() for w in res.warnings)
    assert res.quality_status == "POOR"
    assert res.quality_decision == "QUALITY_REJECTED"

    # Also test an absolute zero black image
    black_img = np.zeros((500, 500, 3), dtype=np.uint8)
    black_res = assess_image_quality(black_img, image_id="pure_black.jpg")
    assert black_res.brightness_ok is False
    assert black_res.brightness_score == 0.0
    assert black_res.quality_decision == "QUALITY_REJECTED"


# 4. Very small image handled safely without crashing
def test_04_very_small_image_handled_safely():
    # 20x20 tiny thumbnail
    tiny_img = np.random.randint(0, 255, (20, 20, 3), dtype=np.uint8)
    res = assess_image_quality(tiny_img, image_id="tiny_20x20.png")
    assert res.resolution_ok is False
    assert res.width == 20
    assert res.height == 20
    assert any("resolution" in w.lower() for w in res.warnings)
    # Must compute safely without throwing dimension or convolution exceptions
    assert isinstance(res.blur_score, float)

    # 4x4 microscopic image
    micro_img = np.ones((4, 4, 3), dtype=np.uint8) * 128
    micro_res = assess_image_quality(micro_img, image_id="micro_4x4.png")
    assert micro_res.resolution_ok is False
    assert isinstance(micro_res.blur_score, float)


# 5. Corrupted image handled safely
def test_05_corrupted_image_handled_safely(client, auth_headers):
    # Service level: invalid bytes raise ValueError
    corrupt_bytes = b"NOT_A_VALID_IMAGE_HEADER_CORRUPTED_STREAM"
    with pytest.raises(ValueError) as excinfo:
        assess_image_quality(corrupt_bytes)
    assert "corrupted" in str(excinfo.value).lower() or "could not decode" in str(excinfo.value).lower()

    # Empty bytes raise ValueError
    with pytest.raises(ValueError):
        assess_image_quality(b"")

    # API level: returns HTTP 422 Unprocessable Entity, not unhandled 500
    resp = client.post(
        "/api/quality-check",
        headers=auth_headers,
        files={"file": ("corrupt.jpg", io.BytesIO(corrupt_bytes), "image/jpeg")}
    )
    assert resp.status_code == 422
    assert "corrupted" in resp.json()["detail"].lower()


# 6. Anti-fabrication: score derived strictly from pixel data
def test_06_anti_fabrication_pixel_driven_blur_score():
    # Synthetic image A: flat uniform gray (zero edges -> blur score zero)
    flat_img = np.ones((600, 600, 3), dtype=np.uint8) * 128
    res_flat = assess_image_quality(flat_img, image_id="flat.jpg")
    assert res_flat.blur_score == 0.0
    assert res_flat.status == "BLURRY"

    # Synthetic image B: high frequency checkerboard pattern (many sharp edges -> high blur score)
    checkerboard = np.zeros((600, 600, 3), dtype=np.uint8)
    checkerboard[::20, :, :] = 255
    checkerboard[:, ::20, :] = 255
    res_checker = assess_image_quality(checkerboard, image_id="checker.jpg")
    assert res_checker.blur_score > 500.0
    assert res_checker.status == "ACCEPTABLE"

    # Verifying scores differ dramatically based strictly on pixel content
    assert res_checker.blur_score != res_flat.blur_score

    # Renaming image filename does NOT change the blur score
    res_renamed = assess_image_quality(checkerboard, image_id="blurry_fake_name.jpg")
    assert res_renamed.blur_score == res_checker.blur_score
    assert res_renamed.status == "ACCEPTABLE"  # ignores "blurry" in filename


# 7. Dedicated /api/quality-check endpoint verification
def test_07_api_quality_check_endpoint_contract(client, auth_headers):
    with open(CLEAR_IMG, "rb") as f:
        resp = client.post(
            "/api/quality-check",
            headers=auth_headers,
            files={"file": ("test_package.jpg", f, "image/jpeg")}
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ACCEPTABLE"
    assert data["quality_decision"] == "QUALITY_ACCEPTED"
    assert data["engine"] == "BlurDetection2"
    assert data["image_id"] == "test_package.jpg"
    assert data["blur_score"] > 100.0
    assert "timestamp" in data
    assert "reason" in data
    assert data["quality_status"] in ["GOOD", "EXCELLENT"]
    assert "details" in data
    assert data["details"]["blur_ok"] is True


# 8. Direct assess_blur_blur_detection2 helper verification
def test_08_direct_assess_blur_helper_contract():
    structured = assess_blur_blur_detection2(str(CLEAR_IMG), image_id="img-001")
    assert structured["status"] == "ACCEPTABLE"
    assert structured["quality_decision"] == "QUALITY_ACCEPTED"
    assert structured["engine"] == "BlurDetection2"
    assert structured["image_id"] == "img-001"
    assert isinstance(structured["blur_score"], float)
    assert structured["blur_score"] > 100.0
    assert isinstance(structured["timestamp"], str)
    assert isinstance(structured["reason"], str)


# 9. BlurDetection2 package utilities verification
def test_09_blur_detection2_package_utilities():
    img = cv2.imread(str(CLEAR_IMG))
    assert img is not None

    # fix_image_size
    norm = fix_image_size(img, expected_pixels=2e6)
    assert norm is not None
    assert norm.shape[0] * norm.shape[1] > 0

    # estimate_blur
    blur_map, score, is_blurry = estimate_blur(img, threshold=100.0)
    assert isinstance(score, float)
    assert is_blurry is False

    # pretty_blur_map
    pretty = pretty_blur_map(blur_map)
    assert pretty is not None
    assert pretty.shape[:2] == img.shape[:2]
