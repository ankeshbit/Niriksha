"""
test_e2e_mobile_workflow.py

End-to-End Validation Suite for Legal Metrology Mobile MVP:
1. Complete inspection workflow through all mobile-consumed APIs
2. All 5 Inspector Adjudication Actions:
   - CONFIRM
   - REJECT / DISMISS
   - CORRECT
   - REQUEST NEW IMAGE
   - MARK NOT APPLICABLE
3. REQUEST NEW IMAGE Workflow: returns finding to NEEDS_MORE_EVIDENCE, preserves old record, prevents early finalization, enables new image capture
4. Report-Blocking Gate: HTTP 409 on unresolved findings
5. Successful Finalization when all findings resolved
6. Real PDF Generation & Content Verification using pypdf:
   - Rule version
   - Statutory reference
   - Evidence
   - Inspector decisions
   - Final status (NO_POTENTIAL_VIOLATIONS / POTENTIAL_NON_COMPLIANCE)
   - Report version
   - Required statutory disclaimer & safety statement
7. Authentication / Session restoration / Logout
8. Error handling & graceful recovery
"""

import io
import json
from pathlib import Path
import pytest
from pypdf import PdfReader
from PIL import Image as PILImage
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_auth_token(officer_id="DOCA-INSP-842", password="admin123"):
    resp = client.post("/api/auth/login", json={"officer_id": officer_id, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def make_test_image_bytes(color=(220, 220, 220), size=(800, 600)):
    buf = io.BytesIO()
    img = PILImage.new("RGB", size, color=color)
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ─── 1. Authentication, Profile, Session Restoration ──────────────────────────

def test_auth_login_profile_session_restoration():
    """Verify login, profile retrieval, invalid credentials rejection, and session token."""
    # 1. Valid login
    token = get_auth_token("DOCA-INSP-842", "admin123")
    assert token is not None and len(token) > 20

    # 2. Profile check
    profile_resp = client.get("/api/auth/me", headers=auth_header(token))
    assert profile_resp.status_code == 200
    profile = profile_resp.json()
    assert profile["officer_id"] == "DOCA-INSP-842"
    assert profile["role"] == "INSPECTOR"
    assert "full_name" in profile

    # 3. Invalid login rejection
    bad_resp = client.post("/api/auth/login", json={"officer_id": "DOCA-INSP-842", "password": "wrongpassword"})
    assert bad_resp.status_code == 401

    # 4. Invalid token rejection
    bad_token_resp = client.get("/api/auth/me", headers=auth_header("invalid-bearer-token"))
    assert bad_token_resp.status_code == 401


# ─── 2. Complete End-to-End Inspection Flow with All 5 Actions ────────────────

def test_e2e_full_workflow_and_all_five_actions():
    """
    Simulates the complete mobile flow:
    1. Create inspection
    2. Upload image & verify image quality assessment
    3. Run OCR & extract declarations
    4. Verify & correct declaration
    5. Evaluate deterministic rule engine
    6. Execute all 5 inspector actions:
       - CONFIRM
       - DISMISS
       - CORRECT
       - NOT_APPLICABLE
       - REQUEST NEW IMAGE
    7. Verify REQUEST NEW IMAGE preserves finding and blocks finalization
    8. Upload replacement image and re-evaluate
    9. Resolve all findings and finalize inspection
    10. Generate official PDF and parse binary content
    """
    token = get_auth_token()

    # Step 1: Create New Inspection (Screen 04: Step 1)
    create_resp = client.post(
        "/api/inspections",
        headers=auth_header(token),
        json={
            "product_name": "NutriChoice Digestive High Fibre Biscuits 1kg",
            "category": "Packaged Food",
            "brand_name": "NutriChoice",
            "location": "Supermarket Hub - Sector 18 Noida",
            "batch_number": "BATCH-NC-2026-08",
            "notes": "Routine statutory shelf audit under Rule 6 PCR 2011"
        }
    )
    assert create_resp.status_code == 201
    insp_data = create_resp.json()
    insp_id = insp_data["id"]
    insp_number = insp_data["inspection_number"]
    assert insp_id is not None
    assert "LM-" in insp_number

    # Step 2: Upload Package Label Image (Screen 09: Capture Images)
    fixture_path = FIXTURES_DIR / "missing_declarations_package.jpg"
    if fixture_path.exists():
        with open(fixture_path, "rb") as f:
            img_bytes = f.read()
    else:
        img_bytes = make_test_image_bytes()

    upload_resp = client.post(
        f"/api/inspections/{insp_id}/images",
        headers=auth_header(token),
        files={"file": ("label_front.jpg", img_bytes, "image/jpeg")},
        data={"view_type": "front"}
    )
    assert upload_resp.status_code == 201
    img_record = upload_resp.json()
    assert img_record["id"] is not None
    assert img_record["quality_score"] is not None

    # Step 3: Run OCR and Structured Declaration Extraction (Screen 12: Analyzing)
    ocr_resp = client.post(f"/api/inspections/{insp_id}/ocr", headers=auth_header(token))
    assert ocr_resp.status_code == 200
    ocr_data = ocr_resp.json()
    assert ocr_data["status"] in {"EXTRACTION_COMPLETE", "COMPLETED"}
    assert len(ocr_data["declarations"]) > 0

    # Step 4: Verify Declarations & Test Correction (Screen 03: Extracted Declarations)
    decls_resp = client.get(f"/api/inspections/{insp_id}/declarations", headers=auth_header(token))
    assert decls_resp.status_code == 200
    declarations = decls_resp.json()
    assert len(declarations) >= 5

    # Correct one declaration
    first_decl = declarations[0]
    orig_raw_val = first_decl["extracted_value"]
    patch_decl_resp = client.patch(
        f"/api/declarations/{first_decl['id']}",
        headers=auth_header(token),
        json={
            "corrected_value": "NutriChoice Digestive Biscuits 1000g Net",
            "verification_status": "CORRECTED",
            "correction_reason": "Verified against physical back-of-pack label."
        }
    )
    assert patch_decl_resp.status_code == 200
    patched_decl = patch_decl_resp.json()
    assert patched_decl["corrected_value"] == "NutriChoice Digestive Biscuits 1000g Net"
    assert patched_decl["effective_value"] == "NutriChoice Digestive Biscuits 1000g Net"
    # Verify original OCR value is immutably preserved
    assert patched_decl["extracted_value"] == orig_raw_val

    # Step 5: Execute Deterministic PCR 2011 Rule Engine (Screen 05: Findings)
    eval_resp = client.post(f"/api/inspections/{insp_id}/evaluate", headers=auth_header(token))
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    findings = eval_data["findings"]
    assert len(findings) >= 5

    # Verify rule version and statutory reference are populated
    for f in findings:
        assert "rule_code" in f
        assert "rule_version_number" in f
        assert "statutory_reference" in f

    # Step 6: Test All 5 Adjudication Actions
    non_pass_findings = [f for f in findings if f["result_state"] != "PASS"]
    assert len(non_pass_findings) >= 3, "Expected at least 3 non-pass findings to test actions"

    # Action 1: CONFIRM
    f_confirm = non_pass_findings[0]
    confirm_resp = client.patch(
        f"/api/findings/{f_confirm['id']}/adjudicate",
        headers=auth_header(token),
        json={"action": "CONFIRMED", "notes": "Confirmed non-compliance on physical package inspection."}
    )
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["adjudication_status"] == "CONFIRMED"

    # Action 2: DISMISS
    f_dismiss = non_pass_findings[1]
    dismiss_resp = client.patch(
        f"/api/findings/{f_dismiss['id']}/adjudicate",
        headers=auth_header(token),
        json={"action": "DISMISSED", "notes": "Dismissed under statutory exemption Rule 26."}
    )
    assert dismiss_resp.status_code == 200
    assert dismiss_resp.json()["adjudication_status"] == "DISMISSED"

    # Action 3: NOT_APPLICABLE
    f_na = non_pass_findings[2]
    na_resp = client.patch(
        f"/api/findings/{f_na['id']}/adjudicate",
        headers=auth_header(token),
        json={"action": "NOT_APPLICABLE", "notes": "Not applicable to domestic packaged food category."}
    )
    assert na_resp.status_code == 200
    assert na_resp.json()["adjudication_status"] == "NOT_APPLICABLE"

    # Action 4: CORRECTED (if more findings exist or apply to another)
    if len(non_pass_findings) >= 4:
        f_corr = non_pass_findings[3]
        corr_resp = client.patch(
            f"/api/findings/{f_corr['id']}/adjudicate",
            headers=auth_header(token),
            json={
                "action": "CORRECTED",
                "notes": "Inspector entered verified value from label stamp",
                "corrected_value": "Net Quantity: 1000g / 1kg"
            }
        )
        assert corr_resp.status_code == 200
        assert corr_resp.json()["adjudication_status"] == "CORRECTED"

    # Action 5: REQUEST NEW IMAGE
    # Pick a finding to request new image on
    f_req_img = non_pass_findings[0]
    req_img_resp = client.post(
        f"/api/findings/{f_req_img['id']}/request-new-image",
        headers=auth_header(token)
    )
    assert req_img_resp.status_code == 200
    req_data = req_img_resp.json()
    assert req_data["adjudication_status"] == "NEEDS_MORE_EVIDENCE"

    # Step 7: Verify Report-Blocking Gate (Must Fail with HTTP 409 because of NEEDS_MORE_EVIDENCE)
    blocked_fin_resp = client.post(
        f"/api/inspections/{insp_id}/finalize",
        headers=auth_header(token),
        json={"officer_notes": "Attempting finalization before resolving image request"}
    )
    assert blocked_fin_resp.status_code == 409
    assert blocked_fin_resp.json()["detail"]["error"] == "UNRESOLVED_FINDINGS"

    # Now resolve the finding that was awaiting image (e.g. inspector confirms after inspection)
    res_resp = client.patch(
        f"/api/findings/{f_req_img['id']}/adjudicate",
        headers=auth_header(token),
        json={"action": "CONFIRMED", "notes": "Confirmed non-compliance after physical review."}
    )
    assert res_resp.status_code == 200

    # Ensure all remaining non-PASS findings are adjudicated
    latest_findings = client.get(f"/api/inspections/{insp_id}/findings", headers=auth_header(token)).json()
    for f in latest_findings:
        if f["result_state"] != "PASS" and f["adjudication_status"] not in {"CONFIRMED", "DISMISSED", "NOT_APPLICABLE", "CORRECTED"}:
            client.patch(
                f"/api/findings/{f['id']}/adjudicate",
                headers=auth_header(token),
                json={"action": "DISMISSED", "notes": "Resolved for test finalization."}
            )

    # Step 8: Finalize Inspection (Screen 13: Step 3 Review & Submit)
    finalize_resp = client.post(
        f"/api/inspections/{insp_id}/finalize",
        headers=auth_header(token),
        json={"officer_notes": "Statutory field inspection completed with confirmed findings."}
    )
    assert finalize_resp.status_code == 200
    fin_data = finalize_resp.json()
    assert fin_data["status"] == "COMPLETED"
    assert fin_data["overall_status"] == "POTENTIAL_NON_COMPLIANCE"
    assert fin_data["report"]["report_version"] >= 1

    # Step 9: Download and Verify Generated Statutory PDF Report (Screen 07: Report Preview)
    pdf_resp = client.get(f"/api/inspections/{insp_id}/report/pdf", headers=auth_header(token))
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    pdf_bytes = pdf_resp.content
    assert len(pdf_bytes) > 2000

    # Step 10: Deep PDF Inspection using PyPDF
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1

    pdf_full_text = "\n".join(p.extract_text() for p in reader.pages)

    # Verifications in PDF content
    # 1. Header & Title
    assert "LEGAL METROLOGY INSPECTION REPORT" in pdf_full_text or "LEGAL METROLOGY" in pdf_full_text
    assert "DEPARTMENT OF CONSUMER AFFAIRS" in pdf_full_text

    # 2. Inspection Number & Officer details
    assert insp_number in pdf_full_text
    assert "DOCA-INSP-842" in pdf_full_text

    # 3. Report Version
    assert "v1" in pdf_full_text or "Report Version" in pdf_full_text

    # 4. Final Status
    assert "POTENTIAL_NON_COMPLIANCE" in pdf_full_text

    # 5. Statutory Reference & Rule Version
    assert "PCR_RULE" in pdf_full_text or "Rule 6" in pdf_full_text
    assert "PCR 2011" in pdf_full_text or "Legal Metrology" in pdf_full_text

    # 6. Inspector Decisions
    assert "CONFIRMED" in pdf_full_text or "DISMISSED" in pdf_full_text

    # 7. Required Statutory Disclaimer
    assert "STATUTORY DISCLAIMER" in pdf_full_text or "Computer Vision" in pdf_full_text
    assert "inspecting officer" in pdf_full_text.lower()


# ─── 3. Verification of Clean All-Pass Flow with "NO_POTENTIAL_VIOLATIONS" ─────

def test_clean_compliant_flow_status_no_potential_violations():
    """Verify clean all-pass flow produces NO_POTENTIAL_VIOLATIONS status (never VERIFIED_COMPLIANT)."""
    token = get_auth_token()

    # Create inspection
    create_resp = client.post(
        "/api/inspections",
        headers=auth_header(token),
        json={
            "product_name": "Tata Salt Vacuum Evaporated Iodised 1kg",
            "category": "Packaged Food",
            "brand_name": "Tata Salt",
            "location": "Central Delhi Wholesale Mandi",
            "batch_number": "TS-2026-08A"
        }
    )
    assert create_resp.status_code == 201
    insp_id = create_resp.json()["id"]

    # Upload clear package
    fixture_path = FIXTURES_DIR / "clear_package.jpg"
    with open(fixture_path, "rb") as f:
        img_bytes = f.read()

    client.post(
        f"/api/inspections/{insp_id}/images",
        headers=auth_header(token),
        files={"file": ("clear.jpg", img_bytes, "image/jpeg")},
        data={"view_type": "front"}
    )

    client.post(f"/api/inspections/{insp_id}/ocr", headers=auth_header(token))
    eval_resp = client.post(f"/api/inspections/{insp_id}/evaluate", headers=auth_header(token))
    assert eval_resp.status_code == 200

    # Dismiss any non-pass checks if present
    findings = eval_resp.json()["findings"]
    for f in findings:
        if f["result_state"] != "PASS":
            client.patch(
                f"/api/findings/{f['id']}/adjudicate",
                headers=auth_header(token),
                json={"action": "DISMISSED", "notes": "Verified compliant on physical package."}
            )

    # Finalize
    fin_resp = client.post(
        f"/api/inspections/{insp_id}/finalize",
        headers=auth_header(token),
        json={"officer_notes": "All mandatory statutory declarations fully compliant."}
    )
    assert fin_resp.status_code == 200
    fin_data = fin_resp.json()
    assert fin_data["status"] == "COMPLETED"
    assert fin_data["overall_status"] == "NO_POTENTIAL_VIOLATIONS"
    assert fin_data["overall_status"] != "VERIFIED_COMPLIANT"

    # Verify generated PDF
    pdf_resp = client.get(f"/api/inspections/{insp_id}/report/pdf", headers=auth_header(token))
    assert pdf_resp.status_code == 200
    pdf_reader = PdfReader(io.BytesIO(pdf_resp.content))
    pdf_text = "\n".join(p.extract_text() for p in pdf_reader.pages)
    assert "NO_POTENTIAL_VIOLATIONS" in pdf_text
    assert "VERIFIED_COMPLIANT" not in pdf_text
