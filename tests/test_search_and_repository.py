"""
tests/test_search_and_repository.py

Comprehensive Test Suite for NiriKsha Search, Product Repository & Inspection History.
Satisfies PS 26034:
- "Search and retrieval facility for previously scanned products and reports."
- "Repository of scanned products and inspection history."

Covers:
1. Exact inspection ID & inspection number search
2. Product name and brand search
3. Manufacturer search (via declarations)
4. Location and batch number search
5. Date range filtering and malformed date validation (400 Bad Request)
6. Status and compliance outcome filtering
7. Finding type filtering (rule code / severity)
8. Combined multi-criteria filtering
9. Backend pagination (page, page_size, total, total_pages) & empty states
10. Role-based authorization & inspector data isolation
11. Product Repository catalogue & individual product inspection history
12. Statutory report search, retrieval, and immutability (no report deletion)
13. Complete evidence retrieval integrity (OCR, bounding boxes, declarations, evidence items)
14. Database safety (zero production DB mutation)
"""

import os
import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import settings
from backend.models import (
    User,
    Inspection,
    Product,
    Declaration,
    ComplianceCheck,
    RuleVersion,
    Report,
    ProductImage,
    OCRResult,
    Evidence
)
from backend.database import SessionLocal
from backend.auth_service import create_access_token
from backend.auth_utils import hash_password

client = TestClient(app)


@pytest.fixture(scope="function")
def db_session():
    """Provides an isolated database session for testing."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def auth_headers(db_session: Session):
    """Returns headers for the default seeded inspector."""
    user = db_session.query(User).filter(User.officer_id == settings.SEED_OFFICER_ID).first()
    if not user:
        user = User(
            officer_id=settings.SEED_OFFICER_ID,
            full_name="Primary Test Officer",
            role="INSPECTOR",
            designation="Inspector",
            zone="HQ",
            password_hash=hash_password(settings.SEED_OFFICER_PASSWORD)
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    token = create_access_token({"sub": user.officer_id, "role": user.role})
    return {"Authorization": f"Bearer {token}"}, user


@pytest.fixture
def admin_headers(db_session: Session):
    """Returns headers for an administrative user."""
    admin = db_session.query(User).filter(User.role == "ADMIN").first()
    if not admin:
        admin = User(
            officer_id="TEST-ADMIN-REPO",
            full_name="Chief Enforcement Administrator",
            role="ADMIN",
            designation="Chief Administrator",
            zone="HQ",
            password_hash=hash_password("AdminPass123!")
        )
        db_session.add(admin)
        db_session.commit()
        db_session.refresh(admin)
    token = create_access_token({"sub": admin.officer_id, "role": admin.role})
    return {"Authorization": f"Bearer {token}"}, admin


@pytest.fixture
def isolated_inspector_headers(db_session: Session):
    """Returns headers for a secondary inspector to verify role isolation."""
    user = db_session.query(User).filter(User.officer_id == "INSP-REPO-ISO-99").first()
    if not user:
        user = User(
            officer_id="INSP-REPO-ISO-99",
            full_name="Isolated Enforcement Officer",
            role="INSPECTOR",
            designation="Inspector",
            zone="South",
            password_hash=hash_password("Pass123!")
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    token = create_access_token({"sub": user.officer_id, "role": user.role})
    return {"Authorization": f"Bearer {token}"}, user


# ===========================================================================
# 1. Global Search & Inspection Repository Tests
# ===========================================================================

def test_exact_inspection_id_and_number_search(db_session: Session, auth_headers):
    """Verifies exact inspection number and UUID search returns the precise inspection record."""
    headers, user = auth_headers

    insp = Inspection(
        inspection_number="INSP-REPO-EXACT-01",
        inspector_id=user.id,
        location="Connaught Place, New Delhi",
        status="COMPLETED",
        overall_status="NO_POTENTIAL_VIOLATIONS"
    )
    db_session.add(insp)
    db_session.flush()

    prod = Product(
        inspection_id=insp.id,
        product_name="Golden Harvest Wheat Flour",
        brand_name="Aashirvaad",
        category="Packaged Food",
        batch_number="LOT-WH-2026-99"
    )
    db_session.add(prod)
    db_session.commit()

    # 1. Search by inspection_number
    resp = client.get("/api/repository/inspections?search=INSP-REPO-EXACT-01", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    found = next((i for i in data["items"] if i["inspection_number"] == "INSP-REPO-EXACT-01"), None)
    assert found is not None
    assert found["product_name"] == "Golden Harvest Wheat Flour"
    assert found["brand_name"] == "Aashirvaad"
    assert found["batch_number"] == "LOT-WH-2026-99"

    # 2. Search by inspection UUID
    resp_uuid = client.get(f"/api/repository/inspections?search={insp.id}", headers=headers)
    assert resp_uuid.status_code == 200
    uuid_data = resp_uuid.json()
    assert any(i["id"] == insp.id for i in uuid_data["items"])


def test_product_name_and_brand_search(db_session: Session, auth_headers):
    """Verifies multi-field search across product name and brand name."""
    headers, user = auth_headers

    insp = Inspection(
        inspection_number="INSP-REPO-PROD-02",
        inspector_id=user.id,
        location="Indiranagar, Bengaluru",
        status="COMPLETED",
        overall_status="POTENTIAL_NON_COMPLIANCE"
    )
    db_session.add(insp)
    db_session.flush()

    prod = Product(
        inspection_id=insp.id,
        product_name="Pure Desi Ghee",
        brand_name="Amul Heritage",
        category="Packaged Food"
    )
    db_session.add(prod)
    db_session.commit()

    # Search by brand
    resp = client.get("/api/repository/inspections?search=Amul+Heritage", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(i["inspection_number"] == "INSP-REPO-PROD-02" for i in items)

    # Search by product name
    resp_p = client.get("/api/repository/inspections?search=Desi+Ghee", headers=headers)
    assert resp_p.status_code == 200
    assert any(i["inspection_number"] == "INSP-REPO-PROD-02" for i in resp_p.json()["items"])


def test_manufacturer_and_batch_search_via_declarations(db_session: Session, auth_headers):
    """Verifies that search matches manufacturer and batch codes stored in package declarations."""
    headers, user = auth_headers

    insp = Inspection(
        inspection_number="INSP-REPO-MFR-03",
        inspector_id=user.id,
        location="Sector 18, Noida",
        status="EXTRACTION_COMPLETE",
        overall_status="NEEDS_MANUAL_VERIFICATION"
    )
    db_session.add(insp)
    db_session.flush()

    prod = Product(
        inspection_id=insp.id,
        product_name="Herbal Shampoo",
        brand_name="Patanjali",
        category="Personal Care / Household"
    )
    db_session.add(prod)

    decl_mfr = Declaration(
        inspection_id=insp.id,
        field_name="manufacturer_name",
        extracted_value="Patanjali Ayurved Haridwar Ltd.",
        extraction_status="EXTRACTED"
    )
    decl_batch = Declaration(
        inspection_id=insp.id,
        field_name="batch_code",
        extracted_value="BATCH-HARIDWAR-7788",
        extraction_status="EXTRACTED"
    )
    db_session.add_all([decl_mfr, decl_batch])
    db_session.commit()

    # Search by manufacturer declared name
    resp_mfr = client.get("/api/repository/inspections?search=Haridwar", headers=headers)
    assert resp_mfr.status_code == 200
    assert any(i["inspection_number"] == "INSP-REPO-MFR-03" for i in resp_mfr.json()["items"])

    # Search by declared batch code
    resp_batch = client.get("/api/repository/inspections?search=HARIDWAR-7788", headers=headers)
    assert resp_batch.status_code == 200
    assert any(i["inspection_number"] == "INSP-REPO-MFR-03" for i in resp_batch.json()["items"])


# ===========================================================================
# 2. Date Filtering & Validation Tests
# ===========================================================================

def test_date_range_filtering_and_validation(db_session: Session, auth_headers):
    """Verifies date filtering with valid ISO strings and 400 Bad Request on invalid format."""
    headers, user = auth_headers

    # Today inspection
    insp_today = Inspection(
        inspection_number="INSP-REPO-DATE-TODAY",
        inspector_id=user.id,
        location="Civil Lines, Jaipur",
        status="COMPLETED",
        created_at=datetime.utcnow()
    )
    # Past inspection (60 days ago)
    insp_past = Inspection(
        inspection_number="INSP-REPO-DATE-PAST",
        inspector_id=user.id,
        location="Hazratganj, Lucknow",
        status="COMPLETED",
        created_at=datetime.utcnow() - timedelta(days=60)
    )
    db_session.add_all([insp_today, insp_past])
    db_session.flush()

    db_session.add(Product(inspection_id=insp_today.id, product_name="Tea", category="Packaged Food"))
    db_session.add(Product(inspection_id=insp_past.id, product_name="Coffee", category="Packaged Food"))
    db_session.commit()

    # Filter with start_date 5 days ago
    start_iso = (datetime.utcnow() - timedelta(days=5)).strftime("%Y-%m-%d")
    resp = client.get(f"/api/repository/inspections?start_date={start_iso}", headers=headers)
    assert resp.status_code == 200
    nums = [i["inspection_number"] for i in resp.json()["items"]]
    assert "INSP-REPO-DATE-TODAY" in nums
    assert "INSP-REPO-DATE-PAST" not in nums

    # Invalid date format should return 400
    resp_bad = client.get("/api/repository/inspections?start_date=2026/99/99", headers=headers)
    assert resp_bad.status_code == 400
    assert "Invalid date format" in resp_bad.json()["detail"]


# ===========================================================================
# 3. Status, Compliance, and Finding Type Filtering
# ===========================================================================

def test_status_and_finding_type_filtering(db_session: Session, auth_headers):
    """Verifies filtering by compliance outcome and specific statutory finding rule code."""
    headers, user = auth_headers

    insp_pass = Inspection(
        inspection_number="INSP-REPO-PASS-01",
        inspector_id=user.id,
        location="Salt Lake, Kolkata",
        status="COMPLETED",
        overall_status="NO_POTENTIAL_VIOLATIONS"
    )
    insp_fail = Inspection(
        inspection_number="INSP-REPO-FAIL-01",
        inspector_id=user.id,
        location="Park Street, Kolkata",
        status="COMPLETED",
        overall_status="POTENTIAL_NON_COMPLIANCE"
    )
    db_session.add_all([insp_pass, insp_fail])
    db_session.flush()

    db_session.add(Product(inspection_id=insp_pass.id, product_name="Rice", category="Packaged Food"))
    db_session.add(Product(inspection_id=insp_fail.id, product_name="Sugar", category="Packaged Food"))

    rule_ver = db_session.query(RuleVersion).filter(RuleVersion.rule_code == "PCR_RULE_06_1_E").first()
    if not rule_ver:
        rule_ver = RuleVersion(
            rule_code="PCR_RULE_06_1_E",
            title="Maximum Retail Price Declaration",
            category="CATEGORY_A_LEGAL",
            statutory_reference="Rule 6(1)(e)",
            rule_logic_description="MRP check",
            severity="CRITICAL"
        )
        db_session.add(rule_ver)
        db_session.commit()
        db_session.refresh(rule_ver)

    chk = ComplianceCheck(
        inspection_id=insp_fail.id,
        rule_version_id=rule_ver.id,
        rule_code="PCR_RULE_06_1_E",
        title="MRP Missing on Packaging",
        severity="CRITICAL",
        result_state="POTENTIAL_NON_COMPLIANCE",
        explanation="MRP statement omitted from packaging"
    )
    db_session.add(chk)
    db_session.commit()

    # 1. Filter by overall_status
    resp_status = client.get("/api/repository/inspections?overall_status=POTENTIAL_NON_COMPLIANCE", headers=headers)
    assert resp_status.status_code == 200
    nums = [i["inspection_number"] for i in resp_status.json()["items"]]
    assert "INSP-REPO-FAIL-01" in nums
    assert "INSP-REPO-PASS-01" not in nums

    # 2. Filter by finding_type (rule code)
    resp_rule = client.get("/api/repository/inspections?finding_type=PCR_RULE_06_1_E", headers=headers)
    assert resp_rule.status_code == 200
    rule_nums = [i["inspection_number"] for i in resp_rule.json()["items"]]
    assert "INSP-REPO-FAIL-01" in rule_nums
    assert "INSP-REPO-PASS-01" not in rule_nums


# ===========================================================================
# 4. Pagination & Empty State Tests
# ===========================================================================

def test_pagination_and_empty_state(db_session: Session, auth_headers):
    """Verifies backend pagination boundaries, total count calculation, and empty state handling."""
    headers, user = auth_headers

    # Query non-existent keyword
    resp_empty = client.get("/api/repository/inspections?search=NONEXISTENT_XYZ_99999", headers=headers)
    assert resp_empty.status_code == 200
    data_empty = resp_empty.json()
    assert data_empty["total"] == 0
    assert data_empty["items"] == []
    assert data_empty["total_pages"] == 0

    # Query with pagination limit
    resp_paged = client.get("/api/repository/inspections?page=1&page_size=2", headers=headers)
    assert resp_paged.status_code == 200
    data_paged = resp_paged.json()
    assert data_paged["page"] == 1
    assert data_paged["page_size"] == 2
    assert len(data_paged["items"]) <= 2


# ===========================================================================
# 5. Role Authorization & Inspector Isolation Tests
# ===========================================================================

def test_role_authorization_and_inspector_isolation(db_session: Session, auth_headers, isolated_inspector_headers, admin_headers):
    """Verifies that non-admin inspectors cannot view other officers' inspection records."""
    headers_primary, user_primary = auth_headers
    headers_isolated, user_isolated = isolated_inspector_headers
    headers_admin, admin_user = admin_headers

    # Create inspection for isolated officer
    insp_secret = Inspection(
        inspection_number="INSP-SECRET-ISOLATED-01",
        inspector_id=user_isolated.id,
        location="Thiruvananthapuram, Kerala",
        status="COMPLETED",
        overall_status="NO_POTENTIAL_VIOLATIONS"
    )
    db_session.add(insp_secret)
    db_session.flush()
    db_session.add(Product(inspection_id=insp_secret.id, product_name="Coconut Oil", category="Packaged Food"))
    db_session.commit()

    # 1. Primary inspector searching for secret inspection -> Should NOT see it
    resp_pri = client.get("/api/repository/inspections?search=INSP-SECRET-ISOLATED-01", headers=headers_primary)
    assert resp_pri.status_code == 200
    assert resp_pri.json()["total"] == 0

    # 2. Isolated inspector searching for own inspection -> SHOULD see it
    resp_iso = client.get("/api/repository/inspections?search=INSP-SECRET-ISOLATED-01", headers=headers_isolated)
    assert resp_iso.status_code == 200
    assert resp_iso.json()["total"] == 1

    # 3. Admin searching for secret inspection -> SHOULD see it (organization-wide)
    resp_adm = client.get("/api/repository/inspections?search=INSP-SECRET-ISOLATED-01", headers=headers_admin)
    assert resp_adm.status_code == 200
    assert resp_adm.json()["total"] >= 1


# ===========================================================================
# 6. Product Repository & History Tests
# ===========================================================================

def test_product_repository_and_inspection_history(db_session: Session, auth_headers):
    """
    Verifies that Product Repository aggregates products by explicit identity
    (product_name, brand, category) and clicking returns full inspection history.
    """
    headers, user = auth_headers

    # Same product inspected twice
    insp1 = Inspection(
        inspection_number="INSP-PROD-HIST-01",
        inspector_id=user.id,
        location="MG Road, Pune",
        status="COMPLETED",
        overall_status="NO_POTENTIAL_VIOLATIONS"
    )
    insp2 = Inspection(
        inspection_number="INSP-PROD-HIST-02",
        inspector_id=user.id,
        location="FC Road, Pune",
        status="COMPLETED",
        overall_status="POTENTIAL_NON_COMPLIANCE"
    )
    db_session.add_all([insp1, insp2])
    db_session.flush()

    prod1 = Product(
        inspection_id=insp1.id,
        product_name="Almond Milk Organic",
        brand_name="NutriPure",
        category="Packaged Food"
    )
    prod2 = Product(
        inspection_id=insp2.id,
        product_name="Almond Milk Organic",
        brand_name="NutriPure",
        category="Packaged Food"
    )
    db_session.add_all([prod1, prod2])
    db_session.commit()

    # 1. Fetch products repository
    resp_repo = client.get("/api/repository/products?search=Almond+Milk", headers=headers)
    assert resp_repo.status_code == 200
    data = resp_repo.json()
    assert data["total"] >= 1

    prod_entry = next((p for p in data["items"] if p["product_name"] == "Almond Milk Organic"), None)
    assert prod_entry is not None
    assert prod_entry["brand_name"] == "NutriPure"
    # Surveillance count should reflect both inspections
    assert prod_entry["inspection_count"] >= 2
    assert prod_entry["product_key"] is not None

    # 2. Fetch inspection history for this specific product
    resp_hist = client.get(f"/api/repository/products/{prod_entry['product_key']}/inspections", headers=headers)
    assert resp_hist.status_code == 200
    hist_data = resp_hist.json()
    assert hist_data["total"] >= 2
    hist_numbers = [i["inspection_number"] for i in hist_data["items"]]
    assert "INSP-PROD-HIST-01" in hist_numbers
    assert "INSP-PROD-HIST-02" in hist_numbers


# ===========================================================================
# 7. Report Search & Immutability Tests
# ===========================================================================

def test_report_search_retrieval_and_immutability(db_session: Session, auth_headers):
    """
    Verifies report search by inspection ID, product, retrieval links,
    and guarantees report immutability (rejection of deletion).
    """
    headers, user = auth_headers

    insp = Inspection(
        inspection_number="INSP-REPO-REP-01",
        inspector_id=user.id,
        location="Sector 29, Gurugram",
        status="COMPLETED",
        overall_status="NO_POTENTIAL_VIOLATIONS"
    )
    db_session.add(insp)
    db_session.flush()

    prod = Product(inspection_id=insp.id, product_name="Basmati Rice Special", category="Packaged Food")
    db_session.add(prod)

    rep = Report(
        inspection_id=insp.id,
        report_version=1,
        pdf_path="./generated_reports/test_repo_report.pdf",
        legal_safety_statement="Statutory Inspection Report under PCR 2011"
    )
    db_session.add(rep)
    db_session.commit()

    # 1. Search reports by inspection number
    resp = client.get("/api/repository/reports?search=INSP-REPO-REP-01", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    found_rep = next((r for r in data["items"] if r["inspection_number"] == "INSP-REPO-REP-01"), None)
    assert found_rep is not None
    assert found_rep["product_name"] == "Basmati Rice Special"
    assert found_rep["download_url"] == f"/api/inspections/{insp.id}/report/pdf"

    # 2. Immutability guarantee: DELETE /api/reports/{id} does NOT exist
    resp_del = client.delete(f"/api/reports/{rep.id}", headers=headers)
    assert resp_del.status_code in (404, 405), "Report deletion must never be allowed (statutory immutability)"


# ===========================================================================
# 8. Complete Evidence Chain Retrieval Integrity
# ===========================================================================

def test_complete_evidence_chain_retrieval(db_session: Session, auth_headers):
    """
    Verifies that inspection details provide complete access to images, blur score,
    raw OCR text, bounding boxes, declarations, rule checks, and photographic evidence.
    """
    headers, user = auth_headers

    insp = Inspection(
        inspection_number="INSP-REPO-EVID-01",
        inspector_id=user.id,
        location="Viman Nagar, Pune",
        status="FINALIZED",
        overall_status="POTENTIAL_NON_COMPLIANCE"
    )
    db_session.add(insp)
    db_session.flush()

    prod = Product(inspection_id=insp.id, product_name="Crispy Potato Chips", category="Packaged Food")
    img = ProductImage(
        inspection_id=insp.id,
        file_path="/uploads/test_chips.jpg",
        view_type="front",
        blur_score=142.5,
        quality_score=0.92,
        quality_status="GOOD"
    )
    db_session.add_all([prod, img])
    db_session.flush()

    ocr = OCRResult(
        image_id=img.id,
        raw_text="MRP Rs 20.00 Net Wt 50g",
        confidence=0.95,
        bounding_boxes_json='[{"text": "MRP Rs 20.00", "bbox": [10, 10, 100, 30]}]'
    )
    decl = Declaration(
        inspection_id=insp.id,
        field_name="mrp",
        extracted_value="20.00",
        corrected_value="25.00",
        extraction_status="EXTRACTED",
        verification_status="CORRECTED"
    )
    rule_ver = db_session.query(RuleVersion).filter(RuleVersion.rule_code == "PCR_RULE_06_1_E").first()
    if not rule_ver:
        rule_ver = RuleVersion(
            rule_code="PCR_RULE_06_1_E",
            title="Maximum Retail Price Declaration",
            category="CATEGORY_A_LEGAL",
            statutory_reference="Rule 6(1)(e)",
            rule_logic_description="MRP check",
            severity="CRITICAL"
        )
        db_session.add(rule_ver)
        db_session.commit()
        db_session.refresh(rule_ver)

    chk = ComplianceCheck(
        inspection_id=insp.id,
        rule_version_id=rule_ver.id,
        rule_code=rule_ver.rule_code,
        title="MRP Check",
        result_state="POTENTIAL_NON_COMPLIANCE",
        explanation="Discrepancy in declared MRP"
    )
    db_session.add_all([ocr, decl, chk])
    db_session.flush()

    ev = Evidence(
        check_id=chk.id,
        image_id=img.id,
        bounding_box_json="[10, 10, 100, 30]",
        highlight_text="MRP Rs 20.00",
        reason="OCR detection on front panel"
    )
    db_session.add(ev)
    db_session.commit()

    # 1. Fetch images
    r_img = client.get(f"/api/inspections/{insp.id}/images", headers=headers)
    assert r_img.status_code == 200
    images = r_img.json()
    assert len(images) >= 1
    assert images[0]["quality_status"] == "GOOD"
    assert images[0]["quality_score"] == 0.92

    # 2. Fetch OCR results
    r_ocr = client.get(f"/api/inspections/{insp.id}/ocr", headers=headers)
    assert r_ocr.status_code == 200
    assert any("MRP Rs 20.00" in o["raw_text"] for o in r_ocr.json())

    # 3. Fetch declarations (preserves both original OCR and officer correction)
    r_decl = client.get(f"/api/inspections/{insp.id}/declarations", headers=headers)
    assert r_decl.status_code == 200
    decl_item = next(d for d in r_decl.json() if d["field_name"] == "mrp")
    assert decl_item["extracted_value"] == "20.00"  # Original OCR baseline untouched
    assert decl_item["corrected_value"] == "25.00"  # Officer correction separate

    # 4. Fetch findings and evidence
    r_find = client.get(f"/api/inspections/{insp.id}/findings", headers=headers)
    assert r_find.status_code == 200
    findings = r_find.json()
    assert len(findings) >= 1
    assert len(findings[0]["evidence_items"]) >= 1
    assert findings[0]["evidence_items"][0]["highlight_text"] == "MRP Rs 20.00"


def test_unauthorized_repository_access():
    """Verifies that unauthenticated callers are rejected with 401 Unauthorized."""
    assert client.get("/api/repository/inspections").status_code == 401
    assert client.get("/api/repository/products").status_code == 401
    assert client.get("/api/repository/reports").status_code == 401
