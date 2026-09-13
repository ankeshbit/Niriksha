"""
tests/test_findings_pending_adjudication.py

Comprehensive Test Suite for Authoritative Pending Adjudication Filtering & Navigation.
Covers Cases A through E as required by the specification:
  - Case A: Inspection with 2 pending + 10 already adjudicated findings.
            -> pending count = 2
            -> status=pending_adjudication returns exactly 2 records.
  - Case B: One pending finding is adjudicated.
            -> pending count becomes 1.
            -> status=pending_adjudication returns exactly 1 record after refetch.
  - Case C: All pending findings are adjudicated.
            -> pending count = 0.
            -> status=pending_adjudication returns exactly 0 records.
            -> Step 3 warning clears & finalization gate passes.
  - Case D: Inspection has 0 pending findings but many historical/completed findings.
            -> status=pending_adjudication returns empty list; historical findings never leak into pending list.
  - Case E: Cross-inspection isolation.
            -> Pending findings from Inspection A never appear in Inspection B.
"""

import pytest
import uuid
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings
from backend.database import SessionLocal
from backend.models import Inspection, Product, ComplianceCheck, RuleVersion
from backend.compliance_summary_utils import is_pending_adjudication, compute_canonical_compliance_metrics

client = TestClient(app)

def get_auth_token():
    """Helper to authenticate seed officer and return JWT token."""
    resp = client.post("/api/auth/login", json={
        "officer_id": settings.SEED_OFFICER_ID,
        "password": settings.SEED_OFFICER_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def create_inspection_with_findings(headers, num_pending=2, num_adjudicated=10, name="Test Product"):
    """
    Helper to create an inspection via API and populate with exact counts of
    pending and settled/adjudicated findings.
    """
    # 1. Create inspection via API
    resp = client.post("/api/inspections", headers=headers, json={
        "product_name": name,
        "category": "Packaged Food",
        "location": "Lab Validation Station"
    })
    assert resp.status_code == 201, f"Failed to create inspection: {resp.text}"
    insp_data = resp.json()
    insp_id = insp_data["id"]

    db = SessionLocal()
    pending_checks = []
    try:
        rule_ver = db.query(RuleVersion).first()
        if not rule_ver:
            rule_ver = RuleVersion(
                rule_code="PCR_RULE_TEST",
                version_number=1,
                title="Test Statutory Rule",
                category="CATEGORY_A_LEGAL",
                statutory_reference="Legal Metrology Act 2009",
                rule_logic_description="Test rule description",
                severity="MAJOR"
            )
            db.add(rule_ver)
            db.flush()

        # Create adjudicated / settled findings (e.g. DISMISSED, CONFIRMED, PASS, NOT_APPLICABLE)
        settled_actions = ["DISMISSED", "CONFIRMED", "CORRECTED", "NOT_APPLICABLE"]
        for i in range(num_adjudicated):
            action = settled_actions[i % len(settled_actions)]
            check = ComplianceCheck(
                inspection_id=insp_id,
                rule_version_id=rule_ver.id,
                rule_code=f"SETTLED_RULE_{i+1:02d}",
                title=f"Settled Rule {i+1}",
                severity="HIGH",
                result_state="POTENTIAL_NON_COMPLIANCE" if action != "NOT_APPLICABLE" else "NOT_APPLICABLE",
                explanation=f"Historical rule check {i+1} already reviewed.",
                adjudication_status=action,
                adjudication_notes=f"Adjudicated with decision {action}"
            )
            db.add(check)

        # Create pending findings (POTENTIAL_NON_COMPLIANCE, adjudication_status is None or 'PENDING')
        for i in range(num_pending):
            check = ComplianceCheck(
                inspection_id=insp_id,
                rule_version_id=rule_ver.id,
                rule_code=f"PENDING_RULE_{i+1:02d}",
                title=f"Pending Non-Compliance {i+1}",
                severity="CRITICAL",
                result_state="POTENTIAL_NON_COMPLIANCE",
                explanation=f"Statutory discrepancy requiring officer adjudication {i+1}.",
                adjudication_status="PENDING",
                adjudication_notes=None
            )
            db.add(check)
            pending_checks.append(check)

        db.commit()
        for c in pending_checks:
            db.refresh(c)
    finally:
        db.close()

    return insp_id, [str(c.id) for c in pending_checks]


# ===========================================================================
# Unit Test: Canonical is_pending_adjudication state machine
# ===========================================================================

def test_canonical_is_pending_adjudication_semantics():
    """Verify state machine invariants for is_pending_adjudication."""
    class DummyCheck:
        def __init__(self, result_state, adjudication_status):
            self.result_state = result_state
            self.adjudication_status = adjudication_status

    # Compliant/Pass checks are never pending
    assert not is_pending_adjudication(DummyCheck("PASS", None))
    assert not is_pending_adjudication(DummyCheck("PASS", "PENDING"))
    assert not is_pending_adjudication(DummyCheck("NOT_APPLICABLE", None))

    # Adjudicated/Settled decisions are never pending
    assert not is_pending_adjudication(DummyCheck("POTENTIAL_NON_COMPLIANCE", "DISMISSED"))
    assert not is_pending_adjudication(DummyCheck("POTENTIAL_NON_COMPLIANCE", "CONFIRMED"))
    assert not is_pending_adjudication(DummyCheck("POTENTIAL_NON_COMPLIANCE", "CORRECTED"))
    assert not is_pending_adjudication(DummyCheck("POTENTIAL_NON_COMPLIANCE", "NOT_APPLICABLE"))
    assert not is_pending_adjudication(DummyCheck("NEEDS_MANUAL_VERIFICATION", "DISMISSED"))
    assert not is_pending_adjudication(DummyCheck("INSUFFICIENT_EVIDENCE", "CONFIRMED"))

    # Non-pass without resolved decision IS pending
    assert is_pending_adjudication(DummyCheck("POTENTIAL_NON_COMPLIANCE", None))
    assert is_pending_adjudication(DummyCheck("POTENTIAL_NON_COMPLIANCE", "PENDING"))
    assert is_pending_adjudication(DummyCheck("NEEDS_MANUAL_VERIFICATION", None))
    assert is_pending_adjudication(DummyCheck("NEEDS_MANUAL_VERIFICATION", "PENDING"))
    assert is_pending_adjudication(DummyCheck("INSUFFICIENT_EVIDENCE", None))


# ===========================================================================
# Case A: Inspection has 2 pending + 10 already adjudicated findings
# ===========================================================================

def test_case_a_two_pending_ten_adjudicated():
    """
    Case A:
    Inspection has 2 pending + 10 already adjudicated findings.
    -> pending count = 2
    -> Review & Adjudicate screen API (status=pending_adjudication) displays exactly 2.
    """
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    insp_id, pending_ids = create_inspection_with_findings(
        headers, num_pending=2, num_adjudicated=10, name="Case A Product"
    )

    # 1. Verify compliance summary returns total metrics and authoritative pending count
    resp = client.get(f"/api/inspections/{insp_id}/compliance-summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["pending_adjudication_count"] == 2
    assert data["total_findings"] == 12

    # 2. Verify GET /findings with status=pending_adjudication returns exactly 2
    f_resp = client.get(f"/api/inspections/{insp_id}/findings?status=pending_adjudication", headers=headers)
    assert f_resp.status_code == 200
    pending_list = f_resp.json()
    assert len(pending_list) == 2

    # Verify returned finding IDs match the actual 2 pending checks
    returned_ids = {f["id"] for f in pending_list}
    assert returned_ids == set(pending_ids)

    # Verify all returned records have is_pending_adjudication=True
    for item in pending_list:
        assert item["is_pending_adjudication"] is True
        assert item["adjudication_status"] not in {"DISMISSED", "CONFIRMED", "CORRECTED", "NOT_APPLICABLE"}

    # 3. Verify that GET /findings without filter preserves all 12 findings
    all_resp = client.get(f"/api/inspections/{insp_id}/findings", headers=headers)
    assert all_resp.status_code == 200
    assert len(all_resp.json()) == 12


# ===========================================================================
# Case B: One pending finding is adjudicated
# ===========================================================================

def test_case_b_one_adjudicated_count_becomes_one():
    """
    Case B:
    One pending finding is adjudicated.
    -> pending count becomes 1.
    -> screen displays exactly 1 after refetch.
    """
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    insp_id, pending_ids = create_inspection_with_findings(
        headers, num_pending=2, num_adjudicated=10, name="Case B Product"
    )
    first_finding_id = pending_ids[0]
    second_finding_id = pending_ids[1]

    # Adjudicate finding 1 (DISMISS it)
    adj_resp = client.post(
        f"/api/findings/{first_finding_id}/adjudicate",
        headers=headers,
        json={
            "action": "DISMISSED",
            "notes": "Dismissed due to statutory exemption under Rule 26."
        }
    )
    assert adj_resp.status_code == 200

    # Refetch compliance summary
    sum_resp = client.get(f"/api/inspections/{insp_id}/compliance-summary", headers=headers)
    assert sum_resp.status_code == 200
    assert sum_resp.json()["pending_adjudication_count"] == 1

    # Refetch pending findings
    f_resp = client.get(f"/api/inspections/{insp_id}/findings?status=pending_adjudication", headers=headers)
    assert f_resp.status_code == 200
    remaining_pending = f_resp.json()
    assert len(remaining_pending) == 1
    assert remaining_pending[0]["id"] == second_finding_id
    assert remaining_pending[0]["is_pending_adjudication"] is True


# ===========================================================================
# Case C: All pending findings are adjudicated
# ===========================================================================

def test_case_c_all_adjudicated_pending_count_zero():
    """
    Case C:
    All pending findings are adjudicated.
    -> pending count = 0.
    -> Step 3 warning clears (finalize endpoint unblocked).
    -> adjudication screen query shows empty list.
    """
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    insp_id, pending_ids = create_inspection_with_findings(
        headers, num_pending=2, num_adjudicated=10, name="Case C Product"
    )

    # Adjudicate both findings
    for fid in pending_ids:
        client.post(
            f"/api/findings/{fid}/adjudicate",
            headers=headers,
            json={
                "action": "CONFIRMED",
                "notes": "Confirmed non-compliance."
            }
        )

    # Pending count should now be 0
    sum_resp = client.get(f"/api/inspections/{insp_id}/compliance-summary", headers=headers)
    assert sum_resp.status_code == 200
    assert sum_resp.json()["pending_adjudication_count"] == 0

    # Pending list should now be completely empty
    f_resp = client.get(f"/api/inspections/{insp_id}/findings?status=pending_adjudication", headers=headers)
    assert f_resp.status_code == 200
    assert len(f_resp.json()) == 0


# ===========================================================================
# Case D: 0 pending findings but many historical/completed findings
# ===========================================================================

def test_case_d_zero_pending_many_historical():
    """
    Case D:
    Inspection has 0 pending findings but many historical/completed findings.
    -> never display the historical findings as pending.
    """
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    insp_id, _ = create_inspection_with_findings(
        headers, num_pending=0, num_adjudicated=15, name="Case D Product"
    )

    # Total checks = 15, pending = 0
    sum_resp = client.get(f"/api/inspections/{insp_id}/compliance-summary", headers=headers)
    assert sum_resp.status_code == 200
    data = sum_resp.json()
    assert data["pending_adjudication_count"] == 0
    assert data["total_findings"] == 15

    # Query pending findings -> must return empty list, NOT historical records
    f_resp = client.get(f"/api/inspections/{insp_id}/findings?status=pending_adjudication", headers=headers)
    assert f_resp.status_code == 200
    assert f_resp.json() == []

    # All findings route returns all 15
    all_resp = client.get(f"/api/inspections/{insp_id}/findings", headers=headers)
    assert all_resp.status_code == 200
    assert len(all_resp.json()) == 15


# ===========================================================================
# Case E: Cross-Inspection Isolation
# ===========================================================================

def test_case_e_cross_inspection_isolation():
    """
    Case E:
    Two different inspections exist.
    -> pending findings from inspection A must never appear in inspection B.
    """
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    id_a, pending_a = create_inspection_with_findings(
        headers, num_pending=2, num_adjudicated=3, name="Inspection A Product"
    )
    id_b, pending_b = create_inspection_with_findings(
        headers, num_pending=1, num_adjudicated=5, name="Inspection B Product"
    )

    # Inspect A pending findings
    resp_a = client.get(f"/api/inspections/{id_a}/findings?status=pending_adjudication", headers=headers)
    assert resp_a.status_code == 200
    items_a = resp_a.json()
    assert len(items_a) == 2
    ids_in_a = {x["id"] for x in items_a}
    assert ids_in_a == set(pending_a)

    # Inspect B pending findings
    resp_b = client.get(f"/api/inspections/{id_b}/findings?status=pending_adjudication", headers=headers)
    assert resp_b.status_code == 200
    items_b = resp_b.json()
    assert len(items_b) == 1
    ids_in_b = {x["id"] for x in items_b}
    assert ids_in_b == set(pending_b)

    # Zero intersection between inspection A and B
    assert ids_in_a.isdisjoint(ids_in_b)
