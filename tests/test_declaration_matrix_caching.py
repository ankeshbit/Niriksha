"""
tests/test_declaration_matrix_caching.py

Verifies that declaration validation matrix is cached in Declaration.validation_matrix_json:
1. First GET computes and caches matrix rows.
2. Second GET reads cached rows and does NOT call readability_analyzer.analyze_readability.
3. PATCH /api/declarations/{id} recomputes and stores updated matrix rows.
4. Subsequent GET reads freshly stored rows without calling readability_analyzer.analyze_readability.
5. Response shapes remain identical.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import settings
from backend.database import SessionLocal
from backend.models import Inspection, Product, ProductImage, Declaration
from backend.declaration_validation_service import declaration_validation_engine

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


@pytest.fixture
def inspection_with_declarations(auth_headers):
    """Creates a fresh inspection with dummy image and 7 mandatory declarations."""
    # 1. Create inspection
    insp_resp = client.post("/api/inspections", json={
        "product_name": "Caching Test Biscuit",
        "category": "Packaged Food",
        "brand_name": "CacheBrand",
        "location": "Test Lab",
        "batch_number": "CB-001"
    }, headers=auth_headers)
    assert insp_resp.status_code == 201
    inspection_id = insp_resp.json()["id"]

    # 2. Upload dummy image
    from PIL import Image
    import io
    img = Image.new("RGB", (100, 100), color=(100, 150, 200))
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
    image_id = upload_resp.json()["id"]

    # 3. Seed 7 mandatory declarations in database
    db = SessionLocal()
    sample_values = {
        "commodity_name": "Biscuit",
        "manufacturer_details": "Britannia Industries Ltd, Kolkata",
        "net_quantity": "100 g",
        "mrp": "Rs. 25.00 (incl. of all taxes)",
        "date_of_manufacture_packing": "01/2026",
        "consumer_care_details": "care@britannia.com",
        "country_of_origin": "India"
    }

    decl_ids = {}
    now = datetime.utcnow()
    for fname, flabel in declaration_validation_engine.MANDATORY_FIELDS:
        decl = Declaration(
            inspection_id=inspection_id,
            field_name=fname,
            extracted_value=sample_values.get(fname, "Sample"),
            confidence=0.95,
            bounding_box_json=json.dumps([10, 10, 50, 20]),
            extraction_status="EXTRACTED",
            is_applicable=True,
            verification_status="UNVERIFIED",
            source_image_id=image_id,
            created_at=now,
            updated_at=now
        )
        db.add(decl)
        db.flush()
        decl_ids[fname] = decl.id

    db.commit()
    db.close()

    return inspection_id, decl_ids


def test_second_get_does_not_call_readability_analyzer(auth_headers, inspection_with_declarations):
    inspection_id, _ = inspection_with_declarations

    # 1. First GET: Rebuilds and caches matrix rows
    resp1 = client.get(f"/api/inspections/{inspection_id}/compliance-summary", headers=auth_headers)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert "overall_status" in data1
    assert "total_mandatory" in data1
    assert data1["total_mandatory"] == 7

    # 2. Second GET to /compliance-summary: Must read cached rows without invoking analyze_readability
    with patch("backend.declaration_validation_service.readability_analyzer.analyze_readability") as mock_read:
        resp2 = client.get(f"/api/inspections/{inspection_id}/compliance-summary", headers=auth_headers)
        assert resp2.status_code == 200
        mock_read.assert_not_called()

        data2 = resp2.json()
        assert data2["overall_status"] == data1["overall_status"]
        assert data2["total_mandatory"] == data1["total_mandatory"]
        assert data2["mandatory_detected"] == data1["mandatory_detected"]

    # 3. Third GET to /declaration-validation: Must also read cached rows without invoking analyze_readability
    with patch("backend.declaration_validation_service.readability_analyzer.analyze_readability") as mock_read:
        resp3 = client.get(f"/api/inspections/{inspection_id}/declaration-validation", headers=auth_headers)
        assert resp3.status_code == 200
        mock_read.assert_not_called()

        data3 = resp3.json()
        assert len(data3["rows"]) == 7
        assert data3["total_mandatory"] == 7
        assert "compliant_count" in data3
        assert "potential_violation_count" in data3


def test_patch_declaration_recomputes_matrix_and_caches(auth_headers, inspection_with_declarations):
    inspection_id, decl_ids = inspection_with_declarations
    mrp_decl_id = decl_ids["mrp"]

    # 1. Initial GET to ensure baseline cached
    resp_init = client.get(f"/api/inspections/{inspection_id}/declaration-validation", headers=auth_headers)
    assert resp_init.status_code == 200

    # 2. PATCH the MRP declaration
    new_value = "Rs. 30.00 (incl. of all taxes)"
    patch_resp = client.patch(
        f"/api/declarations/{mrp_decl_id}",
        json={"corrected_value": new_value, "verification_status": "CORRECTED"},
        headers=auth_headers
    )
    assert patch_resp.status_code == 200
    patched_decl = patch_resp.json()
    assert patched_decl["effective_value"] == new_value
    assert patched_decl["validation_matrix"] is not None

    # 3. GET /declaration-validation reads freshly stored rows without calling analyze_readability
    with patch("backend.declaration_validation_service.readability_analyzer.analyze_readability") as mock_read:
        get_resp = client.get(f"/api/inspections/{inspection_id}/declaration-validation", headers=auth_headers)
        assert get_resp.status_code == 200
        mock_read.assert_not_called()

        data = get_resp.json()
        mrp_row = next(r for r in data["rows"] if r["field_name"] == "mrp")
        assert mrp_row["effective_value"] == new_value


def test_stale_declaration_rebuilds_cache(auth_headers, inspection_with_declarations):
    inspection_id, decl_ids = inspection_with_declarations
    mrp_decl_id = decl_ids["mrp"]

    # Ensure matrix is cached first
    resp1 = client.get(f"/api/inspections/{inspection_id}/declaration-validation", headers=auth_headers)
    assert resp1.status_code == 200

    # Artificially push declaration updated_at into the future to simulate external staleness
    db = SessionLocal()
    try:
        decl = db.query(Declaration).filter(Declaration.id == mrp_decl_id).first()
        decl.updated_at = datetime.utcnow() + timedelta(minutes=5)
        db.commit()
    finally:
        db.close()

    # GET should detect staleness, rebuild cleanly, and return 200
    resp2 = client.get(f"/api/inspections/{inspection_id}/declaration-validation", headers=auth_headers)
    assert resp2.status_code == 200
    assert len(resp2.json()["rows"]) == 7
