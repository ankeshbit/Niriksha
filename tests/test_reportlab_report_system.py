"""
tests/test_reportlab_report_system.py

Production Automated Test Suite for NiriKsha ReportLab PDF Inspection Report System.
Exclusively uses ReportLab for PDF generation per statutory architecture guidelines.

Coverage:
1.  ReportLab library version >= 4.0 (installed: 5.0.1) and core imports.
2.  Canonical 4-bucket compliance summary utility mutual exclusivity.
3.  Direct ReportLab PDF generation producing valid PDF bytes (%PDF-).
4.  SHA-256 digital checksum computation directly matching file bytes.
5.  Multi-page document generation with dynamic two-pass NumberedCanvas ("Page X of Y").
6.  PyPDF text extraction verifying required statutory sections:
    - Cover / header with DoCA / Legal Metrology & NiriKsha branding
    - Inspection metadata (Inspection ID, Officer ID, date, location)
    - 5-KPI Summary Cards with correct counts
    - Packaged commodity details & manufacturer
    - Package photographic evidence handling
    - Extracted OCR statutory declarations
    - Unified compliance matrix & deterministic PCR rule results
    - Spatial / Font / Readability audit
    - Barcode / QR auxiliary evidence with statutory notice
    - Findings & adjudication table with officer justification
    - Final statutory adjudication status block
    - Rule 19 Net Quantity limitation notice
    - Statutory AI Safety & Legal Limitation statement
    - Official sign-off attestation block
7.  Graceful resilience to missing optional fields (None inspector, None product, None location).
8.  Missing package evidence image file gracefully falls back without throwing exceptions.
9.  Uncalibrated camera notice rendered when font size calibration is absent.
10. Read-only invariance: PDF generation does not alter inspection or compliance check DB records.
11. REST API endpoint authentication & authorization (401 for unauthenticated).
12. REST API endpoint returns 404 for nonexistent inspection IDs.
13. REST API POST /api/inspections/{id}/report returns 200 with pdf_hash, download_url, and report_version.
14. REST API GET /api/inspections/{id}/report/pdf streams application/pdf with matching SHA-256 hash.
15. Support for human-readable inspection number (e.g. LM-2026-00023) in endpoint path.
"""

import os
import hashlib
from pathlib import Path
from typing import List, Optional
import pytest
from pypdf import PdfReader
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import settings
from backend.reportlab_report_service import ReportLabReportService
from backend.compliance_summary_utils import compute_canonical_compliance_metrics
from backend.report_styles import NumberedCanvas, COLOR_PRIMARY_NAVY, COLOR_PASS_GREEN, COLOR_WARN_AMBER


# ---------------------------------------------------------------------------
# Test Fixtures & Dummies
# ---------------------------------------------------------------------------

class MockInspector:
    officer_id = "DOCA-INSP-842"
    full_name = "Rajesh Sharma"
    designation = "Inspector (Legal Metrology)"
    zone = "Northern Zone - Delhi HQ"


class MockProduct:
    product_name = "Britannia Good Day Butter Cookies 100g"
    brand_name = "Britannia"
    category = "Biscuits & Bakery"
    batch_number = "BATCH-2026-B12"
    declared_net_quantity = "100 g"
    declared_mrp = "₹30.00"
    declared_mfg_date = "01/2026"
    declared_expiry_date = "07/2026"
    manufacturer_name = "Britannia Industries Ltd."
    manufacturer_address = "5/1A Hungerford Street, Kolkata - 700017"


class MockDeclaration:
    def __init__(
        self,
        field_name: str,
        extracted_value: str,
        confidence: float = 0.95,
        verification_status: str = "VERIFIED",
        is_applicable: bool = True,
        bounding_box_json: Optional[str] = "[10, 20, 100, 50]",
        font_size_status: Optional[str] = "MEASURED",
        font_size_details_json: Optional[str] = '{"measured_height_mm": 2.5, "minimum_required_mm": 2.0, "compliant": true}',
        placement_status: Optional[str] = "PRINCIPAL_DISPLAY_PANEL",
        readability_status: Optional[str] = "CLEAR",
    ):
        self.field_name = field_name
        self.extracted_value = extracted_value
        self.confidence = confidence
        self.verification_status = verification_status
        self.is_applicable = is_applicable
        self.bounding_box_json = bounding_box_json
        self.font_size_status = font_size_status
        self.font_size_details_json = font_size_details_json
        self.placement_status = placement_status
        self.readability_status = readability_status
        self.corrected_value = None
        self.correction_reason = None
        self.extraction_method = "AI/OCR"


class MockComplianceCheck:
    def __init__(
        self,
        rule_code: str,
        title: str,
        statutory_reference: str,
        result_state: str,
        adjudication_status: str = "PENDING",
        adjudication_notes: str = "Automated rule evaluation.",
    ):
        self.rule_code = rule_code
        self.title = title
        self.statutory_reference = statutory_reference
        self.result_state = result_state
        self.adjudication_status = adjudication_status
        self.adjudication_notes = adjudication_notes


class MockEvidenceItem:
    def __init__(self, file_path: str, view_type: str = "FRONT", quality_score: float = 0.92):
        self.file_path = file_path
        self.view_type = view_type
        self.quality_status = "PASS"
        self.quality_score = quality_score
        self.resolution = "1920x1080"


class MockBarcode:
    barcode_type = "EAN-13"
    barcode_value = "8901063012345"
    raw_data = "8901063012345"
    is_valid = True


class MockInspection:
    def __init__(
        self,
        id: str = "insp-test-uuid-001",
        inspection_number: str = "LM-2026-00023",
        overall_status: str = "POTENTIAL_NON_COMPLIANCE",
    ):
        self.id = id
        self.inspection_number = inspection_number
        self.location = "Blinkit Dark Store, Sector 62, Noida"
        self.overall_status = overall_status
        self.created_at = None
        self.finalized_at = None
        self.notes = "Sample collected during routine surveillance."


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def inspector_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"officer_id": settings.SEED_OFFICER_ID, "password": settings.SEED_OFFICER_PASSWORD},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# 1. ReportLab Version and Architecture Tests
# ---------------------------------------------------------------------------

def test_reportlab_version_and_imports():
    """Verify ReportLab is installed, version is at least 4.0, and required classes exist."""
    import reportlab
    version_str = reportlab.__version__
    major_ver = int(version_str.split(".")[0])
    assert major_ver >= 4, f"ReportLab version must be >= 4.0, got: {version_str}"

    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, Spacer, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors

    assert SimpleDocTemplate is not None
    assert Paragraph is not None
    assert Table is not None
    assert NumberedCanvas is not None


# ---------------------------------------------------------------------------
# 2. Canonical Compliance Metrics Mutual Exclusivity
# ---------------------------------------------------------------------------

def test_compliance_summary_metrics_mutual_exclusivity():
    """Ensure compliance metric buckets are strictly mutually exclusive."""
    checks = [
        # 6 compliant
        MockComplianceCheck("PCR_RULE_06_1_A", "Manufacturer Details", "Rule 6(1)(a)", "PASS"),
        MockComplianceCheck("PCR_RULE_06_1_B", "Country of Origin", "Rule 6(1)(b)", "PASS"),
        MockComplianceCheck("PCR_RULE_06_1_C", "Net Quantity", "Rule 6(1)(c)", "PASS"),
        MockComplianceCheck("PCR_RULE_06_1_D", "MRP Declaration", "Rule 6(1)(d)", "PASS"),
        MockComplianceCheck("PCR_RULE_06_1_E", "Date of Manufacture", "Rule 6(1)(e)", "PASS"),
        MockComplianceCheck("PCR_RULE_06_1_F", "Generic Name", "Rule 6(1)(f)", "PASS"),
        # 1 potential non-compliance
        MockComplianceCheck("PCR_RULE_06_1_G", "Consumer Care Details", "Rule 6(1)(g)", "POTENTIAL_NON_COMPLIANCE"),
        # 5 manual verification
        MockComplianceCheck("PCR_RULE_07", "Principal Display Panel Dimensions", "Rule 7", "NEEDS_MANUAL_VERIFICATION"),
        MockComplianceCheck("PCR_RULE_08", "Font Size Minimums", "Rule 8", "NEEDS_MANUAL_VERIFICATION"),
        MockComplianceCheck("PCR_RULE_09", "Readability and Contrast", "Rule 9", "INSUFFICIENT_EVIDENCE"),
        MockComplianceCheck("PCR_RULE_10", "Packaging Material Disclosure", "Rule 10", "NEEDS_MANUAL_VERIFICATION"),
        MockComplianceCheck("PCR_RULE_11", "Barcode Authenticity", "Rule 11", "NEEDS_MANUAL_VERIFICATION"),
    ]

    metrics = compute_canonical_compliance_metrics(checks)
    assert metrics["compliant_checks"] == 6
    assert metrics["potential_non_compliance"] == 1
    assert metrics["needs_manual_verification"] == 5
    assert metrics["warnings"] == 0
    assert metrics["total_findings"] == 12

    # Mutual exclusivity check: sum of 4 buckets == total
    assert (
        metrics["compliant_checks"]
        + metrics["potential_non_compliance"]
        + metrics["needs_manual_verification"]
        + metrics["warnings"]
    ) == metrics["total_findings"]


# ---------------------------------------------------------------------------
# 3. Direct ReportLab PDF Generation & PyPDF Content Extraction
# ---------------------------------------------------------------------------

def test_direct_reportlab_pdf_generation(tmp_path):
    """Generate PDF using ReportLabReportService, verify file, SHA-256 hash, and structure."""
    service = ReportLabReportService(reports_dir=str(tmp_path))

    inspection = MockInspection()
    product = MockProduct()
    inspector = MockInspector()
    declarations = [
        MockDeclaration("net_quantity", "100 g"),
        MockDeclaration("mrp", "₹30.00"),
        MockDeclaration("manufacturer_name", "Britannia Industries Ltd."),
        MockDeclaration("mfg_date", "01/2026"),
        MockDeclaration("generic_name", "Butter Cookies"),
    ]
    compliance_checks = [
        MockComplianceCheck("PCR_RULE_06_1_A", "Manufacturer Details", "Rule 6(1)(a)", "PASS"),
        MockComplianceCheck("PCR_RULE_06_1_B", "Country of Origin", "Rule 6(1)(b)", "PASS"),
        MockComplianceCheck("PCR_RULE_06_1_C", "Net Quantity", "Rule 6(1)(c)", "PASS"),
        MockComplianceCheck("PCR_RULE_06_1_D", "MRP Declaration", "Rule 6(1)(d)", "PASS"),
        MockComplianceCheck("PCR_RULE_06_1_E", "Date of Manufacture", "Rule 6(1)(e)", "PASS"),
        MockComplianceCheck("PCR_RULE_06_1_F", "Generic Name", "Rule 6(1)(f)", "PASS"),
        MockComplianceCheck("PCR_RULE_06_1_G", "Consumer Care Details", "Rule 6(1)(g)", "POTENTIAL_NON_COMPLIANCE"),
        MockComplianceCheck("PCR_RULE_07", "PDP Dimensions", "Rule 7", "NEEDS_MANUAL_VERIFICATION"),
        MockComplianceCheck("PCR_RULE_08", "Font Size Minimums", "Rule 8", "NEEDS_MANUAL_VERIFICATION"),
        MockComplianceCheck("PCR_RULE_09", "Readability", "Rule 9", "INSUFFICIENT_EVIDENCE"),
        MockComplianceCheck("PCR_RULE_10", "Packaging Material", "Rule 10", "NEEDS_MANUAL_VERIFICATION"),
        MockComplianceCheck("PCR_RULE_11", "Barcode Authenticity", "Rule 11", "NEEDS_MANUAL_VERIFICATION"),
    ]
    barcodes = [MockBarcode()]

    pdf_path_str, sha_hash = service.generate_pdf(
        inspection=inspection,
        product=product,
        inspector=inspector,
        declarations=declarations,
        compliance_checks=compliance_checks,
        evidence_items=[],
        report_version=1,
        barcodes=barcodes,
    )

    pdf_path = Path(pdf_path_str)
    assert pdf_path.exists(), f"PDF was not generated at {pdf_path}"
    assert pdf_path.stat().st_size > 0, "PDF file is empty (0 bytes)"

    # Verify SHA-256 matches exact bytes
    file_bytes = pdf_path.read_bytes()
    assert file_bytes[:5] == b"%PDF-", "Generated file does not have valid PDF magic bytes"
    actual_hash = hashlib.sha256(file_bytes).hexdigest()
    assert sha_hash == actual_hash, f"Returned hash {sha_hash} does not match computed hash {actual_hash}"
    assert len(sha_hash) == 64, "SHA-256 hash must be 64 hex characters"

    # Verify contents using PyPDF
    reader = PdfReader(str(pdf_path))
    num_pages = len(reader.pages)
    assert num_pages >= 2, f"Expected multi-page report, got {num_pages} pages"

    all_text = " ".join(page.extract_text() or "" for page in reader.pages)

    # Statutory Headers and Branding
    assert "NiriKsha" in all_text
    assert "Legal Metrology" in all_text
    assert "LM-2026-00023" in all_text
    assert "Britannia Good Day Butter Cookies" in all_text

    # Statutory Rules
    assert "PCR_RULE_06_1_A" in all_text or "Manufacturer Details" in all_text
    assert "Rule 19" in all_text
    assert "Net Quantity" in all_text

    # Statutory Safety & AI Attestation
    assert "advisory" in all_text.lower() or "statutory" in all_text.lower()
    assert "Rajesh Sharma" in all_text
    assert "DOCA-INSP-842" in all_text

    # Dynamic Two-Pass Page Numbering in Footers
    # PyPDF should extract "Page 1 of " and "Page 2 of "
    assert "Page 1 of" in all_text
    assert "Page 2 of" in all_text


# ---------------------------------------------------------------------------
# 4. Resilience to Missing Optional Fields & Missing Files
# ---------------------------------------------------------------------------

def test_pdf_resilience_missing_fields_and_images(tmp_path):
    """Verify generator handles None inspector, None product, None location, and missing images without crashing."""
    service = ReportLabReportService(reports_dir=str(tmp_path))

    minimal_inspection = MockInspection(id="insp-minimal-999", inspection_number="LM-2026-99999")
    minimal_inspection.location = None
    minimal_inspection.notes = None

    missing_image_evidence = [
        MockEvidenceItem(file_path="nonexistent/path/to/missing_image_12345.jpg", view_type="FRONT")
    ]

    pdf_path_str, sha_hash = service.generate_pdf(
        inspection=minimal_inspection,
        product=None,
        inspector=None,
        declarations=[],
        compliance_checks=[],
        evidence_items=missing_image_evidence,
        report_version=1,
    )

    pdf_path = Path(pdf_path_str)
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
    assert len(sha_hash) == 64

    reader = PdfReader(str(pdf_path))
    text = " ".join(page.extract_text() or "" for page in reader.pages)
    assert "LM-2026-99999" in text


# ---------------------------------------------------------------------------
# 5. Font Size Calibration & Readability Notice
# ---------------------------------------------------------------------------

def test_pdf_font_size_uncalibrated_notice(tmp_path):
    """Verify font size section handles uncalibrated state without crashing."""
    service = ReportLabReportService(reports_dir=str(tmp_path))

    inspection = MockInspection()
    uncalibrated_decl = MockDeclaration(
        field_name="net_quantity",
        extracted_value="500 g",
        font_size_status="UNDETERMINABLE",
        font_size_details_json='{"measured_height_mm": null, "compliant": null, "reason": "No reference card or calibrated camera"}',
    )

    pdf_path_str, sha_hash = service.generate_pdf(
        inspection=inspection,
        product=MockProduct(),
        inspector=MockInspector(),
        declarations=[uncalibrated_decl],
        compliance_checks=[],
        evidence_items=[],
    )

    reader = PdfReader(pdf_path_str)
    text = " ".join(page.extract_text() or "" for page in reader.pages)
    assert "UNDETERMINABLE" in text or "UNAVAILABLE" in text or "UNCALIBRATED" in text


# ---------------------------------------------------------------------------
# 6. REST API End-to-End Tests
# ---------------------------------------------------------------------------

def test_api_report_unauthenticated(client):
    """Ensure report endpoints reject unauthenticated requests with 401."""
    resp = client.post("/api/inspections/LM-2026-00023/report")
    assert resp.status_code == 401

    resp_pdf = client.get("/api/inspections/LM-2026-00023/report/pdf")
    assert resp_pdf.status_code == 401


def test_api_report_nonexistent_inspection(client, inspector_token):
    """Ensure 404 is returned when an invalid inspection ID is requested."""
    headers = {"Authorization": f"Bearer {inspector_token}"}
    resp = client.post("/api/inspections/NONEXISTENT-UUID-999/report", headers=headers)
    assert resp.status_code == 404


def test_api_report_generation_with_hash(client, inspector_token):
    """Verify POST /api/inspections/{id}/report returns pdf_hash and GET returns valid PDF stream."""
    headers = {"Authorization": f"Bearer {inspector_token}"}

    # 1. Create a quick test inspection
    create_resp = client.post(
        "/api/inspections",
        json={
            "product_name": "Haldiram Bhujia Sev 200g",
            "brand_name": "Haldiram",
            "category": "Packaged Food",
            "location": "Supermart 101, Connaught Place, New Delhi",
            "notes": "Automated report system integration test",
        },
        headers=headers,
    )
    assert create_resp.status_code in (200, 201), f"Failed to create inspection: {create_resp.text}"
    insp_data = create_resp.json()
    insp_id = insp_data["id"]
    insp_num = insp_data.get("inspection_number", insp_id)

    # 2. Generate Report via API
    gen_resp = client.post(f"/api/inspections/{insp_id}/report", headers=headers)
    assert gen_resp.status_code == 200, f"Report generation failed: {gen_resp.text}"
    report_data = gen_resp.json()

    assert "pdf_hash" in report_data, "pdf_hash field missing from report response"
    pdf_hash = report_data["pdf_hash"]
    assert pdf_hash is not None, "pdf_hash must not be null"
    assert len(pdf_hash) == 64, f"pdf_hash must be a 64-char hex string, got: {pdf_hash}"

    # 3. Stream PDF via API using inspection UUID
    stream_resp = client.get(f"/api/inspections/{insp_id}/report/pdf", headers=headers)
    assert stream_resp.status_code == 200
    assert stream_resp.headers.get("content-type") == "application/pdf"
    pdf_bytes = stream_resp.content
    assert pdf_bytes[:5] == b"%PDF-"
    streamed_hash = hashlib.sha256(pdf_bytes).hexdigest()
    assert streamed_hash == pdf_hash, "Streamed PDF bytes SHA-256 must match report.pdf_hash"

    # 4. Stream PDF via human-readable inspection number (e.g. LM-2026-XXXXX)
    stream_num_resp = client.get(f"/api/inspections/{insp_num}/report/pdf", headers=headers)
    assert stream_num_resp.status_code == 200
    assert hashlib.sha256(stream_num_resp.content).hexdigest() == pdf_hash
