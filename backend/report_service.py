import os
import cv2
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image as RLImage,
    KeepTogether,
    HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

def _docx_set_cell_background(cell, hex_color: str):
    fill_hex = hex_color.lstrip("#")
    shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shading_elm)

def _docx_set_cell_margins(cell, top=80, bottom=80, left=120, right=120):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tcPr.append(tcMar)

def _docx_set_table_borders(table, border_color="CBD5E1"):
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'<w:top w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'<w:left w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'<w:right w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'<w:insideV w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)

def _parse_declaration_compliance_row(d: Any) -> Dict[str, str]:
    """Helper to parse or derive validation matrix values for report generation."""
    matrix_raw = getattr(d, "validation_matrix_json", None)
    if matrix_raw:
        if isinstance(matrix_raw, str):
            try:
                matrix_raw = json.loads(matrix_raw)
            except Exception:
                matrix_raw = {}
        if isinstance(matrix_raw, dict) and matrix_raw.get("declaration"):
            return {
                "field_name": matrix_raw.get("declaration") or getattr(d, "field_name", ""),
                "present": "YES" if matrix_raw.get("present") else "NO",
                "correct": "YES" if matrix_raw.get("correct") else ("NO" if matrix_raw.get("correct") is False else "PENDING"),
                "readable": str(matrix_raw.get("readable") or "UNKNOWN"),
                "placement": str(matrix_raw.get("placement") or "NOT_DETERMINABLE"),
                "font_size": str(matrix_raw.get("font_size") or "UNDETERMINABLE"),
                "format": "COMPLIANT" if matrix_raw.get("format") is True else ("NON_COMPLIANT" if matrix_raw.get("format") is False else str(matrix_raw.get("format") or "UNCERTAIN")),
                "status": str(matrix_raw.get("overall_status") or "MANUAL_VERIFICATION_REQUIRED")
            }

    ext_val = getattr(d, "extracted_value", None)
    has_val = bool(ext_val and str(ext_val).strip() and getattr(d, "extraction_status", "") != "NOT_FOUND")
    p_status = getattr(d, "placement_status", None) or "NOT_DETERMINABLE"
    f_status = getattr(d, "font_size_status", None) or "UNDETERMINABLE"
    r_status = getattr(d, "readability_status", None) or ("READABLE" if has_val else "UNREADABLE")
    fmt_status = getattr(d, "format_status", None) or ("COMPLIANT" if has_val else "UNCERTAIN")
    v_status = getattr(d, "verification_status", None) or "UNVERIFIED"

    correct_str = "YES" if v_status == "VERIFIED" else ("CORRECTED" if v_status == "CORRECTED" else "PENDING")
    is_compliant = (has_val and p_status == "PLACEMENT_COMPLIANT" and r_status == "READABLE" and f_status == "FONT_SIZE_COMPLIANT" and fmt_status == "COMPLIANT")
    overall = "COMPLIANT" if is_compliant else "MANUAL_VERIFICATION_REQUIRED"

    return {
        "field_name": getattr(d, "field_name", ""),
        "present": "YES" if has_val else "NO",
        "correct": correct_str,
        "readable": r_status,
        "placement": p_status,
        "font_size": f_status,
        "format": fmt_status,
        "status": overall
    }


class StatutoryReportGenerator:
    """
    Statutory Legal Metrology PDF Report Generator.
    Produces formal, evidence-backed inspection reports under PCR 2011.
    All data is derived from actual verified database records.
    """

    def __init__(self, reports_dir: str = "./generated_reports"):
        self._reports_dir = Path(reports_dir)
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        from backend.reportlab_report_service import ReportLabReportService
        self.pdf_service = ReportLabReportService(reports_dir=str(self._reports_dir))
        self.last_pdf_hash: Optional[str] = None

    @property
    def reports_dir(self) -> Path:
        return self._reports_dir

    @reports_dir.setter
    def reports_dir(self, val: Any):
        self._reports_dir = Path(val)
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        if hasattr(self, "pdf_service") and self.pdf_service:
            self.pdf_service.reports_dir = self._reports_dir

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
    ) -> str:
        """
        Canonical ReportLab PDF generation for NiriKsha statutory inspections.
        Generates full multi-page evidence-backed A4 report, calculates SHA-256 hash,
        and returns file path.
        """
        pdf_path, sha_hash = self.pdf_service.generate_pdf(
            inspection=inspection,
            product=product,
            inspector=inspector,
            declarations=declarations,
            compliance_checks=compliance_checks,
            evidence_items=evidence_items,
            report_version=report_version,
            report_id=report_id,
            barcodes=barcodes,
        )
        self.last_pdf_hash = sha_hash
        return pdf_path

    def generate_pdf_with_hash(
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
        """Returns both PDF output path and SHA-256 hash."""
        pdf_path, sha_hash = self.pdf_service.generate_pdf(
            inspection=inspection,
            product=product,
            inspector=inspector,
            declarations=declarations,
            compliance_checks=compliance_checks,
            evidence_items=evidence_items,
            report_version=report_version,
            report_id=report_id,
            barcodes=barcodes,
        )
        self.last_pdf_hash = sha_hash
        return pdf_path, sha_hash

    def generate_docx(
        self,
        inspection: Any,
        product: Any,
        inspector: Any,
        declarations: List[Any],
        compliance_checks: List[Any],
        evidence_items: List[Any],
        report_version: int = 1
    ) -> str:
        """
        Generates an official editable Microsoft Word (.docx) compliance report.
        Reuses the exact same verified database snapshot as the statutory PDF report.
        Satisfies PS 26034 requirement for editable compliance reports.
        """
        insp_num = getattr(inspection, "inspection_number", "INSP-UNKNOWN")
        safe_insp_num = insp_num.replace("-", "_").replace("/", "_")
        filename = f"LM_Report_{safe_insp_num}_v{report_version}.docx"
        output_path = self.reports_dir / filename

        doc = docx.Document()

        # Page Setup: Standard A4/Letter margins (0.75 in / 54 pt)
        for s in doc.sections:
            s.top_margin = Inches(0.75)
            s.bottom_margin = Inches(0.75)
            s.left_margin = Inches(0.75)
            s.right_margin = Inches(0.75)

        # Statutory Styling Palette
        HEX_PRIMARY = "031635"
        HEX_SECONDARY = "1E3A8A"
        HEX_ACCENT = "0284C7"
        HEX_PASS = "15803D"
        HEX_FAIL = "B91C1C"
        HEX_WARN = "B45309"
        HEX_DARK = "0F172A"
        HEX_MUTED = "475569"
        HEX_LIGHT = "F8FAFC"
        HEX_BORDER = "CBD5E1"

        CLR_PRIMARY = RGBColor(3, 22, 53)
        CLR_SECONDARY = RGBColor(30, 58, 138)
        CLR_ACCENT = RGBColor(2, 132, 199)
        CLR_PASS = RGBColor(21, 128, 61)
        CLR_FAIL = RGBColor(185, 28, 28)
        CLR_WARN = RGBColor(180, 83, 9)
        CLR_DARK = RGBColor(15, 23, 42)
        CLR_MUTED = RGBColor(71, 85, 105)

        # Helper: add styled paragraph
        def add_p(text: str = "", bold=False, italic=False, size=9.5, color=CLR_DARK, align=WD_ALIGN_PARAGRAPH.LEFT, space_before=0, space_after=4):
            p = doc.add_paragraph()
            p.alignment = align
            p.paragraph_format.space_before = Pt(space_before)
            p.paragraph_format.space_after = Pt(space_after)
            if text:
                r = p.add_run(str(text))
                r.bold = bold
                r.italic = italic
                r.font.size = Pt(size)
                r.font.color.rgb = color
                r.font.name = "Calibri"
            return p

        def add_heading(text: str):
            return add_p(text, bold=True, size=11, color=CLR_PRIMARY, space_before=14, space_after=4)

        def populate_cell(cell, text: str, bold=False, italic=False, size=8.5, color=CLR_DARK, align=WD_ALIGN_PARAGRAPH.LEFT, bg_color=None):
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = align
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(str(text if text is not None else "—"))
            r.bold = bold
            r.italic = italic
            r.font.size = Pt(size)
            r.font.color.rgb = color
            r.font.name = "Calibri"
            if bg_color:
                _docx_set_cell_background(cell, bg_color)
            _docx_set_cell_margins(cell, top=70, bottom=70, left=100, right=100)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

        def populate_cell_runs(cell, runs, bg_color=None, align=WD_ALIGN_PARAGRAPH.LEFT):
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = align
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            for text, bold, italic, size, color in runs:
                r = p.add_run(str(text if text is not None else ""))
                r.bold = bold
                r.italic = italic
                r.font.size = Pt(size)
                r.font.color.rgb = color
                r.font.name = "Calibri"
            if bg_color:
                _docx_set_cell_background(cell, bg_color)
            _docx_set_cell_margins(cell, top=70, bottom=70, left=100, right=100)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

        def format_header_row(table, headers, widths=None):
            hdr_cells = table.rows[0].cells
            for i, h in enumerate(headers):
                populate_cell(hdr_cells[i], h, bold=True, size=8.5, color=RGBColor(255, 255, 255), bg_color=HEX_PRIMARY)
            if widths:
                for row in table.rows:
                    for i, w in enumerate(widths):
                        row.cells[i].width = Inches(w)

        # ----------------- 1. COVER / HEADER -----------------
        add_p("GOVERNMENT OF INDIA • MINISTRY OF CONSUMER AFFAIRS, FOOD & PUBLIC DISTRIBUTION", bold=True, size=9.5, color=CLR_PRIMARY, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
        add_p("DEPARTMENT OF CONSUMER AFFAIRS • LEGAL METROLOGY DIVISION", bold=True, size=11, color=CLR_SECONDARY, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
        add_p("NiriKsha — AI-Assisted Legal Metrology Packaged-Commodity Inspection System (SIH Prototype 2026)", italic=True, size=8.5, color=CLR_MUTED, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=6)
        add_p("LEGAL METROLOGY COMPLIANCE INSPECTION REPORT", bold=True, size=13, color=CLR_PRIMARY, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
        add_p("Statutory Inspection Summary under Legal Metrology (Packaged Commodities) Rules, 2011", size=9, color=CLR_MUTED, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
        add_p(f"[ EDITABLE DIGITAL COMPLIANCE REPORT EXPORT — PS 26034 • v{report_version} ]", bold=True, size=8.5, color=CLR_ACCENT, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=10)

        # ----------------- 2. INSPECTION METADATA TABLE -----------------
        insp_date = inspection.created_at.strftime("%d-%b-%Y %H:%M UTC") if hasattr(inspection, "created_at") and inspection.created_at else datetime.utcnow().strftime("%d-%b-%Y %H:%M UTC")
        officer_name = getattr(inspector, "full_name", None) or "Unknown Inspector"
        officer_id = getattr(inspector, "officer_id", None) or "UNKNOWN"
        officer_desig = getattr(inspector, "designation", None) or "Inspector (Legal Metrology)"
        officer_zone = getattr(inspector, "zone", None) or "Unspecified Zone"
        location = getattr(inspection, "location", "Field Location")

        meta_table = doc.add_table(rows=3, cols=4)
        _docx_set_table_borders(meta_table, HEX_BORDER)
        meta_widths = [1.5, 2.0, 1.5, 2.0]

        meta_rows_data = [
            [
                [("Inspection ID:", True, False, 8.5, CLR_DARK)],
                [(insp_num, True, False, 8.5, CLR_PRIMARY)],
                [("Inspection Date:", True, False, 8.5, CLR_DARK)],
                [(insp_date, False, False, 8.5, CLR_DARK)],
            ],
            [
                [("Inspecting Officer:", True, False, 8.5, CLR_DARK)],
                [(f"{officer_name} ({officer_id})", False, False, 8.5, CLR_DARK)],
                [("Designation / Zone:", True, False, 8.5, CLR_DARK)],
                [(f"{officer_desig} • {officer_zone}", False, False, 8.5, CLR_DARK)],
            ],
            [
                [("Inspection Site:", True, False, 8.5, CLR_DARK)],
                [(location, False, False, 8.5, CLR_DARK)],
                [("Report Version:", True, False, 8.5, CLR_DARK)],
                [(f"v{report_version} (Official Finalized Copy)", True, False, 8.5, CLR_PRIMARY)],
            ]
        ]

        for r_idx, row_runs in enumerate(meta_rows_data):
            for c_idx, cell_runs in enumerate(row_runs):
                bg = HEX_LIGHT if c_idx % 2 == 0 else "FFFFFF"
                populate_cell_runs(meta_table.rows[r_idx].cells[c_idx], cell_runs, bg_color=bg)

        for row in meta_table.rows:
            for i, w in enumerate(meta_widths):
                row.cells[i].width = Inches(w)

        # ----------------- 3. PACKAGED COMMODITY SPECIFICATIONS -----------------
        add_heading("1. PACKAGED COMMODITY SPECIFICATIONS")
        prod_name = getattr(product, "product_name", "Packaged Commodity") if product else "Packaged Commodity"
        brand_name = getattr(product, "brand_name", "N/A") if product else "N/A"
        category = getattr(product, "category", "Packaged Food") if product else "Packaged Food"
        batch_no = getattr(product, "batch_number", "N/A") if product and product.batch_number else "N/A"

        mfr_decl = next((d for d in declarations if getattr(d, "field_name", "") == "manufacturer_details"), None)
        mfr_val = (getattr(mfr_decl, "effective_value", None) or getattr(mfr_decl, "extracted_value", None) or "Not Declared") if mfr_decl else "Not Declared"

        prod_table = doc.add_table(rows=3, cols=4)
        _docx_set_table_borders(prod_table, HEX_BORDER)
        prod_widths = [1.5, 2.0, 1.5, 2.0]

        prod_rows_data = [
            [
                [("Commodity Name:", True, False, 8.5, CLR_DARK)],
                [(prod_name, True, False, 8.5, CLR_PRIMARY)],
                [("Brand / Trademark:", True, False, 8.5, CLR_DARK)],
                [(brand_name or "N/A", False, False, 8.5, CLR_DARK)],
            ],
            [
                [("Category:", True, False, 8.5, CLR_DARK)],
                [(category, False, False, 8.5, CLR_DARK)],
                [("Batch / Lot Number:", True, False, 8.5, CLR_DARK)],
                [(batch_no or "N/A", False, False, 8.5, CLR_DARK)],
            ],
            [
                [("Manufacturer / Packer:", True, False, 8.5, CLR_DARK)],
                [(mfr_val, False, False, 8.5, CLR_DARK)],
                [("Packaging Type:", True, False, 8.5, CLR_DARK)],
                [("Pre-packaged Commodity (Rule 2(l))", False, False, 8.5, CLR_DARK)],
            ]
        ]

        for r_idx, row_runs in enumerate(prod_rows_data):
            for c_idx, cell_runs in enumerate(row_runs):
                bg = HEX_LIGHT if c_idx % 2 == 0 else "FFFFFF"
                populate_cell_runs(prod_table.rows[r_idx].cells[c_idx], cell_runs, bg_color=bg)

        for row in prod_table.rows:
            for i, w in enumerate(prod_widths):
                row.cells[i].width = Inches(w)

        # ----------------- 4. PACKAGE IMAGE EVIDENCE & QUALITY AUDIT -----------------
        add_heading("2. PACKAGE IMAGE EVIDENCE & QUALITY AUDIT")
        images = getattr(inspection, "images", []) or []

        img_table = doc.add_table(rows=1, cols=4)
        _docx_set_table_borders(img_table, HEX_BORDER)
        img_widths = [1.8, 1.3, 2.1, 1.8]
        format_header_row(img_table, ["Package Panel View", "Capture Status", "Image Quality Assessment", "Evidence Reference"], img_widths)

        captured_images_to_embed = []

        # Standard panel views
        panel_configs = [
            ("Front Panel (Required)", "front", True),
            ("Back Panel (Required)", "back", True),
            ("Side Panel (Optional)", "side", False)
        ]

        for label, vtype, is_req in panel_configs:
            matching_img = next((img for img in images if getattr(img, "view_type", "") == vtype or (vtype == "side" and getattr(img, "view_type", "") == "panel")), None)
            row_cells = img_table.add_row().cells
            if matching_img:
                q_status = "Acceptable Quality" if getattr(matching_img, "quality_status", "") in ["GOOD", "ACCEPTABLE"] else "Quality Warning (Blurry / Low Contrast)"
                q_score = getattr(matching_img, "quality_score", None)
                if q_score is not None:
                    q_status += f" (Score: {q_score:.2f})"
                ref_name = Path(matching_img.file_path).name if getattr(matching_img, "file_path", None) else f"{vtype}_panel.jpg"
                populate_cell(row_cells[0], label, bold=True, size=8.5)
                populate_cell(row_cells[1], "Captured", bold=True, color=CLR_PASS, size=8.5)
                populate_cell(row_cells[2], q_status, size=8.5)
                populate_cell(row_cells[3], ref_name, size=8.5)
                if getattr(matching_img, "file_path", None) and Path(matching_img.file_path).exists():
                    captured_images_to_embed.append((label, matching_img.file_path, q_status))
            else:
                populate_cell(row_cells[0], label, bold=True, size=8.5)
                populate_cell(row_cells[1], "Not Provided" if is_req else "Optional — Not Captured", bold=is_req, color=CLR_FAIL if is_req else CLR_MUTED, size=8.5)
                populate_cell(row_cells[2], "—" if is_req else "N/A", size=8.5)
                populate_cell(row_cells[3], "—" if is_req else "No side view required", size=8.5)

        # Additional panel views
        other_imgs = [img for img in images if getattr(img, "view_type", "") not in ["front", "back", "side", "panel"]]
        for o_img in other_imgs:
            v_type = getattr(o_img, "view_type", "additional")
            label = f"Additional: {v_type.title()}"
            q_status = "Acceptable Quality" if getattr(o_img, "quality_status", "") in ["GOOD", "ACCEPTABLE"] else "Quality Warning"
            ref_name = Path(o_img.file_path).name if getattr(o_img, "file_path", None) else f"{v_type}.jpg"
            row_cells = img_table.add_row().cells
            populate_cell(row_cells[0], label, bold=True, size=8.5)
            populate_cell(row_cells[1], "Captured", bold=True, color=CLR_PASS, size=8.5)
            populate_cell(row_cells[2], q_status, size=8.5)
            populate_cell(row_cells[3], ref_name, size=8.5)
            if getattr(o_img, "file_path", None) and Path(o_img.file_path).exists():
                captured_images_to_embed.append((label, o_img.file_path, q_status))

        for row in img_table.rows:
            for i, w in enumerate(img_widths):
                row.cells[i].width = Inches(w)

        # Embedded Image Evidence Gallery (if files exist on disk)
        if captured_images_to_embed:
            add_p("Embedded Photographic Evidence Panels:", bold=True, size=9, color=CLR_SECONDARY, space_before=6, space_after=4)
            for img_label, img_path, img_q in captured_images_to_embed:
                try:
                    p_img = doc.add_paragraph()
                    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p_img.paragraph_format.space_before = Pt(4)
                    p_img.paragraph_format.space_after = Pt(2)
                    run_img = p_img.add_run()
                    run_img.add_picture(str(img_path), width=Inches(2.4))
                    add_p(f"Evidence Plate: {img_label} — {Path(img_path).name} ({img_q})", italic=True, size=8, color=CLR_MUTED, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=6)
                except Exception as e:
                    add_p(f"Evidence Plate: {img_label} ({Path(img_path).name}) — [Image embed preview: {e}]", italic=True, size=8, color=CLR_MUTED)

        # ----------------- 5. OCR & MULTI-MODAL TEXT EXTRACTION EVIDENCE -----------------
        add_heading("3. OCR & MULTI-MODAL TEXT EXTRACTION EVIDENCE")
        add_p("Raw optical character recognition records with extraction engine provenance, confidence scores, and panel coordinates.", italic=True, size=8.5, color=CLR_MUTED, space_after=4)

        ocr_table = doc.add_table(rows=1, cols=6)
        _docx_set_table_borders(ocr_table, HEX_BORDER)
        ocr_widths = [1.2, 2.0, 1.0, 0.8, 1.0, 1.0]
        format_header_row(ocr_table, ["Requirement", "Extracted OCR Text", "OCR Engine", "Confidence", "Source Panel", "Spatial BBox"], ocr_widths)

        field_labels = {
            "commodity_name": "Commodity Name (Rule 6(1)(f))",
            "manufacturer_details": "Manufacturer/Packer (Rule 6(1)(a))",
            "net_quantity": "Net Quantity (Rule 6(1)(c))",
            "mrp": "MRP (Rule 6(1)(e))",
            "date_of_manufacture_packing": "Mfg/Packing Date (Rule 6(1)(d))",
            "consumer_care_details": "Consumer Care (Rule 6(1)(g))",
            "country_of_origin": "Country of Origin (Rule 6(1)(b))"
        }

        if declarations:
            for d in declarations:
                fname = getattr(d, "field_name", "")
                flabel = field_labels.get(fname, fname.replace("_", " ").title())
                raw_text = getattr(d, "extracted_value", None) or "Not Detected"
                conf = getattr(d, "confidence_score", None)
                conf_str = f"{conf * 100:.1f}%" if conf is not None and conf > 0 else "N/A"
                engine = getattr(d, "ocr_engine", None) or "PaddleOCR / Hybrid"
                src_panel = getattr(d, "source_image_id", None) or "Package View"
                bbox = getattr(d, "bounding_box", None) or "Detected on Panel"

                row_cells = ocr_table.add_row().cells
                populate_cell(row_cells[0], flabel, bold=True, size=8)
                populate_cell(row_cells[1], raw_text, size=8)
                populate_cell(row_cells[2], engine, size=8)
                populate_cell(row_cells[3], conf_str, size=8)
                populate_cell(row_cells[4], str(src_panel), size=8)
                populate_cell(row_cells[5], str(bbox), size=8)
        else:
            row_cells = ocr_table.add_row().cells
            populate_cell(row_cells[0], "No OCR declarations recorded", size=8)
            for c_i in range(1, 6):
                populate_cell(row_cells[c_i], "—", size=8)

        for row in ocr_table.rows:
            for i, w in enumerate(ocr_widths):
                row.cells[i].width = Inches(w)

        # ----------------- 6. STATUTORY DECLARATIONS AUDIT (PCR 2011 RULE 6) -----------------
        add_heading("4. STATUTORY DECLARATIONS AUDIT (PCR 2011 RULE 6)")
        decl_table = doc.add_table(rows=1, cols=5)
        _docx_set_table_borders(decl_table, HEX_BORDER)
        decl_widths = [1.6, 1.5, 1.3, 1.4, 1.2]
        format_header_row(decl_table, ["Statutory Field (Rule Ref)", "Baseline OCR Extracted", "Source & Provenance", "Verified / Effective Value", "Verification Status"], decl_widths)

        for d in declarations:
            fname = getattr(d, "field_name", "")
            flabel = field_labels.get(fname, fname.replace("_", " ").title())
            ext_status = getattr(d, "extraction_status", "EXTRACTED")
            v_status = getattr(d, "verification_status", "UNVERIFIED")

            if ext_status == "OCR_UNAVAILABLE":
                extracted_val = "OCR Unavailable"
                provenance = "Manual Verification Required"
            elif ext_status == "NOT_FOUND" or not getattr(d, "extracted_value", None):
                extracted_val = "Not Detected on Label"
                provenance = "Pending Verification"
            else:
                extracted_val = getattr(d, "extracted_value", "")
                provenance = "AI/OCR Extracted"

            effective_val = getattr(d, "effective_value", None) or getattr(d, "extracted_value", None)
            if not effective_val:
                if fname == "commodity_name" and prod_name:
                    effective_val = f"{prod_name} (Inspector Input)"
                else:
                    effective_val = "Not Declared"

            status_color = CLR_DARK
            if v_status == "CORRECTED":
                status_display = "Inspector Corrected"
                status_color = CLR_WARN
            elif v_status == "NEEDS_MANUAL_VERIFICATION":
                status_display = "Needs Verification"
                status_color = CLR_WARN
            elif v_status == "VERIFIED":
                status_display = "Verified"
                status_color = CLR_PASS
            else:
                status_display = v_status

            row_cells = decl_table.add_row().cells
            populate_cell(row_cells[0], flabel, bold=True, size=8)
            populate_cell(row_cells[1], extracted_val, italic=(ext_status != "EXTRACTED"), size=8)
            populate_cell(row_cells[2], provenance, size=8)
            populate_cell(row_cells[3], effective_val, bold=True, size=8)
            populate_cell(row_cells[4], status_display, bold=True, color=status_color, size=8)

        if not declarations:
            row_cells = decl_table.add_row().cells
            populate_cell(row_cells[0], "No declarations recorded", size=8)
            for c_i in range(1, 5):
                populate_cell(row_cells[c_i], "—", size=8)

        for row in decl_table.rows:
            for i, w in enumerate(decl_widths):
                row.cells[i].width = Inches(w)

        # ----------------- 6b. UNIFIED DECLARATION COMPLIANCE MATRIX (SIH PS 26034) -----------------
        add_heading("5. UNIFIED DECLARATION COMPLIANCE MATRIX (SIH PS 26034)")
        add_p("Multi-dimensional audit across Presence, Correctness, Readability, Placement, Font Size, Format, and Adjudication Status under PCR 2011.", italic=True, size=8.5, color=CLR_MUTED, space_after=4)

        matrix_table = doc.add_table(rows=1, cols=8)
        _docx_set_table_borders(matrix_table, HEX_BORDER)
        mat_widths = [1.5, 0.6, 0.7, 0.9, 1.0, 1.0, 0.8, 1.0]
        format_header_row(matrix_table, ["Declaration", "Present", "Correct", "Readable", "Placement", "Font Size", "Format", "Status"], mat_widths)

        for d in declarations:
            mrow = _parse_declaration_compliance_row(d)
            fn = mrow["field_name"]
            flabel = field_labels.get(fn, fn.replace("_", " ").title())
            p_color = CLR_PASS if mrow["present"] == "YES" else CLR_FAIL
            c_color = CLR_PASS if mrow["correct"] == "YES" else CLR_WARN
            r_color = CLR_PASS if "READABLE" in mrow["readable"] else CLR_WARN
            pl_color = CLR_PASS if "COMPLIANT" in mrow["placement"] else CLR_WARN
            fs_color = CLR_PASS if "COMPLIANT" in mrow["font_size"] else CLR_MUTED
            fmt_color = CLR_PASS if "COMP" in mrow["format"] else CLR_WARN
            st_color = CLR_PASS if mrow["status"] == "COMPLIANT" else CLR_WARN

            row_cells = matrix_table.add_row().cells
            populate_cell(row_cells[0], flabel, bold=True, size=8)
            populate_cell(row_cells[1], mrow["present"], bold=True, color=p_color, size=8)
            populate_cell(row_cells[2], mrow["correct"], bold=True, color=c_color, size=8)
            populate_cell(row_cells[3], mrow["readable"], color=r_color, size=8)
            populate_cell(row_cells[4], mrow["placement"].replace("PLACEMENT_", ""), color=pl_color, size=8)
            populate_cell(row_cells[5], mrow["font_size"].replace("FONT_SIZE_", ""), color=fs_color, size=8)
            populate_cell(row_cells[6], mrow["format"], color=fmt_color, size=8)
            populate_cell(row_cells[7], mrow["status"].replace("MANUAL_VERIFICATION_REQUIRED", "MANUAL VERIF"), bold=True, color=st_color, size=8)

        if not declarations:
            row_cells = matrix_table.add_row().cells
            populate_cell(row_cells[0], "No declarations evaluated", size=8)
            for c_i in range(1, 8):
                populate_cell(row_cells[c_i], "—", size=8)

        for row in matrix_table.rows:
            for i, w in enumerate(mat_widths):
                row.cells[i].width = Inches(w)

        # ----------------- 6c. SPATIAL PLACEMENT & READABILITY EVIDENCE AUDIT -----------------
        add_heading("6. SPATIAL PLACEMENT, READABILITY & FONT-SIZE AUDIT")
        add_p("Principal Display Panel (PDP) placement (Rule 6/7/12), physical scale calibration (Rule 9 Table 1), and image crop clarity.", italic=True, size=8.5, color=CLR_MUTED, space_after=4)

        audit_table = doc.add_table(rows=1, cols=4)
        _docx_set_table_borders(audit_table, HEX_BORDER)
        aud_widths = [1.8, 1.9, 2.2, 1.6]
        format_header_row(audit_table, ["Declaration", "Placement Rule & Region", "Font Height & Calibration", "Clarity & Contrast"], aud_widths)

        for d in declarations:
            fname = getattr(d, "field_name", "")
            flabel = field_labels.get(fname, fname.replace("_", " ").title())
            p_st = getattr(d, "placement_status", "NOT_DETERMINABLE") or "NOT_DETERMINABLE"
            f_st = getattr(d, "font_size_status", "UNDETERMINABLE") or "UNDETERMINABLE"
            r_st = getattr(d, "readability_status", "UNKNOWN") or "UNKNOWN"

            p_detail = ""
            p_raw = getattr(d, "placement_details_json", None)
            if p_raw:
                p_dict = json.loads(p_raw) if isinstance(p_raw, str) else p_raw
                if isinstance(p_dict, dict) and p_dict.get("detected_region"):
                    p_detail = f"\nRegion: {p_dict.get('detected_region')}"

            f_detail = ""
            f_raw = getattr(d, "font_size_details_json", None)
            if f_raw:
                f_dict = json.loads(f_raw) if isinstance(f_raw, str) else f_raw
                if isinstance(f_dict, dict) and f_dict.get("calibration_reference_present"):
                    f_detail = f"\n{f_dict.get('estimated_char_height_mm', 0):.1f}mm (Min: {f_dict.get('required_min_height_mm', 0):.1f}mm)"
                else:
                    f_detail = "\nNo physical calibration scale (Rule 9 Table 1)"

            row_cells = audit_table.add_row().cells
            populate_cell(row_cells[0], flabel, bold=True, size=8)
            populate_cell(row_cells[1], f"{p_st}{p_detail}", size=8)
            populate_cell(row_cells[2], f"{f_st}{f_detail}", size=8)
            populate_cell(row_cells[3], r_st, size=8)

        if not declarations:
            row_cells = audit_table.add_row().cells
            populate_cell(row_cells[0], "No placement records", size=8)
            for c_i in range(1, 4):
                populate_cell(row_cells[c_i], "—", size=8)

        for row in audit_table.rows:
            for i, w in enumerate(aud_widths):
                row.cells[i].width = Inches(w)

        # ----------------- 7. CROSS-IMAGE VERIFICATION & CONFLICT AUDIT -----------------
        add_heading("7. CROSS-IMAGE VERIFICATION & CONFLICT AUDIT")
        has_any_conflict = False
        conflict_items = []
        for d in declarations:
            fname = getattr(d, "field_name", "")
            flabel = field_labels.get(fname, fname.replace("_", " ").title())
            is_conf = getattr(d, "extraction_status", "") == "CONFLICTING"
            reason = getattr(d, "correction_reason", "")
            if is_conf or (reason and reason.startswith('{"conflict":')):
                has_any_conflict = True
                cand_str = getattr(d, "extracted_value", "Conflicting values detected across panels")
                if reason and reason.startswith('{"conflict":'):
                    try:
                        cdata = json.loads(reason)
                        cand_list = [f"{c.get('value')} ({c.get('source_image_id') or 'view'})" for c in cdata.get("candidates", [])]
                        if cand_list:
                            cand_str = " vs ".join(cand_list)
                    except Exception:
                        pass
                conflict_items.append((flabel, cand_str))

        if has_any_conflict:
            conf_table = doc.add_table(rows=1, cols=3)
            _docx_set_table_borders(conf_table, HEX_WARN)
            conf_widths = [2.0, 3.2, 1.8]
            format_header_row(conf_table, ["Field Name", "Conflicting Observations Across Panels", "Adjudication Requirement"], conf_widths)
            for flabel, cand_str in conflict_items:
                row_cells = conf_table.add_row().cells
                populate_cell(row_cells[0], flabel, bold=True, size=8)
                populate_cell(row_cells[1], cand_str, color=CLR_WARN, size=8)
                populate_cell(row_cells[2], "NEEDS MANUAL VERIFICATION\n(Physical Package Check Required)", bold=True, color=CLR_FAIL, size=8)
            for row in conf_table.rows:
                for i, w in enumerate(conf_widths):
                    row.cells[i].width = Inches(w)
        else:
            add_p("No cross-image conflicts detected. Declaration values are consistent across all captured package views.", italic=True, size=8.5, color=CLR_MUTED)

        # ----------------- 8. DETERMINISTIC PCR 2011 RULE EVALUATION CHECKS -----------------
        add_heading("8. DETERMINISTIC PCR 2011 STATUTORY EVALUATION CHECKS")
        rule_table = doc.add_table(rows=1, cols=6)
        _docx_set_table_borders(rule_table, HEX_BORDER)
        rule_widths = [1.4, 2.0, 0.9, 1.2, 0.6, 0.9]
        format_header_row(rule_table, ["Rule ID", "Statutory Rule Description", "Applicability", "Legal Source", "Version", "Evaluation Result"], rule_widths)

        for c in compliance_checks:
            rcode = getattr(c, "rule_code", "")
            title = getattr(c, "title", rcode)
            rstate = getattr(c, "result_state", "PASS")
            r_ver = getattr(getattr(c, "rule_version", None), "version_number", 1)
            stat_ref = getattr(getattr(c, "rule_version", None), "statutory_reference", "PCR 2011")
            is_appl = "Applicable" if rstate != "NOT_APPLICABLE" else "Not Applicable"

            state_color = CLR_PASS if rstate == "PASS" else (CLR_FAIL if rstate == "POTENTIAL_NON_COMPLIANCE" else CLR_WARN)

            row_cells = rule_table.add_row().cells
            populate_cell(row_cells[0], rcode, bold=True, size=8)
            populate_cell(row_cells[1], title, size=8)
            populate_cell(row_cells[2], is_appl, size=8)
            populate_cell(row_cells[3], stat_ref or "PCR 2011", italic=True, size=8)
            populate_cell(row_cells[4], f"v{r_ver}", size=8)
            populate_cell(row_cells[5], rstate, bold=True, color=state_color, size=8)

        if not compliance_checks:
            row_cells = rule_table.add_row().cells
            populate_cell(row_cells[0], "No compliance evaluations recorded", size=8)
            for c_i in range(1, 6):
                populate_cell(row_cells[c_i], "—", size=8)

        for row in rule_table.rows:
            for i, w in enumerate(rule_widths):
                row.cells[i].width = Inches(w)

        # ----------------- 9. FINDINGS & INSPECTOR ADJUDICATION -----------------
        add_heading("9. AI-ASSISTED PRELIMINARY OBSERVATIONS VS. INSPECTOR ADJUDICATION")
        add_p("Core Principle: AI detects and assists. Rules evaluate. Evidence supports. Inspector decides.", italic=True, size=8, color=CLR_MUTED, space_after=4)

        find_table = doc.add_table(rows=1, cols=5)
        _docx_set_table_borders(find_table, HEX_BORDER)
        find_widths = [1.5, 1.8, 1.2, 1.1, 1.4]
        format_header_row(find_table, ["Rule & Reference", "Evaluated Value & Evidence", "AI System Finding", "Inspector Decision", "Inspector Remarks"], find_widths)

        for c in compliance_checks:
            rcode = getattr(c, "rule_code", "")
            title = getattr(c, "title", rcode)
            eval_val = getattr(c, "extracted_value", None) or "None"
            rstate = getattr(c, "result_state", "PASS")
            adj_status = getattr(c, "adjudication_status", "PENDING")
            notes = getattr(c, "adjudication_notes", "-") or "-"
            stat_ref = getattr(getattr(c, "rule_version", None), "statutory_reference", "")

            # Evidence highlight
            ev_list = getattr(c, "evidence", [])
            if ev_list:
                ev_snippets = [getattr(e, "highlight_text", "") for e in ev_list if getattr(e, "highlight_text", "")]
                if ev_snippets:
                    eval_val += f" [Evidence: {', '.join(ev_snippets[:2])}]"

            rule_text = f"{rcode}\n{title}"
            if stat_ref:
                rule_text += f"\n({stat_ref})"

            rstate_color = CLR_PASS if rstate == "PASS" else (CLR_FAIL if rstate == "POTENTIAL_NON_COMPLIANCE" else CLR_WARN)
            adj_color = CLR_FAIL if adj_status == "CONFIRMED" else (CLR_PASS if adj_status == "DISMISSED" else CLR_DARK)

            row_cells = find_table.add_row().cells
            populate_cell(row_cells[0], rule_text, bold=True, size=8)
            populate_cell(row_cells[1], eval_val, size=8)
            populate_cell(row_cells[2], rstate, bold=True, color=rstate_color, size=8)
            populate_cell(row_cells[3], adj_status, bold=True, color=adj_color, size=8)
            populate_cell(row_cells[4], notes, size=8)

        if not compliance_checks:
            row_cells = find_table.add_row().cells
            populate_cell(row_cells[0], "No findings recorded", size=8)
            for c_i in range(1, 5):
                populate_cell(row_cells[c_i], "—", size=8)

        for row in find_table.rows:
            for i, w in enumerate(find_widths):
                row.cells[i].width = Inches(w)

        # ----------------- 10. FINAL STATUTORY OVERALL STATUS BLOCK -----------------
        add_heading("10. FINAL STATUTORY COMPLIANCE DETERMINATION")
        overall_status = getattr(inspection, "overall_status", "PENDING_REVIEW") or "PENDING_REVIEW"
        status_color = CLR_PASS if overall_status == "NO_POTENTIAL_VIOLATIONS" else (CLR_FAIL if overall_status == "POTENTIAL_NON_COMPLIANCE" else CLR_WARN)
        status_border_hex = HEX_PASS if overall_status == "NO_POTENTIAL_VIOLATIONS" else (HEX_FAIL if overall_status == "POTENTIAL_NON_COMPLIANCE" else HEX_WARN)

        decision_table = doc.add_table(rows=1, cols=2)
        _docx_set_table_borders(decision_table, status_border_hex)
        decision_widths = [3.0, 4.0]
        c0, c1 = decision_table.rows[0].cells
        populate_cell(c0, "FINAL STATUTORY INSPECTION STATUS:", bold=True, size=10, color=CLR_DARK, bg_color=HEX_LIGHT)
        populate_cell(c1, overall_status, bold=True, size=12, color=status_color, bg_color=HEX_LIGHT)
        c0.width = Inches(decision_widths[0])
        c1.width = Inches(decision_widths[1])

        # Architecture separation clarification
        add_p("Legal Metrology Compliance Workflow Traceability:", bold=True, size=9, color=CLR_SECONDARY, space_before=6, space_after=2)
        add_p("• AI-Generated Observations: Machine-extracted baseline optical text and preliminary field candidate values.", size=8.5, color=CLR_DARK, space_after=1)
        add_p("• Rule-Engine Results: Deterministic statutory evaluations executed against configured PCR 2011 statutory rules.", size=8.5, color=CLR_DARK, space_after=1)
        add_p("• Inspector-Verified Findings: Human inspecting officer verification of package evidence, mandatory fields, and corrections.", size=8.5, color=CLR_DARK, space_after=1)
        add_p("• Final Inspector Decision: Authoritative statutory compliance determination under the Legal Metrology Act, 2009.", size=8.5, color=CLR_DARK, space_after=6)

        # ----------------- 11. STATUTORY LIMITATIONS & SAFETY STATEMENTS -----------------
        add_heading("11. STATUTORY LIMITATIONS & AI SAFETY NOTICE")

        # Physical Quantity Limitation Notice
        quantity_limitation_text = (
            "PHYSICAL NET QUANTITY LIMITATION (RULE 19): "
            "Physical net quantity cannot be verified from package images alone. Measurement using appropriate physical verification equipment is required where applicable. "
            "A package photograph can evaluate the printed net-quantity declaration under Rule 6(1)(c) but cannot verify "
            "whether the package physically contains the declared quantity. Physical quantity verification requires physical "
            "measurement/weighing and the applicable sampling/testing procedures under Rule 19 and the schedules of the "
            "Legal Metrology (Packaged Commodities) Rules, 2011."
        )
        add_p(quantity_limitation_text, italic=True, size=8, color=CLR_MUTED, space_after=4)

        # Statutory Disclaimer & AI Safety Notice
        disclaimer_text = (
            "STATUTORY DISCLAIMER & AI SAFETY NOTICE: "
            "Authoritative Legal Source: The Legal Metrology (Packaged Commodities) Rules, 2011. "
            "This report is generated by NiriKsha (AI-Assisted Legal Metrology Packaged-Commodity Inspection System, SIH Prototype 2026) for inspection-support purposes. "
            "Computer Vision and Machine Learning algorithms are employed exclusively for optical text extraction and data normalization. "
            "All compliance checks are deterministically evaluated against configured statutory rules under the Legal Metrology (Packaged Commodities) "
            "Rules, 2011. Final compliance adjudication, legal determinations, and enforcement actions remain strictly under the human authority "
            "of the designated inspecting officer."
        )
        add_p(disclaimer_text, italic=True, size=8, color=CLR_MUTED, space_after=10)

        # ----------------- 12. OFFICIAL SIGN-OFF BLOCK -----------------
        add_heading("10. OFFICIAL INSPECTION SIGN-OFF & ATTESTATION")
        sign_table = doc.add_table(rows=1, cols=3)
        _docx_set_table_borders(sign_table, HEX_BORDER)
        sign_widths = [2.3, 2.3, 2.4]

        s0, s1, s2 = sign_table.rows[0].cells
        populate_cell_runs(s0, [
            ("Inspecting Officer:\n", True, False, 8.5, CLR_DARK),
            (f"{officer_name}\n", False, False, 8.5, CLR_DARK),
            (f"{officer_desig}\nOfficer ID: {officer_id}", False, False, 8, CLR_MUTED)
        ])
        populate_cell_runs(s1, [
            ("Official Seal / Stamp:\n", True, False, 8.5, CLR_DARK),
            ("Department of Consumer Affairs\n", False, False, 8.5, CLR_DARK),
            (f"Legal Metrology Field Office • {officer_zone}", False, False, 8, CLR_MUTED)
        ])
        populate_cell_runs(s2, [
            ("Signature & Date:\n\n", True, False, 8.5, CLR_DARK),
            ("___________________________\n", False, False, 8.5, CLR_DARK),
            (f"Date: {insp_date}", False, False, 8, CLR_MUTED)
        ])

        for i, w in enumerate(sign_widths):
            sign_table.rows[0].cells[i].width = Inches(w)

        doc.save(str(output_path))
        return str(output_path)

report_generator = StatutoryReportGenerator()
