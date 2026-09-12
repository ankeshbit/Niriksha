"""
backend/reportlab_report_service.py

Production-Grade ReportLab PDF Inspection Report Generator for NiriKsha.
Generates authoritative, evidence-backed statutory compliance reports under PCR 2011.
Features:
- ReportLab Platypus architecture with modular components
- NumberedCanvas dynamic 'Page X of Y' total page stamping and running headers/footers
- Canonical backend bucket aggregation matching FindingsScreen exactly
- Exact SHA-256 integrity hash calculated from generated PDF bytes
- Graceful handling of missing images or fields without crashing
- Completely read-only with respect to inspection records
"""

import os
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from reportlab.platypus import SimpleDocTemplate, PageBreak, Spacer

from backend.report_styles import (
    A4,
    MARGIN_LEFT,
    MARGIN_RIGHT,
    MARGIN_TOP,
    MARGIN_BOTTOM,
    NumberedCanvas,
)
from backend.report_components import (
    build_report_header,
    build_inspection_and_product_details,
    build_kpi_summary_section,
    build_package_images_evidence_section,
    build_ocr_declarations_table,
    build_unified_compliance_matrix,
    build_font_size_readability_placement_audit,
    build_barcode_qr_evidence_section,
    build_findings_and_adjudication_table,
    build_final_adjudication_and_legal_block,
)


class ReportLabReportService:
    """Canonical ReportLab PDF Generator for NiriKsha."""

    def __init__(self, reports_dir: str = "./generated_reports"):
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def generate_pdf(
        self,
        inspection: Any,
        product: Any,
        inspector: Any,
        declarations: List[Any],
        compliance_checks: List[Any],
        evidence_items: Optional[List[Any]] = None,
        report_version: int = 1,
        report_id: Optional[str] = None,
        barcodes: Optional[List[Any]] = None,
    ) -> Tuple[str, str]:
        """
        Generates an authoritative A4 portrait statutory PDF report using ReportLab.

        Returns:
            Tuple[str, str]: (absolute_or_relative_pdf_path, sha256_hash)
        """
        insp_num = getattr(inspection, "inspection_number", "INSP-UNKNOWN")
        safe_insp_num = insp_num.replace("-", "_").replace("/", "_")
        filename = f"LM_Report_{safe_insp_num}_v{report_version}.pdf"
        output_path = self.reports_dir / filename

        rep_id = report_id or getattr(getattr(inspection, "report", None), "id", None) or f"REP-{safe_insp_num}-v{report_version}"
        gen_time = datetime.utcnow()

        # Document Template Setup
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=MARGIN_LEFT,
            rightMargin=MARGIN_RIGHT,
            topMargin=MARGIN_TOP,
            bottomMargin=MARGIN_BOTTOM,
        )

        # Factory for NumberedCanvas to inject runtime metadata
        def canvas_factory(*args, **kwargs):
            c = NumberedCanvas(*args, **kwargs)
            c.inspection_number = insp_num
            c.report_version = report_version
            c.report_id = rep_id
            c.generated_date_str = gen_time.strftime("%d-%b-%Y %H:%M UTC")
            return c

        story = []

        # 1. Header & Title
        story.extend(build_report_header(
            inspection_number=insp_num,
            report_id=rep_id,
            report_version=report_version,
            generated_at=gen_time,
        ))

        # 2. Inspection & Product Specifications
        story.extend(build_inspection_and_product_details(
            inspection=inspection,
            product=product,
            inspector=inspector,
            report_version=report_version,
        ))

        # 3. Executive KPI Summary Cards (Canonical Bucket Logic)
        story.extend(build_kpi_summary_section(compliance_checks))

        # 4. Package Image Evidence
        images = getattr(inspection, "images", []) or []
        story.extend(build_package_images_evidence_section(images))

        # 5. Statutory Declarations Table (PCR Rule 6)
        story.extend(build_ocr_declarations_table(declarations))

        # 6. Unified Declaration Compliance Matrix (PS 26034)
        story.extend(build_unified_compliance_matrix(declarations))

        # 7. Spatial Placement, Font Height & Readability Audit
        story.extend(build_font_size_readability_placement_audit(declarations))

        # 8. Auxiliary Barcode / QR Evidence
        story.extend(build_barcode_qr_evidence_section(inspection, barcodes=barcodes))

        # 9. Findings & Inspector Adjudication Table
        story.extend(build_findings_and_adjudication_table(compliance_checks))

        # 10. Final Statutory Compliance Determination, Safety Notices & Attestation
        story.extend(build_final_adjudication_and_legal_block(
            inspection=inspection,
            inspector=inspector,
            report_version=report_version,
        ))

        # Build Document
        doc.build(story, canvasmaker=canvas_factory)

        # Calculate SHA-256 of exact generated bytes
        with open(output_path, "rb") as f:
            pdf_bytes = f.read()
        sha256_hash = hashlib.sha256(pdf_bytes).hexdigest()

        return str(output_path), sha256_hash
