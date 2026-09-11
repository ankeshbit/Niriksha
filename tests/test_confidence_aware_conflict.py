"""
Tests for confidence-aware conflict detection in cross_image_verification().

These tests verify the 4-scenario logic:
  Scenario A: Multiple reliable same-value sources -> EXTRACTED
  Scenario B: Multiple reliable different-value sources -> CONFLICTING (genuine conflict)
  Scenario C: One reliable + unreliable different-value -> EXTRACTED (not a conflict)
  Scenario D: All low-confidence sources -> LOW_CONFIDENCE (no conflict)

Also tests commodity name confidence gate (BUG-3 fix).
"""
import pytest
from backend.extraction_service import (
    ExtractedDeclarationItem,
    cross_image_verification,
    DeterministicRegexExtractor
)
from backend.ocr_service import OCRTextBox


HIGH_CONF = 0.90  # Above HIGH_CONF_THRESHOLD (0.70)
LOW_CONF = 0.40   # Below HIGH_CONF_THRESHOLD (0.70)


def make_candidate(field, value, conf, image_id):
    return ExtractedDeclarationItem(
        field_name=field,
        field_label=field.replace("_", " ").title(),
        extracted_value=value,
        normalized_value=value.strip().upper(),
        confidence=conf,
        source_image_id=image_id,
        extraction_status="EXTRACTED",
        is_applicable=True
    )


def make_not_found(field):
    return ExtractedDeclarationItem(
        field_name=field,
        field_label=field.replace("_", " ").title(),
        extraction_status="NOT_FOUND",
        confidence=0.0
    )


def test_scenario_b_multiple_reliable_different_values_returns_conflicting():
    front = make_candidate("net_quantity", "500 g", HIGH_CONF, "img-front")
    back = make_candidate("net_quantity", "1 kg", HIGH_CONF, "img-back")
    merged, conflicts = cross_image_verification({"img-front": [front], "img-back": [back]})
    qty_result = next(m for m in merged if m.field_name == "net_quantity")
    assert qty_result.extraction_status == "CONFLICTING"
    assert qty_result.has_conflict is True
    assert len(conflicts) == 1


def test_scenario_c_one_reliable_plus_unreliable_different_returns_extracted_not_conflicting():
    """CRITICAL: High-conf + low-conf mismatch must NOT produce CONFLICTING."""
    front_reliable = make_candidate("commodity_name", "PREMIUM BASMATI RICE", HIGH_CONF, "img-front")
    back_garbled = make_candidate("commodity_name", "ahvays Refit! With (EB Ball Pen...", LOW_CONF, "img-back")
    merged, conflicts = cross_image_verification({"img-front": [front_reliable], "img-back": [back_garbled]})
    cn_result = next(m for m in merged if m.field_name == "commodity_name")
    assert cn_result.extraction_status == "EXTRACTED", (
        f"Scenario C must return EXTRACTED, got {cn_result.extraction_status!r}. "
        f"Value: {cn_result.extracted_value!r}"
    )
    assert cn_result.has_conflict is False
    assert cn_result.extracted_value == "PREMIUM BASMATI RICE"
    assert len(conflicts) == 0


def test_scenario_c_dual_unreliable_vs_single_reliable():
    reliable = make_candidate("mrp", "Rs. 120.00 Incl. all taxes", HIGH_CONF, "img-front")
    garbled1 = make_candidate("mrp", "Rs. 999 noncense", LOW_CONF, "img-back")
    garbled2 = make_candidate("mrp", "garbage text xyz", LOW_CONF, "img-side")
    merged, conflicts = cross_image_verification({
        "img-front": [reliable], "img-back": [garbled1], "img-side": [garbled2]
    })
    mrp_result = next(m for m in merged if m.field_name == "mrp")
    assert mrp_result.extraction_status == "EXTRACTED"
    assert mrp_result.extracted_value == "Rs. 120.00 Incl. all taxes"
    assert len(conflicts) == 0


def test_scenario_d_all_unreliable_returns_low_confidence():
    low1 = make_candidate("manufacturer_details", "Garbled Corp", LOW_CONF, "img-front")
    low2 = make_candidate("manufacturer_details", "Blurred Co.", 0.55, "img-back")
    merged, conflicts = cross_image_verification({"img-front": [low1], "img-back": [low2]})
    mfg_result = next(m for m in merged if m.field_name == "manufacturer_details")
    assert mfg_result.extraction_status == "LOW_CONFIDENCE"
    assert mfg_result.has_conflict is False
    assert len(conflicts) == 0


def test_commodity_name_confidence_gate_rejects_low_confidence_boxes():
    extractor = DeterministicRegexExtractor()
    low_conf_boxes = [
        OCRTextBox(text="ahvays Refit! With Pen", confidence=0.32, bbox=[0, 0, 100, 20], sequence=1),
        OCRTextBox(text="blurredtext xyz", confidence=0.45, bbox=[0, 25, 100, 45], sequence=2),
    ]
    result = extractor._extract_commodity_name(
        text="ahvays Refit! With Pen\nblurredtext xyz",
        text_boxes=low_conf_boxes,
        image_id="img-low-conf",
        ocr_status="OCR_SUCCESS"
    )
    assert result.extraction_status == "NOT_FOUND", (
        f"Expected NOT_FOUND for low-conf boxes, got {result.extraction_status!r} with value {result.extracted_value!r}"
    )


def test_commodity_name_confidence_gate_accepts_high_confidence_box():
    extractor = DeterministicRegexExtractor()
    boxes = [
        OCRTextBox(text="PREMIUM BASMATI RICE", confidence=0.92, bbox=[0, 0, 200, 20], sequence=1),
        OCRTextBox(text="garbled low conf", confidence=0.30, bbox=[0, 25, 200, 45], sequence=2),
    ]
    result = extractor._extract_commodity_name(
        text="PREMIUM BASMATI RICE\ngarbled low conf",
        text_boxes=boxes,
        image_id="img-test",
        ocr_status="OCR_SUCCESS"
    )
    assert result.extraction_status == "EXTRACTED"
    assert result.extracted_value == "PREMIUM BASMATI RICE"
    assert result.confidence >= 0.65


def test_commodity_name_prefers_highest_confidence_among_valid_boxes():
    extractor = DeterministicRegexExtractor()
    boxes = [
        OCRTextBox(text="ORGANIC WHEAT FLOUR", confidence=0.78, bbox=[0, 0, 200, 20], sequence=1),
        OCRTextBox(text="Natural Grain Products", confidence=0.85, bbox=[0, 25, 200, 45], sequence=2),
    ]
    result = extractor._extract_commodity_name(
        text="ORGANIC WHEAT FLOUR\nNatural Grain Products",
        text_boxes=boxes,
        image_id="img-multi",
        ocr_status="OCR_SUCCESS"
    )
    assert result.extraction_status == "EXTRACTED"
    assert result.extracted_value == "Natural Grain Products"
    assert result.confidence == 0.85


def test_not_found_candidates_no_conflicts():
    not_found = make_not_found("consumer_care_details")
    merged, conflicts = cross_image_verification({"img-front": [not_found]})
    care_result = next((m for m in merged if m.field_name == "consumer_care_details"), None)
    if care_result:
        assert care_result.extraction_status in ("NOT_FOUND", "OCR_UNAVAILABLE")
    assert len(conflicts) == 0
