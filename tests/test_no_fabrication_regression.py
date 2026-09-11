import pytest
from backend.placement_service import placement_analyzer
from backend.font_size_service import font_size_analyzer
from backend.readability_service import readability_analyzer
from backend.declaration_validation_service import declaration_validation_engine


class TestNoFabricationRegression:
    """
    CRITICAL REGRESSION TEST SUITE: NO FABRICATION GUARANTEES (Section 30).
    
    Verifies that NiriKsha NEVER fabricates:
    - canned OCR strings
    - fake bounding boxes
    - fabricated confidence scores
    - fabricated physical font dimensions
    - fabricated placement conclusions
    - fake legal rules or references
    """

    def test_no_fabrication_of_font_dimensions_without_calibration(self):
        """Rule 9: Without physical calibration, mm height must NEVER be fabricated from arbitrary pixel heights."""
        arbitrary_pixel_boxes = [
            [10, 10, 100, 30],   # 20px
            [0, 0, 500, 200],    # 200px
            [50, 50, 250, 95],   # 45px
        ]
        for bbox in arbitrary_pixel_boxes:
            res = font_size_analyzer.analyze_font_size(
                field_name="net_quantity",
                bounding_box=bbox,
                text="500 g",
                net_quantity_context="500 g",
                calibration_scale_px_per_mm=None
            )
            # Must NEVER guess or fabricate physical millimeters
            assert res.estimated_physical_height_mm is None
            assert res.font_size_status == "FONT_SIZE_UNDETERMINABLE"
            assert res.is_calibrated is False

    def test_no_fabrication_of_placement_without_coordinates(self):
        """Rule 6/12: Placement engine must NOT fabricate coordinates or guess region when bbox is missing."""
        res = placement_analyzer.analyze_declaration_placement(
            field_name="mrp",
            bounding_box=None,
            view_type="front",
            image_dims=(1000, 1000)
        )
        assert res.bounding_box is None
        assert res.placement_status == "NOT_DETERMINABLE"
        assert "exact spatial coordinate placement cannot be determined" in res.explanation

    def test_no_fabrication_of_readability_on_empty_text(self):
        """Readability engine must NOT claim READABLE if OCR extracted nothing or confidence is 0."""
        res = readability_analyzer.analyze_readability(
            field_name="country_of_origin",
            bounding_box=None,
            image_path_or_array=None,
            ocr_confidence=0.0,
            extracted_text=""
        )
        assert res.readability_status != "READABLE"
        assert res.requires_manual_verification is True

    def test_unknown_values_route_honestly_to_incomplete_or_manual_verification(self):
        """System invariant: When evidence is insufficient, route to MANUAL_VERIFICATION_REQUIRED or INCOMPLETE."""
        matrix = declaration_validation_engine.build_declaration_matrix([])
        assert len(matrix) == len(declaration_validation_engine.MANDATORY_FIELDS)
        for row in matrix:
            assert row.is_present is False
            assert row.overall_status in ("POTENTIAL_NON_COMPLIANCE", "MANUAL_VERIFICATION_REQUIRED", "INCOMPLETE")
