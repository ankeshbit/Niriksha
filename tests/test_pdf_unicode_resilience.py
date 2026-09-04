"""
tests/test_pdf_unicode_resilience.py

Tests whether PDF generation in backend/report_service.py gracefully handles
Hindi text, Devanagari characters, Rupees symbols (₹), and emojis without crashing.
"""

import os
from pathlib import Path
import pytest
from backend.report_service import StatutoryReportGenerator

class DummyInspection:
    id = "insp-unicode-test-123"
    inspection_number = "LM-2026-99999"
    created_at = None
    finalized_at = None
    location = "चांदनी चौक, नई दिल्ली (Chandni Chowk, New Delhi)"
    overall_status = "NO_POTENTIAL_VIOLATIONS"
    notes = "परीक्षण अधिकारी टिप्पणी — ₹150.00 मूल्य एवं गुणवत्ता सत्यापन।"

class DummyProduct:
    product_name = "हिमालयन पतंजलि जैविक ओट्स (Himalayan Organic Oats)"
    brand_name = "पतंजलि (Patanjali)"
    category = "Packaged Food"
    batch_number = "बैच-२०२६"

class DummyInspector:
    full_name = "राजेश शर्मा (Rajesh Sharma)"
    officer_id = "DOCA-INSP-842"
    designation = "Senior Inspector"
    zone = "Northern Zone"

class DummyDeclaration:
    field_name = "commodity_name"
    extracted_value = "जैविक ओट्स (Organic Oats)"
    confidence = 0.95
    extraction_status = "EXTRACTED"
    verification_status = "VERIFIED"
    bounding_box_json = "[80, 220, 450, 290]"
    corrected_value = None
    is_applicable = True
    correction_reason = None
    extraction_method = "AI/OCR"

class DummyCheck:
    rule_code = "PCR_RULE_06_1_F"
    title = "Generic Name or Commodity Identification"
    statutory_reference = "Rule 6(1)(f), PCR 2011"
    result_state = "PASS"
    adjudication_status = "CONFIRMED"
    adjudication_notes = "Inspector confirmed valid Hindi/English label."

def test_report_generation_with_hindi_unicode():
    """Ensure ReportLab handles Hindi Unicode and currency symbols without crashing."""
    generator = StatutoryReportGenerator(reports_dir="./generated_reports")
    inspection = DummyInspection()
    product = DummyProduct()
    inspector = DummyInspector()
    declarations = [DummyDeclaration()]
    compliance_checks = [DummyCheck()]
    evidence_items = []

    pdf_path = generator.generate_pdf(
        inspection=inspection,
        product=product,
        inspector=inspector,
        declarations=declarations,
        compliance_checks=compliance_checks,
        evidence_items=evidence_items,
        report_version=99
    )

    assert os.path.exists(pdf_path), f"PDF file was not created: {pdf_path}"
    file_size = os.path.getsize(pdf_path)
    assert file_size > 1000, f"PDF file is too small ({file_size} bytes)"

    # Clean up test pdf
    try:
        os.unlink(pdf_path)
    except Exception:
        pass
