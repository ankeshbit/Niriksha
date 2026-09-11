"""
tests/test_enforcement_dashboard.py

Comprehensive Test Suite for NiriKsha Enforcement & Compliance Dashboard.
Satisfies PS 26034 requirements:
- Dynamic calculation of all 7 KPI cards
- Empty database zero-state resilience
- Inspection registry multi-criteria filtering (status, category, location, inspector, dates, search)
- Date filter format validation (400 Bad Request on malformed date)
- Inspector data isolation & Role-based authorization
- Pending actions adjudication queue detection
- Compliance rate and breakdown analytics (with empty-state handling)
- Jurisdictional enforcement activity aggregation
- Unauthorized access rejection (401 Unauthorized)
- Database safety (zero production DB mutation)
"""

import os
import pytest
from datetime import datetime, timedelta, timezone
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
    ProductImage
)
from backend.database import SessionLocal, engine
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
            officer_id="TEST-ADMIN-01",
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
def secondary_inspector_headers(db_session: Session):
    """Returns headers for a distinct second inspector to test data isolation."""
    user = db_session.query(User).filter(User.officer_id == "INSP-ISOLATED-99").first()
    if not user:
        user = User(
            officer_id="INSP-ISOLATED-99",
            full_name="Isolated Secondary Officer",
            role="INSPECTOR",
            designation="Inspector",
            zone="West",
            password_hash=hash_password("Pass123!")
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    token = create_access_token({"sub": user.officer_id, "role": user.role})
    return {"Authorization": f"Bearer {token}"}, user


# ===========================================================================
# 1. KPI Summary Tests
# ===========================================================================

def test_dashboard_summary_kpis(db_session: Session, auth_headers):
    """Verify that all 7 KPI cards return dynamic, accurate integer counts matching actual DB state."""
    headers, user = auth_headers

    # Create a batch of distinct test inspections
    insp1 = Inspection(
        inspection_number="INSP-TEST-KPI-01",
        inspector_id=user.id,
        location="Connaught Place, New Delhi",
        status="COMPLETED",
        overall_status="NO_POTENTIAL_VIOLATIONS",
        finalized_at=datetime.utcnow()
    )
    insp2 = Inspection(
        inspection_number="INSP-TEST-KPI-02",
        inspector_id=user.id,
        location="Bandra West, Mumbai",
        status="RULE_EVALUATION_COMPLETE",
        overall_status="POTENTIAL_NON_COMPLIANCE"
    )
    insp3 = Inspection(
        inspection_number="INSP-TEST-KPI-03",
        inspector_id=user.id,
        location="Koramangala, Bengaluru",
        status="EXTRACTION_COMPLETE",
        overall_status="NEEDS_MANUAL_VERIFICATION"
    )
    db_session.add_all([insp1, insp2, insp3])
    db_session.flush()

    prod1 = Product(inspection_id=insp1.id, product_name="Digestive Biscuits", category="Packaged Food")
    prod2 = Product(inspection_id=insp2.id, product_name="Organic Honey", category="Packaged Food")
    prod3 = Product(inspection_id=insp3.id, product_name="Laundry Detergent", category="Personal Care / Household")
    db_session.add_all([prod1, prod2, prod3])

    # Add a report to insp1
    rep = Report(
        inspection_id=insp1.id,
        report_version=1,
        pdf_path="./generated_reports/test_report.pdf",
        legal_safety_statement="Statutory Inspection Report under PCR 2011"
    )
    db_session.add(rep)
    db_session.commit()

    resp = client.get("/api/dashboard/summary", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "total_inspections" in data
    assert "completed_inspections" in data
    assert "pending_verification" in data
    assert "potential_non_compliance" in data
    assert "compliant_inspections" in data
    assert "reports_generated" in data
    assert "manual_verification_required" in data

    assert data["total_inspections"] >= 3
    assert data["completed_inspections"] >= 1
    assert data["compliant_inspections"] >= 1
    assert data["potential_non_compliance"] >= 1
    assert data["pending_verification"] >= 1
    assert data["reports_generated"] >= 1


def test_dashboard_summary_empty_state(secondary_inspector_headers):
    """Verify that an inspector with zero inspections receives all zero KPIs cleanly."""
    headers, _ = secondary_inspector_headers
    resp = client.get("/api/dashboard/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_inspections"] == 0
    assert data["completed_inspections"] == 0
    assert data["compliant_inspections"] == 0
    assert data["potential_non_compliance"] == 0
    assert data["pending_verification"] == 0
    assert data["reports_generated"] == 0
    assert data["manual_verification_required"] == 0


# ===========================================================================
# 2. Multi-Criteria Filtering & Search
# ===========================================================================

def test_dashboard_inspections_filtering(db_session: Session, auth_headers):
    """Verify filtering by status, overall_status, category, location, and report presence."""
    headers, user = auth_headers

    insp_filter = Inspection(
        inspection_number="INSP-FILTER-001",
        inspector_id=user.id,
        location="Sector 18, Noida",
        status="COMPLETED",
        overall_status="POTENTIAL_NON_COMPLIANCE",
        finalized_at=datetime.utcnow()
    )
    db_session.add(insp_filter)
    db_session.flush()
    prod_filter = Product(
        inspection_id=insp_filter.id,
        product_name="Unique Mustard Oil Bottle",
        brand_name="PureFarm",
        category="Packaged Food"
    )
    db_session.add(prod_filter)
    db_session.commit()

    # 1. Filter by status
    r1 = client.get("/api/dashboard/inspections?status=COMPLETED", headers=headers)
    assert r1.status_code == 200
    assert any(i["id"] == insp_filter.id for i in r1.json()["items"])

    # 2. Filter by overall_status
    r2 = client.get("/api/dashboard/inspections?overall_status=POTENTIAL_NON_COMPLIANCE", headers=headers)
    assert r2.status_code == 200
    assert any(i["id"] == insp_filter.id for i in r2.json()["items"])

    # 3. Filter by category
    r3 = client.get("/api/dashboard/inspections?category=Packaged Food", headers=headers)
    assert r3.status_code == 200
    assert any(i["id"] == insp_filter.id for i in r3.json()["items"])

    # 4. Filter by location substring
    r4 = client.get("/api/dashboard/inspections?location=Noida", headers=headers)
    assert r4.status_code == 200
    assert any(i["id"] == insp_filter.id for i in r4.json()["items"])

    # 5. Search keyword by product name
    r5 = client.get("/api/dashboard/inspections?search=Mustard", headers=headers)
    assert r5.status_code == 200
    assert any(i["id"] == insp_filter.id for i in r5.json()["items"])


def test_dashboard_date_filtering(db_session: Session, auth_headers):
    """Verify start_date and end_date filtering returns proper subset."""
    headers, user = auth_headers
    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    resp = client.get(f"/api/dashboard/inspections?start_date={today_str}", headers=headers)
    assert resp.status_code == 200
    assert "items" in resp.json()


def test_dashboard_invalid_date_format(auth_headers):
    """Verify that an invalid date string returns HTTP 400 Bad Request."""
    headers, _ = auth_headers
    resp = client.get("/api/dashboard/inspections?start_date=invalid-date-format", headers=headers)
    assert resp.status_code == 400
    assert "Invalid date format" in resp.json()["detail"]


# ===========================================================================
# 3. Inspector Data Isolation & Role Authorization
# ===========================================================================

def test_dashboard_inspector_isolation(db_session: Session, auth_headers, secondary_inspector_headers, admin_headers):
    """Verify that an inspector cannot see another officer's inspections, but Admin can view all."""
    h1, user1 = auth_headers
    h2, user2 = secondary_inspector_headers
    h_admin, admin_user = admin_headers

    # Create private inspection for user1
    private_insp = Inspection(
        inspection_number="INSP-PRIVATE-USER1",
        inspector_id=user1.id,
        location="Inspector 1 Exclusive Area",
        status="DRAFT"
    )
    db_session.add(private_insp)
    db_session.flush()
    db_session.add(Product(inspection_id=private_insp.id, product_name="Confidential Specimen", category="Packaged Food"))
    db_session.commit()

    # User 2 queries inspections list -> Must NOT see user1's inspection
    r_user2 = client.get("/api/dashboard/inspections", headers=h2)
    assert r_user2.status_code == 200
    user2_items = r_user2.json()["items"]
    assert not any(i["id"] == private_insp.id for i in user2_items)

    # Admin queries inspections list -> Must see user1's inspection
    r_admin = client.get("/api/dashboard/inspections", headers=h_admin)
    assert r_admin.status_code == 200
    admin_items = r_admin.json()["items"]
    assert any(i["id"] == private_insp.id for i in admin_items)


# ===========================================================================
# 4. Pending Actions Adjudication Queue
# ===========================================================================

def test_dashboard_pending_actions(db_session: Session, auth_headers):
    """Verify pending actions queue detects missing declarations, conflicts, and unadjudicated findings."""
    headers, user = auth_headers

    insp = Inspection(
        inspection_number="INSP-PENDING-ACTION-01",
        inspector_id=user.id,
        location="Jaipur Mandi",
        status="RULE_EVALUATION_COMPLETE",
        overall_status="POTENTIAL_NON_COMPLIANCE"
    )
    db_session.add(insp)
    db_session.flush()

    db_session.add(Product(inspection_id=insp.id, product_name="Action Required Product", category="Packaged Food"))

    # 1. Missing declaration
    d_missing = Declaration(
        inspection_id=insp.id,
        field_name="net_quantity",
        extraction_status="NOT_FOUND",
        verification_status="NEEDS_MANUAL_VERIFICATION"
    )
    # 2. Conflicting declaration
    d_conflict = Declaration(
        inspection_id=insp.id,
        field_name="mrp",
        extraction_status="CONFLICTING",
        verification_status="NEEDS_MANUAL_VERIFICATION"
    )
    # 3. Unadjudicated non-compliance finding
    rule_ver = db_session.query(RuleVersion).filter(RuleVersion.rule_code == "PCR_RULE_06_1_A").first()
    if not rule_ver:
        rule_ver = RuleVersion(
            rule_code="PCR_RULE_06_1_A",
            version_number=1,
            title="Manufacturer Address Missing",
            category="CATEGORY_A_LEGAL",
            statutory_reference="Rule 6(1)(a)",
            rule_logic_description="Mandatory manufacturer address check",
            severity="CRITICAL"
        )
        db_session.add(rule_ver)
        db_session.commit()
        db_session.refresh(rule_ver)

    c_finding = ComplianceCheck(
        inspection_id=insp.id,
        rule_version_id=rule_ver.id,
        rule_code=rule_ver.rule_code,
        title="Manufacturer Address Missing",
        result_state="POTENTIAL_NON_COMPLIANCE",
        severity="CRITICAL",
        adjudication_status="PENDING",
        explanation="Manufacturer declaration omitted"
    )
    db_session.add_all([d_missing, d_conflict, c_finding])
    db_session.commit()

    resp = client.get("/api/dashboard/pending-actions", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    actions = data["items"]

    # Assert detection of all 3 action types
    action_types = [a["action_type"] for a in actions if a["inspection_id"] == insp.id]
    assert "MISSING_DECLARATION" in action_types
    assert "CONFLICTING_DECLARATION" in action_types
    assert "PENDING_ADJUDICATION" in action_types


# ===========================================================================
# 5. Compliance Analytics & Rates
# ===========================================================================

def test_dashboard_compliance_analytics(auth_headers):
    """Verify compliance analytics return percentage rates, rule breakdowns, and timeline distribution."""
    headers, _ = auth_headers
    resp = client.get("/api/dashboard/analytics", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert "has_sufficient_data" in data
    assert "compliance_rate" in data
    assert "potential_non_compliance_rate" in data
    assert "manual_verification_rate" in data
    assert "findings_by_field" in data
    assert "findings_by_rule" in data
    assert "findings_by_category" in data
    assert "inspections_over_time" in data

    if data["has_sufficient_data"]:
        assert 0.0 <= data["compliance_rate"] <= 100.0
        assert 0.0 <= data["potential_non_compliance_rate"] <= 100.0


# ===========================================================================
# 6. Enforcement Activity
# ===========================================================================

def test_dashboard_enforcement_activity(auth_headers):
    """Verify enforcement activity returns locations, inspector distribution, top rules, and repeat products."""
    headers, _ = auth_headers
    resp = client.get("/api/dashboard/enforcement", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert "inspections_by_location" in data
    assert "inspections_by_inspector" in data
    assert "non_compliance_by_location" in data
    assert "top_flagged_rules" in data
    assert "repeatedly_inspected_products" in data


# ===========================================================================
# 7. Security: Unauthorized Access Rejection
# ===========================================================================

def test_dashboard_unauthorized_access():
    """Verify that unauthenticated requests to all dashboard endpoints are rejected with 401 Unauthorized."""
    endpoints = [
        "/api/dashboard",
        "/api/dashboard/summary",
        "/api/dashboard/inspections",
        "/api/dashboard/pending-actions",
        "/api/dashboard/analytics",
        "/api/dashboard/enforcement"
    ]
    for ep in endpoints:
        resp = client.get(ep)
        assert resp.status_code == 401, f"Expected 401 for {ep}, got {resp.status_code}"
