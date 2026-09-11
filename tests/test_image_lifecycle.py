"""
Automated Backend Image Lifecycle Tests:
Verifies Upload, Canonical Retake Replacement, Slot Deletion, and Inspection Status Sync.

Database is managed by tests/conftest.py (PostgreSQL test database).
Do NOT set DATABASE_URL here — conftest.py configures the test engine before this module loads.
"""

import os
import io
from pathlib import Path
from PIL import Image
import pytest
from fastapi.testclient import TestClient

# Note: DATABASE_URL is configured by tests/conftest.py to point to the PostgreSQL test database.
# Tables are created/reset by conftest.py's session-scoped setup_test_environment fixture.
from backend.main import app
from backend.config import settings
from backend.database import SessionLocal
from backend.models import User, Inspection, ProductImage

client = TestClient(app)

def create_sample_image_bytes(color=(255, 0, 0), text="test"):
    img = Image.new("RGB", (400, 300), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()

@pytest.fixture(scope="module")
def auth_headers():
    # Login as seed officer
    resp = client.post("/api/auth/login", json={
        "officer_id": settings.SEED_OFFICER_ID,
        "password": settings.SEED_OFFICER_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_image_lifecycle_full_flow(auth_headers):
    # 1. Create inspection
    create_resp = client.post("/api/inspections", json={
        "product_name": "Lifecycle Test Product",
        "category": "Packaged Food",
        "location": "Test Lab Room 1",
        "brand_name": "TestBrand",
        "inspection_type": "PHYSICAL"
    }, headers=auth_headers)
    assert create_resp.status_code == 201
    inspection_id = create_resp.json()["id"]

    # 2. Upload Front image
    front_bytes_1 = create_sample_image_bytes(color=(200, 100, 50))
    up_front_1 = client.post(
        f"/api/inspections/{inspection_id}/images",
        files={"file": ("front_v1.jpg", front_bytes_1, "image/jpeg")},
        data={"view_type": "front"},
        headers=auth_headers
    )
    assert up_front_1.status_code == 201
    front_data_1 = up_front_1.json()
    assert front_data_1["view_type"] == "front"

    # Verify 1 image exists
    list_1 = client.get(f"/api/inspections/{inspection_id}/images", headers=auth_headers).json()
    assert len(list_1) == 1
    assert list_1[0]["view_type"] == "front"

    # 3. Upload Back image
    back_bytes = create_sample_image_bytes(color=(50, 100, 200))
    up_back = client.post(
        f"/api/inspections/{inspection_id}/images",
        files={"file": ("back_v1.jpg", back_bytes, "image/jpeg")},
        data={"view_type": "back"},
        headers=auth_headers
    )
    assert up_back.status_code == 201

    # Verify 2 images exist: 1 Front, 1 Back
    list_2 = client.get(f"/api/inspections/{inspection_id}/images", headers=auth_headers).json()
    assert len(list_2) == 2
    types_2 = {img["view_type"] for img in list_2}
    assert types_2 == {"front", "back"}

    # 4. RETAKE Front image with new image
    front_bytes_2 = create_sample_image_bytes(color=(0, 255, 0))
    up_front_2 = client.post(
        f"/api/inspections/{inspection_id}/images",
        files={"file": ("front_v2_clear.jpg", front_bytes_2, "image/jpeg")},
        data={"view_type": "front"},
        headers=auth_headers
    )
    assert up_front_2.status_code == 201
    front_data_2 = up_front_2.json()
    assert front_data_2["view_type"] == "front"
    assert front_data_2["id"] != front_data_1["id"]

    # Verify STILL exactly 2 images exist (Front was replaced, NOT duplicated!)
    list_3 = client.get(f"/api/inspections/{inspection_id}/images", headers=auth_headers).json()
    assert len(list_3) == 2
    front_images = [img for img in list_3 if img["view_type"] == "front"]
    assert len(front_images) == 1
    assert front_images[0]["id"] == front_data_2["id"]

    # 5. DELETE Front image by slot
    del_front = client.delete(
        f"/api/inspections/{inspection_id}/images/slot/front",
        headers=auth_headers
    )
    assert del_front.status_code == 200

    # Verify only Back remains
    list_4 = client.get(f"/api/inspections/{inspection_id}/images", headers=auth_headers).json()
    assert len(list_4) == 1
    assert list_4[0]["view_type"] == "back"

    # 6. DELETE Back image by ID
    back_id = list_4[0]["id"]
    del_back = client.delete(
        f"/api/images/{back_id}",
        headers=auth_headers
    )
    assert del_back.status_code == 200

    # Verify 0 images remain and status reverted to DRAFT
    list_5 = client.get(f"/api/inspections/{inspection_id}/images", headers=auth_headers).json()
    assert len(list_5) == 0

    insp_after = client.get(f"/api/inspections/{inspection_id}", headers=auth_headers).json()
    assert insp_after["status"] == "DRAFT"
