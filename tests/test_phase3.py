import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings

client = TestClient(app)
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

def get_auth_token():
    """Helper to authenticate and return a valid JWT token."""
    response = client.post("/api/auth/login", json={
        "officer_id": settings.SEED_OFFICER_ID,
        "password": settings.SEED_OFFICER_PASSWORD
    })
    assert response.status_code == 200
    return response.json()["access_token"]

def create_sample_inspection(token: str):
    """Helper to create a test inspection record."""
    resp = client.post(
        "/api/inspections",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_name": "Test Basmati Rice 5kg",
            "category": "Packaged Food",
            "location": "Central Delhi Test Lab",
            "brand_name": "Test Brand"
        }
    )
    assert resp.status_code == 201
    return resp.json()["id"]

# 1. Authenticated Image Upload
def test_authenticated_image_upload():
    token = get_auth_token()
    insp_id = create_sample_inspection(token)
    img_path = FIXTURES_DIR / "good_package.jpg"

    with open(img_path, "rb") as f:
        response = client.post(
            f"/api/inspections/{insp_id}/images",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("good_package.jpg", f, "image/jpeg")},
            data={"view_type": "front"}
        )

    assert response.status_code == 201
    data = response.json()
    assert data["inspection_id"] == insp_id
    assert data["view_type"] == "front"
    assert data["width"] == 800
    assert data["height"] == 800
    assert data["mime_type"] == "image/jpeg"
    assert data["quality_status"] == "GOOD"
    assert data["quality_score"] >= 0.80
    assert data["quality_details"]["blur_ok"] is True
    assert data["quality_details"]["resolution_ok"] is True

# 2. Unauthenticated Image Upload Rejected
def test_unauthenticated_image_upload_rejected():
    token = get_auth_token()
    insp_id = create_sample_inspection(token)
    img_path = FIXTURES_DIR / "good_package.jpg"

    with open(img_path, "rb") as f:
        response = client.post(
            f"/api/inspections/{insp_id}/images",
            files={"file": ("good_package.jpg", f, "image/jpeg")},
            data={"view_type": "front"}
        )
    assert response.status_code == 401

# 3. Invalid / Non-Image File Rejected
def test_invalid_file_type_rejected():
    token = get_auth_token()
    insp_id = create_sample_inspection(token)

    response = client.post(
        f"/api/inspections/{insp_id}/images",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("script.py", b"print('malicious')", "text/plain")},
        data={"view_type": "front"}
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]

# 4. Corrupted Image File Rejected
def test_corrupted_image_rejected():
    token = get_auth_token()
    insp_id = create_sample_inspection(token)

    # Fake JPEG header but corrupted body
    corrupted_bytes = b"\xFF\xD8\xFF\xE0" + b"Corrupted data that cannot decode as image"

    response = client.post(
        f"/api/inspections/{insp_id}/images",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("corrupt.jpg", corrupted_bytes, "image/jpeg")},
        data={"view_type": "front"}
    )
    assert response.status_code == 400
    assert "Invalid or corrupted image" in response.json()["detail"]

# 5. Multiple Images Associated with One Inspection
def test_multiple_images_upload_and_ordering():
    token = get_auth_token()
    insp_id = create_sample_inspection(token)

    # Upload Front
    with open(FIXTURES_DIR / "good_package.jpg", "rb") as f1:
        resp1 = client.post(
            f"/api/inspections/{insp_id}/images",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("good_front.jpg", f1, "image/jpeg")},
            data={"view_type": "front"}
        )
    assert resp1.status_code == 201

    # Upload Back
    with open(FIXTURES_DIR / "blurry_package.jpg", "rb") as f2:
        resp2 = client.post(
            f"/api/inspections/{insp_id}/images",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("back_label.jpg", f2, "image/jpeg")},
            data={"view_type": "back"}
        )
    assert resp2.status_code == 201

    # List images
    list_resp = client.get(
        f"/api/inspections/{insp_id}/images",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert list_resp.status_code == 200
    images = list_resp.json()
    assert len(images) == 2
    assert images[0]["view_type"] == "front"
    assert images[0]["sequence_order"] == 1
    assert images[1]["view_type"] == "back"
    assert images[1]["sequence_order"] == 2

# 6. Blurry Image Quality Detection
def test_blurry_image_quality_detection():
    token = get_auth_token()
    insp_id = create_sample_inspection(token)

    with open(FIXTURES_DIR / "blurry_package.jpg", "rb") as f:
        resp = client.post(
            f"/api/inspections/{insp_id}/images",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("blurry_package.jpg", f, "image/jpeg")},
            data={"view_type": "back"}
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["quality_status"] in ["WARNING", "POOR"]
    assert data["quality_details"]["blur_ok"] is False
    assert any("blurry" in w.lower() for w in data["quality_details"]["warnings"])

# 7. Low-Resolution Image Detection
def test_low_resolution_image_detection():
    token = get_auth_token()
    insp_id = create_sample_inspection(token)

    with open(FIXTURES_DIR / "low_res_package.jpg", "rb") as f:
        resp = client.post(
            f"/api/inspections/{insp_id}/images",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("low_res.jpg", f, "image/jpeg")},
            data={"view_type": "panel"}
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["width"] == 200
    assert data["height"] == 200
    assert data["quality_details"]["resolution_ok"] is False
    assert any("resolution" in w.lower() for w in data["quality_details"]["warnings"])

# 8. Dark / Underexposed Image Detection
def test_dark_image_quality_detection():
    token = get_auth_token()
    insp_id = create_sample_inspection(token)

    with open(FIXTURES_DIR / "dark_package.jpg", "rb") as f:
        resp = client.post(
            f"/api/inspections/{insp_id}/images",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("dark_package.jpg", f, "image/jpeg")},
            data={"view_type": "panel"}
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["quality_details"]["brightness_ok"] is False
    assert any("dark" in w.lower() or "underexposed" in w.lower() for w in data["quality_details"]["warnings"])

# 9. Inspection Lifecycle Updates to IMAGES_UPLOADED
def test_inspection_lifecycle_updated_after_image_upload():
    token = get_auth_token()
    insp_id = create_sample_inspection(token)

    # Verify initial DRAFT status
    init_resp = client.get(f"/api/inspections/{insp_id}", headers={"Authorization": f"Bearer {token}"})
    assert init_resp.json()["status"] == "DRAFT"

    # Upload image
    with open(FIXTURES_DIR / "good_package.jpg", "rb") as f:
        client.post(
            f"/api/inspections/{insp_id}/images",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("good.jpg", f, "image/jpeg")},
            data={"view_type": "front"}
        )

    # Verify updated IMAGES_UPLOADED status
    after_resp = client.get(f"/api/inspections/{insp_id}", headers={"Authorization": f"Bearer {token}"})
    assert after_resp.json()["status"] == "IMAGES_UPLOADED"

# 10. Image Binary Stream and Deletion
def test_image_binary_and_deletion():
    token = get_auth_token()
    insp_id = create_sample_inspection(token)

    with open(FIXTURES_DIR / "good_package.jpg", "rb") as f:
        upload_resp = client.post(
            f"/api/inspections/{insp_id}/images",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("good.jpg", f, "image/jpeg")},
            data={"view_type": "front"}
        )
    img_id = upload_resp.json()["id"]

    # Test binary retrieval
    bin_resp = client.get(
        f"/api/images/{img_id}/file",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert bin_resp.status_code == 200
    assert bin_resp.headers["content-type"].startswith("image/")

    # Test image deletion
    del_resp = client.delete(
        f"/api/images/{img_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert del_resp.status_code == 200

    # Ensure 404 after deletion
    get_after_del = client.get(
        f"/api/images/{img_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert get_after_del.status_code == 404
