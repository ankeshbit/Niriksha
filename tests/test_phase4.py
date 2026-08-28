import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings
from backend.ocr_service import ocr_service
from backend.extraction_service import extraction_service

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

def create_sample_inspection_with_image(token: str, fixture_name: str = "clear_package.jpg"):
    """Helper to create an inspection and upload a package image."""
    insp_resp = client.post(
        "/api/inspections",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_name": "Premium Basmati Rice",
            "category": "Packaged Food",
            "location": "North Delhi Mandi",
            "brand_name": "Agro Pure"
        }
    )
    assert insp_resp.status_code == 201
    insp_id = insp_resp.json()["id"]

    # Upload image
    with open(FIXTURES_DIR / fixture_name, "rb") as f:
        img_resp = client.post(
            f"/api/inspections/{insp_id}/images",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (fixture_name, f, "image/jpeg")},
            data={"view_type": "front"}
        )
    assert img_resp.status_code == 201
    img_id = img_resp.json()["id"]

    return insp_id, img_id

# 1. OCR Service Initialization
def test_ocr_service_initialization():
    assert ocr_service is not None
    assert ocr_service.morph_engine is not None

# 2. OCR Processing of Valid Image Directly
def test_ocr_direct_image_processing():
    img_path = FIXTURES_DIR / "clear_package.jpg"
    res = ocr_service.process_image(str(img_path), image_id="test-img-123")
    assert res is not None
    assert len(res.text_boxes) > 0
    assert res.mean_confidence > 0.50
    assert res.processing_time_ms > 0
    assert all(len(b.bbox) == 4 for b in res.text_boxes)

# 3. Authenticated POST /api/inspections/{id}/ocr Run
def test_authenticated_ocr_execution():
    token = get_auth_token()
    insp_id, _ = create_sample_inspection_with_image(token, "clear_package.jpg")

    response = client.post(
        f"/api/inspections/{insp_id}/ocr",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["inspection_id"] == insp_id
    assert data["status"] == "EXTRACTION_COMPLETE"
    assert data["total_images_processed"] == 1
    assert data["declarations_count"] >= 5
    assert len(data["ocr_results"]) == 1
    assert len(data["ocr_results"][0]["bounding_boxes"]) > 0

# 4. Raw OCR Bounding Boxes Persistence
def test_ocr_raw_bounding_boxes_persistence():
    token = get_auth_token()
    insp_id, _ = create_sample_inspection_with_image(token, "clear_package.jpg")

    client.post(f"/api/inspections/{insp_id}/ocr", headers={"Authorization": f"Bearer {token}"})

    get_ocr_resp = client.get(
        f"/api/inspections/{insp_id}/ocr",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert get_ocr_resp.status_code == 200
    ocr_records = get_ocr_resp.json()
    assert len(ocr_records) == 1
    boxes = ocr_records[0]["bounding_boxes"]
    assert len(boxes) > 0
    assert "bbox" in boxes[0]
    assert "confidence" in boxes[0]

# 5. Structured Declaration Extraction of Mandatory Fields
def test_structured_declarations_extraction_complete_package():
    token = get_auth_token()
    insp_id, _ = create_sample_inspection_with_image(token, "clear_package.jpg")

    # Run OCR and extract
    client.post(f"/api/inspections/{insp_id}/ocr", headers={"Authorization": f"Bearer {token}"})

    # Retrieve declarations
    decl_resp = client.get(
        f"/api/inspections/{insp_id}/declarations",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert decl_resp.status_code == 200
    declarations = decl_resp.json()
    decl_map = {d["field_name"]: d for d in declarations}

    # Verify Commodity Name
    assert "commodity_name" in decl_map
    assert decl_map["commodity_name"]["extraction_status"] == "EXTRACTED"
    assert decl_map["commodity_name"]["confidence"] >= 0.80

    # Verify Net Quantity
    assert "net_quantity" in decl_map

    # Verify MRP
    assert "mrp" in decl_map

    # Verify Manufacturer Details
    assert "manufacturer_details" in decl_map

    # Verify Date of Manufacture
    assert "date_of_manufacture_packing" in decl_map

    # Verify Consumer Care
    assert "consumer_care_details" in decl_map

# 6. Extraction of Package with Missing Declarations
def test_extraction_missing_fields_handling():
    token = get_auth_token()
    insp_id, _ = create_sample_inspection_with_image(token, "missing_declarations_package.jpg")

    client.post(f"/api/inspections/{insp_id}/ocr", headers={"Authorization": f"Bearer {token}"})

    decl_resp = client.get(
        f"/api/inspections/{insp_id}/declarations",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert decl_resp.status_code == 200
    decl_map = {d["field_name"]: d for d in decl_resp.json()}

    # Net quantity & Consumer Care were deliberately omitted from this test image
    assert decl_map["consumer_care_details"]["extraction_status"] in ["NOT_FOUND", "NEEDS_REVIEW"]
    assert decl_map["net_quantity"]["extraction_status"] in ["NOT_FOUND", "NEEDS_REVIEW"]

# 7. Single Declaration Retrieval
def test_get_single_declaration_by_field_name():
    token = get_auth_token()
    insp_id, _ = create_sample_inspection_with_image(token, "clear_package.jpg")

    client.post(f"/api/inspections/{insp_id}/ocr", headers={"Authorization": f"Bearer {token}"})

    resp = client.get(
        f"/api/inspections/{insp_id}/declarations/mrp",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["field_name"] == "mrp"

# 8. Inspector Declaration Review & Modification (PATCH)
def test_inspector_declaration_patch_correction():
    token = get_auth_token()
    insp_id, _ = create_sample_inspection_with_image(token, "clear_package.jpg")

    client.post(f"/api/inspections/{insp_id}/ocr", headers={"Authorization": f"Bearer {token}"})

    # Get MRP declaration
    mrp_decl = client.get(
        f"/api/inspections/{insp_id}/declarations/mrp",
        headers={"Authorization": f"Bearer {token}"}
    ).json()

    decl_id = mrp_decl["id"]

    # Patch with officer correction
    patch_resp = client.patch(
        f"/api/declarations/{decl_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "corrected_value": "Rs. 450.00 (Incl. of all taxes)",
            "verification_status": "CORRECTED_BY_OFFICER"
        }
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["corrected_value"] == "Rs. 450.00 (Incl. of all taxes)"
    assert updated["verification_status"] == "CORRECTED_BY_OFFICER"

# 9. OCR Request with Zero Uploaded Images Rejected
def test_ocr_run_with_no_images_rejected():
    token = get_auth_token()
    # Create empty inspection without images
    empty_resp = client.post(
        "/api/inspections",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_name": "Empty Inspection Product",
            "category": "Packaged Food",
            "location": "Warehouse"
        }
    )
    empty_id = empty_resp.json()["id"]

    response = client.post(
        f"/api/inspections/{empty_id}/ocr",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 400
    assert "No images uploaded" in response.json()["detail"]

# 10. Unauthorized OCR Request Rejected
def test_unauthorized_ocr_request_rejected():
    response = client.post("/api/inspections/fake-id/ocr")
    assert response.status_code == 401
