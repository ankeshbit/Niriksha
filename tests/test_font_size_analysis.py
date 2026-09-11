import pytest
from backend.font_size_service import (
    FontSizeAnalyzer,
    FontSizeAnalysisResult,
    font_size_analyzer
)


class TestFontSizeAnalysis:
    """Test suite for Legal Metrology Font-Size Analysis (PCR 2011 Rule 9 Table 1)."""

    def test_uncalibrated_image_returns_undeterminable_without_fabrication(self):
        """Without physical calibration reference, system must NEVER fabricate physical millimetres."""
        res = font_size_analyzer.analyze_font_size(
            field_name="net_quantity",
            bounding_box=[100, 100, 300, 150],  # 50px height
            text="Net Qty: 200 g",
            net_quantity_context="200 g",
            calibration_scale_px_per_mm=None  # No calibration
        )
        assert res.font_size_status == "FONT_SIZE_UNDETERMINABLE"
        assert res.is_calibrated is False
        assert res.estimated_physical_height_mm is None  # Never fabricate mm!
        assert res.measured_pixel_height == 50
        assert res.statutory_rule_code == "PCR_RULE_09_FONT_SIZE"

    def test_calibrated_measurement_compliant(self):
        """With physical scale calibration (e.g. 20 px/mm), 60px height = 3.0mm; threshold for 200g is 2.0mm -> COMPLIANT."""
        res = font_size_analyzer.analyze_font_size(
            field_name="net_quantity",
            bounding_box=[100, 100, 300, 160],  # 60px height
            text="200 g",
            net_quantity_context="200 g",
            calibration_scale_px_per_mm=20.0
        )
        assert res.font_size_status == "FONT_SIZE_COMPLIANT"
        assert res.is_calibrated is True
        assert res.estimated_physical_height_mm is not None
        assert res.estimated_physical_height_mm >= res.statutory_minimum_height_mm
        assert res.statutory_minimum_height_mm == 2.0

    def test_calibrated_measurement_non_compliant(self):
        """With physical scale calibration (e.g. 20 px/mm), 25px height = 1.02mm; threshold for 200g is 2.0mm -> routes to MANUAL_VERIFICATION_REQUIRED."""
        res = font_size_analyzer.analyze_font_size(
            field_name="net_quantity",
            bounding_box=[100, 100, 300, 125],  # 25px height
            text="200 g",
            net_quantity_context="200 g",
            calibration_scale_px_per_mm=20.0
        )
        assert res.font_size_status in ("FONT_SIZE_NON_COMPLIANT", "MANUAL_VERIFICATION_REQUIRED")
        assert res.is_calibrated is True
        assert res.estimated_physical_height_mm is not None
        assert res.estimated_physical_height_mm < res.statutory_minimum_height_mm

    def test_missing_bounding_box_returns_undeterminable(self):
        """Absence of bounding box returns undeterminable and requires manual verification."""
        res = font_size_analyzer.analyze_font_size(
            field_name="net_quantity",
            bounding_box=None,
            text="500 g",
            net_quantity_context="500 g",
            calibration_scale_px_per_mm=None
        )
        assert res.font_size_status == "FONT_SIZE_UNDETERMINABLE"
        assert res.measured_pixel_height == 0

    def test_statutory_rule_9_table_1_threshold_lookup(self):
        """Verify thresholds match PCR 2011 Rule 9 Table 1 statutory values."""
        # Up to 50g -> 1.0mm
        assert font_size_analyzer.get_statutory_min_height("30 g") == 1.0
        # 50g to 200g -> 2.0mm
        assert font_size_analyzer.get_statutory_min_height("150 g") == 2.0
        # 200g to 1kg -> 4.0mm
        assert font_size_analyzer.get_statutory_min_height("500 g") == 4.0
        # Above 1kg -> 6.0mm
        assert font_size_analyzer.get_statutory_min_height("5 kg") == 6.0
