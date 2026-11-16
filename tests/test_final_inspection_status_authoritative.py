"""
tests/test_final_inspection_status_authoritative.py

Comprehensive tests for authoritative server-side final inspection status:
1. Client submits false clean-compliance status when unresolved findings exist -> 409 Conflict.
2. Client submits clean-compliance status when confirmed violation exists -> 400 Bad Request.
3. Client submits clean-compliance status when insufficient evidence or unverified declarations exist -> 400 Bad Request.
4. Correctly adjudicated inspection with confirmed violation finalizes authoritatively as POTENTIAL_NON_COMPLIANCE -> 200 OK.
5. Correctly adjudicated compliant inspection finalizes as NO_POTENTIAL_VIOLATIONS -> 200 OK.
6. Concurrent finalization attempts do not produce conflicting states or duplicate logs -> Idempotent & thread-safe.
7. Unrecognized client-supplied final status is rejected -> 400 Bad Request.
"""

import concurrent.futures
import pytest
import uuid
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import settings
from backend.models import (
    User,
    Inspection,
    Product,
    ComplianceCheck,
    RuleVersion,
    Declaration,
    AuditLog,
)
from backend.database import SessionLocal
from backend.auth_service import create_access_token
from backend.auth_utils import hash_password

client = TestClient(app)


@pytest.fixture(scope="function")
def db_session():
    """Provides an isolated database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def auth_inspector(db_session: Session):
    """Provides an authenticated test inspector."""
    officer_id = "INSP-AUTH-STAT-01"
    user = db_session.query(User).filter(User.officer_id == officer_id).first()
    if not user:
        user = User(
            officer_id=officer_id,
            full_name="Status Integrity Officer",
            role="INSPECTOR",
            designation="Enforcement Officer",
            zone="North",
            password_hash=hash_password("Pass123!")
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

    token = create_access_token({"sub": user.officer_id, "role": user.role})
    return {"Authorization": f"Bearer {token}"}, user


@pytest.fixture
def rule_version(db_session: Session):
    """Ensures a test RuleVersion exists."""
    rv = db_session.query(RuleVersion).filter(RuleVersion.rule_code == "PCR_RULE_06_MRP").first()
    if not rv:
        rv = RuleVersion(
            rule_code="PCR_RULE_06_MRP",
            version_number=1,
            title="Maximum Retail Price Declaration",
            category="CATEGORY_A_LEGAL",
            statutory_reference="Rule 6(1)(e)",
            rule_logic_description="MRP must be declared with taxes included.",
            severity="CRITICAL"
        )
        db_session.add(rv)
        db_session.commit()
        db_session.refresh(rv)
    return rv


def _create_test_inspection(db_session: Session, user: User, prefix: str = "AUTH-TEST") -> Inspection:
    """Helper to create a fresh test inspection."""
    insp = Inspection(
        id=str(uuid.uuid4()),
        inspection_number=f"INSP-{prefix}-{uuid.uuid4().hex[:6].upper()}",
        inspector_id=user.id,
        status="DRAFT",
        overall_status=None,
        location="Validation Lab",
        created_at=datetime.utcnow()
    )
    product = Product(
        id=str(uuid.uuid4()),
        inspection_id=insp.id,
        product_name=f"Test Commodity {prefix}",
        category="Packaged Food",
        brand_name="TestBrand"
    )
    db_session.add(insp)
    db_session.add(product)
    db_session.commit()
    db_session.refresh(insp)
    return insp


# ===========================================================================
# 1. Unresolved findings block clean-compliance submissions (409 Conflict)
# ===========================================================================

def test_unresolved_findings_prevent_false_clean_finalization(db_session: Session, auth_inspector, rule_version):
    """Client submitting clean-compliance status when unresolved findings exist must fail with 409."""
    headers, user = auth_inspector
    insp = _create_test_inspection(db_session, user, prefix="UNRES")

    # Add finding that requires adjudication (POTENTIAL_NON_COMPLIANCE, PENDING)
    check = ComplianceCheck(
        id=str(uuid.uuid4()),
        inspection_id=insp.id,
        rule_version_id=rule_version.id,
        rule_code=rule_version.rule_code,
        title=rule_version.title,
        severity="CRITICAL",
        result_state="POTENTIAL_NON_COMPLIANCE",
        explanation="MRP declaration missing tax qualifier.",
        adjudication_status="PENDING"
    )
    db_session.add(check)
    db_session.commit()

    # Attempt finalization as NO_POTENTIAL_VIOLATIONS
    resp = client.post(
        f"/api/inspections/{insp.id}/finalize",
        headers=headers,
        json={"final_status": "NO_POTENTIAL_VIOLATIONS", "officer_notes": "Attempting bypass."}
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["detail"]["error"] == "UNRESOLVED_FINDINGS"

    # Verify inspection status remained DRAFT in database
    db_session.refresh(insp)
    assert insp.status == "DRAFT"
    assert insp.overall_status is None


# ===========================================================================
# 2. Confirmed violation cannot be overridden by clean status (400 Bad Request)
# ===========================================================================

def test_confirmed_violation_rejects_clean_status(db_session: Session, auth_inspector, rule_version):
    """Client submitting clean-compliance status when a violation is confirmed must be rejected with 400."""
    headers, user = auth_inspector
    insp = _create_test_inspection(db_session, user, prefix="CONF-VIOL")

    # Add resolved finding with CONFIRMED violation
    check = ComplianceCheck(
        id=str(uuid.uuid4()),
        inspection_id=insp.id,
        rule_version_id=rule_version.id,
        rule_code=rule_version.rule_code,
        title=rule_version.title,
        severity="CRITICAL",
        result_state="POTENTIAL_NON_COMPLIANCE",
        explanation="Confirmed missing MRP tax disclaimer.",
        adjudication_status="CONFIRMED",
        adjudication_notes="Inspecting officer confirmed statutory breach."
    )
    db_session.add(check)
    db_session.commit()

    # Attempt to force clean compliance
    resp = client.post(
        f"/api/inspections/{insp.id}/finalize",
        headers=headers,
        json={"final_status": "NO_POTENTIAL_VIOLATIONS", "officer_notes": "Falsifying clean compliance."}
    )
    assert resp.status_code == 400
    assert "confirmed statutory violations" in resp.json()["detail"].lower()

    # Attempt to send COMPLIANT alias
    resp_alias = client.post(
        f"/api/inspections/{insp.id}/finalize",
        headers=headers,
        json={"final_status": "COMPLIANT"}
    )
    assert resp_alias.status_code == 400
    assert "confirmed statutory violations" in resp_alias.json()["detail"].lower()

    # Verify inspection was not finalized
    db_session.refresh(insp)
    assert insp.status == "DRAFT"
    assert insp.overall_status is None


# ===========================================================================
# 3. Insufficient evidence / unverified declarations reject clean status (400)
# ===========================================================================

def test_unverified_declaration_rejects_clean_status(db_session: Session, auth_inspector, rule_version):
    """Inspection with unverified / conflicting declarations cannot be finalized as clean compliant."""
    headers, user = auth_inspector
    insp = _create_test_inspection(db_session, user, prefix="UNVER-DECL")

    # All checks passed
    check = ComplianceCheck(
        id=str(uuid.uuid4()),
        inspection_id=insp.id,
        rule_version_id=rule_version.id,
        rule_code=rule_version.rule_code,
        title=rule_version.title,
        severity="INFO",
        result_state="PASS",
        explanation="Pass check.",
        adjudication_status="NOT_APPLICABLE"
    )
    # But a mandatory declaration is CONFLICTING and unverified
    decl = Declaration(
        id=str(uuid.uuid4()),
        inspection_id=insp.id,
        field_name="net_quantity",
        extracted_value="500g / 450g",
        extraction_status="CONFLICTING",
        verification_status="UNVERIFIED",
        is_applicable=True
    )
    db_session.add(check)
    db_session.add(decl)
    db_session.commit()

    resp = client.post(
        f"/api/inspections/{insp.id}/finalize",
        headers=headers,
        json={"final_status": "NO_POTENTIAL_VIOLATIONS"}
    )
    assert resp.status_code == 400
    assert "unresolved conflicts" in resp.json()["detail"].lower()

    # If finalized without overriding clean status, it defaults to NEEDS_MANUAL_VERIFICATION
    valid_resp = client.post(
        f"/api/inspections/{insp.id}/finalize",
        headers=headers,
        json={"officer_notes": "Needs manual physical verification."}
    )
    assert valid_resp.status_code == 200
    assert valid_resp.json()["overall_status"] == "NEEDS_MANUAL_VERIFICATION"


# ===========================================================================
# 4. Correctly adjudicated inspection with violation finalizes authoritatively
# ===========================================================================

def test_confirmed_violation_finalizes_authoritatively(db_session: Session, auth_inspector, rule_version):
    """Correctly adjudicated inspection with confirmed violation finalizes as POTENTIAL_NON_COMPLIANCE."""
    headers, user = auth_inspector
    insp = _create_test_inspection(db_session, user, prefix="VALID-VIOL")

    check = ComplianceCheck(
        id=str(uuid.uuid4()),
        inspection_id=insp.id,
        rule_version_id=rule_version.id,
        rule_code=rule_version.rule_code,
        title=rule_version.title,
        severity="CRITICAL",
        result_state="POTENTIAL_NON_COMPLIANCE",
        explanation="Confirmed violation.",
        adjudication_status="CONFIRMED"
    )
    db_session.add(check)
    db_session.commit()

    # Finalize with matching status or omitted status
    resp = client.post(
        f"/api/inspections/{insp.id}/finalize",
        headers=headers,
        json={"officer_notes": "Confirmed non-compliance recorded."}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "COMPLETED"
    assert data["overall_status"] == "POTENTIAL_NON_COMPLIANCE"

    # Check audit log entry
    audit = db_session.query(AuditLog).filter(
        AuditLog.inspection_id == insp.id,
        AuditLog.action == "INSPECTION_FINALIZED"
    ).first()
    assert audit is not None
    assert "POTENTIAL_NON_COMPLIANCE" in audit.details


# ===========================================================================
# 5. Correctly adjudicated compliant inspection finalizes as NO_POTENTIAL_VIOLATIONS
# ===========================================================================

def test_clean_compliant_inspection_finalizes(db_session: Session, auth_inspector, rule_version):
    """Inspection where all checks are PASS or DISMISSED finalizes as NO_POTENTIAL_VIOLATIONS."""
    headers, user = auth_inspector
    insp = _create_test_inspection(db_session, user, prefix="VALID-CLEAN")

    # One PASS check and one DISMISSED finding
    check_pass = ComplianceCheck(
        id=str(uuid.uuid4()),
        inspection_id=insp.id,
        rule_version_id=rule_version.id,
        rule_code=rule_version.rule_code,
        title=rule_version.title,
        severity="MINOR",
        result_state="PASS",
        explanation="Compliant."
    )
    check_dismissed = ComplianceCheck(
        id=str(uuid.uuid4()),
        inspection_id=insp.id,
        rule_version_id=rule_version.id,
        rule_code="PCR_RULE_06_MFG",
        title="Manufacturer Details",
        severity="MAJOR",
        result_state="POTENTIAL_NON_COMPLIANCE",
        explanation="False OCR alarm dismissed by inspector.",
        adjudication_status="DISMISSED",
        adjudication_notes="Customer care label verified on side panel."
    )
    db_session.add(check_pass)
    db_session.add(check_dismissed)
    db_session.commit()

    resp = client.post(
        f"/api/inspections/{insp.id}/finalize",
        headers=headers,
        json={"final_status": "NO_POTENTIAL_VIOLATIONS", "officer_notes": "All labels verified compliant."}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "COMPLETED"
    assert data["overall_status"] == "NO_POTENTIAL_VIOLATIONS"


# ===========================================================================
# 6. Concurrent finalization attempts are transactional & idempotent
# ===========================================================================

def test_concurrent_finalization_is_idempotent(db_session: Session, auth_inspector, rule_version):
    """Concurrent finalization attempts do not produce conflicting states or duplicate audit logs."""
    headers, user = auth_inspector
    insp = _create_test_inspection(db_session, user, prefix="CONCURR")
    insp_id = str(insp.id)

    check = ComplianceCheck(
        id=str(uuid.uuid4()),
        inspection_id=insp_id,
        rule_version_id=rule_version.id,
        rule_code=rule_version.rule_code,
        title=rule_version.title,
        severity="MINOR",
        result_state="PASS",
        explanation="Compliant."
    )
    db_session.add(check)
    db_session.commit()

    def _call_finalize():
        thread_client = TestClient(app)
        return thread_client.post(
            f"/api/inspections/{insp_id}/finalize",
            headers=headers,
            json={"officer_notes": "Concurrent thread test."}
        )

    # Launch 4 concurrent finalization requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(_call_finalize) for _ in range(4)]
        results = [f.result() for f in futures]

    # Every concurrent request must receive 200 OK
    for r in results:
        assert r.status_code == 200
        assert r.json()["status"] == "COMPLETED"
        assert r.json()["overall_status"] == "NO_POTENTIAL_VIOLATIONS"

    # Verify audit log recorded exactly one INSPECTION_FINALIZED event
    audit_count = db_session.query(AuditLog).filter(
        AuditLog.inspection_id == insp_id,
        AuditLog.action == "INSPECTION_FINALIZED"
    ).count()
    assert audit_count == 1, f"Expected 1 audit log entry, found {audit_count}"


# ===========================================================================
# 7. Unrecognized client final status is rejected
# ===========================================================================

def test_invalid_final_status_rejected(db_session: Session, auth_inspector, rule_version):
    """Client sending unrecognized status string must be rejected with 400."""
    headers, user = auth_inspector
    insp = _create_test_inspection(db_session, user, prefix="INVALID-STAT")

    resp = client.post(
        f"/api/inspections/{insp.id}/finalize",
        headers=headers,
        json={"final_status": "MADE_UP_STATUS_XYZ"}
    )
    assert resp.status_code == 400
    assert "invalid final_status" in resp.json()["detail"].lower()
