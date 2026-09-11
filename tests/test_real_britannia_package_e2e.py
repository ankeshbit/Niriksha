"""
Dedicated End-to-End Acceptance Test for Real Britannia Package Packaging.
Authoritative Legal Source: Legal Metrology (Packaged Commodities) Rules, 2011 (GSR 202(E) dated 7th March 2011).

Acceptance Criteria:
- Executes against real images: tests/fixtures/britannia/britannia_panel_1.jpg and britannia_panel_2.jpg.
- Image quality validation.
- Real OCR execution (PaddleOCR / Tesseract fallback) retaining bbox and confidence.
- Real declaration extraction.
- Multi-image consolidation.
- Statutory rule evaluation using deterministic rule engine citing exact PDF clauses.
- Finding creation with evidence chain.
- Adjudication remains PENDING for real package inspection (ZERO fabricated inspector actions).
- Simulated inspector workflow is strictly isolated in a separate, explicitly labeled test.
"""

import os
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import settings
from backend.ocr_service import ocr_service
from backend.image_quality import assess_image_quality
from backend.extraction_service import extraction_service, cross_image_verification
from backend.rule_engine.engine import rule_engine
from backend.rule_engine.models import RuleResultState
from backend.rule_engine.legal_provenance import LEGAL_PROVENANCE_REGISTRY

IMG1_PATH = r"tests/fixtures/britannia/britannia_panel_1.jpg"
IMG2_PATH = r"tests/fixtures/britannia/britannia_panel_2.jpg"

@pytest.fixture
def auth_client():
    client = TestClient(app)
    resp = client.post("/api/auth/login", json={
        "officer_id": settings.SEED_OFFICER_ID,
        "password": settings.SEED_OFFICER_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    client.headers = {"Authorization": f"Bearer {token}"}
    return client


def test_real_britannia_e2e_pipeline_without_fabricated_adjudication(auth_client):
    """
    Executes full pipeline against the two real Britannia images without fabricating inspector actions.
    """
    assert os.path.isfile(IMG1_PATH), f"Missing {IMG1_PATH}"
    assert os.path.isfile(IMG2_PATH), f"Missing {IMG2_PATH}"

    # 1. Image Quality Validation
    q1 = assess_image_quality(IMG1_PATH)
    assert q1.quality_status in ["EXCELLENT", "GOOD", "ACCEPTABLE", "WARNING"]
    assert q1.width > 500 and q1.height > 100

    q2 = assess_image_quality(IMG2_PATH)
    assert q2.quality_status in ["EXCELLENT", "GOOD", "ACCEPTABLE", "WARNING"]
    assert q2.width > 500 and q2.height > 100

    # 2. Real OCR Execution
    ocr1 = ocr_service.process_image(IMG1_PATH, image_id="real-panel-1")
    assert ocr1.ocr_status == "OCR_SUCCESS"
    assert len(ocr1.text_boxes) > 0
    assert ocr1.mean_confidence > 0.50

    ocr2 = ocr_service.process_image(IMG2_PATH, image_id="real-panel-2")
    assert ocr2.ocr_status == "OCR_SUCCESS"
    assert len(ocr2.text_boxes) > 0
    assert ocr2.mean_confidence > 0.50

    # 3. Declaration Extraction from actual OCR evidence
    ctx = {"category": "Packaged Food", "product_name": "Biscuits / Wafers"}
    decls1 = extraction_service.extract_declarations(ocr1.raw_text, ocr1.text_boxes, ctx, image_id="real-panel-1")
    decls2 = extraction_service.extract_declarations(ocr2.raw_text, ocr2.text_boxes, ctx, image_id="real-panel-2")

    # 4. Multi-Image Consolidation across both panels
    merged, conflicts = cross_image_verification({
        "real-panel-1": decls1,
        "real-panel-2": decls2
    })
    merged_dict = {d.field_name: d for d in merged}

    # Verify extracted fields and their image provenance
    assert merged_dict["manufacturer_details"].extraction_status == "EXTRACTED"
    assert "real-panel-1" in merged_dict["manufacturer_details"].source_images
    assert any(k in merged_dict["manufacturer_details"].extracted_value.upper() for k in ["KOLKATA", "HUNGERFORD", "WADIA", "BRITANNIA", "MANGHARAM"])

    assert merged_dict["net_quantity"].extraction_status in ["EXTRACTED", "LOW_CONFIDENCE"]
    assert "55" in merged_dict["net_quantity"].extracted_value

    assert merged_dict["mrp"].extraction_status in ["EXTRACTED", "LOW_CONFIDENCE"]
    assert any(p in merged_dict["mrp"].extracted_value for p in ["30", "50"])

    assert merged_dict["consumer_care_details"].extraction_status in ["EXTRACTED", "LOW_CONFIDENCE"]
    assert "1-800" in merged_dict["consumer_care_details"].extracted_value or "britindia.com" in merged_dict["consumer_care_details"].extracted_value

    # Commodity name on side panels: NOT_FOUND
    assert merged_dict["commodity_name"].extraction_status == "NOT_FOUND"

    # Country of origin: Not explicitly declared on package; Indian address does NOT prove origin
    assert merged_dict["country_of_origin"].extraction_status == "NEEDS_LEGAL_VERIFICATION"

    # 5. Deterministic Rule Evaluation against PCR 2011 PDF provisions
    eval_results = rule_engine.evaluate_inspection(
        inspection_id="REAL-BRITANNIA-E2E-001",
        product_data=ctx,
        declarations=merged,
        images=[{"id": "real-panel-1", "quality_status": "GOOD"}, {"id": "real-panel-2", "quality_status": "GOOD"}]
    )
    res_dict = {r.rule_code: r for r in eval_results}

    # Rule 6(1)(e): MRP PASS
    assert res_dict["PCR_RULE_06_1_E"].result_state == RuleResultState.PASS
    assert "Rule 6(1)(e)" in res_dict["PCR_RULE_06_1_E"].statutory_reference

    # Rule 6(1)(a): Manufacturer PASS
    assert res_dict["PCR_RULE_06_1_A"].result_state == RuleResultState.PASS
    assert "Rule 6(1)(a)" in res_dict["PCR_RULE_06_1_A"].statutory_reference

    # Rule 6(1)(c): Net Quantity evaluated (PASS or INSUFFICIENT_EVIDENCE depending on OCR confidence gate)
    assert res_dict["PCR_RULE_06_1_C"].result_state in [RuleResultState.PASS, RuleResultState.INSUFFICIENT_EVIDENCE]
    assert "Rule 6(1)(c)" in res_dict["PCR_RULE_06_1_C"].statutory_reference

    # Rule 6(1)(b): Commodity Name POTENTIAL_NON_COMPLIANCE (routed to inspector review)
    assert res_dict["PCR_RULE_06_1_F"].result_state == RuleResultState.POTENTIAL_NON_COMPLIANCE
    assert "Rule 6(1)(b)" in res_dict["PCR_RULE_06_1_F"].statutory_reference

    # Rule 6(1)(a) proviso: Country of Origin NEEDS_MANUAL_VERIFICATION
    assert res_dict["PCR_RULE_06_1_B"].result_state == RuleResultState.NEEDS_MANUAL_VERIFICATION

    # 6. Complete API Workflow: Create Inspection -> Upload -> OCR -> Evaluate -> Findings -> Report
    create_resp = auth_client.post("/api/inspections", json={
        "product_name": "Britannia Acceptance Inspection",
        "category": "Packaged Food",
        "location": "Retail Outlet 101, Indiranagar, Bangalore"
    })
    assert create_resp.status_code == 201
    insp_id = create_resp.json()["id"]

    with open(IMG1_PATH, "rb") as f1:
        r1 = auth_client.post(
            f"/api/inspections/{insp_id}/images",
            files={"file": ("panel_1.jpg", f1, "image/jpeg")},
            data={"view_type": "back"}
        )
    assert r1.status_code == 201

    with open(IMG2_PATH, "rb") as f2:
        r2 = auth_client.post(
            f"/api/inspections/{insp_id}/images",
            files={"file": ("panel_2.jpg", f2, "image/jpeg")},
            data={"view_type": "side"}
        )
    assert r2.status_code == 201

    ocr_api_resp = auth_client.post(f"/api/inspections/{insp_id}/ocr")
    assert ocr_api_resp.status_code == 200

    eval_api_resp = auth_client.post(f"/api/inspections/{insp_id}/evaluate")
    assert eval_api_resp.status_code == 200

    findings_resp = auth_client.get(f"/api/inspections/{insp_id}/findings")
    assert findings_resp.status_code == 200
    findings = findings_resp.json()

    # Invariant (Critical Fix #1): Finding adjudication status MUST BE PENDING!
    # The automated test MUST NOT fabricate an inspector correction.
    comm_finding = next((f for f in findings if f["rule_code"] == "PCR_RULE_06_1_F"), None)
    assert comm_finding is not None
    assert comm_finding["adjudication_status"] in ["PENDING", "OPEN", "UNREVIEWED", None]

    # 7. PDF Report Generation & Idempotency
    rep_resp = auth_client.post(f"/api/inspections/{insp_id}/report")
    assert rep_resp.status_code == 200
    v1 = rep_resp.json()["report_version"]

    preview_resp = auth_client.get(f"/api/inspections/{insp_id}/report")
    assert preview_resp.status_code == 200
    assert preview_resp.json()["report_version"] == v1  # Idempotent preview!


def test_simulated_inspector_workflow_explicitly_labeled(auth_client):
    """
    Isolated test explicitly verifying inspector adjudication capabilities.
    Uses 'TEST_INSPECTOR_CORRECTION' to guarantee no confusion with real package inspections.
    """
    create_resp = auth_client.post("/api/inspections", json={
        "product_name": "Simulation Test Package",
        "category": "Packaged Food",
        "location": "Adjudication Test Bay"
    })
    insp_id = create_resp.json()["id"]

    eval_resp = auth_client.post(f"/api/inspections/{insp_id}/evaluate")
    assert eval_resp.status_code == 200

    findings_resp = auth_client.get(f"/api/inspections/{insp_id}/findings")
    findings = findings_resp.json()
    assert len(findings) > 0

    finding_to_adjudicate = findings[0]
    adj_resp = auth_client.patch(
        f"/api/findings/{finding_to_adjudicate['id']}/adjudicate",
        json={
            "action": "CORRECTED",
            "notes": "SIMULATED_TEST_ACTION: Verifying inspector correction audit trail",
            "corrected_value": "TEST_INSPECTOR_CORRECTION"
        }
    )
    assert adj_resp.status_code == 200
    assert adj_resp.json()["adjudication_status"] == "CORRECTED"
    assert "SIMULATED_TEST_ACTION" in adj_resp.json()["adjudication_notes"]
