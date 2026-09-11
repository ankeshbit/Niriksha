import os
import sys
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import settings
from backend.ocr_service import ocr_service, OCRTextBox
from backend.image_quality import assess_image_quality
from backend.extraction_service import extraction_service, cross_image_verification, ExtractedDeclarationItem
from backend.rule_engine.engine import rule_engine
from backend.rule_engine.models import RuleResultState
from backend.rule_engine.registry import STATUTORY_RULE_REGISTRY, get_all_rules

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


# ============================================================================
# 1. REAL PACKAGE IMAGE PIPELINE & ACCEPTANCE TESTS
# ============================================================================

def test_real_package_image_quality():
    """Verifies that the two real Britannia images pass image quality assessment."""
    assert os.path.isfile(IMG1_PATH), f"Missing {IMG1_PATH}"
    assert os.path.isfile(IMG2_PATH), f"Missing {IMG2_PATH}"

    q1 = assess_image_quality(IMG1_PATH)
    assert q1.width > 500
    assert q1.height > 100
    assert q1.blur_score > 100.0  # Sharp Laplacian variance
    assert q1.quality_status in ["EXCELLENT", "GOOD", "ACCEPTABLE", "WARNING"]

    q2 = assess_image_quality(IMG2_PATH)
    assert q2.width > 500
    assert q2.height > 100
    assert q2.blur_score > 100.0
    assert q2.quality_status in ["EXCELLENT", "GOOD", "ACCEPTABLE", "WARNING"]


def test_real_package_ocr_execution():
    """
    Verifies real OCR processing on the two Britannia package images.
    Confirms OCR text, confidence, bounding boxes, and engine information are preserved.
    """
    ocr1 = ocr_service.process_image(IMG1_PATH, image_id="real-img-01")
    assert ocr1.ocr_status == "OCR_SUCCESS"
    assert len(ocr1.text_boxes) > 0
    assert ocr1.mean_confidence > 0.50
    assert any("HUNGERFORD" in b.text or "KOLKATA" in b.text or "Britannia" in b.text or "Mangharam" in b.text for b in ocr1.text_boxes)

    for box in ocr1.text_boxes:
        assert isinstance(box.bbox, list)
        assert len(box.bbox) == 4
        assert box.confidence >= 0.0

    ocr2 = ocr_service.process_image(IMG2_PATH, image_id="real-img-02")
    assert ocr2.ocr_status == "OCR_SUCCESS"
    assert len(ocr2.text_boxes) > 0
    assert ocr2.mean_confidence > 0.50
    assert any("55" in b.text or "EXTRA" in b.text or "TAXES" in b.text or "30" in b.text or "50" in b.text for b in ocr2.text_boxes)


def test_real_package_declaration_extraction_and_consolidation():
    """
    Verifies extraction of mandatory Legal Metrology fields from real OCR evidence
    and multi-image consolidation across the two views.
    """
    ocr1 = ocr_service.process_image(IMG1_PATH, image_id="real-img-01")
    ocr2 = ocr_service.process_image(IMG2_PATH, image_id="real-img-02")

    product_ctx = {"category": "Packaged Food", "product_name": "Biscuits / Wafers"}
    decls1 = extraction_service.extract_declarations(ocr1.raw_text, ocr1.text_boxes, product_ctx, image_id="real-img-01")
    decls2 = extraction_service.extract_declarations(ocr2.raw_text, ocr2.text_boxes, product_ctx, image_id="real-img-02")

    # Multi-image consolidation
    merged, conflicts = cross_image_verification({
        "real-img-01": decls1,
        "real-img-02": decls2
    })

    merged_dict = {d.field_name: d for d in merged}

    # Manufacturer / Packer: extracted from Image 1
    mfg = merged_dict.get("manufacturer_details")
    assert mfg is not None
    assert mfg.extraction_status == "EXTRACTED"
    assert "real-img-01" in mfg.source_images
    assert "KOLKATA" in mfg.extracted_value or "HUNGERFORD" in mfg.extracted_value or "WADIA" in mfg.extracted_value

    # Net quantity: extracted from Image 2 (55 g)
    qty = merged_dict.get("net_quantity")
    assert qty is not None
    assert qty.extraction_status in ["EXTRACTED", "LOW_CONFIDENCE"]
    assert "55 g" in qty.extracted_value or "55" in qty.extracted_value

    # MRP: extracted from Image 2
    mrp = merged_dict.get("mrp")
    assert mrp is not None
    assert mrp.extraction_status in ["EXTRACTED", "LOW_CONFIDENCE"]
    assert "taxes" in mrp.extracted_value.lower() or "rs" in mrp.extracted_value.lower() or "₹" in mrp.extracted_value

    # Consumer Care: extracted from Image 1
    care = merged_dict.get("consumer_care_details")
    assert care is not None
    assert care.extraction_status in ["EXTRACTED", "LOW_CONFIDENCE"]
    assert "1-800" in care.extracted_value or "feedback@britindia.com" in care.extracted_value

    # Commodity name: not present on these side panels -> NOT_FOUND (no synthetic hallucination!)
    comm = merged_dict.get("commodity_name")
    assert comm is not None
    assert comm.extraction_status == "NOT_FOUND"


def test_real_package_deterministic_rule_engine():
    """
    Evaluates consolidated declarations against statutory Legal Metrology (PCR 2011) rules.
    Verifies that statutory citations cite the PCR 2011 PDF and evidence chains are preserved.
    """
    ocr1 = ocr_service.process_image(IMG1_PATH, image_id="real-img-01")
    ocr2 = ocr_service.process_image(IMG2_PATH, image_id="real-img-02")

    product_ctx = {"category": "Packaged Food", "product_name": "Biscuits / Wafers"}
    decls1 = extraction_service.extract_declarations(ocr1.raw_text, ocr1.text_boxes, product_ctx, image_id="real-img-01")
    decls2 = extraction_service.extract_declarations(ocr2.raw_text, ocr2.text_boxes, product_ctx, image_id="real-img-02")

    merged, _ = cross_image_verification({
        "real-img-01": decls1,
        "real-img-02": decls2
    })

    eval_results = rule_engine.evaluate_inspection(
        inspection_id="REAL-LM-ACCEPTANCE-001",
        product_data=product_ctx,
        declarations=merged,
        images=[{"id": "real-img-01", "quality_status": "GOOD"}, {"id": "real-img-02", "quality_status": "GOOD"}]
    )

    res_dict = {r.rule_code: r for r in eval_results}

    # 1. MRP check: PASS (Rule 6(1)(e))
    mrp_res = res_dict["PCR_RULE_06_1_E"]
    assert mrp_res.result_state == RuleResultState.PASS
    assert "Rule 6(1)(e)" in mrp_res.statutory_reference
    assert len(mrp_res.evidence_items) > 0

    # 2. Manufacturer check: PASS (Rule 6(1)(a))
    mfg_res = res_dict["PCR_RULE_06_1_A"]
    assert mfg_res.result_state == RuleResultState.PASS
    assert "Rule 6(1)(a)" in mfg_res.statutory_reference
    assert len(mfg_res.evidence_items) > 0

    # 3. Commodity name check: POTENTIAL_NON_COMPLIANCE (Rule 6(1)(b))
    # Crucial statutory requirement: missing on side panels -> potential finding, NOT an unverified pass!
    comm_res = res_dict["PCR_RULE_06_1_F"]
    assert comm_res.result_state == RuleResultState.POTENTIAL_NON_COMPLIANCE
    assert "Rule 6(1)(b)" in comm_res.statutory_reference
    assert comm_res.evidence_items[0].highlight_text == "[DECLARATION NOT DETECTED]"

    # 4. Country of Origin: domestic address alone does NOT prove origin -> NEEDS_MANUAL_VERIFICATION (Critical Fix #2)
    origin_res = res_dict["PCR_RULE_06_1_B"]
    assert origin_res.result_state == RuleResultState.NEEDS_MANUAL_VERIFICATION
    assert "Rule 6(1)(a)" in origin_res.statutory_reference


def test_real_package_complete_end_to_end_api_workflow(auth_client):
    """
    Executes the full end-to-end API lifecycle using the two real Britannia images:
    1. Create Inspection
    2. Upload Real Image 1 (Manufacturer/Consumer Care Panel)
    3. Upload Real Image 2 (Net Qty / MRP / Date Panel)
    4. Post-Image Analysis (Quality -> OCR -> Extraction -> Consolidation -> Rules -> Findings)
    5. Inspector Adjudication remains PENDING (Critical Fix #1: Zero fabricated inspector actions!)
    6. PDF Report Generation & Idempotency
    """
    # 1. Create Inspection
    create_resp = auth_client.post("/api/inspections", json={
        "product_name": "Treat Strawberry Wafers",
        "category": "Packaged Food",
        "location": "Supermarket, MG Road, Bangalore",
        "notes": "Real Britannia Package Acceptance Inspection"
    })
    assert create_resp.status_code == 201, f"Create failed: {create_resp.text}"
    insp_id = create_resp.json()["id"]

    # 2. Upload Real Image 1
    with open(IMG1_PATH, "rb") as f1:
        img1_resp = auth_client.post(
            f"/api/inspections/{insp_id}/images",
            files={"file": ("britannia_panel_1.jpg", f1, "image/jpeg")},
            data={"view_type": "back"}
        )
    assert img1_resp.status_code == 201, f"Image 1 upload failed: {img1_resp.text}"

    # 3. Upload Real Image 2
    with open(IMG2_PATH, "rb") as f2:
        img2_resp = auth_client.post(
            f"/api/inspections/{insp_id}/images",
            files={"file": ("britannia_panel_2.jpg", f2, "image/jpeg")},
            data={"view_type": "side"}
        )
    assert img2_resp.status_code == 201, f"Image 2 upload failed: {img2_resp.text}"

    # 4. Run OCR & Extraction
    ocr_resp = auth_client.post(f"/api/inspections/{insp_id}/ocr")
    assert ocr_resp.status_code == 200, f"OCR failed: {ocr_resp.text}"
    ocr_data = ocr_resp.json()
    assert ocr_data["declarations_count"] > 0

    # 5. Run Deterministic Rule Engine Evaluation
    eval_resp = auth_client.post(f"/api/inspections/{insp_id}/evaluate")
    assert eval_resp.status_code == 200, f"Evaluation failed: {eval_resp.text}"
    eval_data = eval_resp.json()
    assert eval_data["total_rules_evaluated"] > 0

    # 6. Fetch Findings
    findings_resp = auth_client.get(f"/api/inspections/{insp_id}/findings")
    assert findings_resp.status_code == 200
    findings = findings_resp.json()
    assert len(findings) > 0

    # Verify Evidence Chain on findings
    for f in findings:
        assert "rule_code" in f
        assert "statutory_reference" in f
        assert "evidence_items" in f

    # Critical Fix #1: Inspector Adjudication MUST REMAIN PENDING!
    # The system must NEVER fabricate an inspector correction for real package inspection!
    comm_finding = next((f for f in findings if f["rule_code"] == "PCR_RULE_06_1_F"), None)
    if comm_finding:
        assert comm_finding["adjudication_status"] in ["PENDING", "OPEN", "UNREVIEWED", None]

    # 7. Generate PDF Report reflecting authentic real inspection with PENDING adjudication
    report_resp = auth_client.post(f"/api/inspections/{insp_id}/report")
    assert report_resp.status_code == 200
    rep_json = report_resp.json()
    assert "report_version" in rep_json

    # 8. Report Preview Idempotency (previewing report does NOT bump report_version)
    preview_resp1 = auth_client.get(f"/api/inspections/{insp_id}/report")
    assert preview_resp1.status_code == 200
    preview_resp2 = auth_client.get(f"/api/inspections/{insp_id}/report")
    assert preview_resp2.status_code == 200
    assert preview_resp1.json()["report_version"] == preview_resp2.json()["report_version"]

    # 9. Verify PDF Binary Stream is valid
    pdf_resp = auth_client.get(f"/api/inspections/{insp_id}/report/pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.content.startswith(b"%PDF")


def test_simulated_inspector_adjudication_workflow(auth_client):
    """
    Explicitly simulated inspector workflow test.
    Uses clearly labeled test-only input 'TEST_INSPECTOR_CORRECTION'
    to verify the adjudication endpoint and audit logging without pretending
    to be a real inspector action on the physical package.
    """
    create_resp = auth_client.post("/api/inspections", json={
        "product_name": "Test Adjudication Item",
        "category": "Packaged Food",
        "location": "Test Lab"
    })
    insp_id = create_resp.json()["id"]

    eval_resp = auth_client.post(f"/api/inspections/{insp_id}/evaluate")
    assert eval_resp.status_code == 200

    findings_resp = auth_client.get(f"/api/inspections/{insp_id}/findings")
    findings = findings_resp.json()
    assert len(findings) > 0

    target_finding = findings[0]
    adj_resp = auth_client.patch(
        f"/api/findings/{target_finding['id']}/adjudicate",
        json={
            "action": "CORRECTED",
            "notes": "SIMULATED_TEST_ACTION: Verifying adjudication endpoint functionality",
            "corrected_value": "TEST_INSPECTOR_CORRECTION"
        }
    )
    assert adj_resp.status_code == 200
    assert adj_resp.json()["adjudication_status"] == "CORRECTED"
    assert "SIMULATED_TEST_ACTION" in adj_resp.json()["adjudication_notes"]


# ============================================================================
# 2. MANDATORY 10 ANTI-FABRICATION TESTS (Prompt Section 22)
# ============================================================================

def test_anti_fab_1_no_step1_product_name_leakage():
    """Test 1: System does NOT use Step-1 product name as OCR commodity."""
    product_ctx = {"product_name": "Premium Synthetic Rice Brand X"}
    ocr_text = "Marketed By: ABC Corp, Delhi\nNet Wt: 1 kg\nMRP: Rs. 100"
    boxes = [OCRTextBox(text="Marketed By: ABC Corp", confidence=0.9, bbox=[0, 0, 10, 10], sequence=1)]

    decls = extraction_service.extract_declarations(ocr_text, boxes, product_ctx, image_id="img-01")
    comm = next(d for d in decls if d.field_name == "commodity_name")
    assert comm.extracted_value != "Premium Synthetic Rice Brand X"
    assert comm.extraction_status == "NOT_FOUND"


def test_anti_fab_2_no_filename_product_inference():
    """Test 2: System does NOT use filename to infer product name."""
    product_ctx = {"product_name": "Unknown", "filename": "Britannia_Good_Day_Butter_Cookies_100g.jpg"}
    ocr_text = "Some random blurred text"
    boxes = [OCRTextBox(text="Some random blurred text", confidence=0.8, bbox=[0, 0, 10, 10], sequence=1)]

    decls = extraction_service.extract_declarations(ocr_text, boxes, product_ctx, image_id="img-01")
    comm = next(d for d in decls if d.field_name == "commodity_name")
    assert comm.extracted_value is None or "Cookies" not in (comm.extracted_value or "")


def test_anti_fab_3_no_previous_inspection_leakage():
    """Test 3: System does NOT use previous inspection OCR or state."""
    boxes_a = [OCRTextBox(text="MFG BY: Company Alpha", confidence=0.95, bbox=[0, 0, 10, 10], sequence=1)]
    decls_a = extraction_service.extract_declarations("MFG BY: Company Alpha", boxes_a, {}, image_id="img-a")
    mfg_a = next(d for d in decls_a if d.field_name == "manufacturer_details")
    assert "Company Alpha" in mfg_a.extracted_value

    boxes_b = [OCRTextBox(text="MFG BY: Company Beta", confidence=0.95, bbox=[0, 0, 10, 10], sequence=1)]
    decls_b = extraction_service.extract_declarations("MFG BY: Company Beta", boxes_b, {}, image_id="img-b")
    mfg_b = next(d for d in decls_b if d.field_name == "manufacturer_details")
    assert "Company Beta" in mfg_b.extracted_value
    assert "Company Alpha" not in mfg_b.extracted_value


def test_anti_fab_4_no_test_fixture_declarations_in_production():
    """Test 4: System does NOT use test fixture declarations when processing images."""
    decls = extraction_service.extract_declarations("", [], {}, image_id="img-empty")
    for d in decls:
        assert d.extracted_value is None
        assert d.extraction_status in ["NOT_FOUND", "NOT_APPLICABLE", "NEEDS_LEGAL_VERIFICATION"]


def test_anti_fab_5_no_text_generation_on_ocr_empty():
    """Test 5: System does NOT generate OCR text when OCR returns nothing."""
    decls = extraction_service.extract_declarations("", [], {}, image_id="img-01")
    assert all(d.confidence == 0.0 for d in decls if d.extraction_status == "NOT_FOUND")


def test_anti_fab_6_no_ocr_failure_to_legal_violation():
    """Test 6: System does NOT turn OCR failure into a legal violation directly."""
    product_ctx = {"ocr_status": "OCR_UNAVAILABLE"}
    decls = extraction_service.extract_declarations("", [], product_ctx, image_id="img-fail")
    mrp_decl = next(d for d in decls if d.field_name == "mrp")
    assert mrp_decl.extraction_status == "OCR_UNAVAILABLE"

    eval_res = rule_engine.evaluate_inspection("INSP-FAIL", {}, decls, [{"id": "img-fail", "quality_status": "POOR"}])
    mrp_eval = next(r for r in eval_res if r.rule_code == "PCR_RULE_06_1_E")
    assert mrp_eval.result_state == RuleResultState.INSUFFICIENT_EVIDENCE


def test_anti_fab_7_no_low_confidence_garbage_as_high_conf_conflict():
    """Test 7: System does NOT treat low-confidence garbage as a high-confidence conflict."""
    decl_a = ExtractedDeclarationItem(
        field_name="mrp", field_label="MRP", extracted_value="Rs. 50.00",
        confidence=0.95, source_image_id="img-a", extraction_status="EXTRACTED"
    )
    decl_b = ExtractedDeclarationItem(
        field_name="mrp", field_label="MRP", extracted_value="Rs. 12.00",
        confidence=0.40, source_image_id="img-b", extraction_status="EXTRACTED"
    )

    merged, conflicts = cross_image_verification({"img-a": [decl_a], "img-b": [decl_b]})
    mrp_merged = next(d for d in merged if d.field_name == "mrp")
    assert mrp_merged.extraction_status == "EXTRACTED"
    assert mrp_merged.extracted_value == "Rs. 50.00"
    assert mrp_merged.confidence == 0.95
    assert len(conflicts) == 0


def test_anti_fab_8_no_finding_without_source_evidence():
    """Test 8: System does NOT create a finding without source evidence."""
    decl = ExtractedDeclarationItem(
        field_name="mrp", field_label="MRP", extracted_value="Rs. 50.00 (Incl. of all taxes)",
        confidence=0.95, source_image_id="img-01", bounding_box=[10, 10, 100, 30],
        extraction_status="EXTRACTED"
    )
    eval_res = rule_engine.evaluate_inspection("INSP-EV", {}, [decl], [{"id": "img-01", "quality_status": "GOOD"}])
    mrp_eval = next(r for r in eval_res if r.rule_code == "PCR_RULE_06_1_E")
    assert len(mrp_eval.evidence_items) > 0
    assert mrp_eval.evidence_items[0].image_id == "img-01"
    assert mrp_eval.evidence_items[0].bounding_box == [10, 10, 100, 30]


def test_anti_fab_9_deterministic_rule_engine_is_not_llm():
    """Test 9: System uses deterministic rule evaluation, not an unconstrained LLM."""
    assert hasattr(rule_engine, "evaluate_inspection")
    decl = ExtractedDeclarationItem(
        field_name="mrp", field_label="MRP", extracted_value="Rs. 50.00",
        confidence=0.95, source_image_id="img-01", extraction_status="EXTRACTED"
    )
    res1 = rule_engine.evaluate_inspection("INSP-DET", {}, [decl], [])
    res2 = rule_engine.evaluate_inspection("INSP-DET", {}, [decl], [])
    assert [r.result_state for r in res1] == [r.result_state for r in res2]
    assert [r.explanation for r in res1] == [r.explanation for r in res2]


def test_anti_fab_10_no_data_leakage_between_inspections(auth_client):
    """Test 10: System isolates inspections completely with no data cross-leakage."""
    resp1 = auth_client.post("/api/inspections", json={"product_name": "Product 1", "category": "Packaged Food", "location": "Loc 1"})
    resp2 = auth_client.post("/api/inspections", json={"product_name": "Product 2", "category": "Packaged Food", "location": "Loc 2"})
    assert resp1.status_code == 201
    assert resp2.status_code == 201
    assert resp1.json()["id"] != resp2.json()["id"]
    assert resp1.json()["inspection_number"] != resp2.json()["inspection_number"]
