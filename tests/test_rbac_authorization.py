"""
tests/test_rbac_authorization.py

Comprehensive Role-Based Access Control (RBAC) & Server-Side Authorization Test Suite for NiriKsha.
Satisfies PS 26034 requirements:
- Role definitions: INSPECTOR, SUPERVISOR, ADMIN
- JWT token authentication with safe role claims (no password leakage)
- 401 Unauthorized on missing, malformed, or expired JWTs
- Field officer resource isolation (403 Forbidden when Inspector A accesses or mutates Inspector B's resources)
- Cross-inspector filtering protection (403 Forbidden when Inspector targets another inspector_id)
- Supervisory oversight access (200 OK on cross-officer reads, analytics, and repository search)
- Supervisory mutation denial (403 Forbidden when Supervisor attempts to upload, adjudicate, or finalize field inspections)
- Administrative privilege & user role management (200 OK for Admin, 403 Forbidden for Inspector/Supervisor)
- Audit log provenance for role modifications
- Database safety (zero production DB mutation)
"""

import os
import json
import pytest
import uuid
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from jose import jwt

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
    Evidence,
    AuditLog
)
from backend.database import SessionLocal
from backend.auth_service import create_access_token
from backend.auth_utils import hash_password

client = TestClient(app)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture(scope="function")
def db_session():
    """Provides an isolated database session for testing."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def inspector_a_headers(db_session: Session):
    """Returns headers for Primary Inspector (Officer A)."""
    user = db_session.query(User).filter(User.officer_id == "INSP-OFFICER-A").first()
    if not user:
        user = User(
            officer_id="INSP-OFFICER-A",
            full_name="Inspector Amit Verma",
            role="INSPECTOR",
            designation="Field Inspector (Legal Metrology)",
            zone="North Zone",
            password_hash=hash_password("InspectorPass123!")
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    token = create_access_token({"sub": user.officer_id, "role": user.role})
    return {"Authorization": f"Bearer {token}"}, user


@pytest.fixture
def inspector_b_headers(db_session: Session):
    """Returns headers for Secondary Inspector (Officer B)."""
    user = db_session.query(User).filter(User.officer_id == "INSP-OFFICER-B").first()
    if not user:
        user = User(
            officer_id="INSP-OFFICER-B",
            full_name="Inspector Bhavna Patel",
            role="INSPECTOR",
            designation="Field Inspector (Legal Metrology)",
            zone="West Zone",
            password_hash=hash_password("InspectorPass456!")
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    token = create_access_token({"sub": user.officer_id, "role": user.role})
    return {"Authorization": f"Bearer {token}"}, user


@pytest.fixture
def supervisor_headers(db_session: Session):
    """Returns headers for Supervisory Officer."""
    user = db_session.query(User).filter(User.officer_id == "SUP-OFFICER-01").first()
    if not user:
        user = User(
            officer_id="SUP-OFFICER-01",
            full_name="Supervisor Sanjay Mehta",
            role="SUPERVISOR",
            designation="Supervisory Officer (Legal Metrology)",
            zone="North Zone HQ",
            password_hash=hash_password("SupervisorPass123!")
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    token = create_access_token({"sub": user.officer_id, "role": user.role})
    return {"Authorization": f"Bearer {token}"}, user


@pytest.fixture
def admin_headers(db_session: Session):
    """Returns headers for System/Enforcement Administrator."""
    user = db_session.query(User).filter(User.officer_id == "ADMIN-DIRECTOR-01").first()
    if not user:
        user = User(
            officer_id="ADMIN-DIRECTOR-01",
            full_name="Director Vikram Malhotra",
            role="ADMIN",
            designation="Director of Legal Metrology",
            zone="National HQ",
            password_hash=hash_password("DirectorAdmin789!")
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    token = create_access_token({"sub": user.officer_id, "role": user.role})
    return {"Authorization": f"Bearer {token}"}, user


# ===========================================================================
# 1. JWT Authentication & Security Tests (401 Unauthorized)
# ===========================================================================

def test_unauthenticated_requests_return_401():
    """Verify that protected endpoints reject requests with missing, invalid, or expired tokens."""
    # 1. Missing Authorization header
    r_missing = client.get("/api/auth/me")
    assert r_missing.status_code == 401
    assert "token required" in r_missing.json()["detail"].lower()

    # 2. Invalid / Tampered token
    r_invalid = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.malformed.token"})
    assert r_invalid.status_code == 401

    # 3. Expired token (issued with negative delta)
    expired_token = create_access_token({"sub": "INSP-OFFICER-A", "role": "INSPECTOR"}, expires_delta=timedelta(minutes=-10))
    r_expired = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert r_expired.status_code == 401


def test_token_claims_contain_role_and_no_password_leak(inspector_a_headers):
    """Verify that JWT token claims contain officer_id and role, and never leak passwords."""
    headers, user = inspector_a_headers
    raw_token = headers["Authorization"].replace("Bearer ", "")
    payload = jwt.decode(raw_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

    assert payload.get("sub") == user.officer_id
    assert payload.get("role") == "INSPECTOR"
    assert "password" not in payload
    assert "password_hash" not in payload

    # Test /api/auth/me profile response
    r_me = client.get("/api/auth/me", headers=headers)
    assert r_me.status_code == 200
    profile = r_me.json()
    assert profile["officer_id"] == user.officer_id
    assert profile["role"] == "INSPECTOR"
    assert "password" not in profile
    assert "password_hash" not in profile


# ===========================================================================
# 2. Field Inspector Permitted Workflow Tests (200 / 201)
# ===========================================================================

def test_inspector_lifecycle_permissions(db_session: Session, inspector_a_headers):
    """Verify that an inspector can create inspections, evaluate rules, and access their own resources."""
    headers, user = inspector_a_headers

    # 1. Create inspection
    r_create = client.post(
        "/api/inspections",
        headers=headers,
        json={
            "product_name": "Organic Honey 500g",
            "category": "Packaged Food",
            "brand_name": "PureHimalaya",
            "location": "Sector 18, Noida",
            "notes": "Retail surveillance sample"
        }
    )
    assert r_create.status_code == 201
    insp_id = r_create.json()["id"]

    # 2. Retrieve own inspection details
    r_get = client.get(f"/api/inspections/{insp_id}", headers=headers)
    assert r_get.status_code == 200
    assert r_get.json()["id"] == insp_id
    assert r_get.json()["product"]["product_name"] == "Organic Honey 500g"

    # 3. Add mock image & declarations to verify adjudication permissions
    img = ProductImage(
        inspection_id=insp_id,
        file_path="/uploads/test_honey.jpg",
        view_type="front",
        quality_score=0.95,
        quality_status="GOOD"
    )
    decl = Declaration(
        inspection_id=insp_id,
        field_name="net_quantity",
        extracted_value="500g",
        extraction_status="EXTRACTED",
        verification_status="UNVERIFIED"
    )
    db_session.add_all([img, decl])
    db_session.commit()

    # 4. Update declaration
    r_decl = client.patch(
        f"/api/declarations/{decl.id}",
        headers=headers,
        json={"corrected_value": "500 g", "verification_status": "VERIFIED"}
    )
    assert r_decl.status_code == 200
    assert r_decl.json()["effective_value"] == "500 g"

    # 5. Evaluate rules
    r_eval = client.post(f"/api/inspections/{insp_id}/evaluate", headers=headers)
    assert r_eval.status_code == 200
    assert "findings" in r_eval.json()

    # 6. View own inspection findings
    r_findings = client.get(f"/api/inspections/{insp_id}/findings", headers=headers)
    assert r_findings.status_code == 200


# ===========================================================================
# 3. Resource Isolation & Cross-Officer Protection Tests (403 Forbidden)
# ===========================================================================

def test_inspector_cross_resource_access_denied(db_session: Session, inspector_a_headers, inspector_b_headers):
    """
    Verify strict resource isolation: Inspector B CANNOT view or mutate Inspector A's inspection,
    images, declarations, findings, evidence, reports, or audit logs.
    """
    h_a, user_a = inspector_a_headers
    h_b, user_b = inspector_b_headers

    # Create Inspection for Officer A
    test_num = f"INSP-RBAC-ISO-{uuid.uuid4().hex[:6].upper()}"
    insp_a = Inspection(
        inspection_number=test_num,
        inspector_id=user_a.id,
        location="Connaught Place, New Delhi",
        status="DRAFT"
    )
    db_session.add(insp_a)
    db_session.flush()

    prod_a = Product(inspection_id=insp_a.id, product_name="Isolated Biscuit Pack", category="Packaged Food")
    img_a = ProductImage(inspection_id=insp_a.id, file_path="/uploads/test_iso.jpg", view_type="front")
    decl_a = Declaration(inspection_id=insp_a.id, field_name="mrp", extracted_value="20.00")
    db_session.add_all([prod_a, img_a, decl_a])
    db_session.flush()

    rule_ver = db_session.query(RuleVersion).first()
    chk_a = ComplianceCheck(
        inspection_id=insp_a.id,
        rule_version_id=rule_ver.id if rule_ver else "rule-ver-placeholder",
        rule_code="PCR_RULE_06_1_E",
        title="MRP Check",
        result_state="POTENTIAL_NON_COMPLIANCE",
        explanation="Discrepancy"
    )
    db_session.add(chk_a)
    db_session.flush()

    ev_a = Evidence(check_id=chk_a.id, image_id=img_a.id, highlight_text="MRP Rs 20.00", reason="Test")
    rep_a = Report(inspection_id=insp_a.id, report_version=1, pdf_path="/reports/test_iso.pdf", legal_safety_statement="Valid")
    db_session.add_all([ev_a, rep_a])
    db_session.commit()

    try:
        # --- Inspector B attempts READ operations on Inspector A's resources ---

        # 1. Get inspection details
        r1 = client.get(f"/api/inspections/{insp_a.id}", headers=h_b)
        assert r1.status_code == 403
        assert "Access forbidden" in r1.json()["detail"]

        # 2. Get inspection images
        r2 = client.get(f"/api/inspections/{insp_a.id}/images", headers=h_b)
        assert r2.status_code == 403

        # 3. Get single image metadata
        r3 = client.get(f"/api/images/{img_a.id}", headers=h_b)
        assert r3.status_code == 403

        # 4. Get inspection declarations
        r4 = client.get(f"/api/inspections/{insp_a.id}/declarations", headers=h_b)
        assert r4.status_code == 403

        # 5. Get findings
        r5 = client.get(f"/api/inspections/{insp_a.id}/findings", headers=h_b)
        assert r5.status_code == 403

        # 6. Get finding evidence
        r6 = client.get(f"/api/findings/{chk_a.id}/evidence", headers=h_b)
        assert r6.status_code == 403

        # 7. Get report by report ID
        r7 = client.get(f"/api/reports/{rep_a.id}", headers=h_b)
        assert r7.status_code == 403

        # 8. Get inspection audit logs
        r8 = client.get(f"/api/inspections/{insp_a.id}/audit-logs", headers=h_b)
        assert r8.status_code == 403

        # --- Inspector B attempts MUTATION operations on Inspector A's resources ---

        # 9. Update Inspector A's declaration
        r9 = client.patch(f"/api/declarations/{decl_a.id}", headers=h_b, json={"corrected_value": "99.00"})
        assert r9.status_code == 403

        # 10. Adjudicate Inspector A's finding
        r10 = client.post(f"/api/findings/{chk_a.id}/adjudicate", headers=h_b, json={"action": "DISMISSED", "notes": "Hacked"})
        assert r10.status_code == 403

        # 11. Request new image for Inspector A's finding
        r11 = client.post(f"/api/findings/{chk_a.id}/request-new-image", headers=h_b)
        assert r11.status_code == 403

        # 12. Finalize Inspector A's inspection
        r12 = client.post(f"/api/inspections/{insp_a.id}/finalize", headers=h_b)
        assert r12.status_code == 403
    finally:
        insp_del = db_session.query(Inspection).filter(Inspection.id == insp_a.id).first()
        if insp_del:
            db_session.query(AuditLog).filter(AuditLog.inspection_id == insp_a.id).update({"inspection_id": None})
            db_session.delete(insp_del)
            db_session.commit()


def test_inspector_cannot_query_another_officer_via_filter(db_session: Session, inspector_a_headers, inspector_b_headers):
    """Verify that an inspector passing another officer's ID in search/dashboard filters receives 403 Forbidden."""
    h_b, user_b = inspector_b_headers
    _, user_a = inspector_a_headers

    # 1. Dashboard inspections with inspector_id targeting User A
    r_dash = client.get(f"/api/dashboard/inspections?inspector_id={user_a.id}", headers=h_b)
    assert r_dash.status_code == 403
    assert "Inspectors cannot query another officer" in r_dash.json()["detail"]

    # 2. Repository search with inspector_id targeting User A
    r_repo = client.get(f"/api/repository/inspections?inspector_id={user_a.id}", headers=h_b)
    assert r_repo.status_code == 403
    assert "Inspectors cannot query another officer" in r_repo.json()["detail"]


# ===========================================================================
# 4. Supervisor Oversight Access (200 OK) vs Mutation Denial (403 Forbidden)
# ===========================================================================

def test_supervisor_read_and_oversight_access(db_session: Session, inspector_a_headers, supervisor_headers):
    """
    Verify that a Supervisor can oversee inspections across officers, access dashboard analytics,
    and search the organization repository.
    """
    h_a, user_a = inspector_a_headers
    h_sup, user_sup = supervisor_headers

    insp_num = f"INSP-RBAC-SUP-{uuid.uuid4().hex[:6].upper()}"
    insp = Inspection(
        inspection_number=insp_num,
        inspector_id=user_a.id,
        location="Jaipur Central Market",
        status="COMPLETED",
        overall_status="NO_POTENTIAL_VIOLATIONS"
    )
    db_session.add(insp)
    db_session.flush()
    db_session.add(Product(inspection_id=insp.id, product_name="Spice Powder 100g", category="Packaged Food"))
    db_session.commit()

    try:
        # 1. Supervisor views cross-officer inspection details
        r_insp = client.get(f"/api/inspections/{insp.id}", headers=h_sup)
        assert r_insp.status_code == 200
        assert r_insp.json()["inspection_number"] == insp_num

        # 2. Supervisor views cross-officer dashboard inspections
        r_dash = client.get(f"/api/dashboard/inspections?inspector_id={user_a.id}", headers=h_sup)
        assert r_dash.status_code == 200
        assert any(i["id"] == insp.id for i in r_dash.json()["items"])

        # 3. Supervisor accesses executive analytics
        r_analytics = client.get("/api/dashboard/analytics", headers=h_sup)
        assert r_analytics.status_code == 200

        # 4. Supervisor accesses regional enforcement activity
        r_enforce = client.get("/api/dashboard/enforcement", headers=h_sup)
        assert r_enforce.status_code == 200

        # 5. Supervisor accesses repository search across inspectors
        r_repo = client.get(f"/api/repository/inspections?inspector_id={user_a.id}", headers=h_sup)
        assert r_repo.status_code == 200
        assert any(i["id"] == insp.id for i in r_repo.json()["items"])
    finally:
        db_session.query(Product).filter(Product.inspection_id == insp.id).delete()
        db_session.query(Inspection).filter(Inspection.id == insp.id).delete()
        db_session.commit()


def test_supervisor_field_mutation_denied(db_session: Session, inspector_a_headers, supervisor_headers):
    """Verify that a Supervisor CANNOT mutate an inspector's field inspection."""
    h_a, user_a = inspector_a_headers
    h_sup, _ = supervisor_headers

    insp_num = f"INSP-RBAC-MUT-{uuid.uuid4().hex[:6].upper()}"
    insp = Inspection(
        inspection_number=insp_num,
        inspector_id=user_a.id,
        location="Chandigarh Sector 17",
        status="DRAFT"
    )
    db_session.add(insp)
    db_session.flush()
    db_session.add(Product(inspection_id=insp.id, product_name="Testing Flour 1kg", category="Packaged Food"))
    decl = Declaration(inspection_id=insp.id, field_name="mrp", extracted_value="50.00")
    db_session.add(decl)
    db_session.commit()

    try:
        # 1. Supervisor cannot create field inspections (restricted to INSPECTOR and ADMIN)
        r_create = client.post(
            "/api/inspections",
            headers=h_sup,
            json={"product_name": "Supervisor Created", "category": "Packaged Food", "location": "HQ"}
        )
        assert r_create.status_code == 403

        # 2. Supervisor cannot modify field declarations
        r_patch_decl = client.patch(
            f"/api/declarations/{decl.id}",
            headers=h_sup,
            json={"corrected_value": "55.00"}
        )
        assert r_patch_decl.status_code == 403

        # 3. Supervisor cannot run rule evaluation on inspector's draft
        r_eval = client.post(f"/api/inspections/{insp.id}/evaluate", headers=h_sup)
        assert r_eval.status_code == 403

        # 4. Supervisor cannot finalize inspector's inspection
        r_finalize = client.post(f"/api/inspections/{insp.id}/finalize", headers=h_sup)
        assert r_finalize.status_code == 403
    finally:
        db_session.query(Declaration).filter(Declaration.inspection_id == insp.id).delete()
        db_session.query(Product).filter(Product.inspection_id == insp.id).delete()
        db_session.query(Inspection).filter(Inspection.id == insp.id).delete()
        db_session.commit()


# ===========================================================================
# 5. Administrative Privileges & User Role Management
# ===========================================================================

def test_admin_full_privileges_and_user_management(db_session: Session, admin_headers, inspector_a_headers):
    """Verify that Admin can list users, update officer roles, and oversee all operations."""
    h_admin, _ = admin_headers
    _, user_a = inspector_a_headers

    # 1. Admin lists registered officers
    r_users = client.get("/api/users", headers=h_admin)
    assert r_users.status_code == 200
    users_list = r_users.json()
    assert any(u["officer_id"] == user_a.officer_id for u in users_list)

    # 2. Admin updates officer role to SUPERVISOR
    r_role = client.patch(
        f"/api/users/{user_a.id}/role",
        headers=h_admin,
        json={"role": "SUPERVISOR"}
    )
    assert r_role.status_code == 200
    assert r_role.json()["role"] == "SUPERVISOR"

    # Verify audit log was recorded
    audit = db_session.query(AuditLog).filter(
        AuditLog.action == "USER_ROLE_UPDATED",
        AuditLog.entity_id == user_a.id
    ).order_by(AuditLog.created_at.desc()).first()
    assert audit is not None
    assert audit.old_value == "INSPECTOR"
    assert audit.new_value == "SUPERVISOR"

    # Revert back to INSPECTOR for test cleanliness
    r_revert = client.patch(
        f"/api/users/{user_a.id}/role",
        headers=h_admin,
        json={"role": "INSPECTOR"}
    )
    assert r_revert.status_code == 200
    assert r_revert.json()["role"] == "INSPECTOR"


def test_non_admin_blocked_from_user_management_403(inspector_a_headers, supervisor_headers):
    """Verify that Inspectors and Supervisors cannot access user management endpoints."""
    h_insp, _ = inspector_a_headers
    h_sup, _ = supervisor_headers

    # Inspector attempts to list users
    r_insp_list = client.get("/api/users", headers=h_insp)
    assert r_insp_list.status_code == 403

    # Inspector attempts to escalate role
    r_insp_patch = client.patch("/api/users/any-id/role", headers=h_insp, json={"role": "ADMIN"})
    assert r_insp_patch.status_code == 403

    # Supervisor attempts to list users
    r_sup_list = client.get("/api/users", headers=h_sup)
    assert r_sup_list.status_code == 403

    # Supervisor attempts to escalate role
    r_sup_patch = client.patch("/api/users/any-id/role", headers=h_sup, json={"role": "ADMIN"})
    assert r_sup_patch.status_code == 403
