import os
import cv2
import pytest
import numpy as np
from pathlib import Path
from unittest.mock import patch, MagicMock

from backend.ocr_service import (
    ocr_service,
    is_paddleocr_available,
    is_tesseract_available,
    PaddleOCREngine,
    TesseractOCREngine,
    ModularOCRService,
    OCRTextBox,
    OCRResultData
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_paddleocr_engine_initialization():
    """Verifies PaddleOCREngine initializes with expected default configuration."""
    engine = PaddleOCREngine()
    assert hasattr(engine, "is_available")
    assert hasattr(engine, "extract_text_boxes")
    assert engine._enabled is True
    assert engine._use_angle_cls is True
    assert engine._lang == "en"


def test_paddleocr_polygon_to_rect_bbox_mapping():
    """
    Verifies that 4-point polygon coordinates from PaddleOCR are converted
    strictly to [x1, y1, x2, y2] bounding boxes with correct sequence and confidence.
    """
    engine = PaddleOCREngine()

    mock_paddle_result = [
        [
            [[[50, 100], [250, 100], [250, 140], [50, 140]], ("BASMATI RICE", 0.965)],
            [[[50, 160], [200, 160], [200, 195], [50, 195]], ("NET WEIGHT: 5 KG", 0.942)],
            [[[50, 210], [180, 210], [180, 245], [50, 245]], ("MRP RS 450", 0.978)]
        ]
    ]

    mock_ocr = MagicMock()
    mock_ocr.ocr.return_value = mock_paddle_result

    with patch.object(engine, "is_available", return_value=True):
        with patch.object(engine, "_get_ocr_instance", return_value=mock_ocr):
            dummy_img = np.zeros((400, 600, 3), dtype=np.uint8)
            boxes = engine.extract_text_boxes(dummy_img)

            assert len(boxes) == 3
            assert boxes[0].text == "BASMATI RICE"
            assert boxes[0].bbox == [50, 100, 250, 140]
            assert boxes[0].confidence == 0.96
            assert boxes[0].sequence == 1

            assert boxes[1].text == "NET WEIGHT: 5 KG"
            assert boxes[1].bbox == [50, 160, 200, 195]
            assert boxes[1].sequence == 2

            assert boxes[2].text == "MRP RS 450"
            assert boxes[2].bbox == [50, 210, 180, 245]
            assert boxes[2].sequence == 3


def test_fallback_to_tesseract_when_paddleocr_unavailable(tmp_path):
    """
    Verifies that when PaddleOCR is unavailable or disabled, ModularOCRService
    seamlessly falls back to Tesseract OCR without raising errors or fabricating text.
    """
    service = ModularOCRService()

    img_path = FIXTURES_DIR / "clear_package.jpg"
    assert img_path.exists(), "clear_package.jpg fixture must exist"

    with patch.object(service.paddle_engine, "is_available", return_value=False):
        result = service.process_image(str(img_path), image_id="img-fallback-1")

        assert result is not None
        if service.tesseract_engine.is_available():
            assert result.engine_used == "Tesseract"
            assert result.ocr_status == "OCR_SUCCESS"
            assert len(result.text_boxes) > 0
            assert "BASMATI" in result.raw_text.upper()


def test_structured_unavailability_when_all_engines_disabled(tmp_path):
    """
    Verifies that when neither PaddleOCR nor Tesseract is available, the service
    returns OCR_UNAVAILABLE with empty text, zero confidence, and NO fabricated strings.
    """
    service = ModularOCRService()
    img_path = FIXTURES_DIR / "clear_package.jpg"

    with patch.object(service.paddle_engine, "is_available", return_value=False):
        with patch.object(service.tesseract_engine, "is_available", return_value=False):
            with patch("backend.ocr_service.is_tesseract_available", return_value=False):
                result = service.process_image(str(img_path))

                assert result.ocr_status == "OCR_UNAVAILABLE"
                assert result.raw_text == ""
                assert result.text_boxes == []
                assert result.mean_confidence == 0.0
                assert "unavailable" in result.error.lower()


def test_paddleocr_primary_integration_with_real_or_mocked_inference(tmp_path):
    """
    Verifies PaddleOCR primary engine execution and contract compliance.
    """
    service = ModularOCRService()

    # Create synthetic test package image
    img = np.ones((500, 800, 3), dtype=np.uint8) * 255
    cv2.putText(img, "ORGANIC WHOLE WHEAT FLOUR", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (10, 10, 10), 2)
    cv2.putText(img, "NET QTY: 10 kg", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (10, 10, 10), 2)
    cv2.putText(img, "MRP RS. 520.00", (50, 300), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (10, 10, 10), 2)

    test_file = tmp_path / "test_flour.jpg"
    cv2.imwrite(str(test_file), img)

    result = service.process_image(str(test_file), image_id="img-flour-primary")

    assert result is not None
    assert result.ocr_status == "OCR_SUCCESS"
    assert result.engine_used in ("PaddleOCR", "Tesseract")
    assert all(b.image_id == "img-flour-primary" for b in result.text_boxes)
    assert result.processing_time_ms > 0
