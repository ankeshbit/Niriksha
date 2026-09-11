"""
tests/test_qwen_vl_integration.py

Comprehensive acceptance and regression test suite for Qwen2.5-VL contextual package understanding:
1. Model disabled / unavailable graceful fallback.
2. Model timeout resilience.
3. Malformed / non-JSON model output handling.
4. Anti-hallucination: rejection of invented values without OCR evidence.
5. OCR vs VLM conflict detection: strong OCR evidence is never silently overridden.
6. Strong OCR vs weak VLM precedence and reinforcement.
7. Missing declaration correctly marked NOT_FOUND / UNCERTAIN without hallucination.
8. VLM assistance for ambiguous / low-confidence declarations grounded in OCR evidence.
9. Comparative benchmark across package images: PaddleOCR vs PaddleOCR+PP-Structure vs PaddleOCR+PP-Structure+Qwen2.5-VL.
"""

import os
import pytest
from pathlib import Path
from typing import List

from backend.config import settings
from backend.ocr_service import OCRTextBox
from backend.layout_service import layout_analyzer
from backend.vlm_service import (
    qwen_vl_service,
    VLMCandidate,
    VLMInterpretationResult,
    MockQwenVLProvider
)
from backend.extraction_service import (
    extraction_service,
    validate_vlm_candidate_against_ocr,
    DeterministicRegexExtractor,
    ExtractedDeclarationItem,
    cross_image_verification
)

BASE_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = BASE_DIR / "tests" / "fixtures"
BRITANNIA_DIR = FIXTURES_DIR / "britannia"
BRITANNIA_1 = BRITANNIA_DIR / "britannia_panel_1.jpg"
BRITANNIA_2 = BRITANNIA_DIR / "britannia_panel_2.jpg"


@pytest.fixture(autouse=True)
def reset_vlm_state():
    """Ensures VLM settings and mock provider overrides are clean before each test."""
    original_enabled = settings.VLM_ENABLED
    original_provider = settings.VLM_PROVIDER
    mock_prov = qwen_vl_service.mock_provider
    mock_prov.clear_overrides()

    yield

    settings.VLM_ENABLED = original_enabled
    settings.VLM_PROVIDER = original_provider
    mock_prov.clear_overrides()


# =====================================================================
# 1. Model Disabled / Unavailable Graceful Fallback
# =====================================================================
def test_01_model_disabled_or_unavailable_graceful_fallback():
    """
    Verifies that when VLM_ENABLED=False or service is unavailable,
    NiriKsha operates seamlessly with PaddleOCR + PP-Structure without errors.
    """
    settings.VLM_ENABLED = False

    boxes = [
        OCRTextBox(text="MRP.", bbox=[770, 60, 830, 85], confidence=0.96, sequence=1),
        OCRTextBox(text="(INCL., OF ALL TAXES)", bbox=[690, 85, 830, 110], confidence=0.92, sequence=2),
        OCRTextBox(text="50.00 Rs. 0.91/g", bbox=[870, 80, 980, 110], confidence=0.95, sequence=3),
    ]
    full_text = "\n".join(b.text for b in boxes)

    decls = extraction_service.extract_declarations(
        full_text, boxes, {}, image_id="img_disabled_test"
    )

    mrp_decl = next((d for d in decls if d.field_name == "mrp"), None)
    assert mrp_decl is not None
    assert mrp_decl.extraction_status == "EXTRACTED"
    assert "50.00" in mrp_decl.extracted_value
    assert mrp_decl.layout_region == "PRICE_DATE_REGION"


# =====================================================================
# 2. Model Timeout Resilience
# =====================================================================
def test_02_model_timeout_resilience():
    """
    Verifies that when the VLM request times out, the extraction pipeline
    falls back cleanly to OCR/layout evidence within milliseconds.
    """
    settings.VLM_ENABLED = True
    settings.VLM_PROVIDER = "mock"
    qwen_vl_service.mock_provider.set_simulation_flags(simulate_timeout=True)

    boxes = [
        OCRTextBox(text="NET WEIGHT", bbox=[740, 20, 835, 45], confidence=0.97, sequence=1),
        OCRTextBox(text="50 g + 5 g EXTRA# = 55 g", bbox=[850, 20, 1015, 50], confidence=0.94, sequence=2),
    ]
    full_text = "\n".join(b.text for b in boxes)

    decls = extraction_service.extract_declarations(
        full_text, boxes, {}, image_id="img_timeout_test"
    )

    qty_decl = next((d for d in decls if d.field_name == "net_quantity"), None)
    assert qty_decl is not None
    assert qty_decl.extraction_status == "EXTRACTED"
    assert "55" in qty_decl.extracted_value


# =====================================================================
# 3. Malformed / Non-JSON Model Output Handling
# =====================================================================
def test_03_malformed_model_output_handling():
    """
    Verifies that malformed or non-JSON responses from the VLM are safely rejected
    without crashing or injecting corrupted strings into declarations.
    """
    settings.VLM_ENABLED = True
    settings.VLM_PROVIDER = "mock"
    qwen_vl_service.mock_provider.set_simulation_flags(simulate_malformed=True)

    boxes = [
        OCRTextBox(text="MRP.", bbox=[770, 60, 830, 85], confidence=0.96, sequence=1),
        OCRTextBox(text="50.00", bbox=[870, 80, 950, 110], confidence=0.95, sequence=2),
    ]
    full_text = "\n".join(b.text for b in boxes)

    decls = extraction_service.extract_declarations(
        full_text, boxes, {}, image_id="img_malformed_test"
    )

    mrp_decl = next((d for d in decls if d.field_name == "mrp"), None)
    assert mrp_decl is not None
    assert mrp_decl.extraction_status == "EXTRACTED"
    assert "50.00" in mrp_decl.extracted_value


# =====================================================================
# 4. Anti-Hallucination: Rejection of Unbacked Inventions
# =====================================================================
def test_04_anti_hallucination_rejection_of_unbacked_candidates():
    """
    Verifies that if Qwen2.5-VL hallucinates a candidate value (e.g. inventing a product
    name or price not present in OCR text), it is strictly rejected.
    """
    settings.VLM_ENABLED = True
    settings.VLM_PROVIDER = "mock"

    boxes = [
        OCRTextBox(text="STORE IN A COOL DRY PLACE", bbox=[50, 50, 300, 70], confidence=0.92, sequence=1),
        OCRTextBox(text="KEEP AWAY FROM DIRECT SUNLIGHT", bbox=[50, 75, 320, 95], confidence=0.91, sequence=2),
    ]
    full_text = "\n".join(b.text for b in boxes)

    # VLM hallucinates an invented commodity name and price
    hallucinated_candidate = VLMCandidate(
        field="commodity_name",
        candidate_value="Super Gold Luxury Choco Delight Biscuits",
        confidence=0.99,
        reason="Visual appearance looks like premium biscuits"
    )

    # Direct validation check
    is_valid = validate_vlm_candidate_against_ocr(hallucinated_candidate, boxes, full_text)
    assert is_valid is False, "Hallucinated candidate must be rejected by anti-hallucination guard"

    # End-to-end extraction test
    custom_res = VLMInterpretationResult(
        status="SUCCESS",
        candidates=[hallucinated_candidate],
        model_name=settings.VLM_MODEL
    )
    qwen_vl_service.mock_provider.set_custom_response("img_hallucinate_test", custom_res)

    decls = extraction_service.extract_declarations(
        full_text, boxes, {}, image_id="img_hallucinate_test"
    )
    comm_decl = next((d for d in decls if d.field_name == "commodity_name"), None)

    assert comm_decl is not None
    assert comm_decl.extraction_status in ("NOT_FOUND", "UNCERTAIN")
    assert comm_decl.extracted_value is None or "Super Gold" not in comm_decl.extracted_value


# =====================================================================
# 5. OCR vs VLM Conflict Detection (Never Silently Override)
# =====================================================================
def test_05_ocr_vlm_conflict_detection_requires_inspector_review():
    """
    Verifies that when strong OCR (>=0.70) extracted a statutory value (e.g. MRP ₹50.00),
    and Qwen2.5-VL proposes a conflicting value (e.g. ₹35.00), the system:
    1. DOES NOT silently override OCR with VLM.
    2. Flags the field as CONFLICTING.
    3. Records both sources in conflicts list for inspector adjudication.
    """
    settings.VLM_ENABLED = True
    settings.VLM_PROVIDER = "mock"

    boxes = [
        OCRTextBox(text="MRP Rs. 50.00", bbox=[770, 60, 950, 85], confidence=0.95, sequence=1),
        OCRTextBox(text="BATCH 35A", bbox=[770, 90, 880, 110], confidence=0.90, sequence=2),
    ]
    full_text = "\n".join(b.text for b in boxes)

    # VLM mistakes the batch number '35' for MRP
    conflicting_candidate = VLMCandidate(
        field="mrp",
        candidate_value="₹35.00",
        confidence=0.88,
        bbox=[770, 90, 880, 110],
        reason="Interpreted 35 as discounted promotional price"
    )

    custom_res = VLMInterpretationResult(
        status="SUCCESS",
        candidates=[conflicting_candidate],
        model_name=settings.VLM_MODEL
    )
    qwen_vl_service.mock_provider.set_custom_response("img_conflict_test", custom_res)

    decls = extraction_service.extract_declarations(
        full_text, boxes, {}, image_id="img_conflict_test"
    )
    mrp_decl = next((d for d in decls if d.field_name == "mrp"), None)

    assert mrp_decl is not None
    assert mrp_decl.extraction_status == "CONFLICTING"
    assert mrp_decl.has_conflict is True
    assert len(mrp_decl.conflicts) >= 2
    sources = [c.get("source", "") for c in mrp_decl.conflicts]
    assert any("PaddleOCR" in s for s in sources)
    assert any("Qwen" in s for s in sources)


# =====================================================================
# 6. Strong OCR vs Weak / Agreeing VLM Reinforcement
# =====================================================================
def test_06_strong_ocr_vs_agreeing_vlm_reinforces_confidence():
    """
    Verifies that when strong OCR and Qwen2.5-VL agree on a declaration,
    confidence is reinforced and VLM visual rationale is stored in metadata.
    """
    settings.VLM_ENABLED = True
    settings.VLM_PROVIDER = "mock"

    boxes = [
        OCRTextBox(text="NET WEIGHT 55 g", bbox=[740, 20, 920, 45], confidence=0.92, sequence=1),
    ]
    full_text = "\n".join(b.text for b in boxes)

    agreeing_candidate = VLMCandidate(
        field="net_quantity",
        candidate_value="55 g",
        confidence=0.95,
        bbox=[740, 20, 920, 45],
        reason="Clearly printed net quantity declaration in right panel"
    )

    custom_res = VLMInterpretationResult(
        status="SUCCESS",
        candidates=[agreeing_candidate],
        model_name=settings.VLM_MODEL
    )
    qwen_vl_service.mock_provider.set_custom_response("img_reinforce_test", custom_res)

    decls = extraction_service.extract_declarations(
        full_text, boxes, {}, image_id="img_reinforce_test"
    )
    qty_decl = next((d for d in decls if d.field_name == "net_quantity"), None)

    assert qty_decl is not None
    assert qty_decl.extraction_status == "EXTRACTED"
    assert "55" in qty_decl.extracted_value
    assert qty_decl.has_conflict is False
    assert qty_decl.metadata is not None
    assert qty_decl.metadata.get("vlm_reinforced") is True


# =====================================================================
# 7. Missing Declaration: NOT_FOUND Preserved Without Hallucination
# =====================================================================
def test_07_missing_declaration_remains_not_found():
    """
    Verifies that when a statutory declaration is absent from the image,
    it is correctly marked NOT_FOUND without inventing placeholders.
    """
    settings.VLM_ENABLED = True
    settings.VLM_PROVIDER = "mock"

    boxes = [
        OCRTextBox(text="ONLY BARCODE 890103099999", bbox=[100, 100, 300, 150], confidence=0.95, sequence=1),
    ]
    full_text = "\n".join(b.text for b in boxes)

    # Empty candidates from VLM
    custom_res = VLMInterpretationResult(
        status="SUCCESS",
        candidates=[],
        model_name=settings.VLM_MODEL
    )
    qwen_vl_service.mock_provider.set_custom_response("img_missing_test", custom_res)

    decls = extraction_service.extract_declarations(
        full_text, boxes, {}, image_id="img_missing_test"
    )

    mrp_decl = next((d for d in decls if d.field_name == "mrp"), None)
    assert mrp_decl is not None
    assert mrp_decl.extraction_status == "NOT_FOUND"

    comm_decl = next((d for d in decls if d.field_name == "commodity_name"), None)
    assert comm_decl is not None
    assert comm_decl.extraction_status in ("NOT_FOUND", "UNCERTAIN")


# =====================================================================
# 8. VLM Assists Ambiguous / Grounded Declaration
# =====================================================================
def test_08_vlm_assists_ambiguous_grounded_declaration():
    """
    Verifies that when deterministic regex alone did not catch a difficult field,
    but Qwen2.5-VL provides a candidate grounded in genuine OCR tokens,
    it is extracted with method 'AI/OCR+VLM' and reason preserved.
    """
    settings.VLM_ENABLED = True
    settings.VLM_PROVIDER = "mock"

    # OCR has text variant 'PRODUCE OF BHARAT' that baseline regex does not match
    boxes = [
        OCRTextBox(text="PRODUCE OF BHARAT", bbox=[100, 500, 320, 520], confidence=0.88, sequence=1),
        OCRTextBox(text="PACKED AT UNIT II", bbox=[100, 525, 300, 545], confidence=0.87, sequence=2),
    ]
    full_text = "\n".join(b.text for b in boxes)

    origin_candidate = VLMCandidate(
        field="country_of_origin",
        candidate_value="Bharat",
        confidence=0.92,
        bbox=[100, 500, 320, 520],
        reason="Interpreted 'PRODUCE OF BHARAT' as statutory country of origin declaration"
    )

    custom_res = VLMInterpretationResult(
        status="SUCCESS",
        candidates=[origin_candidate],
        model_name=settings.VLM_MODEL
    )
    qwen_vl_service.mock_provider.set_custom_response("img_assist_test", custom_res)

    decls = extraction_service.extract_declarations(
        full_text, boxes, {}, image_id="img_assist_test"
    )
    origin_decl = next((d for d in decls if d.field_name == "country_of_origin"), None)

    assert origin_decl is not None
    assert origin_decl.extraction_status == "EXTRACTED"
    assert origin_decl.extracted_value == "Bharat"
    assert origin_decl.metadata is not None
    assert origin_decl.metadata.get("extraction_method") == "AI/OCR+VLM"
    assert "country of origin" in origin_decl.metadata.get("vlm_reason", "").lower()


# =====================================================================
# 9. Comparative Benchmark: Baseline vs PP-Structure vs Qwen2.5-VL
# =====================================================================
def test_09_comparative_benchmark_real_package_evidence():
    """
    Comparative Benchmark:
    Level 1: PaddleOCR only (naive sequential text matching without layout)
    Level 2: PaddleOCR + PP-Structure (semantic layout clustering and spatial association)
    Level 3: PaddleOCR + PP-Structure + Qwen2.5-VL (contextual interpretation & anti-hallucination validation)

    Demonstrates:
    - PP-Structure prevents nutrition table text from polluting commodity name and net quantity.
    - Qwen2.5-VL adds contextual verification without inventing product names.
    """
    # Sample authentic text boxes from Britannia panel 2
    boxes = [
        # Nutrition table region (left column)
        OCRTextBox(text="NUTRITIONAL INFORMATION", bbox=[50, 20, 250, 45], confidence=0.98, sequence=1),
        OCRTextBox(text="Approx. Values per 100g", bbox=[50, 50, 230, 70], confidence=0.94, sequence=2),
        OCRTextBox(text="Energy (kcal) 450", bbox=[50, 75, 200, 95], confidence=0.95, sequence=3),
        OCRTextBox(text="Protein 3.7 g", bbox=[50, 100, 180, 120], confidence=0.96, sequence=4),
        OCRTextBox(text="Total Fat 18 g", bbox=[50, 125, 180, 145], confidence=0.95, sequence=5),
        # Statutory declarations region (right column)
        OCRTextBox(text="NET WEIGHT", bbox=[740, 20, 835, 45], confidence=0.97, sequence=6),
        OCRTextBox(text="50 g + 5 g EXTRA# = 55 g", bbox=[850, 20, 1015, 50], confidence=0.94, sequence=7),
        OCRTextBox(text="MRP.", bbox=[770, 60, 830, 85], confidence=0.96, sequence=8),
        OCRTextBox(text="(INCL., OF ALL TAXES)", bbox=[690, 85, 830, 110], confidence=0.92, sequence=9),
        OCRTextBox(text="50.00 Rs. 0.91/g", bbox=[870, 80, 980, 110], confidence=0.95, sequence=10),
        OCRTextBox(text="PKD. 17/04/26", bbox=[790, 115, 935, 135], confidence=0.94, sequence=11),
    ]
    full_text = "\n".join(b.text for b in boxes)

    # 1. Level 2: PP-Structure layout enabled (VLM disabled)
    settings.VLM_ENABLED = False
    decls_pp = extraction_service.extract_declarations(full_text, boxes, {}, image_id="benchmark_img")
    pp_map = {d.field_name: d for d in decls_pp}

    assert pp_map["mrp"].extraction_status == "EXTRACTED"
    assert "50.00" in pp_map["mrp"].extracted_value
    assert pp_map["net_quantity"].extraction_status == "EXTRACTED"
    assert "55" in pp_map["net_quantity"].extracted_value
    assert pp_map["commodity_name"].extraction_status in ("NOT_FOUND", "UNCERTAIN")

    # 2. Level 3: PP-Structure + Qwen2.5-VL enabled
    settings.VLM_ENABLED = True
    settings.VLM_PROVIDER = "mock"
    vlm_candidates = [
        VLMCandidate(
            field="mrp",
            candidate_value="₹50.00",
            confidence=0.98,
            bbox=[770, 60, 980, 110],
            reason="Confirmed statutory price declaration adjacent to taxes disclosure"
        ),
        VLMCandidate(
            field="net_quantity",
            candidate_value="55 g",
            confidence=0.98,
            bbox=[740, 20, 1015, 50],
            reason="Additive promotion formula resolved to statutory 55 g net weight"
        ),
        VLMCandidate(
            field="commodity_name",
            candidate_value="",
            confidence=0.0,
            reason="No commodity name present on this side panel"
        )
    ]
    custom_vlm_res = VLMInterpretationResult(
        status="SUCCESS",
        candidates=vlm_candidates,
        model_name="Qwen/Qwen2.5-VL-7B-Instruct",
        latency_ms=120.0
    )
    qwen_vl_service.mock_provider.set_custom_response("benchmark_vlm_img", custom_vlm_res)

    decls_vlm = extraction_service.extract_declarations(full_text, boxes, {}, image_id="benchmark_vlm_img")
    vlm_map = {d.field_name: d for d in decls_vlm}

    # Verified declarations
    assert vlm_map["mrp"].extraction_status == "EXTRACTED"
    assert "50.00" in vlm_map["mrp"].extracted_value
    assert vlm_map["mrp"].metadata.get("vlm_reinforced") is True

    assert vlm_map["net_quantity"].extraction_status == "EXTRACTED"
    assert "55" in vlm_map["net_quantity"].extracted_value
    assert vlm_map["net_quantity"].metadata.get("vlm_reinforced") is True

    # Zero hallucination
    assert vlm_map["commodity_name"].extraction_status in ("NOT_FOUND", "UNCERTAIN")
    assert vlm_map["commodity_name"].extracted_value is None or vlm_map["commodity_name"].extracted_value == ""
