import os
import cv2
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

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

class StatutoryReportGenerator:
    """
    Statutory Legal Metrology PDF Report Generator.
    Produces formal, evidence-backed inspection reports under PCR 2011.
    All data is derived from actual verified database records.
    """

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
        evidence_items: List[Any],
        report_version: int = 1
    ) -> str:
        insp_num = getattr(inspection, "inspection_number", "INSP-UNKNOWN")
        safe_insp_num = insp_num.replace("-", "_").replace("/", "_")
        filename = f"LM_Report_{safe_insp_num}_v{report_version}.pdf"
        output_path = self.reports_dir / filename

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()

        # Custom Government Style Palette
        PRIMARY_COLOR = colors.HexColor("#031635")
        SECONDARY_COLOR = colors.HexColor("#1e3a8a")
        ACCENT_COLOR = colors.HexColor("#0284c7")
        PASS_COLOR = colors.HexColor("#15803d")
        FAIL_COLOR = colors.HexColor("#b91c1c")
        WARN_COLOR = colors.HexColor("#b45309")
        TEXT_DARK = colors.HexColor("#0f172a")
        BG_LIGHT = colors.HexColor("#f8fafc")
        BORDER_COLOR = colors.HexColor("#cbd5e1")

        # Custom Paragraph Styles
        styles.add(ParagraphStyle(
            name="GovtHeader",
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            alignment=1,
            textColor=PRIMARY_COLOR
        ))
        styles.add(ParagraphStyle(
            name="GovtSubHeader",
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            alignment=1,
            textColor=colors.HexColor("#475569")
        ))
        styles.add(ParagraphStyle(
            name="ReportTitle",
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            alignment=1,
            textColor=PRIMARY_COLOR,
            spaceAfter=8
        ))
        styles.add(ParagraphStyle(
            name="SectionHeading",
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=PRIMARY_COLOR,
            spaceBefore=6,
            spaceAfter=4
        ))
        styles.add(ParagraphStyle(
            name="BodySmall",
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=TEXT_DARK
        ))
        styles.add(ParagraphStyle(
            name="BodySmallBold",
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=TEXT_DARK
        ))
        styles.add(ParagraphStyle(
            name="DisclaimerText",
            fontName="Helvetica-Oblique",
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#64748b")
        ))

        story = []

        # 1. Header: NiriKsha — AI-Assisted Legal Metrology Inspection System
        story.append(Paragraph("NiriKsha — AI-ASSISTED LEGAL METROLOGY INSPECTION SYSTEM", styles["GovtHeader"]))
        story.append(Paragraph("DEPARTMENT OF CONSUMER AFFAIRS (DoCA) • NiriKsha (SIH Prototype 2026)", styles["GovtHeader"]))
        story.append(Paragraph("Packaged Commodities Compliance Verification under PCR 2011", styles["GovtSubHeader"]))
        story.append(Spacer(1, 4))
        story.append(HRFlowable(width="100%", thickness=1.5, color=PRIMARY_COLOR, spaceAfter=8))

        # 2. Document Title
        story.append(Paragraph("LEGAL METROLOGY INSPECTION REPORT", styles["ReportTitle"]))
        story.append(Paragraph(
            "Inspection summary generated from verified data under Legal Metrology (Packaged Commodities) Rules, 2011",
            styles["GovtSubHeader"]
        ))
        story.append(Spacer(1, 8))

        # 3. Metadata Table (Inspection & Officer Info)
        insp_date = inspection.created_at.strftime("%d-%b-%Y %H:%M UTC") if hasattr(inspection, "created_at") and inspection.created_at else datetime.utcnow().strftime("%d-%b-%Y %H:%M UTC")
        officer_name = getattr(inspector, "full_name", None) or "Unknown Inspector"
        officer_id = getattr(inspector, "officer_id", None) or "UNKNOWN"
        officer_desig = getattr(inspector, "designation", None) or "Inspector (Legal Metrology)"
        officer_zone = getattr(inspector, "zone", None) or "Unspecified Zone"
        location = getattr(inspection, "location", "Field Location")

        meta_data = [
            [
                Paragraph("<b>Inspection Number:</b>", styles["BodySmall"]),
                Paragraph(insp_num, styles["BodySmallBold"]),
                Paragraph("<b>Inspection Date:</b>", styles["BodySmall"]),
                Paragraph(insp_date, styles["BodySmall"])
            ],
            [
                Paragraph("<b>Inspecting Officer:</b>", styles["BodySmall"]),
                Paragraph(f"{officer_name} ({officer_id})", styles["BodySmall"]),
                Paragraph("<b>Designation / Zone:</b>", styles["BodySmall"]),
                Paragraph(f"{officer_desig} • {officer_zone}", styles["BodySmall"])
            ],
            [
                Paragraph("<b>Inspection Site:</b>", styles["BodySmall"]),
                Paragraph(location, styles["BodySmall"]),
                Paragraph("<b>Report Version:</b>", styles["BodySmall"]),
                Paragraph(f"v{report_version} (Official Finalized)", styles["BodySmall"])
            ]
        ]
        meta_table = Table(meta_data, colWidths=[110, 150, 110, 150])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
            ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 8))

        # 4. Product Details Block
        prod_name = getattr(product, "product_name", "Packaged Commodity") if product else "Packaged Commodity"
        brand_name = getattr(product, "brand_name", "N/A") if product else "N/A"
        category = getattr(product, "category", "Packaged Food") if product else "Packaged Food"
        batch_no = getattr(product, "batch_number", "N/A") if product and product.batch_number else "N/A"

        story.append(Paragraph("1. PACKAGED COMMODITY SPECIFICATIONS", styles["SectionHeading"]))
        prod_data = [
            [
                Paragraph("<b>Commodity Name:</b>", styles["BodySmall"]),
                Paragraph(prod_name, styles["BodySmallBold"]),
                Paragraph("<b>Brand / Trademark:</b>", styles["BodySmall"]),
                Paragraph(brand_name or "N/A", styles["BodySmall"])
            ],
            [
                Paragraph("<b>Category:</b>", styles["BodySmall"]),
                Paragraph(category, styles["BodySmall"]),
                Paragraph("<b>Batch / Lot Number:</b>", styles["BodySmall"]),
                Paragraph(batch_no or "N/A", styles["BodySmall"])
            ]
        ]
        prod_table = Table(prod_data, colWidths=[110, 150, 110, 150])
        prod_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.white),
            ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(prod_table)
        story.append(Spacer(1, 8))

        # 4b. Package Image Evidence & Quality Audit
        story.append(Paragraph("2. PACKAGE IMAGE EVIDENCE & QUALITY AUDIT", styles["SectionHeading"]))
        images = getattr(inspection, "images", []) or []
        img_evidence_rows = [
            [
                Paragraph("<b>Package Panel View</b>", styles["BodySmallBold"]),
                Paragraph("<b>Capture Status</b>", styles["BodySmallBold"]),
                Paragraph("<b>Image Quality Assessment</b>", styles["BodySmallBold"]),
                Paragraph("<b>Evidence Reference</b>", styles["BodySmallBold"])
            ]
        ]
        
        # Front image
        front_img = next((img for img in images if img.view_type == "front"), None)
        if front_img:
            q_status = "Acceptable Quality" if front_img.quality_status in ["GOOD", "ACCEPTABLE"] else "Quality Warning (Blurry / Low Contrast)"
            ref_name = Path(front_img.file_path).name if front_img.file_path else "front_panel.jpg"
            img_evidence_rows.append([
                Paragraph("<b>Front Panel (Required)</b>", styles["BodySmall"]),
                Paragraph("<font color='green'>Captured</font>", styles["BodySmallBold"]),
                Paragraph(q_status, styles["BodySmall"]),
                Paragraph(ref_name, styles["BodySmall"])
            ])
        else:
            img_evidence_rows.append([
                Paragraph("<b>Front Panel (Required)</b>", styles["BodySmall"]),
                Paragraph("<font color='red'>Not Provided</font>", styles["BodySmallBold"]),
                Paragraph("—", styles["BodySmall"]),
                Paragraph("—", styles["BodySmall"])
            ])

        # Back image
        back_img = next((img for img in images if img.view_type == "back"), None)
        if back_img:
            q_status = "Acceptable Quality" if back_img.quality_status in ["GOOD", "ACCEPTABLE"] else "Quality Warning (Blurry / Low Contrast)"
            ref_name = Path(back_img.file_path).name if back_img.file_path else "back_panel.jpg"
            img_evidence_rows.append([
                Paragraph("<b>Back Panel (Required)</b>", styles["BodySmall"]),
                Paragraph("<font color='green'>Captured</font>", styles["BodySmallBold"]),
                Paragraph(q_status, styles["BodySmall"]),
                Paragraph(ref_name, styles["BodySmall"])
            ])
        else:
            img_evidence_rows.append([
                Paragraph("<b>Back Panel (Required)</b>", styles["BodySmall"]),
                Paragraph("<font color='red'>Not Provided</font>", styles["BodySmallBold"]),
                Paragraph("—", styles["BodySmall"]),
                Paragraph("—", styles["BodySmall"])
            ])

        # Side image (Optional)
        side_img = next((img for img in images if img.view_type in ["side", "panel"]), None)
        if side_img:
            q_status = "Acceptable Quality" if side_img.quality_status in ["GOOD", "ACCEPTABLE"] else "Quality Warning (Blurry / Low Contrast)"
            ref_name = Path(side_img.file_path).name if side_img.file_path else "side_panel.jpg"
            img_evidence_rows.append([
                Paragraph("<b>Side Panel (Optional)</b>", styles["BodySmall"]),
                Paragraph("<font color='green'>Captured</font>", styles["BodySmallBold"]),
                Paragraph(q_status, styles["BodySmall"]),
                Paragraph(ref_name, styles["BodySmall"])
            ])
        else:
            img_evidence_rows.append([
                Paragraph("<b>Side Panel (Optional)</b>", styles["BodySmall"]),
                Paragraph("<font color='#6b7280'>Optional — Not Captured</font>", styles["BodySmall"]),
                Paragraph("N/A", styles["BodySmall"]),
                Paragraph("No side view required", styles["BodySmall"])
            ])

        # Additional evidence images if any
        other_imgs = [img for img in images if img.view_type not in ["front", "back", "side", "panel"]]
        for o_img in other_imgs:
            q_status = "Acceptable Quality" if o_img.quality_status in ["GOOD", "ACCEPTABLE"] else "Quality Warning"
            ref_name = Path(o_img.file_path).name if o_img.file_path else "evidence_panel.jpg"
            img_evidence_rows.append([
                Paragraph(f"<b>Additional: {o_img.view_type.title()}</b>", styles["BodySmall"]),
                Paragraph("<font color='green'>Captured</font>", styles["BodySmallBold"]),
                Paragraph(q_status, styles["BodySmall"]),
                Paragraph(ref_name, styles["BodySmall"])
            ])

        img_table = Table(img_evidence_rows, colWidths=[130, 110, 150, 130])
        img_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BG_LIGHT),
            ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(img_table)
        story.append(Spacer(1, 8))

        # 5. Statutory Declarations Table (Preserving Baseline OCR vs Verified Effective)
        story.append(Paragraph("3. STATUTORY DECLARATIONS AUDIT (PCR 2011 RULE 6)", styles["SectionHeading"]))
        decl_rows = [
            [
                Paragraph("<b>Statutory Field</b>", styles["BodySmallBold"]),
                Paragraph("<b>Baseline OCR Extracted</b>", styles["BodySmallBold"]),
                Paragraph("<b>Verified / Effective Value</b>", styles["BodySmallBold"]),
                Paragraph("<b>Verification Status</b>", styles["BodySmallBold"])
            ]
        ]

        field_labels = {
            "commodity_name": "Commodity Name (Rule 6(1)(f))",
            "manufacturer_details": "Manufacturer/Packer (Rule 6(1)(a))",
            "net_quantity": "Net Quantity (Rule 6(1)(c))",
            "mrp": "MRP (Rule 6(1)(e))",
            "date_of_manufacture_packing": "Mfg/Packing Date (Rule 6(1)(d))",
            "consumer_care_details": "Consumer Care (Rule 6(1)(g))",
            "country_of_origin": "Country of Origin (Rule 6(1)(b))"
        }

        for d in declarations:
            fname = getattr(d, "field_name", "")
            flabel = field_labels.get(fname, fname.replace("_", " ").title())
            ext_status = getattr(d, "extraction_status", "EXTRACTED")
            v_status = getattr(d, "verification_status", "UNVERIFIED")

            if ext_status == "OCR_UNAVAILABLE":
                extracted_val = "<i>OCR Unavailable</i>"
                provenance = "Manual Verification Required"
            elif ext_status == "NOT_FOUND" or not getattr(d, "extracted_value", None):
                extracted_val = "<i>Not Detected on Label</i>"
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

            if v_status == "CORRECTED":
                status_display = "<b>Inspector Corrected</b>"
            elif v_status == "NEEDS_MANUAL_VERIFICATION":
                status_display = "<font color='#b45309'>Needs Verification</font>"
            elif v_status == "VERIFIED":
                status_display = "<font color='green'>Verified</font>"
            else:
                status_display = v_status

            decl_rows.append([
                Paragraph(flabel, styles["BodySmall"]),
                Paragraph(extracted_val, styles["BodySmall"]),
                Paragraph(f"<b>{effective_val}</b>", styles["BodySmall"]),
                Paragraph(status_display, styles["BodySmall"])
            ])

        if len(decl_rows) == 1:
            decl_rows.append([Paragraph("No declarations recorded.", styles["BodySmall"]), Paragraph("-", styles["BodySmall"]), Paragraph("-", styles["BodySmall"]), Paragraph("-", styles["BodySmall"])])

        decl_table = Table(decl_rows, colWidths=[150, 145, 145, 80])
        decl_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BG_LIGHT),
            ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(decl_table)
        story.append(Spacer(1, 8))

        # 2b. Cross-Image Conflicts & Verification Section
        conflict_rows = [
            [
                Paragraph("<b>Field Name</b>", styles["BodySmallBold"]),
                Paragraph("<b>Conflicting Observations Across Images</b>", styles["BodySmallBold"]),
                Paragraph("<b>Adjudication Requirement</b>", styles["BodySmallBold"])
            ]
        ]
        has_any_conflict = False
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
                conflict_rows.append([
                    Paragraph(flabel, styles["BodySmallBold"]),
                    Paragraph(f"<font color='#b45309'>{cand_str}</font>", styles["BodySmall"]),
                    Paragraph("<b>NEEDS MANUAL VERIFICATION</b><br/><font color='#475569'><i>Inspector must verify physical package</i></font>", styles["BodySmall"])
                ])

        story.append(Paragraph("4. CROSS-IMAGE VERIFICATION & CONFLICT AUDIT", styles["SectionHeading"]))
        if has_any_conflict:
            conf_table = Table(conflict_rows, colWidths=[140, 240, 140])
            conf_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), BG_LIGHT),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#f59e0b")),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.append(conf_table)
        else:
            story.append(Paragraph(
                "<i>No cross-image conflicts detected. Declaration values are consistent across all captured package views.</i>",
                styles["BodySmall"]
            ))
        story.append(Spacer(1, 8))

        # 6. Compliance Evaluation & Potential Findings Summary
        passed_cnt = sum(1 for c in compliance_checks if getattr(c, "result_state", "") == "PASS")
        noncomp_cnt = sum(1 for c in compliance_checks if getattr(c, "result_state", "") == "POTENTIAL_NON_COMPLIANCE")
        insufficient_cnt = sum(1 for c in compliance_checks if getattr(c, "result_state", "") in ["INSUFFICIENT_EVIDENCE", "NEEDS_MANUAL_VERIFICATION"])
        notapp_cnt = sum(1 for c in compliance_checks if getattr(c, "result_state", "") == "NOT_APPLICABLE")

        story.append(Paragraph("5. AI-ASSISTED PRELIMINARY OBSERVATIONS VS. INSPECTOR ADJUDICATIONS", styles["SectionHeading"]))
        story.append(Paragraph("<i>Core Principle: AI detects and assists. Rules evaluate. Evidence supports. Inspector decides.</i>", styles["DisclaimerText"]))
        story.append(Spacer(1, 4))
        
        summary_text = (
            f"<b>Rules Evaluated:</b> {len(compliance_checks)} | "
            f"<b>Pass:</b> <font color='green'>{passed_cnt}</font> | "
            f"<b>Potential Non-Compliance:</b> <font color='red'>{noncomp_cnt}</font> | "
            f"<b>Needs Manual Verification:</b> <font color='orange'>{insufficient_cnt}</font> | "
            f"<b>Not Applicable:</b> {notapp_cnt}"
        )
        story.append(Paragraph(summary_text, styles["BodySmallBold"]))
        story.append(Spacer(1, 4))

        # Findings & Adjudication Table
        findings_rows = [
            [
                Paragraph("<b>Rule & Reference</b>", styles["BodySmallBold"]),
                Paragraph("<b>Evaluated Value</b>", styles["BodySmallBold"]),
                Paragraph("<b>AI System Finding</b>", styles["BodySmallBold"]),
                Paragraph("<b>Inspector Decision</b>", styles["BodySmallBold"]),
                Paragraph("<b>Inspector Remarks</b>", styles["BodySmallBold"])
            ]
        ]

        for c in compliance_checks:
            rcode = getattr(c, "rule_code", "")
            title = getattr(c, "title", rcode)
            eval_val = getattr(c, "extracted_value", None) or "None"
            rstate = getattr(c, "result_state", "PASS")
            adj_status = getattr(c, "adjudication_status", "PENDING")
            notes = getattr(c, "adjudication_notes", "-") or "-"

            # Pull rule version and statutory reference
            r_ver = getattr(getattr(c, "rule_version", None), "version_number", 1)
            stat_ref = getattr(getattr(c, "rule_version", None), "statutory_reference", "")

            rule_display = f"<b>{rcode}</b> (v{r_ver})<br/>{title}"
            if stat_ref:
                rule_display += f"<br/><font color='#475569'><i>{stat_ref}</i></font>"

            # Pull evidence highlight if available
            ev_list = getattr(c, "evidence", [])
            if ev_list:
                ev_snippets = [getattr(e, "highlight_text", "") for e in ev_list if getattr(e, "highlight_text", "")]
                if ev_snippets:
                    eval_val += f"<br/><font color='#0284c7'>[Evidence: {', '.join(ev_snippets[:2])}]</font>"

            rstate_color = PASS_COLOR if rstate == "PASS" else (FAIL_COLOR if rstate == "POTENTIAL_NON_COMPLIANCE" else WARN_COLOR)
            adj_color = FAIL_COLOR if adj_status == "CONFIRMED" else (PASS_COLOR if adj_status == "DISMISSED" else colors.black)

            findings_rows.append([
                Paragraph(rule_display, styles["BodySmall"]),
                Paragraph(eval_val, styles["BodySmall"]),
                Paragraph(f"<font color='{rstate_color.hexval()}'><b>{rstate}</b></font>", styles["BodySmall"]),
                Paragraph(f"<font color='{adj_color.hexval()}'><b>{adj_status}</b></font>", styles["BodySmall"]),
                Paragraph(notes, styles["BodySmall"])
            ])

        if len(findings_rows) == 1:
            findings_rows.append([Paragraph("No findings recorded.", styles["BodySmall"]), Paragraph("-", styles["BodySmall"]), Paragraph("-", styles["BodySmall"]), Paragraph("-", styles["BodySmall"]), Paragraph("-", styles["BodySmall"])])

        findings_table = Table(findings_rows, colWidths=[140, 100, 90, 80, 110])
        findings_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BG_LIGHT),
            ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(findings_table)
        story.append(Spacer(1, 8))

        # 7. Final Statutory Overall Status Block
        overall_status = getattr(inspection, "overall_status", "PENDING_REVIEW") or "PENDING_REVIEW"
        status_color = PASS_COLOR if overall_status == "NO_POTENTIAL_VIOLATIONS" else (FAIL_COLOR if overall_status == "POTENTIAL_NON_COMPLIANCE" else WARN_COLOR)
        
        status_box = [
            [
                Paragraph("<b>FINAL STATUTORY INSPECTION STATUS:</b>", styles["BodySmallBold"]),
                Paragraph(f"<font color='{status_color.hexval()}'><b>{overall_status}</b></font>", styles["ReportTitle"])
            ]
        ]
        status_table = Table(status_box, colWidths=[220, 300])
        status_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
            ('BOX', (0, 0), (-1, -1), 1.0, status_color),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(status_table)
        story.append(Spacer(1, 8))

        # 8. Physical Quantity Limitation Notice
        quantity_limitation_text = (
            "<b>PHYSICAL NET QUANTITY LIMITATION:</b><br/>"
            "Physical net quantity cannot be verified from package images alone. Measurement using appropriate physical verification equipment is required where applicable. "
            "A package photograph can evaluate the printed net-quantity declaration under Rule 6(1)(c) but cannot verify "
            "whether the package physically contains the declared quantity. Physical quantity verification requires physical "
            "measurement/weighing and the applicable sampling/testing procedures under Rule 19 and the schedules of the "
            "Legal Metrology (Packaged Commodities) Rules, 2011."
        )
        story.append(Paragraph(quantity_limitation_text, styles["DisclaimerText"]))
        story.append(Spacer(1, 6))

        # 9. Legal Disclaimer & Statutory Safety Statement
        disclaimer_text = (
            "<b>STATUTORY DISCLAIMER & AI SAFETY NOTICE:</b><br/>"
            "Authoritative Legal Source: <i>The Legal Metrology (Packaged Commodities) Rules, 2011</i>.<br/>"
            "This report is generated by NiriKsha (AI-Assisted Legal Metrology Packaged-Commodity Inspection System, SIH Prototype 2026) for inspection-support purposes. "
            "Computer Vision and Machine Learning algorithms are employed exclusively for optical text extraction and data normalization. "
            "All compliance checks are deterministically evaluated against configured statutory rules under the Legal Metrology (Packaged Commodities) "
            "Rules, 2011. Final compliance adjudication, legal determinations, and enforcement actions remain strictly under the human authority "
            "of the designated inspecting officer."
        )
        story.append(Paragraph(disclaimer_text, styles["DisclaimerText"]))
        story.append(Spacer(1, 14))

        # 9. Official Sign-Off Block
        sign_data = [
            [
                Paragraph(f"<b>Inspecting Officer:</b><br/>{officer_name}<br/>{officer_desig}", styles["BodySmall"]),
                Paragraph(f"<b>Official Seal / Stamp:</b><br/>Department of Consumer Affairs<br/>Legal Metrology Field Office", styles["BodySmall"]),
                Paragraph("<b>Signature & Date:</b><br/><br/>_______________________", styles["BodySmall"])
            ]
        ]
        sign_table = Table(sign_data, colWidths=[170, 170, 180])
        sign_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(sign_table)

        doc.build(story)
        return str(output_path)

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

        # ----------------- 7. CROSS-IMAGE VERIFICATION & CONFLICT AUDIT -----------------
        add_heading("5. CROSS-IMAGE VERIFICATION & CONFLICT AUDIT")
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
        add_heading("6. DETERMINISTIC PCR 2011 STATUTORY EVALUATION CHECKS")
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
        add_heading("7. AI-ASSISTED PRELIMINARY OBSERVATIONS VS. INSPECTOR ADJUDICATION")
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
        add_heading("8. FINAL STATUTORY COMPLIANCE DETERMINATION")
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
        add_heading("9. STATUTORY LIMITATIONS & AI SAFETY NOTICE")

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
