"""
backend/font_size_service.py

Font-Size and Numeral Height Analysis Engine for NiriKsha.
Statutory Reference: Rule 9, Table 1 of Legal Metrology (Packaged Commodities) Rules, 2011 (PDF p. 8-10)

Statutory Minimum Heights (Table 1 under Rule 9):
- Net Quantity <= 50 g/ml: Minimum height 1.0 mm (Normal), 2.0 mm (Blown/Molded)
- Net Quantity 50 g/ml to 200 g/ml: Minimum height 2.0 mm (Normal), 4.0 mm (Blown/Molded)
- Net Quantity 200 g/ml to 1 kg/L: Minimum height 4.0 mm (Normal), 6.0 mm (Blown/Molded)
- Net Quantity > 1 kg/L: Minimum height 6.0 mm (Normal), 6.0 mm (Blown/Molded)

CRITICAL LEGAL SAFETY GUARANTEES:
1. Pixel height alone is NOT physical millimetres.
2. If physical calibration reference is unavailable:
   -> Strictly returns FONT_SIZE_UNDETERMINABLE or MANUAL_VERIFICATION_REQUIRED.
   -> Never fabricates physical millimetres from arbitrary uncalibrated pixels.
   -> Never declares a legal violation when calibration is absent.
3. Every evaluated threshold includes statutory citation, rule code, applicability, and provenance.
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel


class FontSizeAnalysisResult(BaseModel):
    field_name: str
    image_id: Optional[str] = None
    bounding_box: Optional[List[int]] = None
    measured_pixel_height: int = 0
    estimated_character_height_px: float = 0.0
    calibration_method: str = "UNCALIBRATED_RAW_PIXELS"  # UNCALIBRATED_RAW_PIXELS, KNOWN_PACK_SCALE, BARCODE_REFERENCE_SCALE
    is_calibrated: bool = False
    estimated_physical_height_mm: Optional[float] = None
    statutory_minimum_height_mm: float = 1.0
    font_size_status: str  # FONT_SIZE_COMPLIANT, FONT_SIZE_NON_COMPLIANT, FONT_SIZE_UNCERTAIN, FONT_SIZE_UNDETERMINABLE, NOT_APPLICABLE, MANUAL_VERIFICATION_REQUIRED
    statutory_rule_code: str = "PCR_RULE_09_FONT_SIZE"
    statutory_rule_reference: str = "Rule 9(1) & Table 1, Legal Metrology (Packaged Commodities) Rules, 2011 (p. 8-10)"
    explanation: str
    confidence: float
    verification_status: str = "STATUTORY_VERIFIED"
    provenance: str = "OPTICAL_METROLOGY_PIPELINE"


class FontSizeAnalyzer:
    """
    Measures text and numeral heights from genuine OCR bounding boxes and
    evaluates statutory compliance under PCR 2011 Rule 9.
    """

    # Table 1: Minimum height of numerals and letters based on Net Quantity
    TABLE_1_THRESHOLDS = [
        {"max_qty_g_or_ml": 50.0, "min_height_mm": 1.0, "molded_height_mm": 2.0},
        {"max_qty_g_or_ml": 200.0, "min_height_mm": 2.0, "molded_height_mm": 4.0},
        {"max_qty_g_or_ml": 1000.0, "min_height_mm": 4.0, "molded_height_mm": 6.0},
        {"max_qty_g_or_ml": float("inf"), "min_height_mm": 6.0, "molded_height_mm": 6.0},
    ]

    def _parse_net_quantity_magnitude(self, net_quantity_str: Optional[str]) -> Optional[float]:
        """Parses net quantity string into normalized grams or millilitres."""
        if not net_quantity_str:
            return None
        text = str(net_quantity_str).lower().replace(",", "").strip()
        m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|kilogram|l|litre|liter|g|gram|ml|millilitre|milliliter)\b", text)
        if not m:
            # Fallback to bare number
            num_match = re.search(r"(\d+(?:\.\d+)?)", text)
            return float(num_match.group(1)) if num_match else None

        val = float(m.group(1))
        unit = m.group(2)
        if unit in ["kg", "kilogram", "l", "litre", "liter"]:
            return val * 1000.0
        return val

    def get_statutory_threshold(self, net_quantity_str: Optional[str], is_blown_or_molded: bool = False) -> Tuple[float, str]:
        """
        Determines the applicable minimum height under Rule 9, Table 1.
        Returns: (min_height_mm, statutory_tier_explanation)
        """
        qty_magnitude = self._parse_net_quantity_magnitude(net_quantity_str)
        if qty_magnitude is None:
            # Default minimum general font size under Rule 9(2) is 1.0 mm
            return 1.0, "Rule 9(2) default minimum height (1.0 mm) applied (net quantity magnitude unspecified)."

        for tier in self.TABLE_1_THRESHOLDS:
            if qty_magnitude <= tier["max_qty_g_or_ml"]:
                h = tier["molded_height_mm"] if is_blown_or_molded else tier["min_height_mm"]
                pkg_type = "blown/molded/perforated" if is_blown_or_molded else "standard printing"
                tier_desc = f"Net quantity {qty_magnitude:g}g/ml -> Rule 9 Table 1 minimum: {h:.1f} mm ({pkg_type})"
                return h, tier_desc

        return 6.0, "Net quantity > 1 kg/L -> Rule 9 Table 1 minimum: 6.0 mm"

    def get_statutory_min_height(self, net_quantity_str: Optional[str], is_blown_or_molded: bool = False) -> float:
        """Returns statutory minimum height in mm as a float."""
        h, _ = self.get_statutory_threshold(net_quantity_str, is_blown_or_molded)
        return h

    def analyze_font_size(
        self,
        field_name: str,
        bounding_box: Optional[List[int]],
        text: Optional[str] = "Sample Text",
        net_quantity_context: Optional[str] = None,
        calibration_scale_px_per_mm: Optional[float] = None,
        source_image_id: Optional[str] = None,
        is_blown_or_molded: bool = False
    ) -> FontSizeAnalysisResult:
        """Convenience alias accepting px_per_mm scale."""
        mm_per_px = (1.0 / calibration_scale_px_per_mm) if calibration_scale_px_per_mm else None
        return self.analyze_declaration_font_size(
            field_name=field_name,
            extracted_value=text,
            bounding_box=bounding_box,
            source_image_id=source_image_id,
            net_quantity_context=net_quantity_context,
            calibration_scale_mm_per_px=mm_per_px,
            calibration_source="CALIBRATION_SCALE" if mm_per_px else None,
            is_blown_or_molded=is_blown_or_molded
        )

    def analyze_declaration_font_size(
        self,
        field_name: str,
        extracted_value: Optional[str],
        bounding_box: Optional[List[int]],
        source_image_id: Optional[str] = None,
        net_quantity_context: Optional[str] = None,
        calibration_scale_mm_per_px: Optional[float] = None,
        calibration_source: Optional[str] = None,
        is_blown_or_molded: bool = False
    ) -> FontSizeAnalysisResult:
        """
        Analyzes font and character height for a declaration.
        Guarantees strict legal safety: never invents physical dimensions without calibration.
        """
        # Case 1: Declaration value not found
        if not extracted_value or not str(extracted_value).strip():
            return FontSizeAnalysisResult(
                field_name=field_name,
                image_id=source_image_id,
                bounding_box=None,
                measured_pixel_height=0,
                estimated_character_height_px=0.0,
                calibration_method="UNCALIBRATED_RAW_PIXELS",
                is_calibrated=False,
                estimated_physical_height_mm=None,
                statutory_minimum_height_mm=1.0,
                font_size_status="NOT_APPLICABLE",
                explanation="Declaration value was not extracted; font size is not applicable.",
                confidence=0.0
            )

        # Case 2: Bounding box missing
        if not bounding_box or len(bounding_box) < 4:
            return FontSizeAnalysisResult(
                field_name=field_name,
                image_id=source_image_id,
                bounding_box=None,
                measured_pixel_height=0,
                estimated_character_height_px=0.0,
                calibration_method="UNCALIBRATED_RAW_PIXELS",
                is_calibrated=False,
                estimated_physical_height_mm=None,
                statutory_minimum_height_mm=1.0,
                font_size_status="FONT_SIZE_UNDETERMINABLE",
                explanation="Bounding box coordinates unavailable. Physical font size cannot be determined without spatial bounds.",
                confidence=0.50
            )

        x1, y1, x2, y2 = bounding_box
        box_h_px = max(0, int(y2 - y1))

        # Estimate character height: for single-line declarations, character height is ~75-90% of box height
        char_h_px = round(box_h_px * 0.82, 1)

        threshold_mm, tier_desc = self.get_statutory_threshold(
            net_quantity_context or (extracted_value if field_name == "net_quantity" else None),
            is_blown_or_molded=is_blown_or_molded
        )

        # Case 3: Physical Calibration Scale is Available
        if calibration_scale_mm_per_px is not None and calibration_scale_mm_per_px > 0:
            computed_mm = round(char_h_px * calibration_scale_mm_per_px, 2)
            cal_method = calibration_source or "KNOWN_PACK_SCALE"

            if computed_mm >= threshold_mm:
                return FontSizeAnalysisResult(
                    field_name=field_name,
                    image_id=source_image_id,
                    bounding_box=bounding_box,
                    measured_pixel_height=box_h_px,
                    estimated_character_height_px=char_h_px,
                    calibration_method=cal_method,
                    is_calibrated=True,
                    estimated_physical_height_mm=computed_mm,
                    statutory_minimum_height_mm=threshold_mm,
                    font_size_status="FONT_SIZE_COMPLIANT",
                    explanation=(
                        f"Estimated physical character height of {computed_mm:.2f} mm meets or exceeds the "
                        f"statutory minimum of {threshold_mm:.1f} mm ({tier_desc}). Calibrated via {cal_method}."
                    ),
                    confidence=0.90
                )
            elif computed_mm >= (threshold_mm * 0.80):
                # Borderline within optical tolerance margin
                return FontSizeAnalysisResult(
                    field_name=field_name,
                    image_id=source_image_id,
                    bounding_box=bounding_box,
                    measured_pixel_height=box_h_px,
                    estimated_character_height_px=char_h_px,
                    calibration_method=cal_method,
                    is_calibrated=True,
                    estimated_physical_height_mm=computed_mm,
                    statutory_minimum_height_mm=threshold_mm,
                    font_size_status="MANUAL_VERIFICATION_REQUIRED",
                    explanation=(
                        f"Estimated physical character height of {computed_mm:.2f} mm is near the statutory threshold "
                        f"({threshold_mm:.1f} mm). Due to perspective distortion, inspector physical measurement is required."
                    ),
                    confidence=0.75
                )
            else:
                return FontSizeAnalysisResult(
                    field_name=field_name,
                    image_id=source_image_id,
                    bounding_box=bounding_box,
                    measured_pixel_height=box_h_px,
                    estimated_character_height_px=char_h_px,
                    calibration_method=cal_method,
                    is_calibrated=True,
                    estimated_physical_height_mm=computed_mm,
                    statutory_minimum_height_mm=threshold_mm,
                    font_size_status="MANUAL_VERIFICATION_REQUIRED",
                    explanation=(
                        f"Estimated character height ({computed_mm:.2f} mm) is below statutory minimum ({threshold_mm:.1f} mm). "
                        f"Flagged for inspector physical verification under Rule 9, Table 1."
                    ),
                    confidence=0.85
                )

        # Case 4: Uncalibrated Camera Image (Standard Mobile Photograph without scale bar)
        # In accordance with SIH Problem Statement and Legal Metrology standards:
        # We report genuine pixel height and indicate that physical millimetres are undeterminable without calibration.
        return FontSizeAnalysisResult(
            field_name=field_name,
            image_id=source_image_id,
            bounding_box=bounding_box,
            measured_pixel_height=box_h_px,
            estimated_character_height_px=char_h_px,
            calibration_method="UNCALIBRATED_RAW_PIXELS",
            is_calibrated=False,
            estimated_physical_height_mm=None,
            statutory_minimum_height_mm=threshold_mm,
            font_size_status="FONT_SIZE_UNDETERMINABLE",
            explanation=(
                f"Declaration measured at {box_h_px}px height ({char_h_px}px character height). "
                f"Physical millimetres cannot be legitimately computed without physical scale calibration. "
                f"Statutory requirement: >= {threshold_mm:.1f} mm ({tier_desc}). Routed to Manual Verification."
            ),
            confidence=0.65
        )


font_size_analyzer = FontSizeAnalyzer()
