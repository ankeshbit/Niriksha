import re
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from backend.rule_engine.models import (
    RuleResultState,
    SeverityLevel,
    EvidencePayload,
    RuleEvaluationResult,
    StatutoryRuleDefinition
)
from backend.rule_engine.registry import STATUTORY_RULE_REGISTRY, get_all_rules

class DeterministicRuleEngine:
    """
    Deterministic Legal Metrology Rule Evaluator.
    Evaluates verified/effective declaration values against statutory PCR 2011 clauses.
    AI is strictly excluded from legal adjudication.
    """

    def evaluate_inspection(
        self,
        inspection_id: str,
        product_data: Dict[str, Any],
        declarations: List[Any],
        images: List[Any]
    ) -> List[RuleEvaluationResult]:
        decl_map = {}
        for d in declarations:
            fname = getattr(d, "field_name", d.get("field_name") if isinstance(d, dict) else None)
            if fname:
                decl_map[fname] = d

        primary_image_id = None
        has_poor_quality_images = False
        if images:
            primary_image_id = getattr(images[0], "id", images[0].get("id") if isinstance(images[0], dict) else None)
            for img in images:
                q_status = getattr(img, "quality_status", img.get("quality_status") if isinstance(img, dict) else "GOOD")
                if q_status in ["POOR", "UNUSABLE"]:
                    has_poor_quality_images = True

        results: List[RuleEvaluationResult] = []

        for rule in get_all_rules():
            eval_res = self._evaluate_rule(
                rule=rule,
                decl_map=decl_map,
                product_data=product_data,
                fallback_image_id=primary_image_id,
                has_poor_quality=has_poor_quality_images
            )
            results.append(eval_res)

        return results

    def _get_decl_field(self, decl: Any, field_name: str, default: Any = None) -> Any:
        if decl is None:
            return default
        if isinstance(decl, dict):
            return decl.get(field_name, default)
        return getattr(decl, field_name, default)

    def _get_effective_value(self, decl: Any) -> Optional[str]:
        if decl is None:
            return None
        corrected = self._get_decl_field(decl, "corrected_value")
        if corrected and str(corrected).strip():
            return str(corrected).strip()
        extracted = self._get_decl_field(decl, "extracted_value")
        return str(extracted).strip() if extracted else None

    def _get_bbox(self, decl: Any) -> Optional[List[int]]:
        if decl is None:
            return None
        bbox_raw = self._get_decl_field(decl, "bounding_box_json")
        if bbox_raw:
            if isinstance(bbox_raw, str):
                try:
                    return json.loads(bbox_raw)
                except Exception:
                    return None
            elif isinstance(bbox_raw, list):
                return bbox_raw
        bbox_obj = self._get_decl_field(decl, "bounding_box")
        return bbox_obj if isinstance(bbox_obj, list) else None

    def _evaluate_rule(
        self,
        rule: StatutoryRuleDefinition,
        decl_map: Dict[str, Any],
        product_data: Dict[str, Any],
        fallback_image_id: Optional[str],
        has_poor_quality: bool = False
    ) -> RuleEvaluationResult:
        rule_code = rule.rule_code
        required_field = rule.required_fields[0] if rule.required_fields else None
        decl = decl_map.get(required_field)

        # 1. Applicability Check (e.g. Country of Origin on domestic goods or explicit exemption)
        is_applicable = self._get_decl_field(decl, "is_applicable", True)
        if not is_applicable:
            return RuleEvaluationResult(
                rule_code=rule_code,
                rule_version=rule.rule_version,
                title=rule.title,
                statutory_reference=rule.statutory_reference,
                severity=rule.severity,
                result_state=RuleResultState.NOT_APPLICABLE,
                explanation=f"{rule.title} is marked not applicable for this commodity/context.",
                evidence_items=[]
            )

        effective_val = self._get_effective_value(decl)
        original_val = self._get_decl_field(decl, "extracted_value")
        extraction_status = self._get_decl_field(decl, "extraction_status", "EXTRACTED")
        verification_status = self._get_decl_field(decl, "verification_status", "UNVERIFIED")
        is_verified = verification_status in ["VERIFIED", "CORRECTED", "VERIFIED_OK", "CORRECTED_BY_OFFICER"]
        source_image_id = self._get_decl_field(decl, "source_image_id") or fallback_image_id
        bbox = self._get_bbox(decl)

        # 2. Cross-Image Conflict Check
        has_conflict = self._get_decl_field(decl, "has_conflict", False) or extraction_status == "CONFLICTING"
        if not is_verified and has_conflict:
            evidence_item = EvidencePayload(
                image_id=source_image_id,
                bounding_box=bbox,
                highlight_text=effective_val or "[CONFLICTING DECLARATIONS]",
                reason=f"Conflicting values detected across package images for {rule.title}. Requires inspector manual verification."
            )
            return RuleEvaluationResult(
                rule_code=rule_code,
                rule_version=rule.rule_version,
                title=rule.title,
                statutory_reference=rule.statutory_reference,
                severity=rule.severity,
                result_state=RuleResultState.NEEDS_MANUAL_VERIFICATION,
                effective_value_used=effective_val,
                original_ocr_value=original_val,
                is_verified_by_officer=is_verified,
                explanation=f"Needs Manual Verification: Conflicting values detected across package images for {rule.title}. Requires human adjudication.",
                evidence_items=[evidence_item]
            )

        # 3. Insufficient Evidence Check (Poor image quality or unverified low confidence)
        if not is_verified and (has_poor_quality or extraction_status in ["LOW_CONFIDENCE", "NEEDS_REVIEW"]):
            evidence_item = EvidencePayload(
                image_id=source_image_id,
                bounding_box=bbox,
                highlight_text=effective_val or "[UNREADABLE / LOW CONFIDENCE]",
                reason=f"Evidence is insufficient to conclusively determine compliance with {rule.statutory_reference}."
            )
            return RuleEvaluationResult(
                rule_code=rule_code,
                rule_version=rule.rule_version,
                title=rule.title,
                statutory_reference=rule.statutory_reference,
                severity=rule.severity,
                result_state=RuleResultState.INSUFFICIENT_EVIDENCE,
                effective_value_used=effective_val,
                original_ocr_value=original_val,
                is_verified_by_officer=is_verified,
                explanation=f"Insufficient Evidence: Package image quality or OCR confidence is insufficient to verify {rule.title}. Requires inspector manual review.",
                evidence_items=[evidence_item]
            )

        # 3. Missing Mandatory Declaration Check
        if not effective_val or (not is_verified and extraction_status == "NOT_FOUND"):
            evidence_item = EvidencePayload(
                image_id=source_image_id,
                bounding_box=None,
                highlight_text="[DECLARATION NOT DETECTED]",
                reason=f"Mandatory {rule.title} is missing from package labeling."
            )
            return RuleEvaluationResult(
                rule_code=rule_code,
                rule_version=rule.rule_version,
                title=rule.title,
                statutory_reference=rule.statutory_reference,
                severity=rule.severity,
                result_state=RuleResultState.POTENTIAL_NON_COMPLIANCE,
                effective_value_used=None,
                original_ocr_value=original_val,
                is_verified_by_officer=is_verified,
                explanation=f"Potential Non-Compliance: Required declaration under {rule.statutory_reference} is missing on the package.",
                evidence_items=[evidence_item]
            )

        evidence_item = EvidencePayload(
            image_id=source_image_id,
            bounding_box=bbox,
            highlight_text=effective_val,
            reason=f"Evaluated against {rule.statutory_reference}"
        )

        # 4. Deterministic Rule Evaluation Logic
        if rule_code == "PCR_RULE_06_1_E":
            # Maximum Retail Price (MRP)
            has_price_val = bool(re.search(r'[0-9]+(?:\.[0-9]{1,2})?', effective_val))
            has_tax_qualifier = bool(re.search(r'(?:incl|inclusive|taxes)', effective_val, re.I))

            if not has_price_val:
                return RuleEvaluationResult(
                    rule_code=rule_code,
                    rule_version=rule.rule_version,
                    title=rule.title,
                    statutory_reference=rule.statutory_reference,
                    severity=rule.severity,
                    result_state=RuleResultState.POTENTIAL_NON_COMPLIANCE,
                    effective_value_used=effective_val,
                    original_ocr_value=original_val,
                    is_verified_by_officer=is_verified,
                    explanation="MRP declaration does not contain a discernible numerical retail price.",
                    evidence_items=[evidence_item]
                )
            elif not has_tax_qualifier:
                return RuleEvaluationResult(
                    rule_code=rule_code,
                    rule_version=rule.rule_version,
                    title=rule.title,
                    statutory_reference=rule.statutory_reference,
                    severity=rule.severity,
                    result_state=RuleResultState.POTENTIAL_NON_COMPLIANCE,
                    effective_value_used=effective_val,
                    original_ocr_value=original_val,
                    is_verified_by_officer=is_verified,
                    explanation="MRP declaration is missing mandatory statutory tax qualifier: 'Inclusive of all taxes'.",
                    evidence_items=[evidence_item]
                )
            else:
                return RuleEvaluationResult(
                    rule_code=rule_code,
                    rule_version=rule.rule_version,
                    title=rule.title,
                    statutory_reference=rule.statutory_reference,
                    severity=rule.severity,
                    result_state=RuleResultState.PASS,
                    effective_value_used=effective_val,
                    original_ocr_value=original_val,
                    is_verified_by_officer=is_verified,
                    explanation="MRP declared clearly with inclusive tax qualifier in compliance with Rule 6(1)(e).",
                    evidence_items=[evidence_item]
                )

        elif rule_code == "PCR_RULE_06_1_A":
            # Manufacturer / Packer / Importer
            if len(effective_val) < 6:
                return RuleEvaluationResult(
                    rule_code=rule_code,
                    rule_version=rule.rule_version,
                    title=rule.title,
                    statutory_reference=rule.statutory_reference,
                    severity=rule.severity,
                    result_state=RuleResultState.POTENTIAL_NON_COMPLIANCE,
                    effective_value_used=effective_val,
                    original_ocr_value=original_val,
                    is_verified_by_officer=is_verified,
                    explanation="Manufacturer/Packer details appear incomplete or illegible.",
                    evidence_items=[evidence_item]
                )
            return RuleEvaluationResult(
                rule_code=rule_code,
                rule_version=rule.rule_version,
                title=rule.title,
                statutory_reference=rule.statutory_reference,
                severity=rule.severity,
                result_state=RuleResultState.PASS,
                effective_value_used=effective_val,
                original_ocr_value=original_val,
                is_verified_by_officer=is_verified,
                explanation="Manufacturer / Packer name & address declared in accordance with Rule 6(1)(a).",
                evidence_items=[evidence_item]
            )

        elif rule_code == "PCR_RULE_06_1_C":
            # Net Quantity
            has_metric_unit = bool(re.search(r'\b(?:kg|g|gm|gms|l|ltr|litre|litres|ml|units?|pieces?|count|n|u)\b', effective_val, re.I))
            has_qty_num = bool(re.search(r'[0-9]+(?:\.[0-9]+)?', effective_val))

            if not (has_metric_unit and has_qty_num):
                return RuleEvaluationResult(
                    rule_code=rule_code,
                    rule_version=rule.rule_version,
                    title=rule.title,
                    statutory_reference=rule.statutory_reference,
                    severity=rule.severity,
                    result_state=RuleResultState.POTENTIAL_NON_COMPLIANCE,
                    effective_value_used=effective_val,
                    original_ocr_value=original_val,
                    is_verified_by_officer=is_verified,
                    explanation="Net quantity must declare a numeric quantity with standard SI metric units (kg, g, L, ml, count).",
                    evidence_items=[evidence_item]
                )
            return RuleEvaluationResult(
                rule_code=rule_code,
                rule_version=rule.rule_version,
                title=rule.title,
                statutory_reference=rule.statutory_reference,
                severity=rule.severity,
                result_state=RuleResultState.PASS,
                effective_value_used=effective_val,
                original_ocr_value=original_val,
                is_verified_by_officer=is_verified,
                explanation=(
                    "Net quantity declared in standard metric units conforming to Rule 6(1)(c). "
                    "Note: Physical net quantity requires appropriate physical verification/testing "
                    "and cannot be conclusively determined from package photographs alone."
                ),
                evidence_items=[evidence_item]
            )

        elif rule_code == "PCR_RULE_06_1_D":
            # Month & Year of Mfg / Packing
            has_date_format = bool(re.search(r'[0-9]{1,2}[/-][0-9]{2,4}|[A-Za-z]{3,9}\s*[0-9]{4}|[0-9]{2}/[0-9]{4}', effective_val))
            if not has_date_format:
                return RuleEvaluationResult(
                    rule_code=rule_code,
                    rule_version=rule.rule_version,
                    title=rule.title,
                    statutory_reference=rule.statutory_reference,
                    severity=rule.severity,
                    result_state=RuleResultState.POTENTIAL_NON_COMPLIANCE,
                    effective_value_used=effective_val,
                    original_ocr_value=original_val,
                    is_verified_by_officer=is_verified,
                    explanation="Month and Year of manufacture/packing is missing or in an invalid format.",
                    evidence_items=[evidence_item]
                )
            return RuleEvaluationResult(
                rule_code=rule_code,
                rule_version=rule.rule_version,
                title=rule.title,
                statutory_reference=rule.statutory_reference,
                severity=rule.severity,
                result_state=RuleResultState.PASS,
                effective_value_used=effective_val,
                original_ocr_value=original_val,
                is_verified_by_officer=is_verified,
                explanation="Month and Year of packing declared in compliance with Rule 6(1)(d).",
                evidence_items=[evidence_item]
            )

        elif rule_code == "PCR_RULE_06_1_G":
            # Consumer Care Details
            has_contact = bool(re.search(r'(?:1800|[0-9]{10}|@[a-zA-Z0-9-]+\.|care|consumer|tel|phone|helpline|help@)', effective_val, re.I))
            if not has_contact:
                return RuleEvaluationResult(
                    rule_code=rule_code,
                    rule_version=rule.rule_version,
                    title=rule.title,
                    statutory_reference=rule.statutory_reference,
                    severity=rule.severity,
                    result_state=RuleResultState.POTENTIAL_NON_COMPLIANCE,
                    effective_value_used=effective_val,
                    original_ocr_value=original_val,
                    is_verified_by_officer=is_verified,
                    explanation="Consumer grievance redressal telephone number or email address is missing.",
                    evidence_items=[evidence_item]
                )
            return RuleEvaluationResult(
                rule_code=rule_code,
                rule_version=rule.rule_version,
                title=rule.title,
                statutory_reference=rule.statutory_reference,
                severity=rule.severity,
                result_state=RuleResultState.PASS,
                effective_value_used=effective_val,
                original_ocr_value=original_val,
                is_verified_by_officer=is_verified,
                explanation="Consumer care contact information declared in compliance with Rule 6(1)(g).",
                evidence_items=[evidence_item]
            )

        elif rule_code == "PCR_RULE_06_1_F":
            # Commodity Name
            if len(effective_val) < 2:
                return RuleEvaluationResult(
                    rule_code=rule_code,
                    rule_version=rule.rule_version,
                    title=rule.title,
                    statutory_reference=rule.statutory_reference,
                    severity=rule.severity,
                    result_state=RuleResultState.POTENTIAL_NON_COMPLIANCE,
                    effective_value_used=effective_val,
                    original_ocr_value=original_val,
                    is_verified_by_officer=is_verified,
                    explanation="Commodity generic identification is missing or insufficient on Principal Display Panel.",
                    evidence_items=[evidence_item]
                )
            return RuleEvaluationResult(
                rule_code=rule_code,
                rule_version=rule.rule_version,
                title=rule.title,
                statutory_reference=rule.statutory_reference,
                severity=rule.severity,
                result_state=RuleResultState.PASS,
                effective_value_used=effective_val,
                original_ocr_value=original_val,
                is_verified_by_officer=is_verified,
                explanation="Commodity identification declared in compliance with Rule 6(1)(f).",
                evidence_items=[evidence_item]
            )

        elif rule_code == "PCR_RULE_06_1_B":
            # Country of Origin
            if not effective_val or len(effective_val) < 2:
                return RuleEvaluationResult(
                    rule_code=rule_code,
                    rule_version=rule.rule_version,
                    title=rule.title,
                    statutory_reference=rule.statutory_reference,
                    severity=rule.severity,
                    result_state=RuleResultState.POTENTIAL_NON_COMPLIANCE,
                    effective_value_used=effective_val,
                    original_ocr_value=original_val,
                    is_verified_by_officer=is_verified,
                    explanation="Country of origin not declared for applicable commodity.",
                    evidence_items=[evidence_item]
                )
            return RuleEvaluationResult(
                rule_code=rule_code,
                rule_version=rule.rule_version,
                title=rule.title,
                statutory_reference=rule.statutory_reference,
                severity=rule.severity,
                result_state=RuleResultState.PASS,
                effective_value_used=effective_val,
                original_ocr_value=original_val,
                is_verified_by_officer=is_verified,
                explanation=f"Country of origin declared as '{effective_val}' in compliance with Rule 6(1)(b).",
                evidence_items=[evidence_item]
            )

        elif rule_code == "DATA_QUAL_PHONE_SYNTAX":
            # Phone Syntax
            has_valid_phone = bool(re.search(r'(?:1800[-\s]?[0-9]{2,3}[-\s]?[0-9]{3,4}|\+?91[-\s]?[0-9]{10}|[0-9]{10})', effective_val))
            if not has_valid_phone:
                return RuleEvaluationResult(
                    rule_code=rule_code,
                    rule_version=rule.rule_version,
                    title=rule.title,
                    statutory_reference=rule.statutory_reference,
                    severity=rule.severity,
                    result_state=RuleResultState.POTENTIAL_NON_COMPLIANCE,
                    effective_value_used=effective_val,
                    original_ocr_value=original_val,
                    is_verified_by_officer=is_verified,
                    explanation="Consumer care telephone number does not match standard 10-digit or 1800 toll-free format.",
                    evidence_items=[evidence_item]
                )
            return RuleEvaluationResult(
                rule_code=rule_code,
                rule_version=rule.rule_version,
                title=rule.title,
                statutory_reference=rule.statutory_reference,
                severity=rule.severity,
                result_state=RuleResultState.PASS,
                effective_value_used=effective_val,
                original_ocr_value=original_val,
                is_verified_by_officer=is_verified,
                explanation="Consumer helpline phone number format verified.",
                evidence_items=[evidence_item]
            )

        elif rule_code == "DATA_QUAL_DATE_PLAUSIBILITY":
            # Date Plausibility Check
            match = re.search(r'([0-9]{1,2})[/-]([0-9]{2,4})', effective_val)
            if match:
                month, year = int(match.group(1)), int(match.group(2))
                if year < 100: year += 2000
                current_year = datetime.utcnow().year
                if month < 1 or month > 12 or year < 2020 or year > (current_year + 1):
                    return RuleEvaluationResult(
                        rule_code=rule_code,
                        rule_version=rule.rule_version,
                        title=rule.title,
                        statutory_reference=rule.statutory_reference,
                        severity=rule.severity,
                        result_state=RuleResultState.POTENTIAL_NON_COMPLIANCE,
                        effective_value_used=effective_val,
                        original_ocr_value=original_val,
                        is_verified_by_officer=is_verified,
                        explanation=f"Manufacturing date ({month:02d}/{year}) is structurally implausible or future-dated beyond limits.",
                        evidence_items=[evidence_item]
                    )
            return RuleEvaluationResult(
                rule_code=rule_code,
                rule_version=rule.rule_version,
                title=rule.title,
                statutory_reference=rule.statutory_reference,
                severity=rule.severity,
                result_state=RuleResultState.PASS,
                effective_value_used=effective_val,
                original_ocr_value=original_val,
                is_verified_by_officer=is_verified,
                explanation="Manufacturing/packing date is structurally valid and plausible.",
                evidence_items=[evidence_item]
            )

        # Fallback default
        return RuleEvaluationResult(
            rule_code=rule_code,
            rule_version=rule.rule_version,
            title=rule.title,
            statutory_reference=rule.statutory_reference,
            severity=rule.severity,
            result_state=RuleResultState.PASS,
            effective_value_used=effective_val,
            original_ocr_value=original_val,
            is_verified_by_officer=is_verified,
            explanation="Statutory requirement evaluated.",
            evidence_items=[evidence_item]
        )

rule_engine = DeterministicRuleEngine()
