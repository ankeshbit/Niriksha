"""
tests/test_async_finalize_report.py

Tests async report generation during inspection finalization:
1. finalize_inspection commits COMPLETED status and returns immediately with report_status="PENDING".
2. Unresolved findings 409 Conflict gate remains intact.
3. GET /api/inspections/{id}/report returns HTTP 202 while generating and HTTP 200 once complete.
4. Fast-path idempotency returns report_status="COMPLETED" with the serialized report.
"""

import time
import uuid
import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.models import (
    User,
    Inspection,
    Product,
    ComplianceCheck,
    RuleVersion,
    Report,
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
def auth_inspector(db_session: Session):
    """Provides an authenticated inspector."""
    officer_id = "INSP-ASYNC-FIN-01"
    user = db_session.query(User).filter(User.officer_id == officer_id).first()
    if not user:
        user = User(
            officer_id=officer_id,
            full_name="Async Finalize Officer",
            role="INSPECTOR",
            designation="Field Officer",
            zone="North",
            password_hash=hash_password("Pass123!")
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

    token = create_access_token({"sub": user.officer_id, "role": user.role})
    return {"Authorization": f"Bearer {token}"}, user


@pytest.fixture(autouse=True)
def cleanup_test_inspections(db_session: Session):
    """Cleans up test inspections."""
    def _clean():
        try:
            insps = db_session.query(Inspection).filter(
                Inspection.inspection_number.like("INSP-ASYNC-%")
            ).all()
            for i in insps:
                db_session.delete(i)
            db_session.commit()
        except Exception:
            db_session.rollback()

    _clean()
    yield
    _clean()


def _create_inspection_with_resolved_findings(db_session: Session, user: User):
    """Creates a test inspection with all findings resolved."""
    insp = Inspection(
        id=str(uuid.uuid4()),
        inspection_number=f"INSP-ASYNC-{uuid.uuid4().hex[:6].upper()}",
        inspector_id=user.id,
        location="Connaught Place, New Delhi",
        status="EVALUATED",
        overall_status="NO_POTENTIAL_VIOLATIONS"
    )
    db_session.add(insp)
    db_session.flush()

    prod = Product(
        inspection_id=insp.id,
        product_name="Mustard Oil 1L",
        brand_name="Fortune",
        category="Packaged Food",
        batch_number="BATCH-ASYNC-01"
    )
    db_session.add(prod)

    rv = db_session.query(RuleVersion).first()
    rv_id = rv.id if rv else str(uuid.uuid4())

    chk = ComplianceCheck(
        id=str(uuid.uuid4()),
        inspection_id=insp.id,
        rule_version_id=rv_id,
        rule_code="PCR-R06-MRP",
        title="MRP Declaration Rule",
        severity="MANDATORY",
        result_state="PASS",
        explanation="MRP compliant.",
        adjudication_status="AUTO_PASSED"
    )
    db_session.add(chk)
    db_session.commit()
    db_session.refresh(insp)
    return insp


def test_finalize_unresolved_findings_gate(db_session: Session, auth_inspector):
    """finalize_inspection rejects finalization with 409 Conflict if findings are pending adjudication."""
    headers, user = auth_inspector
    insp = Inspection(
        id=str(uuid.uuid4()),
        inspection_number=f"INSP-ASYNC-{uuid.uuid4().hex[:6].upper()}",
        inspector_id=user.id,
        location="Connaught Place, New Delhi",
        status="EVALUATED",
        overall_status="POTENTIAL_NON_COMPLIANCE"
    )
    db_session.add(insp)
    db_session.flush()

    prod = Product(
        inspection_id=insp.id,
        product_name="Sunflower Oil",
        category="Packaged Food"
    )
    db_session.add(prod)

    rv = db_session.query(RuleVersion).first()
    rv_id = rv.id if rv else str(uuid.uuid4())

    chk = ComplianceCheck(
        id=str(uuid.uuid4()),
        inspection_id=insp.id,
        rule_version_id=rv_id,
        rule_code="PCR-R06-MRP",
        title="MRP Declaration Missing",
        severity="MANDATORY",
        result_state="POTENTIAL_NON_COMPLIANCE",
        explanation="MRP missing.",
        adjudication_status="PENDING"  # Unresolved finding
    )
    db_session.add(chk)
    db_session.commit()

    resp = client.post(f"/api/inspections/{insp.id}/finalize", headers=headers)
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "UNRESOLVED_FINDINGS"


def test_finalize_returns_pending_and_report_polls_202_then_200(db_session: Session, auth_inspector):
    """finalize_inspection returns status=COMPLETED and report_status=PENDING; GET /report polls 202/200."""
    headers, user = auth_inspector
    insp = _create_inspection_with_resolved_findings(db_session, user)

    # 1. Finalize inspection
    resp = client.post(
        f"/api/inspections/{insp.id}/finalize",
        headers=headers,
        json={"officer_notes": "Inspection completed successfully."}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["status"] == "COMPLETED"
    assert data["report_status"] in ("PENDING", "COMPLETED")

    # 2. Poll report endpoint (in TestClient background tasks run during/at response completion)
    report_ready = False
    for _ in range(25):
        poll_resp = client.get(f"/api/inspections/{insp.id}/report", headers=headers)
        if poll_resp.status_code == 200:
            report_data = poll_resp.json()
            assert report_data["id"] is not None
            assert report_data["inspection_id"] == insp.id
            report_ready = True
            break
        elif poll_resp.status_code == 202:
            assert poll_resp.json()["status"] == "PENDING"
            time.sleep(0.2)
        else:
            pytest.fail(f"Unexpected status polling report: {poll_resp.status_code}")

    assert report_ready, "Report generation did not finish in time"

    # 3. Fast-path idempotency: calling finalize again returns existing completed report
    retry_resp = client.post(f"/api/inspections/{insp.id}/finalize", headers=headers)
    assert retry_resp.status_code == 200
    retry_data = retry_resp.json()
    assert retry_data["status"] == "COMPLETED"
    assert retry_data["report_status"] == "COMPLETED"
    assert retry_data["report"] is not None
    assert retry_data["report"]["id"] == report_data["id"]
