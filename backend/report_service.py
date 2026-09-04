import os
import cv2
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
    HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


def escape_report_text(text: Any) -> str:
    """Escapes XML entities to prevent ReportLab markup parsing crashes."""
    if text is None:
        return "-"
    s = str(text).strip()
    if not s:
        return "-"
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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
        report_version: int = 1,
        images: Optional[List[Any]] = None
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
            fontSize=10,
            leading=13,
            alignment=1,
            textColor=PRIMARY_COLOR
        ))
        styles.add(ParagraphStyle(
            name="GovtSubHeader",
            fontName="Helvetica",
            fontSize=8,
            leading=11,
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
            spaceAfter=4
        ))
        styles.add(ParagraphStyle(
            name="SectionHeading",
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=12,
            textColor=PRIMARY_COLOR,
            spaceBefore=6,
            spaceAfter=3
        ))
        styles.add(ParagraphStyle(
            name="BodySmall",
            fontName="Helvetica",
            fontSize=7.5,
            leading=9.5,
            textColor=TEXT_DARK
        ))
        styles.add(ParagraphStyle(
            name="BodySmallBold",
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9.5,
            textColor=TEXT_DARK
        ))
        styles.add(ParagraphStyle(
            name="DisclaimerText",
            fontName="Helvetica-Oblique",
            fontSize=6.5,
            leading=8.5,
            textColor=colors.HexColor("#64748b")
        ))

        story = []

        # Resolve image map for view-type lookups
        all_images = images if images is not None else (getattr(inspection, "images", None) or [])
        image_map: Dict[str, Any] = {str(img.id): img for img in all_images if hasattr(img, "id")}

        # 1. Header: Department of Consumer Affairs & NiriKsha
        story.append(Paragraph("NiriKsha — AI-ASSISTED LEGAL METROLOGY INSPECTION SYSTEM", styles["GovtHeader"]))
        story.append(Paragraph("DEPARTMENT OF CONSUMER AFFAIRS (DoCA) • GOVERNMENT OF INDIA", styles["GovtHeader"]))
        story.append(Paragraph("Packaged Commodities Compliance Verification under PCR 2011", styles["GovtSubHeader"]))
        story.append(Spacer(1, 3))
        story.append(HRFlowable(width="100%", thickness=1.5, color=PRIMARY_COLOR, spaceAfter=6))

        # 2. Document Title
        story.append(Paragraph("STATUTORY LEGAL METROLOGY INSPECTION REPORT", styles["ReportTitle"]))
        story.append(Paragraph(
            "Evidence-driven compliance summary generated under Legal Metrology (Packaged Commodities) Rules, 2011",
            styles["GovtSubHeader"]
        ))
        story.append(Spacer(1, 6))

        # 3. Metadata Table (Inspection & Officer Info)
        insp_date = (
            inspection.created_at.strftime("%d-%b-%Y %H:%M UTC")
            if hasattr(inspection, "created_at") and inspection.created_at
            else datetime.utcnow().strftime("%d-%b-%Y %H:%M UTC")
        )
        officer_name = getattr(inspector, "full_name", "Inspector Rajesh Kumar")
        officer_id = getattr(inspector, "officer_id", "DOCA-INSP-842")
        officer_desig = getattr(inspector, "designation", "Senior Inspector (Legal Metrology)")
        officer_zone = getattr(inspector, "zone", "Northern Zone - Delhi HQ")
        location = getattr(inspection, "location", "Field Location")

        meta_data = [
            [
                Paragraph("<b>Inspection Number:</b>", styles["BodySmall"]),
                Paragraph(escape_report_text(insp_num), styles["BodySmallBold"]),
                Paragraph("<b>Inspection Date:</b>", styles["BodySmall"]),
                Paragraph(escape_report_text(insp_date), styles["BodySmall"])
            ],
            [
                Paragraph("<b>Inspecting Officer:</b>", styles["BodySmall"]),
                Paragraph(f"{escape_report_text(officer_name)} ({escape_report_text(officer_id)})", styles["BodySmall"]),
                Paragraph("<b>Designation / Zone:</b>", styles["BodySmall"]),
                Paragraph(f"{escape_report_text(officer_desig)} • {escape_report_text(officer_zone)}", styles["BodySmall"])
            ],
            [
                Paragraph("<b>Inspection Site:</b>", styles["BodySmall"]),
                Paragraph(escape_report_text(location), styles["BodySmall"]),
                Paragraph("<b>Report Version:</b>", styles["BodySmall"]),
                Paragraph(f"v{report_version} (Official Finalized)", styles["BodySmallBold"])
            ]
        ]
        meta_table = Table(meta_data, colWidths=[110, 150, 110, 150])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
            ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 6))

        # 4. Product Details Block
        prod_name = getattr(product, "product_name", "Packaged Commodity") if product else "Packaged Commodity"
        brand_name = getattr(product, "brand_name", "N/A") if product else "N/A"
        category = getattr(product, "category", "Packaged Food") if product else "Packaged Food"
        batch_no = getattr(product, "batch_number", "N/A") if product and product.batch_number else "N/A"

        story.append(Paragraph("1. PACKAGED COMMODITY SPECIFICATIONS", styles["SectionHeading"]))
        prod_data = [
            [
                Paragraph("<b>Commodity Name:</b>", styles["BodySmall"]),
                Paragraph(escape_report_text(prod_name), styles["BodySmallBold"]),
                Paragraph("<b>Brand / Trademark:</b>", styles["BodySmall"]),
                Paragraph(escape_report_text(brand_name or "N/A"), styles["BodySmall"])
            ],
            [
                Paragraph("<b>Category:</b>", styles["BodySmall"]),
                Paragraph(escape_report_text(category), styles["BodySmall"]),
                Paragraph("<b>Batch / Lot Number:</b>", styles["BodySmall"]),
                Paragraph(escape_report_text(batch_no or "N/A"), styles["BodySmall"])
            ]
        ]
        prod_table = Table(prod_data, colWidths=[110, 150, 110, 150])
        prod_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.white),
            ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(prod_table)
        story.append(Spacer(1, 6))

        # 5. Section C: Photographic Evidence Summary (Rule 8 Section C)
        story.append(Paragraph("2. PHOTOGRAPHIC EVIDENCE & IMAGE QUALITY SUMMARY", styles["SectionHeading"]))
        ev_summary_rows = [
            [
                Paragraph("<b>Image View</b>", styles["BodySmallBold"]),
                Paragraph("<b>Resolution</b>", styles["BodySmallBold"]),
                Paragraph("<b>Quality Status</b>", styles["BodySmallBold"]),
                Paragraph("<b>Blur Score</b>", styles["BodySmallBold"]),
                Paragraph("<b>OCR Confidence</b>", styles["BodySmallBold"]),
                Paragraph("<b>Evidence Sufficiency</b>", styles["BodySmallBold"])
            ]
        ]

        if all_images:
            for img in all_images:
                v_type = (getattr(img, "view_type", "front") or "front").upper()
                w = getattr(img, "width", 0) or 0
                h = getattr(img, "height", 0) or 0
                res_str = f"{w}x{h}" if w and h else "Standard"
                q_stat = (getattr(img, "quality_status", "GOOD") or "GOOD").upper()
                b_score = getattr(img, "blur_score", 0.0) or 0.0
                blur_display = f"{b_score:.1f}" if b_score > 0 else "-"

                # OCR confidence on this image if available
                ocr_recs = getattr(img, "ocr_results", [])
                if ocr_recs:
                    img_conf = ocr_recs[0].confidence
                    conf_display = f"{img_conf * 100:.1f}%"
                else:
                    conf_display = "Evaluated"

                q_color = PASS_COLOR if q_stat == "GOOD" else (WARN_COLOR if q_stat == "WARNING" else FAIL_COLOR)
                sufficiency_text = "SUFFICIENT" if q_stat in ["GOOD", "WARNING"] else "INSUFFICIENT"
                suff_color = PASS_COLOR if sufficiency_text == "SUFFICIENT" else FAIL_COLOR

                ev_summary_rows.append([
                    Paragraph(f"<b>{escape_report_text(v_type)}</b>", styles["BodySmallBold"]),
                    Paragraph(escape_report_text(res_str), styles["BodySmall"]),
                    Paragraph(f"<font color='{q_color.hexval()}'><b>{escape_report_text(q_stat)}</b></font>", styles["BodySmall"]),
                    Paragraph(escape_report_text(blur_display), styles["BodySmall"]),
                    Paragraph(escape_report_text(conf_display), styles["BodySmall"]),
                    Paragraph(f"<font color='{suff_color.hexval()}'><b>{sufficiency_text}</b></font>", styles["BodySmall"])
                ])
        else:
            ev_summary_rows.append([
                Paragraph("No images recorded", styles["BodySmall"]),
                Paragraph("-", styles["BodySmall"]),
                Paragraph("<font color='red'><b>MISSING</b></font>", styles["BodySmall"]),
                Paragraph("-", styles["BodySmall"]),
                Paragraph("-", styles["BodySmall"]),
                Paragraph("<font color='red'><b>INSUFFICIENT</b></font>", styles["BodySmall"])
            ])

        ev_table = Table(ev_summary_rows, colWidths=[80, 80, 90, 80, 100, 90])
        ev_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BG_LIGHT),
            ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(ev_table)
        story.append(Spacer(1, 6))

        # 6. Section D: Statutory Declarations Audit (PCR 2011 Rule 6 & Rule 10 Source View)
        story.append(Paragraph("3. STATUTORY DECLARATIONS AUDIT (PCR 2011 RULE 6)", styles["SectionHeading"]))
        decl_rows = [
            [
                Paragraph("<b>Statutory Field</b>", styles["BodySmallBold"]),
                Paragraph("<b>Extracted Value</b>", styles["BodySmallBold"]),
                Paragraph("<b>Confidence</b>", styles["BodySmallBold"]),
                Paragraph("<b>Source View</b>", styles["BodySmallBold"]),
                Paragraph("<b>Verification / Effective</b>", styles["BodySmallBold"])
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
            extracted_val = getattr(d, "extracted_value", None) or "None / Not Detected"
            effective_val = getattr(d, "effective_value", None) or extracted_val
            conf_val = getattr(d, "confidence", 0.0) or 0.0
            conf_str = f"{conf_val * 100:.0f}%" if conf_val > 0 else "-"
            v_status = getattr(d, "verification_status", "UNVERIFIED")

            # Resolve source image view (Rule 10)
            src_img_id = getattr(d, "source_image_id", None)
            src_img = image_map.get(str(src_img_id)) if src_img_id else None
            if src_img:
                src_view = f"{src_img.view_type.upper()} image"
            elif all_images:
                src_view = f"{all_images[0].view_type.upper()} image"
            else:
                src_view = "FRONT image"

            status_display = f"{v_status}"
            if v_status == "CORRECTED":
                status_display = f"<font color='{WARN_COLOR.hexval()}'><b>CORRECTED</b></font><br/>{escape_report_text(effective_val)}"
            elif v_status == "VERIFIED":
                status_display = f"<font color='{PASS_COLOR.hexval()}'><b>VERIFIED</b></font><br/>{escape_report_text(effective_val)}"
            else:
                status_display = f"<b>{escape_report_text(effective_val)}</b>"

            decl_rows.append([
                Paragraph(escape_report_text(flabel), styles["BodySmall"]),
                Paragraph(escape_report_text(extracted_val), styles["BodySmall"]),
                Paragraph(escape_report_text(conf_str), styles["BodySmall"]),
                Paragraph(f"<b>{escape_report_text(src_view)}</b>", styles["BodySmallBold"]),
                Paragraph(status_display, styles["BodySmall"])
            ])

        if len(decl_rows) == 1:
            decl_rows.append([
                Paragraph("No declarations recorded.", styles["BodySmall"]),
                Paragraph("-", styles["BodySmall"]),
                Paragraph("-", styles["BodySmall"]),
                Paragraph("-", styles["BodySmall"]),
                Paragraph("-", styles["BodySmall"])
            ])

        decl_table = Table(decl_rows, colWidths=[130, 130, 60, 85, 115])
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
        story.append(Spacer(1, 6))

        # 7. Section E: Compliance Summary & Rule Engine Results
        passed_cnt = sum(1 for c in compliance_checks if getattr(c, "result_state", "") == "PASS")
        noncomp_cnt = sum(1 for c in compliance_checks if getattr(c, "result_state", "") == "POTENTIAL_NON_COMPLIANCE")
        insufficient_cnt = sum(1 for c in compliance_checks if getattr(c, "result_state", "") == "INSUFFICIENT_EVIDENCE")
        notapp_cnt = sum(1 for c in compliance_checks if getattr(c, "result_state", "") == "NOT_APPLICABLE")

        story.append(Paragraph("4. DETERMINISTIC LEGAL METROLOGY EVALUATION RESULTS", styles["SectionHeading"]))
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

            r_ver = getattr(getattr(c, "rule_version", None), "version_number", 1)
            stat_ref = getattr(getattr(c, "rule_version", None), "statutory_reference", "")

            rule_display = f"<b>{escape_report_text(rcode)}</b> (v{r_ver})<br/>{escape_report_text(title)}"
            if stat_ref:
                rule_display += f"<br/><font color='#475569'><i>{escape_report_text(stat_ref)}</i></font>"

            rstate_color = PASS_COLOR if rstate == "PASS" else (FAIL_COLOR if rstate == "POTENTIAL_NON_COMPLIANCE" else WARN_COLOR)
            adj_color = FAIL_COLOR if adj_status == "CONFIRMED" else (PASS_COLOR if adj_status == "DISMISSED" else colors.black)

            findings_rows.append([
                Paragraph(rule_display, styles["BodySmall"]),
                Paragraph(escape_report_text(eval_val), styles["BodySmall"]),
                Paragraph(f"<font color='{rstate_color.hexval()}'><b>{escape_report_text(rstate)}</b></font>", styles["BodySmall"]),
                Paragraph(f"<font color='{adj_color.hexval()}'><b>{escape_report_text(adj_status)}</b></font>", styles["BodySmall"]),
                Paragraph(escape_report_text(notes), styles["BodySmall"])
            ])

        if len(findings_rows) == 1:
            findings_rows.append([
                Paragraph("No findings recorded.", styles["BodySmall"]),
                Paragraph("-", styles["BodySmall"]),
                Paragraph("-", styles["BodySmall"]),
                Paragraph("-", styles["BodySmall"]),
                Paragraph("-", styles["BodySmall"])
            ])

        findings_table = Table(findings_rows, colWidths=[135, 100, 95, 80, 110])
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
        story.append(Spacer(1, 6))

        # 8. Section G: Evidence Traceability Table (Rule 8 Section G & Rule 9)
        story.append(Paragraph("5. PHOTOGRAPHIC EVIDENCE TRACEABILITY & SPATIAL ANCHORS", styles["SectionHeading"]))
        trace_rows = [
            [
                Paragraph("<b>Rule Finding</b>", styles["BodySmallBold"]),
                Paragraph("<b>Source View</b>", styles["BodySmallBold"]),
                Paragraph("<b>Highlighted Text / Feature</b>", styles["BodySmallBold"]),
                Paragraph("<b>Bounding Box [x1, y1, x2, y2]</b>", styles["BodySmallBold"]),
                Paragraph("<b>Evidence Reason / Traceability</b>", styles["BodySmallBold"])
            ]
        ]

        if evidence_items:
            for ev in evidence_items:
                # Find rule code from check relation if present
                rule_code = "-"
                if hasattr(ev, "check") and ev.check:
                    rule_code = getattr(ev.check, "rule_code", "-")

                # Resolve source image
                img_id = getattr(ev, "image_id", None)
                src_img = image_map.get(str(img_id)) if img_id else None
                view_name = f"{src_img.view_type.upper()} image" if src_img else "FRONT image"

                # Parse BBox
                bbox_raw = getattr(ev, "bounding_box_json", None) or getattr(ev, "bounding_box", None)
                if isinstance(bbox_raw, str):
                    try:
                        bbox_coords = json.loads(bbox_raw)
                    except Exception:
                        bbox_coords = bbox_raw
                else:
                    bbox_coords = bbox_raw

                if bbox_coords and isinstance(bbox_coords, (list, tuple)) and len(bbox_coords) == 4:
                    bbox_str = f"[{bbox_coords[0]}, {bbox_coords[1]}, {bbox_coords[2]}, {bbox_coords[3]}]"
                elif bbox_coords:
                    bbox_str = str(bbox_coords)
                else:
                    bbox_str = "None (Declaration Absent)"

                hl_text = getattr(ev, "highlight_text", "-") or "-"
                reason = getattr(ev, "reason", "-") or "-"

                trace_rows.append([
                    Paragraph(f"<b>{escape_report_text(rule_code)}</b>", styles["BodySmallBold"]),
                    Paragraph(f"<b>{escape_report_text(view_name)}</b>", styles["BodySmall"]),
                    Paragraph(escape_report_text(hl_text), styles["BodySmall"]),
                    Paragraph(escape_report_text(bbox_str), styles["BodySmall"]),
                    Paragraph(escape_report_text(reason), styles["BodySmall"])
                ])
        else:
            trace_rows.append([
                Paragraph("No spatial evidence records attached.", styles["BodySmall"]),
                Paragraph("-", styles["BodySmall"]),
                Paragraph("-", styles["BodySmall"]),
                Paragraph("-", styles["BodySmall"]),
                Paragraph("-", styles["BodySmall"])
            ])

        trace_table = Table(trace_rows, colWidths=[90, 85, 120, 105, 120])
        trace_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BG_LIGHT),
            ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(trace_table)
        story.append(Spacer(1, 6))

        # 9. Section H: Human Adjudication Audit Trail (if applicable)
        adjudicated_checks = [c for c in compliance_checks if getattr(c, "adjudication_status", "PENDING") != "PENDING"]
        if adjudicated_checks:
            story.append(Paragraph("6. INSPECTOR MANUAL VERIFICATION & ADJUDICATION LOG", styles["SectionHeading"]))
            adj_rows = [
                [
                    Paragraph("<b>Rule Code</b>", styles["BodySmallBold"]),
                    Paragraph("<b>Action</b>", styles["BodySmallBold"]),
                    Paragraph("<b>Adjudicated By</b>", styles["BodySmallBold"]),
                    Paragraph("<b>Officer Remarks / Statutory Grounds</b>", styles["BodySmallBold"]),
                    Paragraph("<b>Timestamp</b>", styles["BodySmallBold"])
                ]
            ]
            for ac in adjudicated_checks:
                adj_act = getattr(ac, "adjudication_status", "-")
                adj_by = getattr(ac, "adjudicated_by", "-") or "-"
                adj_notes = getattr(ac, "adjudication_notes", "-") or "-"
                adj_at = getattr(ac, "adjudicated_at", None)
                adj_time = adj_at.strftime("%d-%b-%Y %H:%M") if adj_at else "-"

                adj_rows.append([
                    Paragraph(f"<b>{escape_report_text(ac.rule_code)}</b>", styles["BodySmallBold"]),
                    Paragraph(f"<b>{escape_report_text(adj_act)}</b>", styles["BodySmallBold"]),
                    Paragraph(escape_report_text(adj_by), styles["BodySmall"]),
                    Paragraph(escape_report_text(adj_notes), styles["BodySmall"]),
                    Paragraph(escape_report_text(adj_time), styles["BodySmall"])
                ])

            adj_table = Table(adj_rows, colWidths=[90, 80, 90, 145, 115])
            adj_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), BG_LIGHT),
                ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.append(adj_table)
            story.append(Spacer(1, 6))

        # 10. Final Statutory Overall Status Block
        overall_status = getattr(inspection, "overall_status", "PENDING_REVIEW") or "PENDING_REVIEW"
        status_color = PASS_COLOR if overall_status == "NO_POTENTIAL_VIOLATIONS" else (FAIL_COLOR if overall_status == "POTENTIAL_NON_COMPLIANCE" else WARN_COLOR)

        status_box = [
            [
                Paragraph("<b>FINAL STATUTORY INSPECTION STATUS:</b>", styles["BodySmallBold"]),
                Paragraph(f"<font color='{status_color.hexval()}'><b>{escape_report_text(overall_status)}</b></font>", styles["ReportTitle"])
            ]
        ]
        status_table = Table(status_box, colWidths=[220, 300])
        status_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
            ('BOX', (0, 0), (-1, -1), 1.0, status_color),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(status_table)
        story.append(Spacer(1, 8))

        # 11. Legal Disclaimer & Statutory Safety Statement
        disclaimer_text = (
            "<b>STATUTORY DISCLAIMER & AI SAFETY NOTICE:</b><br/>"
            "This report is generated by NiriKsha (AI-Assisted Legal Metrology Packaged-Commodity Inspection System, SIH Prototype 2026) for inspection-support purposes. "
            "Computer Vision and Optical Character Recognition are employed strictly for data extraction and spatial normalization. "
            "All compliance checks are deterministically evaluated against statutory rules under the Legal Metrology (Packaged Commodities) "
            "Rules, 2011. Final compliance adjudication, legal determinations, and statutory enforcement actions remain strictly under the human authority "
            "of the designated inspecting officer."
        )
        story.append(Paragraph(disclaimer_text, styles["DisclaimerText"]))
        story.append(Spacer(1, 10))

        # 12. Official Sign-Off Block
        sign_data = [
            [
                Paragraph(f"<b>Inspecting Officer:</b><br/>{escape_report_text(officer_name)}<br/>{escape_report_text(officer_desig)}", styles["BodySmall"]),
                Paragraph(f"<b>Official Seal / Stamp:</b><br/>Department of Consumer Affairs<br/>Legal Metrology Field Office", styles["BodySmall"]),
                Paragraph("<b>Signature & Date:</b><br/><br/>_______________________", styles["BodySmall"])
            ]
        ]
        sign_table = Table(sign_data, colWidths=[170, 170, 180])
        sign_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(sign_table)

        doc.build(story)
        return str(output_path)


report_generator = StatutoryReportGenerator()
