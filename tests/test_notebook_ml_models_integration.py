import pytest
import numpy as np
from pathlib import Path
from backend.font_size_service import font_size_analyzer, FontSizeAnalysisResult
from backend.readability_service import readability_analyzer, DeclarationReadabilityResult
from backend.declaration_validation_service import declaration_validation_engine


class TestNotebookMLModelsIntegration:
    """
    Test suite verifying the integration of trained Font Size & Readability ML models
    from NiriKsha_Font_Size_Readability_Analysis.ipynb into the NiriKsha backend.
    """

    def test_ml_models_are_loaded_and_active(self):
        """Verify that both exported models and scalers are loaded."""
        assert font_size_analyzer._font_model is not None, "Font size ML model should be loaded"
        assert readability_analyzer._read_model is not None, "Readability ML model should be loaded"
        assert len(font_size_analyzer._font_features) == 15, "Font size should have 15 features"
        assert len(readability_analyzer._read_features) == 15, "Readability should have 15 features"

    def test_font_size_ml_model_predicts_when_calibrated(self):
        """
        When physical calibration is supplied (e.g. 10 px/mm), the ML model runs inference
        and preserves provenance, features, and predicted mm.
        """
        res = font_size_analyzer.analyze_declaration_font_size(
            field_name="net_quantity",
            extracted_value="500 g",
            bounding_box=[50, 50, 250, 100],  # 50px height
            calibration_scale_mm_per_px=0.1,    # 10 px/mm (0.1 mm/px)
            calibration_source="REFERENCE_RULER_SCALE"
        )
        assert res.is_calibrated is True
        assert res.ml_model_name == "GradientBoostingRegressor"
        assert res.ml_predicted_height_mm is not None
        assert res.ml_features is not None
        assert len(res.ml_features) == 15
        assert "pixel_height" in res.ml_features
        assert res.provenance == "ML_AND_OPTICAL_METROLOGY_PIPELINE"

    def test_font_size_uncalibrated_strictly_undeterminable(self):
        """Without calibration, ML model must NOT fabricate physical millimetres."""
        res = font_size_analyzer.analyze_declaration_font_size(
            field_name="net_quantity",
            extracted_value="500 g",
            bounding_box=[50, 50, 250, 100],
            calibration_scale_mm_per_px=None
        )
        assert res.is_calibrated is False
        assert res.font_size_status == "FONT_SIZE_UNDETERMINABLE"
        assert res.estimated_physical_height_mm is None
        assert res.ml_predicted_height_mm is None
        # Features are still extracted for audit provenance
        assert res.ml_features is not None

    def test_readability_quality_gate_low_resolution_routes_to_uncertain(self):
        """
        Notebook Section 21 Quality Gate:
        Crops smaller than MIN_TRUSTED_CROP_PIXELS (200 px) route to READABILITY_UNCERTAIN
        and require manual verification.
        """
        tiny_crop = np.ones((10, 15, 3), dtype=np.uint8) * 200  # 150 pixels (< 200)
        res = readability_analyzer.analyze_readability(
            field_name="mrp",
            extracted_value="Rs 99",
            bounding_box=[0, 0, 15, 10],
            image_path_or_array=tiny_crop,
            ocr_confidence=0.88
        )
        assert res.readability_status == "READABILITY_UNCERTAIN"
        assert res.requires_manual_verification is True
        assert "below trusted threshold" in res.explanation.lower()

    def test_readability_ml_model_infers_and_preserves_provenance(self):
        """Readability ML model executes inference, reports confidence, label, and features."""
        crop = np.zeros((100, 200, 3), dtype=np.uint8)
        crop[:, :100] = 255  # Distinct edge

        res = readability_analyzer.analyze_readability(
            field_name="mrp",
            extracted_value="MRP Rs. 250.00",
            bounding_box=[10, 10, 210, 110],
            image_path_or_array=crop,
            ocr_confidence=0.92
        )
        assert res.ml_model_name == "LogisticRegression"
        assert res.ml_predicted_label is not None
        assert res.ml_features is not None
        assert len(res.ml_features) == 15
        assert "sharpness_laplacian_var" in res.ml_features
        assert res.provenance == "ML_AND_CROP_VISION_PIPELINE"

    def test_ml_layer_does_not_issue_legal_convictions(self):
        """
        System invariant: ML layer outputs measurement/clarity, never legal verdicts.
        Poor readability or undetermined font size routes to MANUAL_VERIFICATION_REQUIRED.
        """
        res = readability_analyzer.analyze_readability(
            field_name="manufacturer_packer_name_address",
            extracted_value="Unclear text",
            bounding_box=[0, 0, 100, 30],
            ocr_confidence=0.20,
            image_path_or_array=None
        )
        assert res.readability_status != "VIOLATION"
        assert res.requires_manual_verification is True
