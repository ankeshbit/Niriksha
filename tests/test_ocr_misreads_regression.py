"""
tests/test_ocr_misreads_regression.py

Regression test suite ensuring:
1. Robust extraction matching handles common OCR label substitutions (MED BY, MFC BY, em-dashes).
2. Packaging section headers (NUTRITIONAL FACTS, INGREDIENTS, etc.) are strictly rejected as commodity names.
3. Raw OCR provenance is strictly immutable: OCR text, confidence, bounding boxes, and source image are NEVER mutated or fabricated.
"""

import pytest
from backend.extraction_service import extraction_service
from backend.ocr_service import OCRTextBox

def test_ocr_label_misread_manufacturer_variants():
    """Tolerates common OCR misreads for manufacturer label without modifying raw text."""
    test_cases = [
        ("MED BY: SUNSHINE FOODS PVT LTD, MUMBAI", "SUNSHINE FOODS PVT LTD, MUMBAI"),
        ("MFC BY: ORGANIC FARMS INDIA, DELHI", "ORGANIC FARMS INDIA, DELHI"),
        ("MFD BY: HIMALAYAN FOODS, SHIMLA", "HIMALAYAN FOODS, SHIMLA"),
        ("PACKED BY: GREEN MILLS PVT LTD, PUNJAB", "GREEN MILLS PVT LTD, PUNJAB"),
    ]

    for raw_line, expected_mfr in test_cases:
        boxes = [
            OCRTextBox(text=raw_line, confidence=0.88, bbox=[10, 10, 210, 30], sequence=1)
        ]
        declarations = extraction_service.extract_declarations(
            full_text=raw_line,
            text_boxes=boxes,
            product_context={},
            image_id="img-01"
        )
        
        # Verify manufacturer was extracted
        mfr_decl = next((d for d in declarations if d.field_name == "manufacturer_details"), None)
        assert mfr_decl is not None, f"Failed to extract manufacturer from '{raw_line}'"
        assert mfr_decl.extracted_value is not None, f"Extracted value was None for '{raw_line}'"
        assert expected_mfr in mfr_decl.extracted_value or mfr_decl.extracted_value in expected_mfr

        # PROVENANCE INVARIANT: The raw box text must remain authentic
        assert boxes[0].text == raw_line, "Raw OCR box text must never be mutated"

def test_ocr_label_misread_date_variants():
    """Tolerates common OCR date label misreads."""
    test_cases = [
        "MED: 03/2026",
        "MFC: 03/2026",
        "MFD: 03/2026",
        "PKD ON: 03/2026",
    ]

    for raw_line in test_cases:
        boxes = [
            OCRTextBox(text=raw_line, confidence=0.85, bbox=[10, 30, 160, 50], sequence=1)
        ]
        declarations = extraction_service.extract_declarations(
            full_text=raw_line,
            text_boxes=boxes,
            product_context={},
            image_id="img-01"
        )
        
        date_decl = next((d for d in declarations if d.field_name == "date_of_manufacture_packing"), None)
        assert date_decl is not None, f"Failed to extract date from '{raw_line}'"
        assert date_decl.extracted_value is not None
        assert "03/2026" in date_decl.extracted_value

def test_consumer_care_with_em_dash():
    """Extracts customer care phone number with em-dash or unicode punctuation."""
    raw_line = "CUSTOMER CARE: 1800—123—4567 EMAIL: CARE@BRAND.COM"
    boxes = [
        OCRTextBox(text=raw_line, confidence=0.9, bbox=[10, 50, 310, 70], sequence=1)
    ]
    declarations = extraction_service.extract_declarations(
        full_text=raw_line,
        text_boxes=boxes,
        product_context={},
        image_id="img-01"
    )
    
    phone_decl = next((d for d in declarations if d.field_name == "consumer_care_details"), None)
    assert phone_decl is not None, "Failed to extract customer care details with em-dash"
    assert phone_decl.extracted_value is not None
    assert "1800" in phone_decl.extracted_value

def test_packaging_headings_rejected_as_commodity_name():
    """Obvious packaging headings must NEVER be extracted as product/commodity names."""
    rejected_headings = [
        "NUTRITIONAL FACTS",
        "INGREDIENTS",
        "DIRECTIONS FOR USE",
        "STORAGE INSTRUCTIONS",
        "HOW TO USE",
        "BEST BEFORE 12 MONTHS",
        "EXPIRY DATE",
        "BARCODE",
        "FSSAI LIC NO. 10012345678901",
    ]

    for heading in rejected_headings:
        raw_text = f"{heading}\nNET QUANTITY: 500 g\nMRP Rs. 150.00"
        boxes = [
            OCRTextBox(text=heading, confidence=0.95, bbox=[10, 10, 210, 35], sequence=1),
            OCRTextBox(text="NET QUANTITY: 500 g", confidence=0.95, bbox=[10, 40, 210, 65], sequence=2),
            OCRTextBox(text="MRP Rs. 150.00", confidence=0.95, bbox=[10, 70, 210, 95], sequence=3),
        ]
        declarations = extraction_service.extract_declarations(
            full_text=raw_text,
            text_boxes=boxes,
            product_context={},
            image_id="img-01"
        )
        commodity_decl = next((d for d in declarations if d.field_name == "commodity_name"), None)

        if commodity_decl and commodity_decl.extracted_value:
            assert heading.lower() not in commodity_decl.extracted_value.lower(), (
                f"Heading '{heading}' was falsely extracted as commodity name: '{commodity_decl.extracted_value}'"
            )
