"""
backend/declaration_validation_service.py

Unified Declaration Compliance Matrix & Non-Standard / Misleading Declaration Validation Engine.
Statutory Reference: Legal Metrology (Packaged Commodities) Rules, 2011
- Rule 6(1): Mandatory Declarations & Formatting (MRP tax qualifier, manufacturer address, date)
- Rule 7 & 12: Placement on Principal Display Panel
- Rule 9: Font size and numeral height
- Rule 11 & 13: Standard Metric Units for Net Quantity (Second & Third Schedules)
- Rule 18(2A): Online vs Physical consistency

Generates the Unified Declaration Compliance Matrix:
| Declaration | Present | Correct | Readable | Placement | Font Size | Format | Status |

CRITICAL LEGAL SAFETY:
- Deterministic rule verification; no autonomous LLM legal conclusions.
- Discrepancies generate POTENTIAL_MISLEADING_DECLARATION or MANUAL_VERIFICATION_REQUIRED.
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel

from backend.placement_service import placement_analyzer, PlacementAnalysisResult
from backend.font_size_service import font_size_analyzer, FontSizeAnalysisResult
from backend.readability_service import readability_analyzer, DeclarationReadabilityResult


class DeclarationMatrixRow(BaseModel):
    field_name: str
    field_label: str
    is_present: bool = False
    is_correct: str = "UNCERTAIN"  # YES, NO, UNCERTAIN, NOT_APPLICABLE
    readability_status: str = "NOT_OBSERVABLE"  # READABLE, POOR_READABILITY, UNREADABLE, UNCERTAIN, NOT_OBSERVABLE
    placement_status: str = "NOT_DETERMINABLE"  # PLACEMENT_COMPLIANT, PLACEMENT_NON_COMPLIANT, PLACEMENT_UNCERTAIN, NOT_DETERMINABLE, NOT_APPLICABLE
    font_size_status: str = "FONT_SIZE_UNDETERMINABLE"  # FONT_SIZE_COMPLIANT, FONT_SIZE_NON_COMPLIANT, FONT_SIZE_UNDETERMINABLE, NOT_APPLICABLE
    format_status: str = "COMPLIANT"  # COMPLIANT, NON_COMPLIANT, POTENTIAL_MISLEADING, UNCERTAIN
    overall_status: str = "INCOMPLETE"  # COMPLIANT, POTENTIAL_NON_COMPLIANCE, MANUAL_VERIFICATION_REQUIRED, INCOMPLETE
    extracted_value: Optional[str] = None
    effective_value: Optional[str] = None
    confidence: float = 0.0
    bounding_box: Optional[List[int]] = None
    source_image_id: Optional[str] = None
    view_type: Optional[str] = None
    statutory_reference: str = ""
    findings: List[str] = []
    explanation: str = ""


class ComplianceSummaryData(BaseModel):
    overall_status: str  # COMPLIANT, POTENTIAL_NON_COMPLIANCE, MANUAL_VERIFICATION_REQUIRED, INCOMPLETE
    total_mandatory: int = 7
    mandatory_detected: int = 0
    mandatory_missing: int = 0
    mandatory_correct: int = 0
    mandatory_uncertain: int = 0
    placement_compliant: int = 0
    placement_uncertain: int = 0
    placement_non_compliant: int = 0
    readability_good: int = 0
    readability_uncertain: int = 0
    readability_poor: int = 0
    font_size_compliant: int = 0
    font_size_non_compliant: int = 0
    font_size_undeterminable: int = 0
    listing_comparison_matched: int = 0
    listing_comparison_mismatched: int = 0
    listing_comparison_uncertain: int = 0
    potential_violations_count: int = 0
    manual_verification_count: int = 0
    timestamp: str = ""


class DeclarationValidationEngine:
    """
    Evaluates extracted declarations across Presence, Correctness, Readability,
    Placement, Font Size, Format, and Misleading declaration detection.
    """

    MANDATORY_FIELDS = [
        ("commodity_name", "Commodity Name"),
        ("net_quantity", "Net Quantity"),
        ("mrp", "Maximum Retail Price (MRP)"),
        ("date_of_manufacture_packing", "Date of Packing / Mfg"),
        ("manufacturer_details", "Manufacturer / Packer Details"),
        ("consumer_care_details", "Consumer Care Information"),
        ("country_of_origin", "Country of Origin"),
    ]

    STANDARD_METRIC_UNITS = re.compile(
        r"\b(?:g|gram|grams|kg|kilogram|kilograms|ml|millilitre|milliliter|millilitres|l|litre|liter|litres|m|meter|metre|meters|cm|centimeter|centimetre|sq\s*m|sq\s*cm|count|units?|n|piece|pieces|tablets?|capsules?)\b",
        re.IGNORECASE
    )

    PROHIBITED_QUANTITY_TERMS = re.compile(
        r"\b(?:when\s*packed|net\s*wt\s*approx|approximately|not\s*less\s*than|minimum\s*weight)\b",
        re.IGNORECASE
    )

    PROMOTIONAL_QUANTITY_TERMS = re.compile(
        r"\b(?:\d+%\s*(?:extra|free)|buy\s*\d+\s*get\s*\d+|promo\s*pack|special\s*offer)\b",
        re.IGNORECASE
    )

    TAX_QUALIFIER_TERMS = re.compile(
        r"(?:incl(?:usive)?\.?\s*of\s*all\s*taxes|incl\.?\s*taxes|\(incl\.?\s*of\s*all\s*taxes\))",
        re.IGNORECASE
    )

    def validate_format_and_misleading(
        self,
        field_name: str,
        value: Optional[str] = None,
        extracted_value: Optional[str] = None,
        category: Optional[str] = None
    ) -> Tuple[str, List[str], str]:
        """
        Validates declaration syntax, standard units, and deceptive/misleading expressions.
        Returns: (format_status, list_of_findings, explanation)
        """
        if value is None and extracted_value is not None:
            value = extracted_value
        if not value or not str(value).strip():
            return "NOT_APPLICABLE", [], "Declaration value missing."

        v = str(value).strip()
        findings: List[str] = []

        # 1. Net Quantity Validation
        if field_name == "net_quantity":
            # Check for prohibited qualifying words under Rule 13(5)
            if self.PROHIBITED_QUANTITY_TERMS.search(v):
                findings.append("Prohibited qualification used (e.g. 'when packed' or 'approximate') under Rule 13(5).")
                return "POTENTIAL_MISLEADING", findings, "Net quantity qualified by ambiguous or non-standard condition."

            # Check if promotional text was mixed without base net weight
            if self.PROMOTIONAL_QUANTITY_TERMS.search(v) and not re.search(r"\b\d+\s*(?:g|kg|ml|l|count)\b", v, re.IGNORECASE):
                findings.append("Promotional claim detected without mandatory base net quantity declaration.")
                return "POTENTIAL_MISLEADING", findings, "Promotional quantity expression masquerading as net quantity."

            # Verify standard SI metric units under Rule 11
            if not self.STANDARD_METRIC_UNITS.search(v):
                findings.append("Net quantity does not declare standard SI metric units (kg, g, l, ml, count) under Rule 11.")
                return "NON_COMPLIANT", findings, "Non-standard unit abbreviation or missing metric unit."

            return "COMPLIANT", [], "Net quantity declared in compliant standard metric unit."

        # 2. MRP Validation
        elif field_name == "mrp":
            # Check for currency indicator
            has_currency = bool(re.search(r"(?:₹|rs\.?|inr|rupees)", v, re.IGNORECASE))
            has_taxes = bool(self.TAX_QUALIFIER_TERMS.search(v))

            if not has_currency:
                findings.append("MRP declaration lacks statutory Indian currency symbol (₹ or Rs.) under Rule 6(1)(e).")

            if not has_taxes:
                findings.append("MRP declaration missing mandatory qualifier 'inclusive of all taxes' under Rule 6(1)(e).")

            if findings:
                return "NON_COMPLIANT", findings, "; ".join(findings)

            return "COMPLIANT", [], "MRP declared with currency and mandatory statutory tax qualifier."

        # 3. Date Validation
        elif field_name == "date_of_manufacture_packing":
            # Pattern for MM/YYYY, Month YYYY, etc.
            has_valid_date = bool(re.search(
                r"(?:\b\d{1,2}[/-]\d{2,4}\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s,.'/-]+\d{2,4}\b)",
                v,
                re.IGNORECASE
            ))
            if not has_valid_date:
                findings.append("Date of packing/manufacture does not conform to standard Month and Year format under Rule 6(1)(d).")
                return "NON_COMPLIANT", findings, "Non-standard date declaration format."

            return "COMPLIANT", [], "Month and year of manufacture/packing declared in standard format."

        # 4. Manufacturer Details Validation
        elif field_name == "manufacturer_details":
            # Must declare name and complete address (not just a website or phone)
            has_address_keywords = bool(re.search(
                r"(?:road|street|nagar|plot|phase|sector|industrial|area|dist|pin|pincode|\b\d{6}\b|city|state|floor|bldg|building|complex)",
                v,
                re.IGNORECASE
            ))
            if len(v) < 15 or not has_address_keywords:
                findings.append("Manufacturer declaration appears incomplete (requires name and complete postal address under Rule 6(1)(a)).")
                return "POTENTIAL_MISLEADING", findings, "Incomplete manufacturer address details."

            return "COMPLIANT", [], "Manufacturer name and address structure verified."

        # 5. Consumer Care Validation
        elif field_name == "consumer_care_details":
            has_phone = bool(re.search(r"(?:1800|\b[6-9]\d{9}\b|\b0\d{2,4}[-\s]?\d{6,8}\b)", v))
            has_email = bool(re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", v))
            if not (has_phone or has_email):
                findings.append("Consumer care declaration lacks phone number or email for grievance redressal under Rule 6(2).")
                return "NON_COMPLIANT", findings, "Missing consumer care grievance contact channels."

            return "COMPLIANT", [], "Consumer care grievance contact information verified."

        return "COMPLIANT", [], "Format conforms to statutory requirements."

    evaluate_format_compliance = validate_format_and_misleading

    def build_declaration_matrix(
        self,
        declarations: List[Any],
        images: Optional[List[Any]] = None,
        net_quantity_str: Optional[str] = None
    ) -> List[DeclarationMatrixRow]:
        """
        Builds the unified declaration compliance matrix covering all mandatory fields.
        """
        images = images or []
        decl_map: Dict[str, Any] = {}
        for d in declarations:
            fname = getattr(d, "field_name", d.get("field_name") if isinstance(d, dict) else None)
            if fname:
                decl_map[fname] = d

        img_map: Dict[str, Any] = {}
        for img in images:
            iid = getattr(img, "id", img.get("id") if isinstance(img, dict) else None)
            if iid:
                img_map[iid] = img

        matrix_rows: List[DeclarationMatrixRow] = []

        for field_name, field_label in self.MANDATORY_FIELDS:
            decl = decl_map.get(field_name)

            extracted_val = getattr(decl, "extracted_value", decl.get("extracted_value") if isinstance(decl, dict) else None) if decl else None
            effective_val = getattr(decl, "effective_value", extracted_val) if decl else None
            conf = float(getattr(decl, "confidence", decl.get("confidence", 0.0) if isinstance(decl, dict) else 0.0)) if decl else 0.0
            raw_bbox = getattr(decl, "bounding_box_json", decl.get("bounding_box_json") if isinstance(decl, dict) else None) if decl else None
            bbox = None
            if raw_bbox:
                import json
                try:
                    bbox = json.loads(raw_bbox) if isinstance(raw_bbox, str) else raw_bbox
                except Exception:
                    bbox = None

            source_img_id = getattr(decl, "source_image_id", decl.get("source_image_id") if isinstance(decl, dict) else None) if decl else None
            source_img = img_map.get(source_img_id)
            view_type = getattr(source_img, "view_type", source_img.get("view_type") if isinstance(source_img, dict) else "unknown") if source_img else "unknown"

            # 1. Presence
            is_present = bool(effective_val and str(effective_val).strip())

            # 2. Format & Misleading Check
            format_status, format_findings, format_exp = self.validate_format_and_misleading(field_name, effective_val)

            # 3. Readability Analysis (calls trained ML model and local optical metrics)
            source_file_path = getattr(source_img, "file_path", None) if source_img else (source_img.get("file_path") if isinstance(source_img, dict) else None)
            read_res: DeclarationReadabilityResult = readability_analyzer.analyze_readability(
                field_name=field_name,
                extracted_value=effective_val,
                bounding_box=bbox,
                ocr_confidence=conf,
                source_image_id=source_img_id,
                image_input=source_file_path
            )

            # 4. Placement Analysis
            place_res: PlacementAnalysisResult = placement_analyzer.analyze_declaration_placement(
                field_name=field_name,
                extracted_value=effective_val,
                source_image_id=source_img_id,
                view_type=view_type,
                bounding_box=bbox,
                all_images=images
            )

            # 5. Font Size Analysis
            font_res: FontSizeAnalysisResult = font_size_analyzer.analyze_declaration_font_size(
                field_name=field_name,
                extracted_value=effective_val,
                bounding_box=bbox,
                source_image_id=source_img_id,
                net_quantity_context=net_quantity_str or (effective_val if field_name == "net_quantity" else None)
            )

            # 6. Correctness Evaluation
            if not is_present:
                is_correct = "NO" if field_name != "country_of_origin" else "UNCERTAIN"
            elif format_status == "COMPLIANT" and conf >= 0.70:
                is_correct = "YES"
            elif format_status in ["NON_COMPLIANT", "POTENTIAL_MISLEADING"]:
                is_correct = "NO"
            else:
                is_correct = "UNCERTAIN"

            # 7. Overall Row Status
            all_findings = list(format_findings)
            if not is_present:
                if field_name == "country_of_origin":
                    overall = "MANUAL_VERIFICATION_REQUIRED"
                    all_findings.append("Country of origin not declared. Requires manual verification to establish whether item is domestic or imported.")
                else:
                    overall = "POTENTIAL_NON_COMPLIANCE"
                    all_findings.append(f"Mandatory declaration '{field_label}' missing from package OCR.")
            elif format_status == "POTENTIAL_MISLEADING" or place_res.placement_status == "PLACEMENT_NON_COMPLIANT":
                overall = "POTENTIAL_NON_COMPLIANCE"
            elif (
                place_res.placement_status == "MANUAL_VERIFICATION_REQUIRED"
                or read_res.requires_manual_verification
                or font_res.font_size_status == "MANUAL_VERIFICATION_REQUIRED"
                or is_correct == "UNCERTAIN"
            ):
                overall = "MANUAL_VERIFICATION_REQUIRED"
            elif format_status == "NON_COMPLIANT":
                overall = "POTENTIAL_NON_COMPLIANCE"
            else:
                overall = "COMPLIANT"

            row = DeclarationMatrixRow(
                field_name=field_name,
                field_label=field_label,
                is_present=is_present,
                is_correct=is_correct,
                readability_status=read_res.readability_status,
                placement_status=place_res.placement_status,
                font_size_status=font_res.font_size_status,
                format_status=format_status,
                overall_status=overall,
                extracted_value=extracted_val,
                effective_value=effective_val,
                confidence=conf,
                bounding_box=bbox,
                source_image_id=source_img_id,
                view_type=view_type,
                statutory_reference=place_res.statutory_rule_reference,
                findings=all_findings,
                explanation=f"{format_exp} Readability: {read_res.readability_status}. Placement: {place_res.placement_status}."
            )
            matrix_rows.append(row)

        return matrix_rows

    def compute_compliance_summary(
        self,
        matrix_rows: List[DeclarationMatrixRow],
        listing_comparisons: Optional[List[Any]] = None
    ) -> ComplianceSummaryData:
        """
        Computes the aggregate enforcement compliance summary from the matrix rows.
        """
        from datetime import datetime

        total_mand = len(matrix_rows)
        detected = sum(1 for r in matrix_rows if r.is_present)
        missing = total_mand - detected
        correct = sum(1 for r in matrix_rows if r.is_correct == "YES")
        uncertain = sum(1 for r in matrix_rows if r.is_correct == "UNCERTAIN")

        place_comp = sum(1 for r in matrix_rows if r.placement_status == "PLACEMENT_COMPLIANT")
        place_unc = sum(1 for r in matrix_rows if r.placement_status in ["PLACEMENT_UNCERTAIN", "NOT_DETERMINABLE", "MANUAL_VERIFICATION_REQUIRED"])
        place_non = sum(1 for r in matrix_rows if r.placement_status == "PLACEMENT_NON_COMPLIANT")

        read_good = sum(1 for r in matrix_rows if r.readability_status == "READABLE")
        read_unc = sum(1 for r in matrix_rows if r.readability_status in ["UNCERTAIN", "POOR_READABILITY"])
        read_poor = sum(1 for r in matrix_rows if r.readability_status in ["UNREADABLE", "NOT_OBSERVABLE"])

        font_comp = sum(1 for r in matrix_rows if r.font_size_status == "FONT_SIZE_COMPLIANT")
        font_non = sum(1 for r in matrix_rows if r.font_size_status == "FONT_SIZE_NON_COMPLIANT")
        font_undet = sum(1 for r in matrix_rows if r.font_size_status in ["FONT_SIZE_UNDETERMINABLE", "NOT_APPLICABLE", "MANUAL_VERIFICATION_REQUIRED"])

        list_matched = 0
        list_mismatched = 0
        list_uncertain = 0
        if listing_comparisons:
            for lc in listing_comparisons:
                st = getattr(lc, "comparison_status", lc.get("comparison_status") if isinstance(lc, dict) else "")
                if st == "MATCH":
                    list_matched += 1
                elif st in ["MISMATCH", "MISSING_ON_LISTING", "MISSING_ON_PACKAGE"]:
                    list_mismatched += 1
                else:
                    list_uncertain += 1

        pot_viol = sum(1 for r in matrix_rows if r.overall_status == "POTENTIAL_NON_COMPLIANCE") + list_mismatched
        man_ver = sum(1 for r in matrix_rows if r.overall_status == "MANUAL_VERIFICATION_REQUIRED") + list_uncertain

        if pot_viol > 0:
            overall = "POTENTIAL_NON_COMPLIANCE"
        elif man_ver > 0 or missing > 0:
            overall = "MANUAL_VERIFICATION_REQUIRED"
        elif detected == total_mand and correct == total_mand:
            overall = "COMPLIANT"
        else:
            overall = "INCOMPLETE"

        return ComplianceSummaryData(
            overall_status=overall,
            total_mandatory=total_mand,
            mandatory_detected=detected,
            mandatory_missing=missing,
            mandatory_correct=correct,
            mandatory_uncertain=uncertain,
            placement_compliant=place_comp,
            placement_uncertain=place_unc,
            placement_non_compliant=place_non,
            readability_good=read_good,
            readability_uncertain=read_unc,
            readability_poor=read_poor,
            font_size_compliant=font_comp,
            font_size_non_compliant=font_non,
            font_size_undeterminable=font_undet,
            listing_comparison_matched=list_matched,
            listing_comparison_mismatched=list_mismatched,
            listing_comparison_uncertain=list_uncertain,
            potential_violations_count=pot_viol,
            manual_verification_count=man_ver,
            timestamp=datetime.utcnow().isoformat()
        )


declaration_validation_engine = DeclarationValidationEngine()
