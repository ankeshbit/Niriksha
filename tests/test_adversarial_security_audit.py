"""
tests/test_adversarial_security_audit.py

Authoritative Adversarial Security Audit Test Suite for NiriKsha Backend.
Directly verifies every security invariant mandated in docs/SECURITY.md:
  1. Unauthenticated requests
  2. Inspector cross-inspection isolation
  3. Inspector forbidden from supervisor endpoints
  4. Supervisor forbidden from field write operations
  5. Invalid JWT
  6. Expired JWT
  7. Forged JWT
  8. Invalid inspection ID
  9. UUID vs human inspection number resolution
  10. Storage path traversal prevention
  11. Unauthorized image retrieval
  12. Unauthorized report retrieval
  13. Unauthorized evidence mutation (cross-inspector and post-finalization DEF-02)
  14. Unauthorized adjudication
  15. Unauthorized finalization
  16. Attempts to bypass pending adjudication
"""

import io
import uuid
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.orm import Session

from PIL import Image as PILImage

from backend.main import app
from backend.config import settings
from backend.database import SessionLocal
from backend.models import User, Inspection, Product, ProductImage, ComplianceCheck, RuleVersion, Report
from backend.auth_service import create_access_token
from backend.auth_utils import hash_password
from backend.storage_service import normalize_storage_key

client = TestClient(app)


def make_test_jpeg() -> bytes:
    img = PILImage.new("RGB", (100, 100), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="module")
def inspector_1(db: Session):
    user = db.query(User).filter(User.officer_id == "TEST-SEC-INSP-01").first()
    if not user:
        user = User(
            officer_id="TEST-SEC-INSP-01",
            full_name="Security Test Inspector One",
            role="INSPECTOR",
            designation="Field Inspector",
            zone="North Zone",
            password_hash=hash_password("SecTestPass123!")
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.fixture(scope="module")
def inspector_2(db: Session):
    user = db.query(User).filter(User.officer_id == "TEST-SEC-INSP-02").first()
    if not user:
        user = User(
            officer_id="TEST-SEC-INSP-02",
            full_name="Security Test Inspector Two",
            role="INSPECTOR",
            designation="Field Inspector",
            zone="South Zone",
            password_hash=hash_password("SecTestPass456!")
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.fixture(scope="module")
def supervisor_user(db: Session):
    user = db.query(User).filter(User.officer_id == "TEST-SEC-SUP-01").first()
    if not user:
        user = User(
            officer_id="TEST-SEC-SUP-01",
            full_name="Security Test Supervisor",
            role="SUPERVISOR",
            designation="Supervisory Officer",
            zone="Central HQ",
            password_hash=hash_password("SecSupPass789!")
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@pytest.fixture(scope="module")
def insp1_token(inspector_1: User):
    return create_access_token({"sub": inspector_1.officer_id, "role": inspector_1.role})


@pytest.fixture(scope="module")
def insp2_token(inspector_2: User):
    return create_access_token({"sub": inspector_2.officer_id, "role": inspector_2.role})


@pytest.fixture(scope="module")
def sup_token(supervisor_user: User):
    return create_access_token({"sub": supervisor_user.officer_id, "role": supervisor_user.role})


def _auth(token: str):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_01_unauthenticated_requests():
    """Endpoints requiring authentication must reject unauthenticated requests with 401."""
    endpoints = [
        ("GET", "/api/inspections"),
        ("POST", "/api/inspections"),
        ("GET", "/api/rules"),
        ("GET", "/api/supervisor/dashboard"),
        ("GET", "/api/reports"),
        ("GET", "/api/auth/me"),
    ]
    for method, path in endpoints:
        resp = client.request(method, path)
        assert resp.status_code == 401, f"{method} {path} should be 401, got {resp.status_code}"


def test_02_inspector_cross_inspection_isolation(insp1_token, insp2_token):
    """Inspector 2 must not be able to read Inspector 1's inspection data (403 Forbidden)."""
    # Inspector 1 creates inspection
    res = client.post(
        "/api/inspections",
        headers=_auth(insp1_token),
        json={"product_name": "Insp1 Product", "category": "Packaged Food", "location": "Warehouse A"}
    )
    assert res.status_code in (200, 201)
    insp_id = res.json()["id"]

    # Inspector 2 attempts read
    r_get = client.get(f"/api/inspections/{insp_id}", headers=_auth(insp2_token))
    assert r_get.status_code == 403, f"Expected 403, got {r_get.status_code}"

    # Inspector 2 attempts findings read
    r_findings = client.get(f"/api/inspections/{insp_id}/findings", headers=_auth(insp2_token))
    assert r_findings.status_code == 403, f"Expected 403, got {r_findings.status_code}"


def test_03_inspector_forbidden_from_supervisor_endpoints(insp1_token):
    """Inspectors must receive 403 Forbidden on supervisor management endpoints."""
    paths = [
        "/api/supervisor/dashboard",
        "/api/supervisor/inspectors",
        "/api/supervisor/inspections",
    ]
    for p in paths:
        r = client.get(p, headers=_auth(insp1_token))
        assert r.status_code == 403, f"Expected 403 on {p}, got {r.status_code}"


def test_04_supervisor_forbidden_from_field_write_operations(insp1_token, sup_token):
    """Supervisors must receive 403 Forbidden when attempting field writes on another officer's inspection."""
    res = client.post(
        "/api/inspections",
        headers=_auth(insp1_token),
        json={"product_name": "Field Write Guard Test", "category": "Packaged Food", "location": "Dock 3"}
    )
    insp_id = res.json()["id"]

    # Supervisor attempts image upload
    img_bytes = make_test_jpeg()
    r_up = client.post(
        f"/api/inspections/{insp_id}/images",
        headers=_auth(sup_token),
        files={"file": ("test.jpg", io.BytesIO(img_bytes), "image/jpeg")},
        data={"view_type": "front"}
    )
    assert r_up.status_code == 403, f"Expected 403 on supervisor image upload, got {r_up.status_code}"

    # Supervisor attempts finalization
    r_fin = client.post(f"/api/inspections/{insp_id}/finalize", headers=_auth(sup_token))
    assert r_fin.status_code == 403, f"Expected 403 on supervisor finalize, got {r_fin.status_code}"


def test_05_invalid_jwt():
    """Tampered or invalid JWT must return 401 Unauthorized."""
    r = client.get("/api/inspections", headers={"Authorization": "Bearer not.a.valid.jwt.token"})
    assert r.status_code == 401


def test_06_expired_jwt(inspector_1: User):
    """Expired JWT must return 401 Unauthorized."""
    expired_token = jwt.encode(
        {"sub": inspector_1.officer_id, "role": inspector_1.role, "exp": datetime.utcnow() - timedelta(minutes=10)},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    r = client.get("/api/inspections", headers={"Authorization": f"Bearer {expired_token}"})
    assert r.status_code == 401


def test_07_forged_jwt(inspector_1: User):
    """JWT signed with unauthorized key must return 401 Unauthorized."""
    forged_token = jwt.encode(
        {"sub": inspector_1.officer_id, "role": "ADMIN", "exp": datetime.utcnow() + timedelta(hours=1)},
        "completely_wrong_secret_key_that_was_forged_12345",
        algorithm="HS256"
    )
    r = client.get("/api/inspections", headers={"Authorization": f"Bearer {forged_token}"})
    assert r.status_code == 401


def test_08_invalid_inspection_id(insp1_token):
    """Non-existent UUID must return 404 Not Found."""
    fake_uuid = str(uuid.uuid4())
    r = client.get(f"/api/inspections/{fake_uuid}", headers=_auth(insp1_token))
    assert r.status_code == 404


def test_09_uuid_and_human_number_resolution(insp1_token):
    """Both UUID and human inspection number (LM-YYYY-NNNNN) must resolve the same inspection."""
    res = client.post(
        "/api/inspections",
        headers=_auth(insp1_token),
        json={"product_name": "Number Resolution Test", "category": "Packaged Food", "location": "Store 5"}
    )
    assert res.status_code in (200, 201)
    data = res.json()
    insp_uuid = data["id"]
    insp_num = data["inspection_number"]

    # Query by UUID
    r_uuid = client.get(f"/api/inspections/{insp_uuid}", headers=_auth(insp1_token))
    assert r_uuid.status_code == 200
    assert r_uuid.json()["id"] == insp_uuid

    # Query by human number
    r_num = client.get(f"/api/inspections/{insp_num}", headers=_auth(insp1_token))
    assert r_num.status_code == 200
    assert r_num.json()["id"] == insp_uuid


def test_10_storage_path_traversal():
    """Path traversal sequences, null bytes, and absolute paths must be rejected by storage sanitizer."""
    malicious_keys = [
        "../../etc/passwd",
        "inspections/123/../../../shadow",
        "C:\\Windows\\System32\\calc.exe",
        "/etc/hosts",
        "inspections/123/\x00evil.jpg",
        "a" * 600,
    ]
    for mk in malicious_keys:
        with pytest.raises(ValueError):
            normalize_storage_key(mk)


def test_11_unauthorized_image_retrieval(insp1_token, insp2_token, db: Session):
    """Inspector 2 must not be able to retrieve metadata or binary of Inspector 1's image."""
    res = client.post(
        "/api/inspections",
        headers=_auth(insp1_token),
        json={"product_name": "Image Access Test", "category": "Packaged Food", "location": "Lab 1"}
    )
    insp_id = res.json()["id"]

    # Upload an image as Inspector 1
    img_bytes = make_test_jpeg()
    up_resp = client.post(
        f"/api/inspections/{insp_id}/images",
        headers=_auth(insp1_token),
        files={"file": ("front.jpg", io.BytesIO(img_bytes), "image/jpeg")},
        data={"view_type": "front"}
    )
    assert up_resp.status_code == 201
    image_id = up_resp.json()["id"]

    # Inspector 2 attempts metadata retrieval
    r_meta = client.get(f"/api/images/{image_id}", headers=_auth(insp2_token))
    assert r_meta.status_code == 403

    # Inspector 2 attempts binary retrieval
    r_file = client.get(f"/api/images/{image_id}/file", headers=_auth(insp2_token))
    assert r_file.status_code == 403


def test_12_unauthorized_report_retrieval(insp1_token, insp2_token, db: Session, inspector_1: User):
    """Inspector 2 must not be able to retrieve Inspector 1's report."""
    res = client.post(
        "/api/inspections",
        headers=_auth(insp1_token),
        json={"product_name": "Report Access Test", "category": "Packaged Food", "location": "Lab 2"}
    )
    insp_id = res.json()["id"]

    # Create dummy report for Inspector 1
    report = Report(
        inspection_id=insp_id,
        report_version=1,
        pdf_path="reports/dummy.pdf",
        legal_safety_statement="Statutory test report"
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    # Inspector 2 attempts report retrieval by report ID
    r_rep = client.get(f"/api/reports/{report.id}", headers=_auth(insp2_token))
    assert r_rep.status_code == 403

    # Inspector 2 attempts report retrieval by inspection ID
    r_insp_rep = client.get(f"/api/inspections/{insp_id}/report", headers=_auth(insp2_token))
    assert r_insp_rep.status_code == 403


def test_13_unauthorized_evidence_mutation_and_def02(insp1_token, insp2_token, db: Session):
    """Inspector 2 cannot delete Inspector 1's image; Inspector 1 cannot delete image after finalization."""
    res = client.post(
        "/api/inspections",
        headers=_auth(insp1_token),
        json={"product_name": "DEF-02 Test", "category": "Packaged Food", "location": "Lab 3"}
    )
    insp_id = res.json()["id"]

    img_bytes = make_test_jpeg()
    up_resp = client.post(
        f"/api/inspections/{insp_id}/images",
        headers=_auth(insp1_token),
        files={"file": ("front.jpg", io.BytesIO(img_bytes), "image/jpeg")},
        data={"view_type": "front"}
    )
    assert up_resp.status_code == 201
    image_id = up_resp.json()["id"]

    # Cross-inspector deletion attempt -> 403
    r_del2 = client.delete(f"/api/images/{image_id}", headers=_auth(insp2_token))
    assert r_del2.status_code == 403

    # Finalize inspection in DB
    insp = db.query(Inspection).filter(Inspection.id == insp_id).first()
    insp.status = "COMPLETED"
    db.commit()

    # Inspector 1 deletion attempt on finalized inspection -> 409 Conflict (DEF-02)
    r_del1 = client.delete(f"/api/images/{image_id}", headers=_auth(insp1_token))
    assert r_del1.status_code == 409


def test_14_unauthorized_adjudication(insp1_token, insp2_token, sup_token, db: Session):
    """Only the assigned inspector can adjudicate findings."""
    res = client.post(
        "/api/inspections",
        headers=_auth(insp1_token),
        json={"product_name": "Adjudication Test", "category": "Packaged Food", "location": "Lab 4"}
    )
    insp_id = res.json()["id"]

    rule = db.query(RuleVersion).first()
    check = ComplianceCheck(
        inspection_id=insp_id,
        rule_version_id=rule.id,
        rule_code=rule.rule_code,
        title="Test Check",
        result_state="POTENTIAL_NON_COMPLIANCE",
        explanation="Missing MRP declaration",
        adjudication_status="PENDING"
    )
    db.add(check)
    db.commit()
    db.refresh(check)

    # Inspector 2 attempts adjudication -> 403
    r_adj2 = client.post(
        f"/api/findings/{check.id}/adjudicate",
        headers=_auth(insp2_token),
        json={"action": "DISMISSED", "notes": "Unauthorized attempt"}
    )
    assert r_adj2.status_code == 403

    # Supervisor attempts adjudication -> 403
    r_adjsup = client.post(
        f"/api/findings/{check.id}/adjudicate",
        headers=_auth(sup_token),
        json={"action": "DISMISSED", "notes": "Supervisor attempt"}
    )
    assert r_adjsup.status_code == 403


def test_15_unauthorized_finalization(insp1_token, insp2_token, sup_token):
    """Only the assigned inspector can finalize an inspection."""
    res = client.post(
        "/api/inspections",
        headers=_auth(insp1_token),
        json={"product_name": "Finalize Test", "category": "Packaged Food", "location": "Lab 5"}
    )
    insp_id = res.json()["id"]

    # Inspector 2 attempts finalization -> 403
    r_fin2 = client.post(f"/api/inspections/{insp_id}/finalize", headers=_auth(insp2_token))
    assert r_fin2.status_code == 403

    # Supervisor attempts finalization -> 403
    r_finsup = client.post(f"/api/inspections/{insp_id}/finalize", headers=_auth(sup_token))
    assert r_finsup.status_code == 403


def test_16_attempts_to_bypass_pending_adjudication(insp1_token, db: Session):
    """Finalization and direct report generation must both be blocked (409) if findings remain pending."""
    res = client.post(
        "/api/inspections",
        headers=_auth(insp1_token),
        json={"product_name": "Bypass Test", "category": "Packaged Food", "location": "Lab 6"}
    )
    insp_id = res.json()["id"]

    rule = db.query(RuleVersion).first()
    check = ComplianceCheck(
        inspection_id=insp_id,
        rule_version_id=rule.id,
        rule_code=rule.rule_code,
        title="Test Check",
        result_state="POTENTIAL_NON_COMPLIANCE",
        explanation="Missing MRP declaration",
        adjudication_status="PENDING"
    )
    db.add(check)
    db.commit()

    # Attempt to finalize -> 409 Conflict
    r_fin = client.post(f"/api/inspections/{insp_id}/finalize", headers=_auth(insp1_token))
    assert r_fin.status_code == 409
    assert r_fin.json()["detail"]["error"] == "UNRESOLVED_FINDINGS"

    # Attempt to generate report directly -> 409 Conflict
    r_rep = client.post(f"/api/inspections/{insp_id}/report", headers=_auth(insp1_token))
    assert r_rep.status_code == 409
    assert r_rep.json()["detail"]["error"] == "UNRESOLVED_FINDINGS"
