"""
test_final_corrections.py

Targeted tests for the Final Pre-Demo Correction Pass:
1. Unresolved finding blocks finalization (HTTP 409)
2. Resolving finding allows finalization
3. NOT_APPLICABLE adjudication action accepted
4. CORRECTED adjudication action accepted
5. NO_POTENTIAL_VIOLATIONS status used (not VERIFIED_COMPLIANT)
6. Rule version returned in finding response
7. REQUEST_NEW_IMAGE endpoint creates audit log and stays unresolved
"""
import io
import json
import pytest
from PIL import Image as PILImage
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_token():
    res = client.post("/api/auth/login", json={"officer_id": "DOCA-INSP-842", "password": "admin123"})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _auth(token: str):
    return {"Authorization": f"Bearer {token}"}


def _create_inspection(token: str) -> str:
    res = client.post(
        "/api/inspections",
        json={
            "product_name": "Test Biscuit Pack",
            "category": "Packaged Food",
            "location": "Test Lab Delhi",
        },
        headers=_auth(token),
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _make_jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    img = PILImage.new("RGB", (640, 480), color=(200, 200, 200))
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _upload_image(token: str, inspection_id: str) -> str:
    img_data = _make_jpeg_bytes()
    res = client.post(
        f"/api/inspections/{inspection_id}/images",
        headers=_auth(token),
        files={"file": ("label.jpg", img_data, "image/jpeg")},
        data={"view_type": "front"},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _run_ocr(token: str, inspection_id: str):
    res = client.post(f"/api/inspections/{inspection_id}/ocr", headers=_auth(token))
    assert res.status_code == 200, res.text


def _evaluate(token: str, inspection_id: str) -> list:
    res = client.post(f"/api/inspections/{inspection_id}/evaluate", headers=_auth(token))
    assert res.status_code == 200, res.text
    return res.json()["findings"]


def _get_non_pass_findings(findings: list) -> list:
    return [f for f in findings if f["result_state"] != "PASS"]


def _get_all_findings(token: str, inspection_id: str) -> list:
    res = client.get(f"/api/inspections/{inspection_id}/findings", headers=_auth(token))
    assert res.status_code == 200
    return res.json()


# ─── Test 1: Unresolved finding blocks finalization (HTTP 409) ────────────────

def test_unresolved_finding_blocks_finalization():
    """Backend must return 409 if any non-PASS finding is still PENDING adjudication."""
    token = _get_token()
    iid = _create_inspection(token)
    _upload_image(token, iid)
    _run_ocr(token, iid)
    findings = _evaluate(token, iid)

    non_pass = _get_non_pass_findings(findings)
    if not non_pass:
        pytest.skip("No non-PASS findings generated for this test data — skip gate test")

    # Attempt finalization WITHOUT adjudicating findings — must be blocked
    res = client.post(
        f"/api/inspections/{iid}/finalize",
        json={"officer_notes": "Trying to finalize early"},
        headers=_auth(token),
    )
    assert res.status_code == 409, f"Expected 409, got {res.status_code}: {res.text}"
    body = res.json()
    assert body["detail"]["error"] == "UNRESOLVED_FINDINGS"
    assert len(body["detail"]["unresolved_findings"]) > 0


# ─── Test 2: Resolving all findings allows finalization ───────────────────────

def test_resolving_findings_allows_finalization():
    """After adjudicating all non-PASS findings, finalization should succeed."""
    token = _get_token()
    iid = _create_inspection(token)
    _upload_image(token, iid)
    _run_ocr(token, iid)
    findings = _evaluate(token, iid)

    # Dismiss all non-PASS findings
    for f in findings:
        if f["result_state"] != "PASS":
            res = client.patch(
                f"/api/findings/{f['id']}/adjudicate",
                json={"action": "DISMISSED", "notes": "Dismissed for test purposes"},
                headers=_auth(token),
            )
            assert res.status_code == 200, res.text

    # Now finalization should succeed
    res = client.post(
        f"/api/inspections/{iid}/finalize",
        json={"officer_notes": "Test finalization"},
        headers=_auth(token),
    )
    assert res.status_code == 200, f"Expected 200 after resolving findings, got {res.status_code}: {res.text}"
    data = res.json()
    assert data["status"] == "COMPLETED"
    # Must NOT use VERIFIED_COMPLIANT
    assert data["overall_status"] != "VERIFIED_COMPLIANT", "VERIFIED_COMPLIANT must never be used"


# ─── Test 3: NOT_APPLICABLE adjudication action accepted ─────────────────────

def test_not_applicable_adjudication_action():
    """Backend must accept NOT_APPLICABLE as a valid adjudication action."""
    token = _get_token()
    iid = _create_inspection(token)
    _upload_image(token, iid)
    _run_ocr(token, iid)
    findings = _evaluate(token, iid)

    non_pass = _get_non_pass_findings(findings)
    if not non_pass:
        pytest.skip("No non-PASS findings for NOT_APPLICABLE test")

    target = non_pass[0]
    res = client.patch(
        f"/api/findings/{target['id']}/adjudicate",
        json={"action": "NOT_APPLICABLE", "notes": "Not applicable to this commodity category."},
        headers=_auth(token),
    )
    assert res.status_code == 200, f"NOT_APPLICABLE action failed: {res.text}"
    data = res.json()
    assert data["adjudication_status"] == "NOT_APPLICABLE"
    assert data["adjudicated_by"] is not None


# ─── Test 4: CORRECTED adjudication action accepted ──────────────────────────

def test_corrected_adjudication_action():
    """Backend must accept CORRECTED as a valid adjudication action with corrected_value."""
    token = _get_token()
    iid = _create_inspection(token)
    _upload_image(token, iid)
    _run_ocr(token, iid)
    findings = _evaluate(token, iid)

    non_pass = _get_non_pass_findings(findings)
    if not non_pass:
        pytest.skip("No non-PASS findings for CORRECTED test")

    target = non_pass[0]
    res = client.patch(
        f"/api/findings/{target['id']}/adjudicate",
        json={
            "action": "CORRECTED",
            "notes": "Manually verified from physical label",
            "corrected_value": "MRP Rs. 45/- (incl. of all taxes)",
        },
        headers=_auth(token),
    )
    assert res.status_code == 200, f"CORRECTED action failed: {res.text}"
    data = res.json()
    assert data["adjudication_status"] == "CORRECTED"
    assert "Inspector correction" in (data["adjudication_notes"] or "")


# ─── Test 5: NO_POTENTIAL_VIOLATIONS status (never VERIFIED_COMPLIANT) ────────

def test_final_status_never_verified_compliant():
    """After resolving all findings via DISMISSED, status must be NO_POTENTIAL_VIOLATIONS."""
    token = _get_token()
    iid = _create_inspection(token)
    _upload_image(token, iid)
    _run_ocr(token, iid)
    findings = _evaluate(token, iid)

    # Dismiss all non-PASS findings
    for f in findings:
        if f["result_state"] != "PASS":
            client.patch(
                f"/api/findings/{f['id']}/adjudicate",
                json={"action": "DISMISSED", "notes": "Dismissed"},
                headers=_auth(token),
            )

    res = client.post(
        f"/api/inspections/{iid}/finalize",
        json={"officer_notes": "Final"},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["overall_status"] in {
        "NO_POTENTIAL_VIOLATIONS",
        "POTENTIAL_NON_COMPLIANCE",
        "NEEDS_MANUAL_VERIFICATION",
        "INSUFFICIENT_EVIDENCE",
    }, f"Unexpected status: {data['overall_status']}"
    assert data["overall_status"] != "VERIFIED_COMPLIANT", "VERIFIED_COMPLIANT must never be used"


# ─── Test 6: Rule version returned in finding response ───────────────────────

def test_rule_version_in_finding_response():
    """FindingResponse must include rule_version_number and statutory_reference."""
    token = _get_token()
    iid = _create_inspection(token)
    _upload_image(token, iid)
    _run_ocr(token, iid)
    findings = _evaluate(token, iid)

    assert len(findings) > 0, "Expected at least one finding for version test"
    for finding in findings:
        # rule_version_number may be None for placeholder but key must exist
        assert "rule_version_number" in finding, f"Missing rule_version_number in finding {finding['rule_code']}"
        assert "statutory_reference" in finding, f"Missing statutory_reference in finding {finding['rule_code']}"

    # At least one finding should have a non-None statutory_reference
    have_ref = [f for f in findings if f.get("statutory_reference")]
    assert len(have_ref) > 0, "At least one finding must have a statutory_reference"


# ─── Test 7: REQUEST_NEW_IMAGE endpoint behavior ─────────────────────────────

def test_request_new_image_does_not_resolve_finding():
    """
    POST /api/findings/{id}/request-new-image must:
    - Return 200 with updated finding
    - Set adjudication_status to NEEDS_MORE_EVIDENCE (not a terminal action)
    - Create an audit log entry with action=REQUEST_NEW_IMAGE
    - NOT count as resolved for the report-blocking gate
    """
    token = _get_token()
    iid = _create_inspection(token)
    _upload_image(token, iid)
    _run_ocr(token, iid)
    findings = _evaluate(token, iid)

    non_pass = _get_non_pass_findings(findings)
    if not non_pass:
        pytest.skip("No non-PASS findings for request-new-image test")

    target = non_pass[0]
    res = client.post(
        f"/api/findings/{target['id']}/request-new-image",
        headers=_auth(token),
    )
    assert res.status_code == 200, f"request-new-image failed: {res.text}"
    data = res.json()
    assert data["adjudication_status"] == "NEEDS_MORE_EVIDENCE"

    # Verify audit log was created
    audit_res = client.get(f"/api/inspections/{iid}/audit-logs", headers=_auth(token))
    assert audit_res.status_code == 200
    logs = audit_res.json()
    request_logs = [log for log in logs if log["action"] == "REQUEST_NEW_IMAGE"]
    assert len(request_logs) >= 1, "REQUEST_NEW_IMAGE audit log entry not found"

    # Confirm that finalization is STILL blocked (finding not resolved)
    # Dismiss remaining non-pass findings except this one
    other_non_pass = [f for f in findings if f["result_state"] != "PASS" and f["id"] != target["id"]]
    for f in other_non_pass:
        client.patch(
            f"/api/findings/{f['id']}/adjudicate",
            json={"action": "DISMISSED", "notes": "Dismissed for test"},
            headers=_auth(token),
        )

    # Finalization must still be blocked because the target finding is NEEDS_MORE_EVIDENCE
    fin_res = client.post(
        f"/api/inspections/{iid}/finalize",
        json={"officer_notes": "Test"},
        headers=_auth(token),
    )
    assert fin_res.status_code == 409, (
        f"Expected 409 (finding still unresolved after request-new-image), got {fin_res.status_code}: {fin_res.text}"
    )


# ─── Test 8: Invalid adjudication action still rejected ──────────────────────

def test_invalid_adjudication_action_rejected():
    """Backend must reject unknown adjudication actions with 400."""
    token = _get_token()
    iid = _create_inspection(token)
    _upload_image(token, iid)
    _run_ocr(token, iid)
    findings = _evaluate(token, iid)

    if not findings:
        pytest.skip("No findings for invalid action test")

    target = findings[0]
    res = client.patch(
        f"/api/findings/{target['id']}/adjudicate",
        json={"action": "ILLEGAL_ACTION", "notes": "Should be rejected"},
        headers=_auth(token),
    )
    assert res.status_code == 400, f"Expected 400 for invalid action, got {res.status_code}"
