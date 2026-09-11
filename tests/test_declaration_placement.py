import pytest
from backend.placement_service import (
    DeclarationPlacementAnalyzer,
    PlacementAnalysisResult,
    placement_analyzer
)


class TestDeclarationPlacement:
    """Test suite for Legal Metrology Declaration Placement Analysis (PCR 2011 Rules 6, 7 & 12)."""

    def test_mandatory_pdp_field_on_front_panel_compliant(self):
        """Rule 6(1)(c) / Rule 7: Net quantity declared on Principal Display Panel (front) is compliant."""
        res = placement_analyzer.analyze_declaration_placement(
            field_name="net_quantity",
            bounding_box=[100, 700, 300, 750],  # Bottom area of 1000x1000 image
            view_type="front",
            image_dims=(1000, 1000)
        )
        assert res.placement_status == "PLACEMENT_COMPLIANT"
        assert res.panel_classified == "PRINCIPAL_DISPLAY_PANEL"
        assert "Rule 7 read with Rule 12(1)" in res.statutory_rule_reference

    def test_mandatory_pdp_field_on_back_panel_routes_to_manual_verification(self):
        """Rule 12: Net quantity detected on back panel requires manual verification / review."""
        all_imgs = [{"view_type": "front"}, {"view_type": "back"}]
        res = placement_analyzer.analyze_declaration_placement(
            field_name="net_quantity",
            bounding_box=[100, 200, 300, 250],
            view_type="back",
            image_dims=(1000, 1000),
            all_images=all_imgs
        )
        assert res.placement_status == "MANUAL_VERIFICATION_REQUIRED"
        assert res.panel_classified == "INFORMATION_PANEL"
        assert "mandates placement on the Principal Display Panel" in res.explanation

    def test_information_panel_fields_on_back_compliant(self):
        """Rule 6: Manufacturer details & consumer care on back/side information panel are compliant."""
        res = placement_analyzer.analyze_declaration_placement(
            field_name="manufacturer_details",
            bounding_box=[50, 50, 400, 200],
            view_type="back",
            image_dims=(1000, 1000)
        )
        assert res.placement_status == "PLACEMENT_COMPLIANT"
        assert res.panel_classified == "INFORMATION_PANEL"

    def test_missing_bounding_box_routes_to_not_determinable(self):
        """Absence of bounding box coordinates cannot establish legal violation; returns NOT_DETERMINABLE."""
        res = placement_analyzer.analyze_declaration_placement(
            field_name="net_quantity",
            bounding_box=None,
            view_type="front",
            image_dims=(1000, 1000)
        )
        assert res.placement_status == "NOT_DETERMINABLE"
        assert "exact spatial coordinate placement cannot be determined" in res.explanation

    def test_unknown_panel_view_type_routes_to_manual_verification(self):
        """Unidentified package view (e.g. angle photo) must not fabricate compliance or violation."""
        res = placement_analyzer.analyze_declaration_placement(
            field_name="mrp",
            bounding_box=[100, 100, 200, 200],
            view_type="unknown_angle",
            image_dims=(1000, 1000)
        )
        assert res.placement_status == "MANUAL_VERIFICATION_REQUIRED"
        assert res.panel_classified == "UNKNOWN_PANEL"

    def test_all_statutory_declarations_have_configured_placement_rules(self):
        """Verified Rule Registry ensures all statutory fields have placement specifications."""
        mandatory_fields = [
            "commodity_name",
            "net_quantity",
            "mrp",
            "manufacturer_details",
            "date_of_manufacture_packing",
            "consumer_care_details",
            "country_of_origin"
        ]
        for f in mandatory_fields:
            assert f in DeclarationPlacementAnalyzer.STATUTORY_PLACEMENT_SPECS
            spec = DeclarationPlacementAnalyzer.STATUTORY_PLACEMENT_SPECS[f]
            assert "expected_panel" in spec
            assert "statutory_ref" in spec
            assert "rule_code" in spec
