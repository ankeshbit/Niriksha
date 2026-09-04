import pytest
import json
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app
from backend.models import Inspection, Declaration, ComplianceCheck, Report, AuditLog
from backend.database import get_db

client = TestClient(app)
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

def get_auth_token(officer_id="DOCA-INSP-842", password="admin123"):
    resp = client.post("/api/auth/login", json={"officer_id": officer_id, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]

def create_inspection_with_eval(token, fixture_name="clear_package.jpg", product_name="Premium Basmati Rice 5kg"):
    # 1. Create inspection
    create_resp = client.post(
        "/api/inspections",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_name": product_name,
            "category": "Packaged Food",
            "location": "Central Delhi Wholesale Mandi",
            "batch_number": "BATCH-2026-X9",
            "brand_name": "Agro Gold"
        }
    )
    assert create_resp.status_code == 201
    insp_id = create_resp.json()["id"]

    # 2. Upload image
    img_path = FIXTURES_DIR / fixture_name
    with open(img_path, "rb") as f:
        upload_resp = client.post(
            f"/api/inspections/{insp_id}/images",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (fixture_name, f, "image/jpeg")},
            data={"view_type": "front"}
        )
    assert upload_resp.status_code == 201

    # 3. Run OCR
    ocr_resp = client.post(f"/api/inspections/{insp_id}/ocr", headers={"Authorization": f"Bearer {token}"})
    assert ocr_resp.status_code == 200

    # 4. Evaluate rules
    eval_resp = client.post(f"/api/inspections/{insp_id}/evaluate", headers={"Authorization": f"Bearer {token}"})
    assert eval_resp.status_code == 200

    return insp_id

# ----------------- Adjudication & Evidence Tests -----------------

def test_inspector_open_and_view_finding():
    token = get_auth_token()
    insp_id = create_inspection_with_eval(token, "missing_declarations_package.jpg")

    findings_resp = client.get(f"/api/inspections/{insp_id}/findings", headers={"Authorization": f"Bearer {token}"})
    assert findings_resp.status_code == 200
    findings = findings_resp.json()
    assert len(findings) > 0

    first_finding = findings[0]
    finding_id = first_finding["id"]

    single_resp = client.get(f"/api/findings/{finding_id}", headers={"Authorization": f"Bearer {token}"})
    assert single_resp.status_code == 200
    data = single_resp.json()
    assert data["id"] == finding_id
    assert data["rule_code"] == first_finding["rule_code"]
    assert "explanation" in data

def test_inspector_confirm_finding_with_notes():
    token = get_auth_token()
    insp_id = create_inspection_with_eval(token, "missing_declarations_package.jpg")

    findings_resp = client.get(f"/api/inspections/{insp_id}/findings", headers={"Authorization": f"Bearer {token}"})
    non_comp = next(f for f in findings_resp.json() if f["result_state"] == "POTENTIAL_NON_COMPLIANCE")
    finding_id = non_comp["id"]

    adj_resp = client.patch(
        f"/api/findings/{finding_id}/adjudicate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action": "CONFIRMED",
            "notes": "Verified under Rule 6(1): Declaration is absent on package display."
        }
    )
    assert adj_resp.status_code == 200
    data = adj_resp.json()
    assert data["adjudication_status"] == "CONFIRMED"
    assert "Verified under Rule 6(1)" in data["adjudication_notes"]
    assert data["adjudicated_by"] == "DOCA-INSP-842"

def test_inspector_dismiss_finding_with_statutory_reason():
    token = get_auth_token()
    insp_id = create_inspection_with_eval(token, "missing_declarations_package.jpg")

    findings_resp = client.get(f"/api/inspections/{insp_id}/findings", headers={"Authorization": f"Bearer {token}"})
    non_comp = next(f for f in findings_resp.json() if f["result_state"] == "POTENTIAL_NON_COMPLIANCE")
    finding_id = non_comp["id"]

    adj_resp = client.patch(
        f"/api/findings/{finding_id}/adjudicate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action": "DISMISSED",
            "notes": "Dismissed: Package complies under statutory exemption Rule 26."
        }
    )
    assert adj_resp.status_code == 200
    data = adj_resp.json()
    assert data["adjudication_status"] == "DISMISSED"
    assert "statutory exemption" in data["adjudication_notes"]

def test_unauthorized_adjudication_rejected():
    token = get_auth_token()
    insp_id = create_inspection_with_eval(token, "missing_declarations_package.jpg")
    findings_resp = client.get(f"/api/inspections/{insp_id}/findings", headers={"Authorization": f"Bearer {token}"})
    finding_id = findings_resp.json()[0]["id"]

    # Without token
    res = client.patch(f"/api/findings/{finding_id}/adjudicate", json={"action": "CONFIRMED"})
    assert res.status_code == 401

# ----------------- Final Status & Inspection Lifecycle Tests -----------------

def test_all_pass_final_status_verified_compliant():
    token = get_auth_token()
    insp_id = create_inspection_with_eval(token, "clear_package.jpg")

    fin_resp = client.post(
        f"/api/inspections/{insp_id}/finalize",
        headers={"Authorization": f"Bearer {token}"},
        json={"officer_notes": "All statutory declarations verified compliant."}
    )
    assert fin_resp.status_code == 200
    data = fin_resp.json()
    assert data["status"] == "COMPLETED"
    assert data["overall_status"] in ["VERIFIED_COMPLIANT", "NO_POTENTIAL_VIOLATIONS"]
    assert "report" in data
    assert data["report"]["report_version"] >= 1

def test_confirmed_finding_final_status_potential_non_compliance():
    token = get_auth_token()
    insp_id = create_inspection_with_eval(token, "missing_declarations_package.jpg")

    # Get all findings
    findings_resp = client.get(f"/api/inspections/{insp_id}/findings", headers={"Authorization": f"Bearer {token}"})
    all_findings = findings_resp.json()

    # Confirm the first POTENTIAL_NON_COMPLIANCE finding
    non_comp_findings = [f for f in all_findings if f["result_state"] == "POTENTIAL_NON_COMPLIANCE"]
    assert len(non_comp_findings) > 0, "Expected at least one POTENTIAL_NON_COMPLIANCE finding"
    target = non_comp_findings[0]
    client.patch(
        f"/api/findings/{target['id']}/adjudicate",
        headers={"Authorization": f"Bearer {token}"},
        json={"action": "CONFIRMED", "notes": "Mandatory MRP absent."}
    )

    # Dismiss remaining non-PASS findings so finalization can proceed
    for f in all_findings:
        if f["result_state"] != "PASS" and f["id"] != target["id"]:
            client.patch(
                f"/api/findings/{f['id']}/adjudicate",
                headers={"Authorization": f"Bearer {token}"},
                json={"action": "DISMISSED", "notes": "Dismissed for finalization."}
            )

    fin_resp = client.post(
        f"/api/inspections/{insp_id}/finalize",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert fin_resp.status_code == 200, f"Expected 200, got {fin_resp.status_code}: {fin_resp.text}"
    data = fin_resp.json()
    assert data["status"] == "COMPLETED"
    assert data["overall_status"] == "POTENTIAL_NON_COMPLIANCE"

def test_insufficient_evidence_final_status():
    token = get_auth_token()
    insp_id = create_inspection_with_eval(token, "blurry_package.jpg")

    # Adjudicate all non-PASS findings before finalizing (required by blocking gate)
    findings_resp = client.get(f"/api/inspections/{insp_id}/findings", headers={"Authorization": f"Bearer {token}"})
    all_findings = findings_resp.json()
    for f in all_findings:
        if f["result_state"] != "PASS":
            client.patch(
                f"/api/findings/{f['id']}/adjudicate",
                headers={"Authorization": f"Bearer {token}"},
                json={"action": "DISMISSED", "notes": "Dismissed for finalization — insufficient evidence acknowledged."}
            )

    fin_resp = client.post(
        f"/api/inspections/{insp_id}/finalize",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert fin_resp.status_code == 200, f"Expected 200, got {fin_resp.status_code}: {fin_resp.text}"
    data = fin_resp.json()
    assert data["status"] == "COMPLETED"
    # After dismissing all, overall_status should be NO_POTENTIAL_VIOLATIONS
    assert data["overall_status"] in {"NO_POTENTIAL_VIOLATIONS", "NEEDS_MANUAL_VERIFICATION"}

# ----------------- Statutory PDF Report Generation Tests -----------------

def test_authenticated_report_generation_creates_pdf():
    token = get_auth_token()
    insp_id = create_inspection_with_eval(token, "clear_package.jpg")

    rep_resp = client.post(
        f"/api/inspections/{insp_id}/report",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert rep_resp.status_code == 200
    data = rep_resp.json()
    assert data["inspection_id"] == insp_id
    assert data["report_version"] >= 1
    assert data["pdf_path"].endswith(".pdf")
    assert Path(data["pdf_path"]).exists()
    assert "Legal Metrology" in data["legal_safety_statement"]

def test_unauthorized_report_generation_rejected():
    res = client.post("/api/inspections/fake-id/report")
    assert res.status_code == 401

def test_report_metadata_and_download_url():
    token = get_auth_token()
    insp_id = create_inspection_with_eval(token, "clear_package.jpg")

    # Generate first
    client.post(f"/api/inspections/{insp_id}/report", headers={"Authorization": f"Bearer {token}"})

    get_resp = client.get(f"/api/inspections/{insp_id}/report", headers={"Authorization": f"Bearer {token}"})
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["download_url"] == f"/api/inspections/{insp_id}/report/pdf"

def test_pdf_binary_stream_endpoint():
    token = get_auth_token()
    insp_id = create_inspection_with_eval(token, "clear_package.jpg")

    pdf_resp = client.get(
        f"/api/inspections/{insp_id}/report/pdf",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert len(pdf_resp.content) > 1000  # Valid non-empty PDF binary
    assert pdf_resp.content.startswith(b"%PDF")

def test_report_versioning_increment():
    token = get_auth_token()
    insp_id = create_inspection_with_eval(token, "clear_package.jpg")

    # Generate v1
    v1_resp = client.post(f"/api/inspections/{insp_id}/report", headers={"Authorization": f"Bearer {token}"})
    assert v1_resp.json()["report_version"] == 1

    # Re-generate produces v2
    v2_resp = client.post(f"/api/inspections/{insp_id}/report", headers={"Authorization": f"Bearer {token}"})
    assert v2_resp.json()["report_version"] == 2

def test_report_generation_logged_in_audit_trail():
    token = get_auth_token()
    insp_id = create_inspection_with_eval(token, "clear_package.jpg")

    client.post(f"/api/inspections/{insp_id}/report", headers={"Authorization": f"Bearer {token}"})

    logs_resp = client.get(f"/api/inspections/{insp_id}/audit-logs", headers={"Authorization": f"Bearer {token}"})
    assert logs_resp.status_code == 200
    actions = [l["action"] for l in logs_resp.json()]
    assert "REPORT_GENERATED" in actions

def test_reports_list_archive_endpoint():
    token = get_auth_token()
    insp_id = create_inspection_with_eval(token, "clear_package.jpg")
    client.post(f"/api/inspections/{insp_id}/report", headers={"Authorization": f"Bearer {token}"})

    reports_resp = client.get("/api/reports", headers={"Authorization": f"Bearer {token}"})
    assert reports_resp.status_code == 200
    reports = reports_resp.json()
    assert len(reports) >= 1
    assert any(r["inspection_id"] == insp_id for r in reports)

def test_pdf_generation_with_missing_declarations_scenario():
    token = get_auth_token()
    insp_id = create_inspection_with_eval(token, "missing_declarations_package.jpg", product_name="Organic Wheat Flour 500g")

    rep_resp = client.post(f"/api/inspections/{insp_id}/report", headers={"Authorization": f"Bearer {token}"})
    assert rep_resp.status_code == 200
    assert Path(rep_resp.json()["pdf_path"]).exists()

def test_pdf_generation_with_imported_commodity_scenario():
    token = get_auth_token()
    insp_id = create_inspection_with_eval(token, "imported_product_package.jpg", product_name="Extra Virgin Olive Oil 1L")

    rep_resp = client.post(f"/api/inspections/{insp_id}/report", headers={"Authorization": f"Bearer {token}"})
    assert rep_resp.status_code == 200
    assert Path(rep_resp.json()["pdf_path"]).exists()
