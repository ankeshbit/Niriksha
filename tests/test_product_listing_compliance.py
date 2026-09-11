"""
tests/test_product_listing_compliance.py

Automated Test Suite for Product Information / Online Listing Compliance Module.
Satisfies PS 26034:
"Checking packaged commodities using product images, labels, and product information,
and identifying violations through image and label analysis."

Guarantees Verified:
1. Product information input & retrieval without arbitrary web scraping.
2. Comparison between Online Listing ↔ Package OCR declarations.
3. Accurate detection of statuses: MATCH, MISMATCH, MISSING_ON_LISTING, MISSING_ON_PACKAGE, UNCERTAIN.
4. MRP overcharging linked to Rule 18(2A) (e.g. online ₹55 vs package ₹50).
5. Mandatory disclosure issues linked to Rule 6(10) E-Commerce provisions.
6. Mismatches do NOT automatically become legal violations; preserved as reviewable discrepancies.
7. Inspector retains final adjudication authority with audit logging.
8. Anti-fabrication guarantees: strict provenance tagging, no synthesized or inferred data.
9. Security & RBAC: inspector isolation and supervisory read access.
10. Database safety: isolated test database, zero records written to production.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import settings
from backend.models import Inspection, Product, Declaration, ProductListing, ListingComparison, User
from tests.conftest import TestSessionLocal


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def inspector_headers(client):
    resp = client.post(
        "/api/auth/login",
        json={"officer_id": settings.SEED_OFFICER_ID, "password": settings.SEED_OFFICER_PASSWORD},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def second_inspector_headers(client):
    from backend.auth_utils import hash_password
    from backend.auth_service import create_access_token

    db = TestSessionLocal()
    u = db.query(User).filter(User.officer_id == "DOCA-INSP-202").first()
    if not u:
        u = User(
            officer_id="DOCA-INSP-202",
            full_name="Inspector Amit Sharma",
            password_hash=hash_password("password123"),
            role="INSPECTOR",
            designation="Inspector (Legal Metrology)",
            zone="Western Zone"
        )
        db.add(u)
        db.commit()
    token = create_access_token({"sub": u.officer_id, "role": u.role})
    db.close()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def supervisor_headers(client):
    from backend.auth_utils import hash_password
    from backend.auth_service import create_access_token

    db = TestSessionLocal()
    u = db.query(User).filter(User.officer_id == "DOCA-SUP-101").first()
    if not u:
        u = User(
            officer_id="DOCA-SUP-101",
            full_name="Supervisor Sanjay Mehta",
            password_hash=hash_password("password123"),
            role="SUPERVISOR",
            designation="Supervisory Officer (Legal Metrology)",
            zone="North Zone HQ"
        )
        db.add(u)
        db.commit()
    token = create_access_token({"sub": u.officer_id, "role": u.role})
    db.close()
    return {"Authorization": f"Bearer {token}"}


def test_product_listing_input_and_retrieval(client, inspector_headers):
    """Test manual product listing input, saving, and retrieval."""
    # 1. Create an inspection in ONLINE_LISTING mode
    resp = client.post(
        "/api/inspections",
        headers=inspector_headers,
        json={
            "product_name": "Premium Basmati Rice",
            "category": "Packaged Food",
            "brand_name": "Royal Harvest",
            "location": "Online Retail Warehouse, Sector 18",
            "inspection_type": "ONLINE_LISTING",
        }
    )
    assert resp.status_code == 201, resp.text
    insp_id = resp.json()["id"]

    # 2. Save product listing information
    listing_payload = {
        "product_name": "Premium Basmati Rice 5kg",
        "brand_name": "Royal Harvest",
        "mrp": "₹550.00",
        "net_quantity": "5 kg",
        "manufacturer_details": "Royal Agri Foods Ltd, Karnal, Haryana",
        "country_of_origin": "India",
        "consumer_care_details": "support@royalharvest.in, 1800-222-333",
        "seller_information": "FastDelivery E-Commerce Ltd",
        "listing_url": "https://marketplace.example/item/10982",
    }
    resp = client.post(
        f"/api/inspections/{insp_id}/listing",
        headers=inspector_headers,
        json=listing_payload,
    )
    assert resp.status_code == 200, resp.text
    saved = resp.json()
    assert saved["product_name"] == "Premium Basmati Rice 5kg"
    assert saved["mrp"] == "₹550.00"
    assert saved["net_quantity"] == "5 kg"
    assert saved["source"] == "MANUAL_LISTING_INPUT"

    # 3. Retrieve product listing
    resp = client.get(f"/api/inspections/{insp_id}/listing", headers=inspector_headers)
    assert resp.status_code == 200
    retrieved = resp.json()
    assert retrieved["brand_name"] == "Royal Harvest"
    assert retrieved["country_of_origin"] == "India"
    assert retrieved["seller_information"] == "FastDelivery E-Commerce Ltd"


def test_comparison_exact_match(client, inspector_headers):
    """Test full match across all fields between listing and physical package declarations."""
    # Create inspection
    resp = client.post(
        "/api/inspections",
        headers=inspector_headers,
        json={
            "product_name": "Pure Desi Ghee",
            "category": "Packaged Food",
            "brand_name": "Shree Dairy",
            "location": "Market Yard",
        }
    )
    insp_id = resp.json()["id"]

    # Save online listing
    client.post(
        f"/api/inspections/{insp_id}/listing",
        headers=inspector_headers,
        json={
            "product_name": "Pure Desi Ghee 1L",
            "brand_name": "Shree Dairy",
            "mrp": "₹650.00",
            "net_quantity": "1 L",
            "manufacturer_details": "Shree Milk Products, Anand, Gujarat",
            "country_of_origin": "India",
            "consumer_care_details": "care@shreedairy.com",
        }
    )

    # Inject matching package declarations in database
    db = TestSessionLocal()
    declarations = [
        Declaration(inspection_id=insp_id, field_name="commodity_name", extracted_value="Pure Desi Ghee 1L", confidence=0.95),
        Declaration(inspection_id=insp_id, field_name="brand_name", extracted_value="Shree Dairy", confidence=0.96),
        Declaration(inspection_id=insp_id, field_name="mrp", extracted_value="₹650.00", confidence=0.98),
        Declaration(inspection_id=insp_id, field_name="net_quantity", extracted_value="1000 ml", confidence=0.94),
        Declaration(inspection_id=insp_id, field_name="manufacturer_details", extracted_value="Shree Milk Products, Anand, Gujarat", confidence=0.92),
        Declaration(inspection_id=insp_id, field_name="country_of_origin", extracted_value="India", confidence=0.97),
        Declaration(inspection_id=insp_id, field_name="consumer_care_details", extracted_value="care@shreedairy.com", confidence=0.91),
    ]
    for d in declarations:
        db.add(d)
    db.commit()
    db.close()

    # Execute comparison
    resp = client.post(f"/api/inspections/{insp_id}/listing/compare", headers=inspector_headers)
    assert resp.status_code == 200, resp.text
    summary = resp.json()

    # Matches check (product_name, brand, mrp, net_qty [1 L == 1000 ml], mfg, country, consumer_care)
    assert summary["matches_count"] >= 6
    assert summary["mismatches_count"] == 0
    assert summary["missing_on_listing_count"] == 0


def test_comparison_mrp_mismatch_overcharging(client, inspector_headers):
    """Test MRP mismatch where online listing price exceeds physical package MRP (Rule 18(2A))."""
    resp = client.post(
        "/api/inspections",
        headers=inspector_headers,
        json={
            "product_name": "Digestive Biscuits",
            "category": "Packaged Food",
            "location": "Online Marketplace Hub",
        }
    )
    insp_id = resp.json()["id"]

    # Online listing claims price ₹55.00
    client.post(
        f"/api/inspections/{insp_id}/listing",
        headers=inspector_headers,
        json={
            "product_name": "Digestive Biscuits 200g",
            "mrp": "₹55.00",
            "net_quantity": "200 g",
        }
    )

    # Physical package OCR established MRP is ₹50.00
    db = TestSessionLocal()
    db.add(Declaration(
        inspection_id=insp_id,
        field_name="mrp",
        extracted_value="MRP ₹50.00 (incl. of all taxes)",
        confidence=0.94
    ))
    db.add(Declaration(
        inspection_id=insp_id,
        field_name="net_quantity",
        extracted_value="200 g",
        confidence=0.95
    ))
    db.commit()
    db.close()

    # Compare
    resp = client.post(f"/api/inspections/{insp_id}/listing/compare", headers=inspector_headers)
    assert resp.status_code == 200
    summary = resp.json()

    mrp_comp = next((c for c in summary["comparisons"] if c["field_name"] == "mrp"), None)
    assert mrp_comp is not None
    assert mrp_comp["comparison_status"] == "MISMATCH"
    assert "exceeds physical package MRP" in mrp_comp["difference_explanation"]
    assert mrp_comp["applicable_rule_code"] == "PCR_RULE_18_2A_ONLINE_PRICE_OVERCHARGING"
    assert mrp_comp["listing_provenance"] == "MANUAL_LISTING_INPUT"
    assert mrp_comp["package_provenance"] == "PACKAGE_OCR"


def test_comparison_quantity_mismatch(client, inspector_headers):
    """Test Net Quantity discrepancy between listing and physical package."""
    resp = client.post(
        "/api/inspections",
        headers=inspector_headers,
        json={"product_name": "Roasted Almonds", "category": "Packaged Food", "location": "Warehouse"}
    )
    insp_id = resp.json()["id"]

    # Online listing claims 500 g
    client.post(
        f"/api/inspections/{insp_id}/listing",
        headers=inspector_headers,
        json={"product_name": "Roasted Almonds", "net_quantity": "500 g"}
    )

    # Package is 400 g
    db = TestSessionLocal()
    db.add(Declaration(inspection_id=insp_id, field_name="net_quantity", extracted_value="400 g", confidence=0.92))
    db.commit()
    db.close()

    resp = client.post(f"/api/inspections/{insp_id}/listing/compare", headers=inspector_headers)
    assert resp.status_code == 200
    summary = resp.json()

    qty_comp = next(c for c in summary["comparisons"] if c["field_name"] == "net_quantity")
    assert qty_comp["comparison_status"] == "MISMATCH"
    assert "Net quantity differs" in qty_comp["difference_explanation"]
    assert qty_comp["applicable_rule_code"] == "PCR_RULE_06_1_C"


def test_comparison_missing_on_listing_rule_6_10(client, inspector_headers):
    """Test declaration established on package but omitted from online listing (Rule 6(10) E-Commerce disclosure)."""
    resp = client.post(
        "/api/inspections",
        headers=inspector_headers,
        json={"product_name": "Herbal Shampoo", "category": "Household/Personal Care", "location": "Retail Outlet"}
    )
    insp_id = resp.json()["id"]

    # Listing has name and MRP, but consumer care and country of origin are omitted
    client.post(
        f"/api/inspections/{insp_id}/listing",
        headers=inspector_headers,
        json={"product_name": "Herbal Shampoo 200ml", "mrp": "₹180.00"}
    )

    # Package OCR contains consumer care
    db = TestSessionLocal()
    db.add(Declaration(
        inspection_id=insp_id,
        field_name="consumer_care_details",
        extracted_value="Email: care@herbals.in, Helpline: 1800-456-789",
        confidence=0.89
    ))
    db.commit()
    db.close()

    resp = client.post(f"/api/inspections/{insp_id}/listing/compare", headers=inspector_headers)
    assert resp.status_code == 200
    summary = resp.json()

    cc_comp = next(c for c in summary["comparisons"] if c["field_name"] == "consumer_care_details")
    assert cc_comp["comparison_status"] == "MISSING_ON_LISTING"
    assert "missing from online product listing" in cc_comp["difference_explanation"]
    assert cc_comp["applicable_rule_code"] == "PCR_RULE_06_10_ECOMMERCE_DECLARATION"


def test_comparison_missing_on_package(client, inspector_headers):
    """Test when online listing claims declaration that package OCR does not establish."""
    resp = client.post(
        "/api/inspections",
        headers=inspector_headers,
        json={"product_name": "Imported Olive Oil", "category": "Packaged Food", "location": "Gourmet Store"}
    )
    insp_id = resp.json()["id"]

    # Online listing claims specific importer
    client.post(
        f"/api/inspections/{insp_id}/listing",
        headers=inspector_headers,
        json={"product_name": "Imported Olive Oil", "importer_details": "Global Imports Pvt Ltd, New Delhi"}
    )

    # Package has no importer declaration
    resp = client.post(f"/api/inspections/{insp_id}/listing/compare", headers=inspector_headers)
    assert resp.status_code == 200
    summary = resp.json()

    imp_comp = next(c for c in summary["comparisons"] if c["field_name"] == "importer_details")
    assert imp_comp["comparison_status"] == "MISSING_ON_PACKAGE"
    assert "does not establish this declaration" in imp_comp["difference_explanation"]


def test_comparison_uncertain_when_ocr_confidence_low(client, inspector_headers):
    """Test that low OCR confidence (< 0.50) results in UNCERTAIN, requiring inspector verification."""
    resp = client.post(
        "/api/inspections",
        headers=inspector_headers,
        json={"product_name": "Spice Blend", "category": "Packaged Food", "location": "Local Bazaar"}
    )
    insp_id = resp.json()["id"]

    # Listing gives manufacturer
    client.post(
        f"/api/inspections/{insp_id}/listing",
        headers=inspector_headers,
        json={"product_name": "Spice Blend", "manufacturer_details": "Heritage Spices, Jaipur"}
    )

    # Package has blurry extraction with 0.38 confidence
    db = TestSessionLocal()
    db.add(Declaration(
        inspection_id=insp_id,
        field_name="manufacturer_details",
        extracted_value="H..itage Sp..s, Ja..ur",
        confidence=0.38,
        corrected_value=None
    ))
    db.commit()
    db.close()

    resp = client.post(f"/api/inspections/{insp_id}/listing/compare", headers=inspector_headers)
    assert resp.status_code == 200
    summary = resp.json()

    mfg_comp = next(c for c in summary["comparisons"] if c["field_name"] == "manufacturer_details")
    assert mfg_comp["comparison_status"] == "UNCERTAIN"
    assert "below verification threshold" in mfg_comp["difference_explanation"]


def test_no_automatic_violation_from_mismatch_alone(client, inspector_headers):
    """
    CRITICAL STATUTORY REQUIREMENT:
    A mismatch must NOT automatically become a legal violation.
    It remains an evidence discrepancy in PENDING_REVIEW status until inspector adjudication.
    """
    resp = client.post(
        "/api/inspections",
        headers=inspector_headers,
        json={"product_name": "Fruit Jam", "category": "Packaged Food", "location": "Supermarket"}
    )
    insp_id = resp.json()["id"]

    # Listing has mismatching MRP
    client.post(
        f"/api/inspections/{insp_id}/listing",
        headers=inspector_headers,
        json={"product_name": "Fruit Jam", "mrp": "₹120.00"}
    )
    db = TestSessionLocal()
    db.add(Declaration(inspection_id=insp_id, field_name="mrp", extracted_value="₹100.00", confidence=0.95))
    db.commit()
    db.close()

    resp = client.post(f"/api/inspections/{insp_id}/listing/compare", headers=inspector_headers)
    assert resp.status_code == 200
    summary = resp.json()

    comp = next(c for c in summary["comparisons"] if c["field_name"] == "mrp")
    assert comp["comparison_status"] == "MISMATCH"
    # Inspector status must be PENDING_REVIEW, not automatically a confirmed legal violation
    assert comp["inspector_status"] == "PENDING_REVIEW"
    assert comp["adjudicated_by"] is None


def test_inspector_adjudication_lifecycle(client, inspector_headers):
    """Test that enforcement inspector can adjudicate comparison findings."""
    resp = client.post(
        "/api/inspections",
        headers=inspector_headers,
        json={"product_name": "Bath Soap", "category": "Household/Personal Care", "location": "Retail Outlet"}
    )
    insp_id = resp.json()["id"]

    client.post(
        f"/api/inspections/{insp_id}/listing",
        headers=inspector_headers,
        json={"product_name": "Bath Soap 125g", "mrp": "₹45.00"}
    )
    db = TestSessionLocal()
    db.add(Declaration(inspection_id=insp_id, field_name="mrp", extracted_value="₹40.00", confidence=0.95))
    db.commit()
    db.close()

    resp = client.post(f"/api/inspections/{insp_id}/listing/compare", headers=inspector_headers)
    summary = resp.json()
    comp_id = next(c["id"] for c in summary["comparisons"] if c["field_name"] == "mrp")

    # Inspector adjudicates as CONFIRMED_DISCREPANCY
    adj_resp = client.post(
        f"/api/inspections/{insp_id}/listing/comparisons/{comp_id}/adjudicate",
        headers=inspector_headers,
        json={
            "status": "CONFIRMED_DISCREPANCY",
            "remarks": "Verified online marketplace URL. Price ₹45 exceeds printed package MRP ₹40 under Rule 18(2A)."
        }
    )
    assert adj_resp.status_code == 200, adj_resp.text
    adjudicated = adj_resp.json()
    assert adjudicated["inspector_status"] == "CONFIRMED_DISCREPANCY"
    assert adjudicated["adjudicated_by"] == settings.SEED_OFFICER_ID
    assert "Rule 18(2A)" in adjudicated["inspector_remarks"]


def test_anti_fabrication_provenance_preservation(client, inspector_headers):
    """
    ANTI-FABRICATION GUARANTEE:
    Verify that provenance is strictly preserved as MANUAL_LISTING_INPUT and PACKAGE_OCR.
    No country of origin is guessed from manufacturer address.
    """
    resp = client.post(
        "/api/inspections",
        headers=inspector_headers,
        json={"product_name": "Organic Honey", "category": "Packaged Food", "location": "Co-op Store"}
    )
    insp_id = resp.json()["id"]

    # Manufacturer given, but Country of Origin left completely blank
    client.post(
        f"/api/inspections/{insp_id}/listing",
        headers=inspector_headers,
        json={
            "product_name": "Organic Honey 500g",
            "manufacturer_details": "Himalayan Apiaries, Dehradun, Uttarakhand, India",
            "country_of_origin": None,  # Not provided on listing
        }
    )

    db = TestSessionLocal()
    db.add(Declaration(
        inspection_id=insp_id,
        field_name="manufacturer_details",
        extracted_value="Himalayan Apiaries, Dehradun",
        confidence=0.90
    ))
    db.commit()
    db.close()

    resp = client.post(f"/api/inspections/{insp_id}/listing/compare", headers=inspector_headers)
    summary = resp.json()

    # Country of origin should NOT be hallucinated or inferred from address
    coo_comp = next(c for c in summary["comparisons"] if c["field_name"] == "country_of_origin")
    assert coo_comp["listing_value"] is None
    assert coo_comp["listing_provenance"] == "MANUAL_LISTING_INPUT"


def test_comparison_without_listing_returns_400(client, inspector_headers):
    """Test error handling when comparison is triggered without entering listing data first."""
    resp = client.post(
        "/api/inspections",
        headers=inspector_headers,
        json={"product_name": "Test Snack", "category": "Packaged Food", "location": "Retail Outlet"}
    )
    insp_id = resp.json()["id"]

    resp = client.post(f"/api/inspections/{insp_id}/listing/compare", headers=inspector_headers)
    assert resp.status_code == 400
    assert "No product listing found" in resp.json()["detail"]


def test_rbac_scoping_on_listing_endpoints(client, inspector_headers, second_inspector_headers, supervisor_headers):
    """Test that RBAC protects listing endpoints across inspectors and allows supervisor oversight."""
    # 1. Inspector A creates inspection & listing
    resp = client.post(
        "/api/inspections",
        headers=inspector_headers,
        json={"product_name": "Washing Powder", "category": "Household/Personal Care", "location": "Depot"}
    )
    insp_id = resp.json()["id"]

    client.post(
        f"/api/inspections/{insp_id}/listing",
        headers=inspector_headers,
        json={"product_name": "Washing Powder 1kg", "mrp": "₹150.00"}
    )

    # 2. Inspector B cannot modify Inspector A's listing (403 Forbidden)
    resp = client.post(
        f"/api/inspections/{insp_id}/listing",
        headers=second_inspector_headers,
        json={"product_name": "Unauthorized Tamper"}
    )
    assert resp.status_code == 403

    # 3. Supervisor can view Inspector A's listing (200 OK)
    resp = client.get(f"/api/inspections/{insp_id}/listing", headers=supervisor_headers)
    assert resp.status_code == 200
    assert resp.json()["product_name"] == "Washing Powder 1kg"
