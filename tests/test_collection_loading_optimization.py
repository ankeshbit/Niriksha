"""
tests/test_collection_loading_optimization.py

Verifies the performance optimization replacing collection joinedload with selectinload
and pushdown COUNT subqueries for list screens:
1. GET /api/inspections returns InspectionDetailResponse with collections populated correctly via selectinload.
2. GET /api/repository/inspections computes findings_count and non_compliant_count via COUNT subqueries.
3. GET /api/repository/products/{product_key}/inspections computes findings_count and non_compliant_count via COUNT subqueries.
4. GET /api/supervisor/inspections computes findings_count and non_compliant_count via COUNT subqueries.
5. Response models and shapes are strictly preserved.
"""

import uuid
import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.config import settings
from backend.models import (
    User,
    Inspection,
    Product,
    ProductImage,
    Declaration,
    ComplianceCheck,
    Report,
    generate_product_key,
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
def test_users(db_session: Session):
    """Ensures test inspector and supervisor exist."""
    inspector = db_session.query(User).filter(User.officer_id == "INSP-SELECTIN-01").first()
    if not inspector:
        inspector = User(
            officer_id="INSP-SELECTIN-01",
            full_name="Selectinload Test Officer",
            role="INSPECTOR",
            designation="Enforcement Inspector",
            zone="Central",
            password_hash=hash_password("Pass123!")
        )
        db_session.add(inspector)

    supervisor = db_session.query(User).filter(User.officer_id == "SUP-SELECTIN-01").first()
    if not supervisor:
        supervisor = User(
            officer_id="SUP-SELECTIN-01",
            full_name="Selectinload Test Supervisor",
            role="SUPERVISOR",
            designation="Supervisory Officer",
            zone="Central",
            password_hash=hash_password("Pass123!")
        )
        db_session.add(supervisor)

    db_session.commit()
    db_session.refresh(inspector)
    db_session.refresh(supervisor)

    insp_token = create_access_token({"sub": inspector.officer_id, "role": inspector.role})
    sup_token = create_access_token({"sub": supervisor.officer_id, "role": supervisor.role})

    return {
        "inspector": inspector,
        "supervisor": supervisor,
        "inspector_headers": {"Authorization": f"Bearer {insp_token}"},
        "supervisor_headers": {"Authorization": f"Bearer {sup_token}"},
    }


@pytest.fixture(autouse=True)
def cleanup_test_records(db_session: Session):
    """Cleans up any test records created with prefix INSP-SEL-."""
    def _clean():
        try:
            insps = db_session.query(Inspection).filter(
                Inspection.inspection_number.like("INSP-SEL-%")
            ).all()
            for i in insps:
                db_session.delete(i)
            db_session.commit()
        except Exception:
            db_session.rollback()

    _clean()
    yield
    _clean()


def _seed_sample_inspection(db_session: Session, inspector_id: str, num_images=3, num_decls=4, num_pass=3, num_fail=2):
    """Helper to create an inspection with multiple collection items to verify selectinload and COUNT subqueries."""
    insp_id = str(uuid.uuid4())
    insp_num = f"INSP-SEL-{uuid.uuid4().hex[:8].upper()}"

    p_name = "Premium Basmati Rice"
    b_name = "India Gate"
    cat = "Packaged Food"
    pkey = generate_product_key(p_name, b_name, cat)

    insp = Inspection(
        id=insp_id,
        inspection_number=insp_num,
        inspector_id=inspector_id,
        location="Connaught Place Market, New Delhi",
        status="FINALIZED",
        overall_status="POTENTIAL_NON_COMPLIANCE",
        inspection_type="PHYSICAL",
        created_at=datetime.utcnow()
    )
    db_session.add(insp)
    db_session.flush()

    prod = Product(
        inspection_id=insp.id,
        product_name=p_name,
        brand_name=b_name,
        category=cat,
        batch_number="BATCH-SEL-999",
        product_key=pkey
    )
    db_session.add(prod)

    # Add images
    for i in range(num_images):
        img = ProductImage(
            id=str(uuid.uuid4()),
            inspection_id=insp.id,
            view_type=f"view_{i}",
            file_path=f"/fake/storage/sel_{i}.jpg",
            quality_status="GOOD"
        )
        db_session.add(img)

    # Add declarations
    fields = ["mrp", "net_quantity", "manufacturer_name", "date_of_manufacture"]
    for i, fn in enumerate(fields[:num_decls]):
        decl = Declaration(
            id=str(uuid.uuid4()),
            inspection_id=insp.id,
            field_name=fn,
            extracted_value="KRBL Limited" if fn == "manufacturer_name" else f"val_{i}",
            confidence=0.95
        )
        db_session.add(decl)

    # Find a rule_version for foreign key
    from backend.models import RuleVersion
    rv = db_session.query(RuleVersion).first()
    rv_id = rv.id if rv else str(uuid.uuid4())

    # Add compliance checks: num_pass pass, num_fail fail
    for i in range(num_pass):
        chk = ComplianceCheck(
            id=str(uuid.uuid4()),
            inspection_id=insp.id,
            rule_version_id=rv_id,
            rule_code=f"RULE-PASS-{i}",
            title=f"Passing Rule {i}",
            severity="MANDATORY",
            result_state="PASS",
            explanation=f"Passing rule explanation {i}",
            adjudication_status="AUTO_PASSED"
        )
        db_session.add(chk)

    for i in range(num_fail):
        chk = ComplianceCheck(
            id=str(uuid.uuid4()),
            inspection_id=insp.id,
            rule_version_id=rv_id,
            rule_code=f"RULE-FAIL-{i}",
            title=f"Failing Rule {i}",
            severity="MANDATORY",
            result_state="POTENTIAL_NON_COMPLIANCE",
            explanation=f"Failing rule explanation {i}",
            adjudication_status="PENDING"
        )
        db_session.add(chk)

    # Add report
    rep = Report(
        id=str(uuid.uuid4()),
        inspection_id=insp.id,
        pdf_path=f"/fake/reports/{insp_num}.pdf",
        legal_safety_statement="Statutory report generated under PCR 2011.",
        generated_at=datetime.utcnow()
    )
    db_session.add(rep)

    db_session.commit()
    db_session.refresh(insp)
    return insp, pkey


def test_list_inspections_selectinload(db_session: Session, test_users):
    """GET /api/inspections returns InspectionDetailResponse with collections loaded cleanly without row duplication."""
    headers = test_users["inspector_headers"]
    user = test_users["inspector"]

    insp, _ = _seed_sample_inspection(db_session, user.id, num_images=2, num_decls=3, num_pass=2, num_fail=1)

    resp = client.get("/api/inspections?limit=10", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Find the seeded inspection
    found = next((item for item in data if item["id"] == insp.id), None)
    assert found is not None, "Seeded inspection must be present in response"

    # Verify collections are populated correctly
    assert len(found["images"]) == 2
    assert len(found["declarations"]) == 3
    assert len(found["compliance_checks"]) == 3
    assert found["product"] is not None
    assert found["product"]["product_name"] == "Premium Basmati Rice"
    assert found["report"] is not None


def test_repository_inspections_count_subqueries(db_session: Session, test_users):
    """GET /api/repository/inspections uses COUNT subqueries for findings_count and non_compliant_count."""
    headers = test_users["supervisor_headers"]
    user = test_users["inspector"]

    insp, _ = _seed_sample_inspection(db_session, user.id, num_images=1, num_decls=3, num_pass=4, num_fail=2)

    resp = client.get(f"/api/repository/inspections?search={insp.inspection_number}", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["total"] >= 1
    found = next((item for item in data["items"] if item["id"] == insp.id), None)
    assert found is not None
    assert found["findings_count"] == 6  # 4 pass + 2 fail
    assert found["non_compliant_count"] == 2  # 2 POTENTIAL_NON_COMPLIANCE
    assert found["has_report"] is True
    assert found["manufacturer"] == "KRBL Limited"


def test_product_inspection_history_count_subqueries(db_session: Session, test_users):
    """GET /api/repository/products/{key}/inspections uses COUNT subqueries for findings_count and non_compliant_count."""
    headers = test_users["supervisor_headers"]
    user = test_users["inspector"]

    insp, pkey = _seed_sample_inspection(db_session, user.id, num_images=1, num_decls=2, num_pass=5, num_fail=3)

    resp = client.get(f"/api/repository/products/{pkey}/inspections", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["total"] >= 1
    found = next((item for item in data["items"] if item["id"] == insp.id), None)
    assert found is not None
    assert found["findings_count"] == 8  # 5 pass + 3 fail
    assert found["non_compliant_count"] == 3  # 3 POTENTIAL_NON_COMPLIANCE


def test_supervisor_inspections_count_subqueries(db_session: Session, test_users):
    """GET /api/supervisor/inspections uses COUNT subqueries for findings_count and non_compliant_count."""
    headers = test_users["supervisor_headers"]
    user = test_users["inspector"]

    insp, _ = _seed_sample_inspection(db_session, user.id, num_images=1, num_decls=2, num_pass=3, num_fail=1)

    resp = client.get(f"/api/supervisor/inspections?search={insp.inspection_number}", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["total_count"] >= 1
    found = next((item for item in data["items"] if item["id"] == insp.id), None)
    assert found is not None
    assert found["findings_count"] == 4  # 3 pass + 1 fail
    assert found["non_compliant_count"] == 1  # 1 POTENTIAL_NON_COMPLIANCE
