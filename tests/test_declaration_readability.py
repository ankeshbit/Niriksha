import pytest
import numpy as np
from backend.readability_service import (
    DeclarationReadabilityAnalyzer,
    DeclarationReadabilityResult,
    readability_analyzer
)


class TestDeclarationReadability:
    """Test suite for Declaration-Level Readability Analysis."""

    def test_high_confidence_clear_text_is_readable(self):
        """Clean OCR with high confidence is classified as READABLE."""
        sharp_crop = np.zeros((100, 200, 3), dtype=np.uint8)
        sharp_crop[:, :100] = 255  # High contrast edge

        res = readability_analyzer.analyze_readability(
            field_name="mrp",
            bounding_box=[10, 10, 210, 110],
            image_path_or_array=sharp_crop,
            ocr_confidence=0.95,
            extracted_text="Rs. 45.00 (Incl. of all taxes)"
        )
        assert res.readability_status == "READABLE"
        assert res.requires_manual_verification is False
        assert res.is_sufficiently_observable is True

    def test_low_ocr_confidence_routes_to_uncertain(self):
        """Low OCR confidence (0.35) must route to UNCERTAIN/MANUAL_VERIFICATION, not an automatic violation."""
        res = readability_analyzer.analyze_readability(
            field_name="consumer_care_details",
            bounding_box=[10, 10, 100, 50],
            image_path_or_array=None,
            ocr_confidence=0.35,
            extracted_text="care@brand.in"
        )
        assert res.readability_status in ("UNCERTAIN", "POOR_READABILITY")
        assert res.requires_manual_verification is True

    def test_ocr_unavailable_routes_to_manual_verification(self):
        """When OCR is unavailable, status must be UNREADABLE / UNCERTAIN, never a legal violation."""
        res = readability_analyzer.analyze_readability(
            field_name="mrp",
            bounding_box=None,
            image_path_or_array=None,
            ocr_confidence=0.0,
            extracted_text=""
        )
        assert res.readability_status in ("NOT_OBSERVABLE", "UNREADABLE", "UNCERTAIN")
        assert res.requires_manual_verification is True

    def test_blurry_crop_detected_as_poor_readability(self):
        """Flat / blurry crop with zero edge variance and modest confidence routes to poor readability."""
        flat_crop = np.ones((100, 200, 3), dtype=np.uint8) * 128
        res = readability_analyzer.analyze_readability(
            field_name="batch_code",
            bounding_box=[0, 0, 200, 100],
            image_path_or_array=flat_crop,
            ocr_confidence=0.60,
            extracted_text="B23"
        )
        assert res.local_blur_score < 50.0
        assert res.readability_status in ("POOR_READABILITY", "UNCERTAIN")
        assert res.requires_manual_verification is True

    def test_anti_fabrication_rule_never_converts_low_confidence_to_violation(self):
        """Legal safety invariant: OCR uncertainty is an observation defect, not evidence of statutory non-compliance."""
        res = readability_analyzer.analyze_readability(
            field_name="net_quantity",
            bounding_box=None,
            image_path_or_array=None,
            ocr_confidence=0.0,
            extracted_text=None
        )
        assert res.requires_manual_verification is True
        assert res.readability_status != "VIOLATION"
