import os
import shutil
import inspect
import cv2
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import patch

from backend.ocr_service import (
    ocr_service,
    find_tesseract_binary,
    is_tesseract_available,
    normalize_ocr_text,
    OCRTextBox,
    OCRResultData,
    ModularOCRService
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# ---------------------------------------------------------------------------
# TEST 1: A real readable image produces actual OCR text
# ---------------------------------------------------------------------------
def test_real_readable_image_produces_actual_ocr():
    img_path = FIXTURES_DIR / "clear_package.jpg"
    assert img_path.exists(), "clear_package.jpg fixture must exist"

    result = ocr_service.process_image(str(img_path), image_id="img-clear-1")
    assert result is not None
    assert result.engine_used == "Tesseract"
    assert result.error is None
    assert len(result.text_boxes) >= 5
    assert result.mean_confidence > 0.50
    assert result.processing_time_ms > 0

    # Must contain text actually drawn on clear_package.jpg
    assert "BASMATI" in result.raw_text.upper()
    assert "QUANTITY" in result.raw_text.upper()
    assert "MRP" in result.raw_text.upper()


# ---------------------------------------------------------------------------
# TEST 2: Unrelated text does NOT produce packaged-product sample declarations
# ---------------------------------------------------------------------------
def test_unrelated_text_image_does_not_produce_package_declarations(tmp_path):
    # Create an image containing completely unrelated text
    img = np.ones((400, 800, 3), dtype=np.uint8) * 240
    cv2.putText(img, "HELLO WORLD ALPHA BETA GAMMA", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (10, 10, 10), 2)
    cv2.putText(img, "INVOICE NUMBER 99887766", (50, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (10, 10, 10), 2)
    unrelated_path = tmp_path / "unrelated_doc.jpg"
    cv2.imwrite(str(unrelated_path), img)

    result = ocr_service.process_image(str(unrelated_path), image_id="img-unrelated")
    assert result is not None
    assert "HELLO" in result.raw_text.upper()
    assert "INVOICE" in result.raw_text.upper()

    # Must NEVER contain fabricated package declarations
    fabricated_keywords = [
        "PREMIUM BASMATI RICE",
        "NET QUANTITY: 5 kg",
        "MRP Rs. 450.00",
        "AGRO FOODS PVT LTD",
        "EXTRA VIRGIN OLIVE OIL",
        "MEDITERRANEAN IMPORTS",
        "GREEN MILLS PVT LTD",
        "ORGANIC WHEAT FLOUR"
    ]
    for fake_str in fabricated_keywords:
        assert fake_str not in result.raw_text, f"Fabricated string '{fake_str}' found in OCR output!"


# ---------------------------------------------------------------------------
# TEST 3 & REQUIREMENT 16: Filename does NOT control OCR output (Anti-Fabrication)
# ---------------------------------------------------------------------------
def test_filename_cannot_control_ocr_output(tmp_path):
    """
    Explicit regression test proving filenames cannot dictate OCR output.
    Naming an image 'imported_product.jpg' or 'missing_mrp.jpg' must NOT alter OCR results.
    """
    img = np.ones((400, 800, 3), dtype=np.uint8) * 240
    cv2.putText(img, "SPECIAL COFFEE ROAST 250g", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (10, 10, 10), 2)
    cv2.putText(img, "PRICE RS 350", (50, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (10, 10, 10), 2)

    # 1. Save with neutral name
    neutral_path = tmp_path / "neutral_item.jpg"
    cv2.imwrite(str(neutral_path), img)
    res_neutral = ocr_service.process_image(str(neutral_path))

    # 2. Save identical image with name 'imported_product.jpg'
    imported_named_path = tmp_path / "imported_product.jpg"
    cv2.imwrite(str(imported_named_path), img)
    res_imported = ocr_service.process_image(str(imported_named_path))

    # 3. Save identical image with name 'missing_mrp.jpg'
    missing_named_path = tmp_path / "missing_mrp.jpg"
    cv2.imwrite(str(missing_named_path), img)
    res_missing = ocr_service.process_image(str(missing_named_path))

    # 4. Save identical image with name 'multi_panel_back.jpg'
    multipanel_named_path = tmp_path / "multi_panel_back.jpg"
    cv2.imwrite(str(multipanel_named_path), img)
    res_multipanel = ocr_service.process_image(str(multipanel_named_path))

    # OCR text must be identical regardless of filename
    assert res_neutral.raw_text == res_imported.raw_text
    assert res_neutral.raw_text == res_missing.raw_text
    assert res_neutral.raw_text == res_multipanel.raw_text

    # The imported filename must NOT inject Spain origin or olive oil
    assert "SPAIN" not in res_imported.raw_text
    assert "OLIVE OIL" not in res_imported.raw_text
    assert "MEDITERRANEAN" not in res_imported.raw_text

    # The missing filename must NOT remove the PRICE line
    assert "350" in res_missing.raw_text


# ---------------------------------------------------------------------------
# TEST 4: Tesseract failure/unavailability does NOT produce fake text
# ---------------------------------------------------------------------------
def test_tesseract_unavailability_returns_structured_failure():
    with patch("backend.ocr_service.is_tesseract_available", return_value=False):
        svc = ModularOCRService()
        result = svc.process_image(str(FIXTURES_DIR / "clear_package.jpg"))

        assert result.engine_used == "tesseract_unavailable"
        assert result.raw_text == ""
        assert result.text_boxes == []
        assert result.mean_confidence == 0.0
        assert "unavailable" in result.error.lower()


# ---------------------------------------------------------------------------
# TEST 5: OCR boxes contain actual detected text and coordinates
# ---------------------------------------------------------------------------
def test_ocr_boxes_contain_actual_detected_text_and_coords():
    img_path = FIXTURES_DIR / "clear_package.jpg"
    result = ocr_service.process_image(str(img_path), image_id="test-box-coords")

    assert len(result.text_boxes) > 0
    img = cv2.imread(str(img_path))
    h, w = img.shape[:2]

    for b in result.text_boxes:
        assert isinstance(b, OCRTextBox)
        assert len(b.text.strip()) > 0
        assert len(b.bbox) == 4
        x1, y1, x2, y2 = b.bbox
        assert 0 <= x1 < x2 <= w
        assert 0 <= y1 < y2 <= h
        assert b.image_id == "test-box-coords"
        assert 0.0 <= b.confidence <= 1.0


# ---------------------------------------------------------------------------
# TEST 6: Confidence is based on OCR output (not hard-coded 0.85 or 1.0)
# ---------------------------------------------------------------------------
def test_confidence_is_derived_from_ocr_output():
    # Good clear package should have high confidence (> 0.80)
    res_clear = ocr_service.process_image(str(FIXTURES_DIR / "clear_package.jpg"))
    # Low-res or degraded image should have lower confidence
    res_low = ocr_service.process_image(str(FIXTURES_DIR / "low_res_package.jpg"))

    assert res_clear.mean_confidence > 0.80
    assert res_clear.mean_confidence != 0.85, "Confidence should not be a fixed dummy value of 0.85"
    assert res_low.mean_confidence < res_clear.mean_confidence


# ---------------------------------------------------------------------------
# TEST 7: Multiple images preserve different image IDs
# ---------------------------------------------------------------------------
def test_multiple_images_preserve_different_image_ids():
    img1_path = FIXTURES_DIR / "clear_package.jpg"
    img2_path = FIXTURES_DIR / "missing_declarations_package.jpg"

    res1 = ocr_service.process_image(str(img1_path), image_id="img-front-001")
    res2 = ocr_service.process_image(str(img2_path), image_id="img-back-002")

    assert all(b.image_id == "img-front-001" for b in res1.text_boxes)
    assert all(b.image_id == "img-back-002" for b in res2.text_boxes)


# ---------------------------------------------------------------------------
# TEST 8: Corrupted or missing image produces controlled failure
# ---------------------------------------------------------------------------
def test_corrupted_or_missing_image_handled_gracefully(tmp_path):
    # 1. Non-existent path
    res_missing = ocr_service.process_image(str(tmp_path / "does_not_exist.jpg"))
    assert res_missing.engine_used == "error"
    assert res_missing.raw_text == ""
    assert res_missing.text_boxes == []
    assert res_missing.mean_confidence == 0.0
    assert "File not found" in res_missing.error

    # 2. Corrupted file (zero bytes or invalid header)
    corrupt_file = tmp_path / "corrupt.jpg"
    corrupt_file.write_bytes(b"NOT_A_VALID_JPEG_HEADER_RANDOM_GARBAGE")
    res_corrupt = ocr_service.process_image(str(corrupt_file))
    assert res_corrupt.engine_used == "error"
    assert res_corrupt.raw_text == ""
    assert res_corrupt.text_boxes == []
    assert res_corrupt.mean_confidence == 0.0
    assert "Could not load or decode" in res_corrupt.error

    # 3. Degenerate resolution (10x10)
    small_img = np.zeros((10, 10, 3), dtype=np.uint8)
    small_path = tmp_path / "tiny.jpg"
    cv2.imwrite(str(small_path), small_img)
    res_small = ocr_service.process_image(str(small_path))
    assert res_small.text_boxes == []
    assert "too low" in res_small.error.lower()


# ---------------------------------------------------------------------------
# TEST 9: Preprocessing preserves and extracts clean packaging text
# ---------------------------------------------------------------------------
def test_preprocessing_improves_or_preserves_ocr():
    # Test on dark image where Otsu/CLAHE makes text readable
    dark_path = FIXTURES_DIR / "dark_package.jpg"
    res_dark = ocr_service.process_image(str(dark_path))
    assert len(res_dark.text_boxes) >= 5
    assert "BASMATI" in res_dark.raw_text.upper()
    assert res_dark.mean_confidence > 0.70


# ---------------------------------------------------------------------------
# TEST 10: Source code audit - NO hard-coded declaration text arrays remain
# ---------------------------------------------------------------------------
def test_no_hardcoded_sample_declaration_arrays_in_ocr_service():
    import backend.ocr_service as ocr_mod
    source_lines = inspect.getsource(ocr_mod)

    forbidden_hardcoded_phrases = [
        "standard_lines = [",
        "imported_lines = [",
        "multipanel_lines = [",
        "missing_lines = [",
        "PREMIUM BASMATI RICE",
        "EXTRA VIRGIN OLIVE OIL",
        "NUTRITIONAL FACTS & DETAILS",
        "ORGANIC WHEAT FLOUR",
        "AGRO FOODS PVT LTD",
        "MEDITERRANEAN IMPORTS DELHI",
        "GREEN MILLS PVT LTD",
        "NATURAL FARMS INDIA",
        "1800-11-2233",
        "1800-77-8899",
        "1800-44-5566",
        'active_lines = standard_lines',
        'active_lines = imported_lines'
    ]

    for phrase in forbidden_hardcoded_phrases:
        assert phrase not in source_lines, f"Forbidden hardcoded phrase '{phrase}' still present in ocr_service.py!"


# ---------------------------------------------------------------------------
# TEST 11: Text Normalization preserves statutory formats
# ---------------------------------------------------------------------------
def test_text_normalization_preserves_statutory_formats():
    raw_sample = "MRP   Rs. 450.00 (INCL. OF ALL TAXES) \n MFD:  08/2026 \nNET   QTY: 5 kg\nCARE@AGRO.IN"
    normalized = normalize_ocr_text(raw_sample)

    assert "450.00" in normalized
    assert "08/2026" in normalized
    assert "5 kg" in normalized
    assert "CARE@AGRO.IN" in normalized
    # Checks that multi-spaces were collapsed
    assert "MRP Rs. 450.00 (INCL. OF ALL TAXES)" in normalized
