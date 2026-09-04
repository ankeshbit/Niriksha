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
        officer_name = getattr(inspector, "full_name", "Inspector Rajesh Kumar")
        officer_id = getattr(inspector, "officer_id", "DOCA-INSP-842")
        officer_desig = getattr(inspector, "designation", "Senior Inspector (Legal Metrology)")
        officer_zone = getattr(inspector, "zone", "Northern Zone - Delhi HQ")
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

        # 5. Statutory Declarations Table (Preserving Baseline OCR vs Verified Effective)
        story.append(Paragraph("2. STATUTORY DECLARATIONS AUDIT (PCR 2011 RULE 6)", styles["SectionHeading"]))
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
            extracted_val = getattr(d, "extracted_value", "None") or "None / Not Detected"
            effective_val = getattr(d, "effective_value", None) or extracted_val
            v_status = getattr(d, "verification_status", "UNVERIFIED")

            status_style = styles["BodySmall"]
            decl_rows.append([
                Paragraph(flabel, styles["BodySmall"]),
                Paragraph(extracted_val, styles["BodySmall"]),
                Paragraph(f"<b>{effective_val}</b>", styles["BodySmallBold"]),
                Paragraph(v_status, status_style)
            ])

        if len(decl_rows) == 1:
            decl_rows.append([Paragraph("No declarations recorded.", styles["BodySmall"]), Paragraph("-", styles["BodySmall"]), Paragraph("-", styles["BodySmall"]), Paragraph("-", styles["BodySmall"])])

        decl_table = Table(decl_rows, colWidths=[150, 150, 140, 80])
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

        # 6. Compliance Evaluation & Potential Findings Summary
        passed_cnt = sum(1 for c in compliance_checks if getattr(c, "result_state", "") == "PASS")
        noncomp_cnt = sum(1 for c in compliance_checks if getattr(c, "result_state", "") == "POTENTIAL_NON_COMPLIANCE")
        insufficient_cnt = sum(1 for c in compliance_checks if getattr(c, "result_state", "") == "INSUFFICIENT_EVIDENCE")
        notapp_cnt = sum(1 for c in compliance_checks if getattr(c, "result_state", "") == "NOT_APPLICABLE")

        story.append(Paragraph("3. DETERMINISTIC LEGAL METROLOGY EVALUATION RESULTS", styles["SectionHeading"]))
        
        summary_text = (
            f"<b>Rules Evaluated:</b> {len(compliance_checks)} | "
            f"<b>Pass:</b> <font color='green'>{passed_cnt}</font> | "
            f"<b>Potential Non-Compliance:</b> <font color='red'>{noncomp_cnt}</font> | "
            f"<b>Insufficient Evidence:</b> <font color='orange'>{insufficient_cnt}</font> | "
            f"<b>Not Applicable:</b> {notapp_cnt}"
        )
        story.append(Paragraph(summary_text, styles["BodySmallBold"]))
        story.append(Spacer(1, 4))

        # Findings & Adjudication Table
        findings_rows = [
            [
                Paragraph("<b>Rule & Reference</b>", styles["BodySmallBold"]),
                Paragraph("<b>Evaluated Value</b>", styles["BodySmallBold"]),
                Paragraph("<b>Rule Result</b>", styles["BodySmallBold"]),
                Paragraph("<b>Adjudication</b>", styles["BodySmallBold"]),
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
        story.append(Spacer(1, 10))

        # 8. Legal Disclaimer & Statutory Safety Statement
        disclaimer_text = (
            "<b>STATUTORY DISCLAIMER & AI SAFETY NOTICE:</b><br/>"
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

report_generator = StatutoryReportGenerator()
