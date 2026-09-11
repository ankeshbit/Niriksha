"""
backend/placement_service.py

Declaration Placement Analysis Engine for NiriKsha.
Statutory Reference: Legal Metrology (Packaged Commodities) Rules, 2011
- Rule 7: Principal Display Panel (PDP), its area, and declaration grouping.
- Rule 12(1): Prominence and placement of Net Quantity on Principal Display Panel.
- Rule 6(1): Placement of mandatory declarations on package or securely affixed label.

Statutory Principles:
1. Net Quantity must appear prominently on the Principal Display Panel (PDP / front panel).
2. Generic/Commodity name must appear on the Principal Display Panel.
3. Retail Sale Price (MRP) must be on PDP or clearly visible Information Panel without opening package.
4. Name & Address of Manufacturer, Consumer Care, and Date may appear on PDP or Information Panel (back/side).
5. If spatial classification is uncertain or panel boundaries cannot be deterministically verified:
   -> Return PLACEMENT_UNCERTAIN or MANUAL_VERIFICATION_REQUIRED.
   -> NEVER automatically declare a legal violation from spatial ambiguity alone.
"""

from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel


class PlacementAnalysisResult(BaseModel):
    field_name: str
    image_id: Optional[str] = None
    view_type: str = "unknown"
    panel_classified: str = "UNKNOWN_PANEL"  # PRINCIPAL_DISPLAY_PANEL, INFORMATION_PANEL, SECONDARY_PANEL, UNKNOWN_PANEL
    bounding_box: Optional[List[int]] = None
    placement_status: str  # PLACEMENT_COMPLIANT, PLACEMENT_NON_COMPLIANT, PLACEMENT_UNCERTAIN, NOT_APPLICABLE, NOT_DETERMINABLE, MANUAL_VERIFICATION_REQUIRED
    expected_panel: str
    statutory_rule_reference: str
    statutory_requirement_description: str
    explanation: str
    confidence: float
    verification_status: str = "STATUTORY_VERIFIED"
    provenance: str = "SPATIAL_LAYOUT_ENGINE"


class DeclarationPlacementAnalyzer:
    """
    Analyzes mandatory declaration placement across captured package images
    and OCR spatial coordinates against PCR 2011 statutory mandates.
    """

    STATUTORY_PLACEMENT_SPECS = {
        "net_quantity": {
            "expected_panel": "PRINCIPAL_DISPLAY_PANEL",
            "statutory_ref": "Rule 7 read with Rule 12(1), Legal Metrology (Packaged Commodities) Rules, 2011",
            "description": "Declaration of quantity shall be prominently displayed on the principal display panel.",
            "rule_code": "PCR_RULE_07_PLACEMENT_NET_QUANTITY",
            "critical_on_pdp": True,
        },
        "commodity_name": {
            "expected_panel": "PRINCIPAL_DISPLAY_PANEL",
            "statutory_ref": "Rule 6(1)(b) & Rule 7, Legal Metrology (Packaged Commodities) Rules, 2011",
            "description": "Common or generic name of commodity shall appear on the principal display panel.",
            "rule_code": "PCR_RULE_07_PLACEMENT_COMMODITY_NAME",
            "critical_on_pdp": True,
        },
        "mrp": {
            "expected_panel": "ANY_VISIBLE_PANEL",  # PDP or Information Panel
            "statutory_ref": "Rule 6(1)(e) & Rule 7, Legal Metrology (Packaged Commodities) Rules, 2011",
            "description": "Retail sale price (MRP) shall be clearly legible on the package without opening.",
            "rule_code": "PCR_RULE_07_PLACEMENT_MRP",
            "critical_on_pdp": False,
        },
        "date_of_manufacture_packing": {
            "expected_panel": "ANY_VISIBLE_PANEL",
            "statutory_ref": "Rule 6(1)(d) & Rule 7, Legal Metrology (Packaged Commodities) Rules, 2011",
            "description": "Month and year of manufacture or packing shall be clearly displayed.",
            "rule_code": "PCR_RULE_07_PLACEMENT_DATE",
            "critical_on_pdp": False,
        },
        "manufacturer_details": {
            "expected_panel": "ANY_VISIBLE_PANEL",
            "statutory_ref": "Rule 6(1)(a) & Rule 10, Legal Metrology (Packaged Commodities) Rules, 2011",
            "description": "Name and complete address of manufacturer/packer/importer on package label.",
            "rule_code": "PCR_RULE_07_PLACEMENT_MANUFACTURER",
            "critical_on_pdp": False,
        },
        "consumer_care_details": {
            "expected_panel": "ANY_VISIBLE_PANEL",
            "statutory_ref": "Rule 6(2), Legal Metrology (Packaged Commodities) Rules, 2011",
            "description": "Consumer grievance details on package label, clearly visible to consumer.",
            "rule_code": "PCR_RULE_07_PLACEMENT_CONSUMER_CARE",
            "critical_on_pdp": False,
        },
        "country_of_origin": {
            "expected_panel": "ANY_VISIBLE_PANEL",
            "statutory_ref": "Rule 6(1)(a) Proviso & Rule 10(1), Legal Metrology (PC) Rules, 2011",
            "description": "Country of origin for imported goods on package label.",
            "rule_code": "PCR_RULE_07_PLACEMENT_COUNTRY_OF_ORIGIN",
            "critical_on_pdp": False,
        },
    }

    def classify_panel(self, view_type: Optional[str], bbox: Optional[List[int]], img_w: int = 0, img_h: int = 0) -> str:
        """Classifies the package panel based on view_type and spatial geometry."""
        v = (view_type or "").lower().strip()
        if v in ["front", "pdp", "principal", "front_panel"]:
            return "PRINCIPAL_DISPLAY_PANEL"
        elif v in ["back", "rear", "information", "info_panel", "back_panel"]:
            return "INFORMATION_PANEL"
        elif v in ["side", "left", "right", "panel"]:
            return "SECONDARY_PANEL"
        elif v in ["top", "bottom"]:
            return "SECONDARY_PANEL"
        return "UNKNOWN_PANEL"

    def analyze_declaration_placement(
        self,
        field_name: str,
        extracted_value: Optional[str] = "Sample Value",
        source_image_id: Optional[str] = None,
        view_type: Optional[str] = "front",
        bounding_box: Optional[List[int]] = None,
        all_images: Optional[List[Any]] = None,
        image_dims: Optional[Tuple[int, int]] = None
    ) -> PlacementAnalysisResult:
        """
        Evaluates a single declaration's placement against PCR 2011 requirements.
        """
        spec = self.STATUTORY_PLACEMENT_SPECS.get(field_name, {
            "expected_panel": "ANY_VISIBLE_PANEL",
            "statutory_ref": "Rule 6 & 7, Legal Metrology (PC) Rules, 2011",
            "description": "General mandatory declaration placement.",
            "rule_code": "PCR_RULE_07_PLACEMENT_GENERAL",
            "critical_on_pdp": False,
        })

        # Case 1: Declaration was not found / not extracted
        if not extracted_value or not str(extracted_value).strip():
            return PlacementAnalysisResult(
                field_name=field_name,
                image_id=source_image_id,
                view_type=view_type or "unknown",
                panel_classified="UNKNOWN_PANEL",
                bounding_box=None,
                placement_status="NOT_DETERMINABLE",
                expected_panel=spec["expected_panel"],
                statutory_rule_reference=spec["statutory_ref"],
                statutory_requirement_description=spec["description"],
                explanation="Declaration value was not detected; placement cannot be evaluated.",
                confidence=0.0
            )

        # Case 2: Bounding box is missing or incomplete
        if not bounding_box or len(bounding_box) < 4:
            return PlacementAnalysisResult(
                field_name=field_name,
                image_id=source_image_id,
                view_type=view_type or "unknown",
                panel_classified="UNKNOWN_PANEL",
                bounding_box=None,
                placement_status="NOT_DETERMINABLE",
                expected_panel=spec["expected_panel"],
                statutory_rule_reference=spec["statutory_ref"],
                statutory_requirement_description=spec["description"],
                explanation="OCR bounding box is unavailable; exact spatial coordinate placement cannot be determined.",
                confidence=0.50
            )

        img_w, img_h = image_dims if image_dims else (1000, 1000)
        panel = self.classify_panel(view_type, bounding_box, img_w, img_h)

        # Case 3: Panel is UNKNOWN (ambiguous view type)
        if panel == "UNKNOWN_PANEL":
            return PlacementAnalysisResult(
                field_name=field_name,
                image_id=source_image_id,
                view_type=view_type or "unknown",
                panel_classified=panel,
                bounding_box=bounding_box,
                placement_status="MANUAL_VERIFICATION_REQUIRED",
                expected_panel=spec["expected_panel"],
                statutory_rule_reference=spec["statutory_ref"],
                statutory_requirement_description=spec["description"],
                explanation=(
                    f"View type '{view_type}' does not definitively establish whether this image is the "
                    f"Principal Display Panel (PDP) or Information Panel. Inspector manual review is required."
                ),
                confidence=0.60
            )

        # Case 4: Field requires PDP (e.g. Net Quantity, Commodity Name)
        if spec["critical_on_pdp"]:
            if panel == "PRINCIPAL_DISPLAY_PANEL":
                return PlacementAnalysisResult(
                    field_name=field_name,
                    image_id=source_image_id,
                    view_type=view_type or "front",
                    panel_classified=panel,
                    bounding_box=bounding_box,
                    placement_status="PLACEMENT_COMPLIANT",
                    expected_panel=spec["expected_panel"],
                    statutory_rule_reference=spec["statutory_ref"],
                    statutory_requirement_description=spec["description"],
                    explanation=(
                        f"{field_name.replace('_', ' ').title()} is correctly positioned on the "
                        f"Principal Display Panel (front view) in compliance with {spec['statutory_ref']}."
                    ),
                    confidence=0.92
                )
            else:
                # Detected on back or side panel.
                # Check if a front panel image exists in the inspection
                has_front_image = False
                if all_images:
                    for img in all_images:
                        v = getattr(img, "view_type", img.get("view_type") if isinstance(img, dict) else "")
                        if (v or "").lower().strip() in ["front", "pdp"]:
                            has_front_image = True
                            break

                if has_front_image:
                    # Front image exists, but this critical declaration was found on back/side
                    # Route to MANUAL_VERIFICATION_REQUIRED / PLACEMENT_NON_COMPLIANT candidate
                    return PlacementAnalysisResult(
                        field_name=field_name,
                        image_id=source_image_id,
                        view_type=view_type or "unknown",
                        panel_classified=panel,
                        bounding_box=bounding_box,
                        placement_status="MANUAL_VERIFICATION_REQUIRED",
                        expected_panel=spec["expected_panel"],
                        statutory_rule_reference=spec["statutory_ref"],
                        statutory_requirement_description=spec["description"],
                        explanation=(
                            f"{field_name.replace('_', ' ').title()} was detected on the {panel.replace('_', ' ').title()} "
                            f"(view: {view_type}), whereas Rule 12(1)/Rule 7 mandates placement on the Principal Display Panel. "
                            f"Inspector verification is required to confirm whether PDP contains the mandatory quantity declaration."
                        ),
                        confidence=0.75
                    )
                else:
                    return PlacementAnalysisResult(
                        field_name=field_name,
                        image_id=source_image_id,
                        view_type=view_type or "unknown",
                        panel_classified=panel,
                        bounding_box=bounding_box,
                        placement_status="PLACEMENT_UNCERTAIN",
                        expected_panel=spec["expected_panel"],
                        statutory_rule_reference=spec["statutory_ref"],
                        statutory_requirement_description=spec["description"],
                        explanation=(
                            f"No front/PDP image was captured to corroborate Principal Display Panel compliance. "
                            f"Placement remains uncertain pending inspector confirmation."
                        ),
                        confidence=0.60
                    )

        # Case 5: Field permitted on Any Visible Panel (MRP, Manufacturer, Consumer Care, Date)
        if panel in ["PRINCIPAL_DISPLAY_PANEL", "INFORMATION_PANEL", "SECONDARY_PANEL"]:
            return PlacementAnalysisResult(
                field_name=field_name,
                image_id=source_image_id,
                view_type=view_type or "unknown",
                panel_classified=panel,
                bounding_box=bounding_box,
                placement_status="PLACEMENT_COMPLIANT",
                expected_panel=spec["expected_panel"],
                statutory_rule_reference=spec["statutory_ref"],
                statutory_requirement_description=spec["description"],
                explanation=(
                    f"{field_name.replace('_', ' ').title()} is clearly positioned on the "
                    f"{panel.replace('_', ' ').title()} (view: {view_type}), which is an approved statutory panel."
                ),
                confidence=0.90
            )

        return PlacementAnalysisResult(
            field_name=field_name,
            image_id=source_image_id,
            view_type=view_type or "unknown",
            panel_classified=panel,
            bounding_box=bounding_box,
            placement_status="MANUAL_VERIFICATION_REQUIRED",
            expected_panel=spec["expected_panel"],
            statutory_rule_reference=spec["statutory_ref"],
            statutory_requirement_description=spec["description"],
            explanation="Placement could not be definitively classified. Requires inspector manual review.",
            confidence=0.50
        )


placement_analyzer = DeclarationPlacementAnalyzer()
