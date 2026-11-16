import pytest
import numpy as np
import os
from unittest.mock import patch, MagicMock
from backend.config import settings
from backend.readability_service import (
    DeclarationReadabilityAnalyzer,
    readability_analyzer
)

class TestMLReadabilitySafety:
    """
    Test suite verifying safety gates for machine learning readability decisions:
    - Synthetic training data models cannot independently declare a declaration READABLE.
    - Missing, disabled, or unvalidated ML models produce safe deterministic fallbacks.
    - Low-confidence predictions route to MANUAL_VERIFICATION_REQUIRED.
    - Deterministic measurements (high OCR confidence + sharp edges) continue to function.
    - Low OCR confidence / OCR failures never produce an automatic violation.
    """

    def test_synthetic_model_detected_and_disabled(self):
        """Metadata flagged with synthetic data or demonstration status must be marked as not production-ready."""
        analyzer = DeclarationReadabilityAnalyzer()
        assert analyzer.is_synthetic_model is True
        assert analyzer.is_model_production_ready is False
        assert analyzer.model_readiness_reason != ""

    def test_synthetic_model_cannot_automatically_approve_readability(self):
        """
        Even if the ML model predicts 'READABLE' with 0.99 confidence, if the model is synthetic
        and OCR confidence is borderline (e.g. 0.70), it must NOT be marked READABLE.
        It must route to MANUAL_VERIFICATION_REQUIRED.
        """
        analyzer = DeclarationReadabilityAnalyzer()
        # Mock ML model to predict READABLE with high confidence
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array(["READABLE"])
        mock_model.predict_proba.return_value = np.array([[0.01, 0.99]])
        mock_model.classes_ = np.array(["NOT_READABLE", "READABLE"])

        analyzer._read_model = mock_model
        analyzer.is_synthetic_model = True
        analyzer.is_model_production_ready = False

        sharp_crop = np.zeros((100, 200, 3), dtype=np.uint8)
        sharp_crop[:, :100] = 255

        # Borderline OCR confidence (0.70) with ML predicting READABLE
        with patch("backend.readability_service.settings.ML_READABILITY_MODEL_ENABLED", True):
            res = analyzer.analyze_readability(
                field_name="mrp",
                bounding_box=[10, 10, 210, 110],
                image_path_or_array=sharp_crop,
                ocr_confidence=0.70,
                extracted_text="Rs. 45.00"
            )

        assert res.readability_status in ("UNCERTAIN", "MANUAL_VERIFICATION_REQUIRED")
        assert res.requires_manual_verification is True
        assert "synthetic" in res.explanation.lower() or "not validated" in res.explanation.lower() or "unvalidated" in res.explanation.lower()

    def test_missing_model_produces_safe_deterministic_result(self):
        """When ML model is None or file is missing, the analyzer safely relies on deterministic metrics."""
        analyzer = DeclarationReadabilityAnalyzer()
        analyzer._read_model = None

        sharp_crop = np.zeros((100, 200, 3), dtype=np.uint8)
        sharp_crop[:, :100] = 255

        # High confidence deterministic text should still pass as READABLE
        res = analyzer.analyze_readability(
            field_name="manufacturer_name",
            bounding_box=[10, 10, 210, 110],
            image_path_or_array=sharp_crop,
            ocr_confidence=0.92,
            extracted_text="ABC Consumer Goods Pvt Ltd"
        )

        assert res.readability_status == "READABLE"
        assert res.requires_manual_verification is False
        assert res.ml_confidence is None

    def test_disabled_feature_flag_bypasses_ml_inference(self):
        """When ML_READABILITY_MODEL_ENABLED is False, ML inference is not consulted."""
        analyzer = DeclarationReadabilityAnalyzer()
        mock_model = MagicMock()
        analyzer._read_model = mock_model

        with patch("backend.readability_service.settings.ML_READABILITY_MODEL_ENABLED", False):
            sharp_crop = np.zeros((100, 200, 3), dtype=np.uint8)
            sharp_crop[:, :100] = 255

            res = analyzer.analyze_readability(
                field_name="batch_number",
                bounding_box=[10, 10, 210, 110],
                image_path_or_array=sharp_crop,
                ocr_confidence=0.75,
                extracted_text="BATCH-2024-X"
            )

            # Under borderline OCR and disabled ML, routes to manual verification
            assert res.requires_manual_verification is True

    def test_low_confidence_production_model_requires_manual_verification(self):
        """
        Even if a validated production-ready model exists, if its confidence is below
        ML_READABILITY_MIN_CONFIDENCE (0.85), it must require manual verification.
        """
        analyzer = DeclarationReadabilityAnalyzer()
        mock_model = MagicMock()
        mock_model.predict.return_value = np.array(["READABLE"])
        mock_model.predict_proba.return_value = np.array([[0.25, 0.75]]) # 75% < 85% threshold
        mock_model.classes_ = np.array(["NOT_READABLE", "READABLE"])

        analyzer._read_model = mock_model
        analyzer.is_synthetic_model = False
        analyzer.is_model_production_ready = True

        sharp_crop = np.zeros((100, 200, 3), dtype=np.uint8)
        sharp_crop[:, :100] = 255

        with patch("backend.readability_service.settings.ML_READABILITY_MODEL_ENABLED", True):
            res = analyzer.analyze_readability(
                field_name="net_quantity",
                bounding_box=[10, 10, 210, 110],
                image_path_or_array=sharp_crop,
                ocr_confidence=0.72,
                extracted_text="500 g"
            )

            assert res.readability_status in ("UNCERTAIN", "MANUAL_VERIFICATION_REQUIRED")
            assert res.requires_manual_verification is True
            assert res.ml_confidence == 0.75

    def test_valid_deterministic_measurements_still_work(self):
        """Statutory optical quality and high OCR confidence deterministically resolve to READABLE."""
        sharp_crop = np.zeros((100, 200, 3), dtype=np.uint8)
        sharp_crop[:, :100] = 255

        res = readability_analyzer.analyze_readability(
            field_name="consumer_care_email",
            bounding_box=[10, 10, 210, 110],
            image_path_or_array=sharp_crop,
            ocr_confidence=0.95,
            extracted_text="support@example.com"
        )

        assert res.readability_status == "READABLE"
        assert res.requires_manual_verification is False
        assert res.is_sufficiently_observable is True
        assert res.local_blur_score > 35.0
        assert res.local_contrast_score > 0.15

    def test_ocr_failure_never_produces_false_compliance_or_automatic_violation(self):
        """
        Missing OCR or 0.0 confidence must produce UNCERTAIN / MANUAL_VERIFICATION_REQUIRED,
        never a false compliant result or an automatic statutory violation.
        """
        res = readability_analyzer.analyze_readability(
            field_name="country_of_origin",
            bounding_box=None,
            image_path_or_array=None,
            ocr_confidence=0.0,
            extracted_text=""
        )

        assert res.requires_manual_verification is True
        assert res.readability_status in ("NOT_OBSERVABLE", "UNREADABLE", "UNCERTAIN", "MANUAL_VERIFICATION_REQUIRED")
        assert res.readability_status != "READABLE"
        assert res.readability_status != "VIOLATION"
