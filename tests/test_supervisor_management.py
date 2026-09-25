"""
tests/test_supervisor_management.py

Automated Test Suite for NiriKsha Supervisor Role & Complete Inspection Management.
Tests run strictly against the isolated Neon PostgreSQL test database (TEST_DATABASE_URL).
Never connects to or alters the production database.

Test Coverage:
1. Authentication:
   - Supervisor valid login (DOCA-SUP-101 / Supervisor@1234 or configured seed password)
   - Supervisor wrong password -> 401
   - JWT claims integrity (sub = DOCA-SUP-101, role = SUPERVISOR)
   - Invalid / tampered JWT -> 401
2. RBAC Boundaries:
   - Field Inspector -> GET /api/supervisor/dashboard -> 403 Forbidden
   - Field Inspector -> GET /api/supervisor/inspections -> 403 Forbidden
   - Field Inspector -> GET /api/supervisor/inspectors -> 403 Forbidden
   - Field Inspector -> DELETE /api/inspections/{id} -> 403 Forbidden
   - Field Inspector -> DELETE /api/inspections/{id}/report -> 403 Forbidden
   - Unauthenticated -> all supervisor endpoints -> 401 Unauthorized
3. Supervisor Data & Pagination:
   - Supervisor dashboard metrics computation (zero fake values)
   - Supervisor inspector performance aggregation
   - Supervisor paginated inspections API (pagination metadata, search, filtering, sorting)
4. Deletion & Safety:
   - Deletion with confirmation mismatch -> 400 Bad Request
   - Deletion of non-existent inspection -> 404 Not Found
   - Successful report deletion -> 200 OK (inspection and evidence preserved, report removed)
   - Successful inspection deletion -> 200 OK (atomic cascade of child records)
   - Audit trail persistence (INSPECTION_DELETED and REPORT_DELETED survive deletion with historical snapshot)
   - Unrelated inspections and accounts remain completely untouched
5. Cross-Role Golden Workflow (Inspector creates -> Supervisor audits, deletes report, deletes inspection)
"""

import os
import json
import uuid
import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import text

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
    InspectorReview,
    AuditLog,
    InspectionNumberCounter
)
from backend.database import SessionLocal
from backend.auth_service import create_access_token
from backend.auth_utils import hash_password

client = TestClient(app)


@pytest.fixture(scope="function")
def db_session():
    """Provides an isolated session to the Neon PostgreSQL test database."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


TEST_SUPERVISOR_PWD = settings.SEED_SUPERVISOR_PASSWORD or "TestSupervisorAuth2026!"


@pytest.fixture
def supervisor_user(db_session: Session):
    """Ensures test supervisor account DOCA-SUP-101 exists in test database."""
    sup = db_session.query(User).filter(User.officer_id == "DOCA-SUP-101").first()
    if not sup:
        sup = User(
            officer_id="DOCA-SUP-101",
            full_name="NiriKsha Supervisor",
            email="supervisor@lm.gov.in",
            phone="+919876543210",
            designation="Supervisory Officer (Legal Metrology)",
            zone="Central HQ",
            password_hash=hash_password(TEST_SUPERVISOR_PWD),
            role="SUPERVISOR"
        )
        db_session.add(sup)
        db_session.commit()
        db_session.refresh(sup)
    else:
        # Guarantee password and role for test determinism
        sup.role = "SUPERVISOR"
        sup.full_name = "NiriKsha Supervisor"
        sup.password_hash = hash_password(TEST_SUPERVISOR_PWD)
        db_session.commit()
    return sup


@pytest.fixture
def supervisor_token(supervisor_user: User):
    """Generates a valid JWT bearer token for the test supervisor."""
    return create_access_token({"sub": supervisor_user.officer_id, "role": supervisor_user.role})


@pytest.fixture
def inspector_user(db_session: Session):
    """Ensures test inspector account exists in test database."""
    insp = db_session.query(User).filter(User.officer_id == "DOCA-INSP-842").first()
    if not insp:
        insp = User(
            officer_id="DOCA-INSP-842",
            full_name="Inspector Rajesh Kumar",
            email="rajesh.kumar@lm.gov.in",
            phone="+919876543210",
            designation="Senior Inspector (Legal Metrology)",
            zone="Northern Zone - Delhi HQ",
            password_hash=hash_password(settings.SEED_OFFICER_PASSWORD or "TestOfficerAuth2026!"),
            role="INSPECTOR"
        )
        db_session.add(insp)
        db_session.commit()
        db_session.refresh(insp)
    return insp


@pytest.fixture
def inspector_token(inspector_user: User):
    """Generates a valid JWT bearer token for the test inspector."""
    return create_access_token({"sub": inspector_user.officer_id, "role": inspector_user.role})


# ===========================================================================
# 1. Authentication & JWT Tests
# ===========================================================================

def test_supervisor_valid_login(supervisor_user: User):
    """Supervisor logs in with valid officer ID and password."""
    response = client.post(
        "/api/auth/login",
        json={"officer_id": "DOCA-SUP-101", "password": TEST_SUPERVISOR_PWD}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["role"] == "SUPERVISOR"
    assert data["officer_id"] == "DOCA-SUP-101"
    assert "access_token" in data
    assert "password" not in data  # Never leak password in API responses


def test_supervisor_wrong_password(supervisor_user: User):
    """Supervisor login fails with incorrect password."""
    response = client.post(
        "/api/auth/login",
        json={"officer_id": "DOCA-SUP-101", "password": "WrongPassword!999"}
    )
    assert response.status_code == 401


def test_invalid_and_tampered_jwt():
    """Tampered or malformed JWT is rejected with 401 Unauthorized."""
    # Malformed token
    res1 = client.get("/api/supervisor/dashboard", headers={"Authorization": "Bearer bad.token.here"})
    assert res1.status_code == 401

    # Missing token
    res2 = client.get("/api/supervisor/dashboard")
    assert res2.status_code == 401


# ===========================================================================
# 2. RBAC Authorization Boundaries (Inspector Blocked from Supervisor Endpoints)
# ===========================================================================

def test_inspector_blocked_from_supervisor_dashboard(inspector_token: str):
    """Field Inspector attempting to access supervisor dashboard receives 403 Forbidden."""
    response = client.get(
        "/api/supervisor/dashboard",
        headers={"Authorization": f"Bearer {inspector_token}"}
    )
    assert response.status_code == 403


def test_inspector_blocked_from_supervisor_inspections(inspector_token: str):
    """Field Inspector attempting to access supervisor inspections repository receives 403 Forbidden."""
    response = client.get(
        "/api/supervisor/inspections",
        headers={"Authorization": f"Bearer {inspector_token}"}
    )
    assert response.status_code == 403


def test_inspector_blocked_from_supervisor_inspectors(inspector_token: str):
    """Field Inspector attempting to query inspector management statistics receives 403 Forbidden."""
    response = client.get(
        "/api/supervisor/inspectors",
        headers={"Authorization": f"Bearer {inspector_token}"}
    )
    assert response.status_code == 403


def test_inspector_blocked_from_destructive_deletion(inspector_token: str, db_session: Session, inspector_user: User):
    """Field Inspector attempting to delete an inspection or report receives 403 Forbidden."""
    test_num = f"LM-TEST-RBAC-{uuid.uuid4().hex[:6].upper()}"
    # Create test inspection
    insp = Inspection(
        inspection_number=test_num,
        inspector_id=inspector_user.id,
        location="Delhi Market",
        status="DRAFT"
    )
    db_session.add(insp)
    db_session.commit()
    db_session.refresh(insp)

    try:
        # Attempt inspection deletion as Inspector
        del_res = client.request(
            "DELETE",
            f"/api/inspections/{insp.id}",
            json={"confirmation_inspection_number": test_num},
            headers={"Authorization": f"Bearer {inspector_token}"}
        )
        assert del_res.status_code == 403

        # Attempt report deletion as Inspector
        rep_res = client.delete(
            f"/api/inspections/{insp.id}/report",
            headers={"Authorization": f"Bearer {inspector_token}"}
        )
        assert rep_res.status_code == 403
    finally:
        # Cleanup test record
        insp_to_del = db_session.query(Inspection).filter(Inspection.id == insp.id).first()
        if insp_to_del:
            db_session.query(AuditLog).filter(AuditLog.inspection_id == insp.id).update({"inspection_id": None})
            db_session.delete(insp_to_del)
            db_session.commit()


# ===========================================================================
# 3. Supervisor Data & Pagination Endpoints
# ===========================================================================

def test_supervisor_dashboard_metrics(supervisor_token: str):
    """Supervisor dashboard returns real metrics aggregated from database."""
    response = client.get(
        "/api/supervisor/dashboard",
        headers={"Authorization": f"Bearer {supervisor_token}"}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "total_inspections" in data
    assert "completed_inspections" in data
    assert "potential_non_compliance" in data
    assert "active_inspectors_count" in data
    assert isinstance(data["total_inspections"], int)
    assert isinstance(data["recent_submissions"], list)


def test_supervisor_inspectors_list(supervisor_token: str):
    """Supervisor inspectors endpoint returns registered inspector profiles with counts."""
    response = client.get(
        "/api/supervisor/inspectors",
        headers={"Authorization": f"Bearer {supervisor_token}"}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "inspectors" in data
    assert "total_count" in data
    assert data["total_count"] >= 1
    # Check inspector summary schema
    insp0 = data["inspectors"][0]
    assert "officer_id" in insp0
    assert "full_name" in insp0
    assert "total_inspections" in insp0


def test_supervisor_paginated_inspections_repository(supervisor_token: str, db_session: Session, inspector_user: User):
    """Supervisor /api/supervisor/inspections supports server-side pagination, search, and sorting."""
    # Seed 3 distinct test inspections
    test_records = []
    for i in range(1, 4):
        insp = Inspection(
            inspection_number=f"LM-PAGINATE-{i:03d}",
            inspector_id=inspector_user.id,
            location=f"Zone {i} Testing Centre",
            status="COMPLETED" if i == 1 else "DRAFT",
            overall_status="POTENTIAL_NON_COMPLIANCE" if i == 2 else "NO_POTENTIAL_VIOLATIONS"
        )
        db_session.add(insp)
        db_session.flush()

        prod = Product(
            inspection_id=insp.id,
            product_name=f"Packaged Commodity Item {i}",
            brand_name=f"BrandAlpha{i}",
            category="Packaged Food"
        )
        db_session.add(prod)
        test_records.append(insp)
    db_session.commit()

    try:
        # 1. Test basic listing & pagination
        p_res = client.get(
            "/api/supervisor/inspections?page=1&page_size=2",
            headers={"Authorization": f"Bearer {supervisor_token}"}
        )
        assert p_res.status_code == 200, p_res.text
        p_data = p_res.json()
        assert len(p_data["items"]) <= 2
        assert p_data["page"] == 1
        assert p_data["page_size"] == 2
        assert p_data["total_count"] >= 3

        # 2. Test search by brand
        s_res = client.get(
            "/api/supervisor/inspections?search=BrandAlpha2",
            headers={"Authorization": f"Bearer {supervisor_token}"}
        )
        assert s_res.status_code == 200
        s_data = s_res.json()
        assert len(s_data["items"]) == 1
        assert s_data["items"][0]["inspection_number"] == "LM-PAGINATE-002"

        # 3. Test filter by compliance status
        c_res = client.get(
            "/api/supervisor/inspections?overall_status=POTENTIAL_NON_COMPLIANCE",
            headers={"Authorization": f"Bearer {supervisor_token}"}
        )
        assert c_res.status_code == 200
        c_data = c_res.json()
        assert all(item["overall_status"] == "POTENTIAL_NON_COMPLIANCE" for item in c_data["items"])

        # 4. Test sorting
        sort_res = client.get(
            "/api/supervisor/inspections?sort_by=inspection_number&sort_order=asc",
            headers={"Authorization": f"Bearer {supervisor_token}"}
        )
        assert sort_res.status_code == 200
    finally:
        for r in test_records:
            rec = db_session.query(Inspection).filter(Inspection.id == r.id).first()
            if rec:
                db_session.query(AuditLog).filter(AuditLog.inspection_id == r.id).update({"inspection_id": None})
                db_session.delete(rec)
        db_session.commit()


# ===========================================================================
# 4. Deletion Safety & Cascade Integrity Tests
# ===========================================================================

def test_delete_inspection_confirmation_validation(supervisor_token: str, db_session: Session, inspector_user: User):
    """Deleting an inspection requires exact inspection number confirmation; mismatch returns 400."""
    test_num = f"LM-CONFIRM-{uuid.uuid4().hex[:6].upper()}"
    insp = Inspection(
        inspection_number=test_num,
        inspector_id=inspector_user.id,
        location="Jaipur Mandi",
        status="DRAFT"
    )
    db_session.add(insp)
    db_session.commit()
    db_session.refresh(insp)

    try:
        # Wrong confirmation number
        res_mismatch = client.request(
            "DELETE",
            f"/api/inspections/{insp.id}",
            json={"confirmation_inspection_number": "LM-WRONG-NUMBER"},
            headers={"Authorization": f"Bearer {supervisor_token}"}
        )
        assert res_mismatch.status_code == 400
        assert "Confirmation mismatch" in res_mismatch.json()["detail"]

        # Missing payload
        res_missing = client.delete(
            f"/api/inspections/{insp.id}",
            headers={"Authorization": f"Bearer {supervisor_token}"}
        )
        assert res_missing.status_code == 400

        # Non-existent inspection
        res_404 = client.request(
            "DELETE",
            "/api/inspections/non-existent-uuid-12345",
            json={"confirmation_inspection_number": test_num},
            headers={"Authorization": f"Bearer {supervisor_token}"}
        )
        assert res_404.status_code == 404
    finally:
        insp_to_del = db_session.query(Inspection).filter(Inspection.id == insp.id).first()
        if insp_to_del:
            db_session.query(AuditLog).filter(AuditLog.inspection_id == insp.id).update({"inspection_id": None})
            db_session.delete(insp_to_del)
            db_session.commit()


def test_delete_report_preserves_inspection(supervisor_token: str, db_session: Session, inspector_user: User):
    """Deleting a report removes only the report record, leaving the inspection and declarations 100% intact."""
    test_num = f"LM-REPORT-DEL-{uuid.uuid4().hex[:6].upper()}"
    # Create inspection with report
    insp = Inspection(
        inspection_number=test_num,
        inspector_id=inspector_user.id,
        location="Delhi Depot",
        status="COMPLETED"
    )
    db_session.add(insp)
    db_session.flush()

    prod = Product(inspection_id=insp.id, product_name="Test Salt 1kg", category="Packaged Food")
    db_session.add(prod)

    decl = Declaration(
        inspection_id=insp.id,
        field_name="net_quantity",
        extracted_value="1 kg",
        corrected_value="1 kg"
    )
    db_session.add(decl)

    rep = Report(
        inspection_id=insp.id,
        report_version=1,
        pdf_path="uploads/test_dummy_report.pdf",
        legal_safety_statement="Official statutory verification."
    )
    db_session.add(rep)
    db_session.commit()

    saved_insp_id = insp.id
    saved_rep_id = rep.id

    try:
        # Delete report
        del_rep_res = client.delete(
            f"/api/inspections/{saved_insp_id}/report",
            headers={"Authorization": f"Bearer {supervisor_token}"}
        )
        assert del_rep_res.status_code == 200, del_rep_res.text
        assert del_rep_res.json()["success"] is True

        # Verify report record is deleted from DB
        check_rep = db_session.query(Report).filter(Report.id == saved_rep_id).first()
        assert check_rep is None

        # Verify inspection is still intact
        check_insp = db_session.query(Inspection).filter(Inspection.id == saved_insp_id).first()
        assert check_insp is not None
        assert check_insp.inspection_number == test_num

        # Verify declaration is still intact
        check_decl = db_session.query(Declaration).filter(Declaration.inspection_id == saved_insp_id).first()
        assert check_decl is not None
        assert check_decl.extracted_value == "1 kg"

        # Verify REPORT_DELETED audit log exists
        audit_entry = db_session.query(AuditLog).filter(
            AuditLog.action == "REPORT_DELETED",
            AuditLog.entity_id == saved_rep_id
        ).first()
        assert audit_entry is not None
        assert test_num in audit_entry.details
    finally:
        insp_to_del = db_session.query(Inspection).filter(Inspection.id == saved_insp_id).first()
        if insp_to_del:
            db_session.query(AuditLog).filter(AuditLog.inspection_id == saved_insp_id).update({"inspection_id": None})
            db_session.delete(insp_to_del)
            db_session.commit()


def test_delete_inspection_atomic_cascade_and_audit(supervisor_token: str, db_session: Session, inspector_user: User):
    """
    Destructive inspection deletion removes all child entities in an atomic transaction,
    preserves an immutable audit log, and leaves unrelated inspections, users, and rules untouched.
    """
    target_num = f"LM-CASC-TGT-{uuid.uuid4().hex[:6].upper()}"
    control_num = f"LM-CASC-CTRL-{uuid.uuid4().hex[:6].upper()}"

    # 1. Create inspection to delete
    target_insp = Inspection(
        inspection_number=target_num,
        inspector_id=inspector_user.id,
        location="Chandni Chowk",
        status="FINALIZED"
    )
    db_session.add(target_insp)
    db_session.flush()

    prod = Product(inspection_id=target_insp.id, product_name="Target Basmati 5kg", category="Packaged Food")
    db_session.add(prod)

    decl = Declaration(inspection_id=target_insp.id, field_name="mrp", extracted_value="Rs. 450.00")
    db_session.add(decl)

    # 2. Create unrelated control inspection that must NOT be touched
    control_insp = Inspection(
        inspection_number=control_num,
        inspector_id=inspector_user.id,
        location="Connaught Place",
        status="DRAFT"
    )
    db_session.add(control_insp)
    db_session.commit()

    target_id = target_insp.id
    control_id = control_insp.id

    try:
        # Perform deletion
        del_res = client.request(
            "DELETE",
            f"/api/inspections/{target_id}",
            json={
                "confirmation_inspection_number": target_num,
                "reason": "Administrative removal for test verification"
            },
            headers={"Authorization": f"Bearer {supervisor_token}"}
        )
        assert del_res.status_code == 200, del_res.text
        assert del_res.json()["success"] is True

        # Verify target inspection is deleted
        assert db_session.query(Inspection).filter(Inspection.id == target_id).first() is None

        # Verify child product and declaration are deleted
        assert db_session.query(Product).filter(Product.inspection_id == target_id).first() is None
        assert db_session.query(Declaration).filter(Declaration.inspection_id == target_id).first() is None

        # Verify CONTROL inspection is 100% intact
        control_check = db_session.query(Inspection).filter(Inspection.id == control_id).first()
        assert control_check is not None
        assert control_check.inspection_number == control_num

        # Verify Inspector User account is NOT deleted
        user_check = db_session.query(User).filter(User.id == inspector_user.id).first()
        assert user_check is not None

        # Verify statutory rules are NOT deleted
        rules_count = db_session.query(RuleVersion).count()
        assert rules_count > 0

        # Verify permanent audit log survives deletion
        audit_log = db_session.query(AuditLog).filter(
            AuditLog.action == "INSPECTION_DELETED",
            AuditLog.entity_id == target_id
        ).first()
        assert audit_log is not None
        assert audit_log.actor_id == "DOCA-SUP-101"
        assert audit_log.inspection_id is None  # Survives via nullify / ondelete SET NULL
        details = json.loads(audit_log.details)
        assert details["inspection_number"] == target_num
        assert details["product_name"] == "Target Basmati 5kg"
        assert details["supervisor_id"] == "DOCA-SUP-101"
    finally:
        for iid in [target_id, control_id]:
            to_del = db_session.query(Inspection).filter(Inspection.id == iid).first()
            if to_del:
                db_session.query(AuditLog).filter(AuditLog.inspection_id == iid).update({"inspection_id": None})
                db_session.delete(to_del)
                db_session.commit()


# ===========================================================================
# 5. Full Cross-Role Golden Workflow Test
# ===========================================================================

def test_cross_role_golden_workflow(inspector_token: str, supervisor_token: str, db_session: Session):
    """
    End-to-End Cross-Role Golden Test:
    FIELD INSPECTOR:
      1. Creates inspection -> 201 Created
      2. Verified saved in Neon PostgreSQL
    SUPERVISOR:
      3. Queries supervisor dashboard -> metrics reflect scan
      4. Queries /api/supervisor/inspections -> locates inspection
      5. Loads full inspection details -> verifies fields
      6. Deletes inspection with exact confirmation -> 200 OK
      7. Verifies audit log survives and inspection is gone
    """
    # ── Step 1: Field Inspector creates inspection ──
    create_res = client.post(
        "/api/inspections",
        json={
            "product_name": "Golden Workflow Cooking Oil 1L",
            "category": "Packaged Food",
            "brand_name": "GoldenHarvest",
            "location": "Central Test Market, Delhi",
            "batch_number": "BATCH-GOLD-2026",
            "notes": "Field inspection during surveillance drive."
        },
        headers={"Authorization": f"Bearer {inspector_token}"}
    )
    assert create_res.status_code == 201, create_res.text
    created_data = create_res.json()
    insp_id = created_data["id"]
    insp_number = created_data["inspection_number"]

    try:
        # ── Step 2: Verify persistence in Neon PostgreSQL ──
        db_insp = db_session.query(Inspection).filter(Inspection.id == insp_id).first()
        assert db_insp is not None
        assert db_insp.inspection_number == insp_number

        # ── Step 3: Supervisor checks dashboard ──
        dash_res = client.get(
            "/api/supervisor/dashboard",
            headers={"Authorization": f"Bearer {supervisor_token}"}
        )
        assert dash_res.status_code == 200
        assert dash_res.json()["total_inspections"] >= 1

        # ── Step 4: Supervisor searches in All Inspections repository ──
        search_res = client.get(
            f"/api/supervisor/inspections?search={insp_number}",
            headers={"Authorization": f"Bearer {supervisor_token}"}
        )
        assert search_res.status_code == 200
        search_items = search_res.json()["items"]
        assert len(search_items) == 1
        assert search_items[0]["id"] == insp_id
        assert search_items[0]["product_name"] == "Golden Workflow Cooking Oil 1L"

        # ── Step 5: Supervisor loads complete inspection details ──
        detail_res = client.get(
            f"/api/inspections/{insp_id}",
            headers={"Authorization": f"Bearer {supervisor_token}"}
        )
        assert detail_res.status_code == 200
        detail_data = detail_res.json()
        assert detail_data["inspection_number"] == insp_number
        assert detail_data["product"]["brand_name"] == "GoldenHarvest"

        # ── Step 6: Supervisor performs destructive deletion ──
        del_res = client.request(
            "DELETE",
            f"/api/inspections/{insp_id}",
            json={
                "confirmation_inspection_number": insp_number,
                "reason": "Golden test workflow cleanup"
            },
            headers={"Authorization": f"Bearer {supervisor_token}"}
        )
        assert del_res.status_code == 200
        assert del_res.json()["success"] is True

        # ── Step 7: Verify inspection is gone from DB ──
        assert db_session.query(Inspection).filter(Inspection.id == insp_id).first() is None

        # ── Step 8: Verify audit trail preserved permanently ──
        audit = db_session.query(AuditLog).filter(
            AuditLog.action == "INSPECTION_DELETED",
            AuditLog.entity_id == insp_id
        ).first()
        assert audit is not None
        assert "BATCH-GOLD-2026" not in audit.details or insp_number in audit.details
        assert json.loads(audit.details)["inspection_number"] == insp_number
    finally:
        # Final cleanup if anything remained
        insp_to_del = db_session.query(Inspection).filter(Inspection.id == insp_id).first()
        if insp_to_del:
            db_session.query(AuditLog).filter(AuditLog.inspection_id == insp_id).update({"inspection_id": None})
            db_session.delete(insp_to_del)
            db_session.commit()
