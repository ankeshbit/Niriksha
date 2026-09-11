"""
tests/test_paddleocr_strengthened_acceptance.py

Comprehensive acceptance tests for strengthening PaddleOCR as primary OCR engine:
1. OCR Output Schema: text, confidence, bounding_box, source_image_id, engine, timestamp preserved on every box.
2. PaddleOCR Primary Execution on clean package image.
3. Dense packaging image extraction on realistic package text (MRP, dates, net quantity, manufacturer, care).
4. Fallback pipeline: PaddleOCR -> Tesseract fallback -> OCR_UNAVAILABLE.
5. Transient failure does not permanently disable PaddleOCR.
6. Anti-fabrication: OCR derives text strictly from image pixels (no filename, context, or fixture leakage).
7. Real Britannia package images extraction audit (capturing authentic text, confidences, bboxes, engine).
"""
import os
import cv2
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from backend.ocr_service import (
    ocr_service,
    PaddleOCREngine,
    TesseractOCREngine,
    ModularOCRService,
    OCRTextBox,
    OCRResultData,
    is_paddleocr_available,
    is_tesseract_available
)

BASE_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = BASE_DIR / "tests" / "fixtures"
CLEAR_IMG = FIXTURES_DIR / "clear_package.jpg"
BRITANNIA_DIR = FIXTURES_DIR / "britannia"
BRITANNIA_1 = BRITANNIA_DIR / "britannia_panel_1.jpg"
BRITANNIA_2 = BRITANNIA_DIR / "britannia_panel_2.jpg"


# 1. OCR Output Schema Preservation
def test_01_ocr_output_schema_preservation():
    service = ModularOCRService()
    res = service.process_image(str(CLEAR_IMG), image_id="test-schema-001")
    assert res.ocr_status == "OCR_SUCCESS"
    assert len(res.text_boxes) > 0
    assert res.timestamp is not None

    for box in res.text_boxes:
        assert isinstance(box.text, str) and len(box.text) > 0
        assert isinstance(box.confidence, float) and 0.0 <= box.confidence <= 1.0
        assert isinstance(box.bbox, list) and len(box.bbox) == 4
        assert box.bbox[2] >= box.bbox[0] and box.bbox[3] >= box.bbox[1]
        assert box.image_id == "test-schema-001"
        assert box.engine in ("paddleocr", "tesseract")
        assert box.timestamp is not None
        assert isinstance(box.sequence, int) and box.sequence > 0


# 2. PaddleOCR Primary Execution
def test_02_paddleocr_primary_engine_execution():
    if not is_paddleocr_available():
        pytest.skip("PaddleOCR not available in this environment")

    engine = PaddleOCREngine()
    boxes = engine.extract_text_boxes(str(CLEAR_IMG))
    assert len(boxes) > 0
    assert any("BASMATI" in b.text.upper() for b in boxes)
    assert all(b.engine == "paddleocr" for b in boxes)
    assert all(b.timestamp is not None for b in boxes)


# 3. Dense Packaging Extraction (Small text, dates, MRP, Net Qty, Care)
def test_03_dense_packaging_text_extraction(tmp_path):
    service = ModularOCRService()

    # Create synthetic dense packaging image with multiple statutory regions
    img = np.ones((800, 1000, 3), dtype=np.uint8) * 255
    cv2.putText(img, "ORGANIC SPICED BISCUITS", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    cv2.putText(img, "NET WEIGHT: 75 g + 15 g FREE = 90 g", (50, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    cv2.putText(img, "MRP Rs. 35.00 (INCL. OF ALL TAXES)", (50, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    cv2.putText(img, "MFD. 12/25, USE BY 06/26", (50, 380), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    cv2.putText(img, "MFG BY: SHREE FOODS LTD, JAIPUR RAJASTHAN - 302001", (50, 480), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    cv2.putText(img, "CARE CELL: 1800 123 4567 / HELP@SHREEFOODS.IN", (50, 580), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

    test_file = tmp_path / "dense_pack.jpg"
    cv2.imwrite(str(test_file), img)

    res = service.process_image(str(test_file), image_id="img-dense-01")
    assert res.ocr_status == "OCR_SUCCESS"
    assert len(res.text_boxes) >= 4

    extracted_upper = res.raw_text.upper()
    assert "BISCUITS" in extracted_upper or "ORGANIC" in extracted_upper
    assert "NET" in extracted_upper or "WEIGHT" in extracted_upper
    assert "MRP" in extracted_upper or "35" in extracted_upper


# 4. Fallback Pipeline: PaddleOCR Failure -> Tesseract Fallback
def test_04_fallback_to_tesseract_on_paddle_failure():
    service = ModularOCRService()

    with patch.object(service.paddle_engine, "extract_text_boxes", side_effect=RuntimeError("Simulated Paddle inference error")):
        res = service.process_image(str(CLEAR_IMG), image_id="fallback-test-01")
        if service.tesseract_engine.is_available():
            assert res.engine_used == "Tesseract"
            assert res.ocr_status == "OCR_SUCCESS"
            assert len(res.text_boxes) > 0
            assert all(b.engine == "tesseract" for b in res.text_boxes)


# 5. Fallback Pipeline: Both Fail -> OCR_UNAVAILABLE (Zero Fabricated Text)
def test_05_both_engines_fail_returns_ocr_unavailable():
    service = ModularOCRService()

    with patch.object(service.paddle_engine, "is_available", return_value=False):
        with patch.object(service.tesseract_engine, "is_available", return_value=False):
            with patch("backend.ocr_service.is_tesseract_available", return_value=False):
                res = service.process_image(str(CLEAR_IMG), image_id="unavailable-test")
                assert res.ocr_status == "OCR_UNAVAILABLE"
                assert res.raw_text == ""
                assert res.normalized_text == ""
                assert res.text_boxes == []
                assert res.mean_confidence == 0.0
                assert "No OCR engine is available" in res.error


# 6. Transient Failure Does NOT Permanently Brick PaddleOCR
def test_06_transient_failure_recovery_without_permanent_disablement():
    service = ModularOCRService()
    PaddleOCREngine.reset_engine()

    # Image 1: Fails with transient error -> falls back cleanly to Tesseract
    with patch.object(service.paddle_engine, "_get_ocr_instance") as mock_inst:
        mock_ocr = MagicMock()
        mock_ocr.predict.side_effect = RuntimeError("Transient GPU/CPU timeout")
        mock_ocr.ocr.side_effect = RuntimeError("Transient GPU/CPU timeout")
        mock_inst.return_value = mock_ocr

        res1 = service.process_image(str(CLEAR_IMG), image_id="transient-1")
        assert res1.ocr_status == "OCR_SUCCESS"

    # Verify engine is NOT marked permanently with _init_error
    assert PaddleOCREngine._init_error is None
    assert service.paddle_engine.is_available() is True


# 7. Anti-Fabrication: Derived Strictly from Pixels
def test_07_anti_fabrication_pixel_driven_content(tmp_path):
    service = ModularOCRService()

    # Create image with arbitrary unseen synthetic token
    unseen_token = "KRYPTONITE_XYZ_987654"
    img = np.ones((400, 800, 3), dtype=np.uint8) * 255
    cv2.putText(img, unseen_token, (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)

    # Name the file intentionally misleadingly
    misleading_path = tmp_path / "cadbury_dairy_milk_mrp_50.jpg"
    cv2.imwrite(str(misleading_path), img)

    res = service.process_image(str(misleading_path), image_id="anti-fab-1")
    assert res.ocr_status == "OCR_SUCCESS"

    # Must extract the actual pixel token
    assert unseen_token in res.raw_text.replace(" ", "")

    # Must NOT hallucinate product name from filename
    assert "CADBURY" not in res.raw_text.upper()
    assert "DAIRY" not in res.raw_text.upper()


# 8. Real Package Test on Britannia Packaging
def test_08_real_britannia_package_paddleocr_extraction():
    assert BRITANNIA_1.exists(), f"Missing {BRITANNIA_1}"
    assert BRITANNIA_2.exists(), f"Missing {BRITANNIA_2}"

    service = ModularOCRService()

    # Panel 1
    res1 = service.process_image(str(BRITANNIA_1), image_id="media_britannia_1")
    assert res1.ocr_status == "OCR_SUCCESS"
    assert len(res1.text_boxes) > 0
    assert res1.mean_confidence > 0.70
    assert any("BRITANNIA" in b.text.upper() for b in res1.text_boxes)
    assert any("1-800" in b.text or "FEEDBACK" in b.text.upper() for b in res1.text_boxes)

    # Panel 2
    res2 = service.process_image(str(BRITANNIA_2), image_id="media_britannia_2")
    assert res2.ocr_status == "OCR_SUCCESS"
    assert len(res2.text_boxes) > 0
    assert res2.mean_confidence > 0.70
    assert any("NET" in b.text.upper() or "50" in b.text or "55" in b.text for b in res2.text_boxes)
    assert any("MRP" in b.text.upper() or "50.00" in b.text or "0.91" in b.text for b in res2.text_boxes)
