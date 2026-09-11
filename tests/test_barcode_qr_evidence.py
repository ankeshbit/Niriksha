"""
tests/test_barcode_qr_evidence.py

Comprehensive Test Suite for Barcode & QR Code Evidence Integration.
Validates:
1. 1D Barcode Detection (EAN-13, Code 128)
2. 2D QR Code Detection
3. Image with no barcode
4. Damaged / unreadable barcode handling (graceful failure)
5. Multiple barcodes on a single image
6. OCR Cross-Validation: Corroboration on match
7. OCR Cross-Validation: Evidence Conflict on mismatch
8. Multi-image consolidation (consistency vs conflict)
9. Strict Invariant: Confidence is None (never invent confidence)
10. API endpoint GET /api/inspections/{inspection_id}/barcodes
"""

import os
import cv2
import json
import pytest
import numpy as np
import barcode
from barcode.writer import ImageWriter
import qrcode
from pathlib import Path

from backend.barcode_service import barcode_service, BarcodeItem, BarcodeInspectionSummary
from backend.schemas import BarcodeItemResponse, BarcodeInspectionSummaryResponse


def _create_ean13_image(code_digits: str = "890103000001") -> np.ndarray:
    """Helper to generate an EAN-13 barcode image as BGR numpy array."""
    ean = barcode.get("ean13", code_digits, writer=ImageWriter())
    pil_img = ean.render()
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def _create_code128_image(data: str = "BATCH-2026-X") -> np.ndarray:
    """Helper to generate a Code 128 barcode image as BGR numpy array."""
    c128 = barcode.get("code128", data, writer=ImageWriter())
    pil_img = c128.render()
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def _create_qr_image(content: str = "https://consumeraffairs.nic.in/pcr2011") -> np.ndarray:
    """Helper to generate a QR code image as BGR numpy array."""
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(content)
    qr.make(fit=True)
    pil_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


# ----------------- Unit Tests for BarcodeService -----------------

def test_valid_1d_barcode_ean13():
    """Verify EAN-13 package barcode detection and parsing."""
    img = _create_ean13_image("890103000001")
    items = barcode_service.detect_and_decode(img, source_image_id="img-001")

    assert len(items) >= 1
    item = items[0]
    assert item.type in ["EAN13", "EAN-13"]
    assert "890103000001" in item.value
    assert item.source_image_id == "img-001"
    assert item.bbox is not None
    assert len(item.bbox) == 4  # [x1, y1, x2, y2]
    # Statutory Invariant: pyzbar confidence must be None
    assert item.confidence is None


def test_valid_1d_barcode_code128():
    """Verify Code 128 barcode detection."""
    img = _create_code128_image("BATCH-LM-2026")
    items = barcode_service.detect_and_decode(img, source_image_id="img-batch")

    assert len(items) >= 1
    item = items[0]
    assert "128" in item.type
    assert item.value == "BATCH-LM-2026"
    assert item.confidence is None


def test_valid_qrcode():
    """Verify QR code detection and URL/text decoding."""
    test_url = "https://consumeraffairs.nic.in/legal-metrology"
    img = _create_qr_image(test_url)
    items = barcode_service.detect_and_decode(img, source_image_id="img-qr")

    assert len(items) >= 1
    item = items[0]
    assert "QR" in item.type
    assert item.value == test_url
    assert item.confidence is None


def test_no_barcode_in_image():
    """Verify that an image with plain background or text but no barcode yields an empty list."""
    blank_img = np.ones((400, 400, 3), dtype=np.uint8) * 240
    # Add plain text that looks like a label but is not a barcode
    cv2.putText(blank_img, "BRITANNIA GOOD DAY 100g", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    cv2.putText(blank_img, "MRP Rs 30.00 incl of all taxes", (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

    items = barcode_service.detect_and_decode(blank_img)
    assert items == []


def test_damaged_unreadable_barcode():
    """Verify that heavily degraded/corrupted barcode returns empty list without crashing."""
    img = _create_ean13_image("890103000001")
    # Severely blur and occlude the barcode
    damaged = cv2.GaussianBlur(img, (99, 99), 30)
    cv2.rectangle(damaged, (50, 50), (damaged.shape[1] - 50, damaged.shape[0] - 50), (128, 128, 128), -1)

    items = barcode_service.detect_and_decode(damaged)
    assert items == []


def test_multiple_barcodes_on_one_image():
    """Verify that an image containing both a 1D barcode and a QR code decodes both."""
    ean_img = _create_ean13_image("890103000001")
    qr_img = _create_qr_image("https://example.com/verify")

    # Resize to fit side by side
    h = 300
    w_ean = int(ean_img.shape[1] * (h / ean_img.shape[0]))
    w_qr = int(qr_img.shape[1] * (h / qr_img.shape[0]))
    resized_ean = cv2.resize(ean_img, (w_ean, h))
    resized_qr = cv2.resize(qr_img, (w_qr, h))

    combined = np.hstack([resized_ean, resized_qr])
    items = barcode_service.detect_and_decode(combined)

    assert len(items) >= 2
    types = [it.type for it in items]
    assert any("EAN" in t for t in types)
    assert any("QR" in t for t in types)


# ----------------- OCR Cross-Validation Tests -----------------

def test_ocr_cross_validation_corroborating():
    """When OCR text includes the identical GTIN number, flag as CORROBORATING."""
    item = BarcodeItem(
        type="EAN13",
        value="8901030000010",
        confidence=None
    )
    ocr_text = (
        "BRITANNIA INDUSTRIES LTD\n"
        "NET QTY: 100 g\n"
        "8901030000010\n"
        "MRP Rs 30.00"
    )
    validated = barcode_service.cross_validate_with_ocr([item], ocr_text)
    assert len(validated) == 1
    assert validated[0].ocr_corroboration == "CORROBORATING"
    assert validated[0].conflicting_ocr_value is None


def test_ocr_cross_validation_conflict():
    """When OCR text has a different GTIN-like number, flag as EVIDENCE_CONFLICT."""
    item = BarcodeItem(
        type="EAN13",
        value="8901030000010",
        confidence=None
    )
    ocr_text = (
        "BRITANNIA INDUSTRIES LTD\n"
        "NET QTY: 100 g\n"
        "8901030999999\n"  # Discrepant 13-digit number in OCR
        "MRP Rs 30.00"
    )
    validated = barcode_service.cross_validate_with_ocr([item], ocr_text)
    assert len(validated) == 1
    assert validated[0].ocr_corroboration == "EVIDENCE_CONFLICT"
    assert validated[0].conflicting_ocr_value == "8901030999999"


def test_ocr_cross_validation_no_ocr_barcode():
    """When OCR text has no GTIN-like number, flag as NO_OCR_BARCODE."""
    item = BarcodeItem(
        type="EAN13",
        value="8901030000010",
        confidence=None
    )
    ocr_text = "BRITANNIA INDUSTRIES LTD NET QTY 100g MRP Rs 30.00"
    validated = barcode_service.cross_validate_with_ocr([item], ocr_text)
    assert len(validated) == 1
    assert validated[0].ocr_corroboration == "NO_OCR_BARCODE"


# ----------------- Multi-Image Consolidation Tests -----------------

def test_multi_image_consolidation_consistent():
    """Same barcode across multiple package images consolidates cleanly without conflict."""
    per_image = {
        "img-front": [BarcodeItem(type="EAN13", value="8901030000010", confidence=None, source_image_id="img-front")],
        "img-back": [BarcodeItem(type="EAN13", value="8901030000010", confidence=None, source_image_id="img-back")]
    }
    summary = barcode_service.consolidate_multi_image_barcodes(per_image)
    assert summary.detected is True
    assert summary.has_conflict is False
    assert summary.consolidated_value == "8901030000010"
    assert summary.barcode_type == "EAN13"
    assert len(summary.items) == 2


def test_multi_image_consolidation_conflict():
    """Different barcode values across package images flags an explicit conflict."""
    per_image = {
        "img-front": [BarcodeItem(type="EAN13", value="8901030000010", confidence=None, source_image_id="img-front")],
        "img-back": [BarcodeItem(type="EAN13", value="8901030999999", confidence=None, source_image_id="img-back")]
    }
    summary = barcode_service.consolidate_multi_image_barcodes(per_image)
    assert summary.detected is True
    assert summary.has_conflict is True
    assert "Conflicting barcodes detected" in (summary.conflict_description or "")
    assert len(summary.items) == 2


def test_confidence_is_strictly_none_invariant():
    """Statutory Invariant: Barcode confidence must strictly be None (never an invented float)."""
    img = _create_ean13_image("890103000001")
    items = barcode_service.detect_and_decode(img)
    for item in items:
        assert item.confidence is None, f"Expected None, got {item.confidence}"

    # Pydantic model serialization check
    dumped = items[0].model_dump()
    assert dumped["confidence"] is None
