"""
backend/readability_service.py

Declaration-Level Readability Analysis Engine for NiriKsha.
Statutory Reference: Rule 6 & 7, Legal Metrology (Packaged Commodities) Rules, 2011 (PDF p. 5-7)
Mandate: Declarations shall be conspicuous, legible, and prominent.

CRITICAL INVARIANTS:
1. Whole-image quality score is NOT declaration readability. A clear image may contain tiny, unreadable date stamps;
   conversely, a slightly blurry photo may have a large, highly readable MRP.
2. Readability is evaluated specifically on the declaration's localized region:
   - OCR character confidence
   - Local crop Laplacian variance / blur score
   - Local contrast (Michelson / RMS contrast)
   - Text visibility and character recognition completeness
3. LEGAL SAFETY GUARANTEE:
   The system must NEVER convert OCR_UNAVAILABLE, LOW_CONFIDENCE, UNREADABLE, or NOT_OBSERVABLE
   into an automatic legal violation. Such conditions route strictly to MANUAL_VERIFICATION_REQUIRED.
"""

import cv2
import json
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple, Union
from pydantic import BaseModel
from pathlib import Path

from backend.blur_detection import estimate_blur

ML_MODELS_DIR = Path(__file__).resolve().parent / "ml_models"
if not ML_MODELS_DIR.exists():
    ML_MODELS_DIR = Path(__file__).resolve().parent.parent / "nirikSha_font_readability" / "models"


class DeclarationReadabilityResult(BaseModel):
    field_name: str
    image_id: Optional[str] = None
    bounding_box: Optional[List[int]] = None
    ocr_confidence: float = 0.0
    local_blur_score: float = 0.0
    local_contrast_score: float = 0.0
    text_visibility_score: float = 0.0
    readability_status: str  # READABLE, POOR_READABILITY, UNREADABLE, UNCERTAIN, NOT_OBSERVABLE, MANUAL_VERIFICATION_REQUIRED, READABILITY_UNCERTAIN
    is_sufficiently_observable: bool = False
    requires_manual_verification: bool = False
    explanation: str
    ml_model_name: Optional[str] = None
    ml_confidence: Optional[float] = None
    ml_predicted_label: Optional[str] = None
    ml_features: Optional[Dict[str, Any]] = None
    statutory_reference: str = "Rule 7(2) Legibility Mandate, Legal Metrology (Packaged Commodities) Rules, 2011"
    provenance: str = "ML_AND_CROP_VISION_PIPELINE"


class DeclarationReadabilityAnalyzer:
    """
    Evaluates declaration-level readability and optical legibility on localized image regions
    using trained classical ML models and localized optical feature analysis.
    """

    # Image quality gate thresholds from notebook Section 21
    MIN_TRUSTED_CROP_PIXELS = 200
    MIN_MODEL_CONFIDENCE = 0.55

    def __init__(self):
        self._read_model = None
        self._read_scaler = None
        self._read_features = None
        self._model_name = "LogisticRegression"
        self._load_ml_model()

    def _load_ml_model(self):
        try:
            import joblib
            model_p = ML_MODELS_DIR / "readability_model.joblib"
            scaler_p = ML_MODELS_DIR / "readability_scaler.joblib"
            feat_p = ML_MODELS_DIR / "readability_features.json"
            meta_p = ML_MODELS_DIR / "model_metadata.json"

            if model_p.exists():
                self._read_model = joblib.load(model_p)
            if scaler_p.exists():
                self._read_scaler = joblib.load(scaler_p)
            if feat_p.exists():
                with open(feat_p, "r", encoding="utf-8") as f:
                    self._read_features = json.load(f).get("features", [])
            if meta_p.exists():
                with open(meta_p, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    self._model_name = meta.get("readability_model", {}).get("model_type", "LogisticRegression")
        except Exception:
            self._read_model = None

    @staticmethod
    def _edge_density(gray: np.ndarray) -> float:
        edges = cv2.Canny(gray, 60, 150)
        return float((edges > 0).mean())

    @staticmethod
    def _noise_estimate(gray: np.ndarray) -> float:
        denoised = cv2.medianBlur(gray, 3)
        return float(np.mean(np.abs(gray.astype(np.float32) - denoised.astype(np.float32))))

    @staticmethod
    def _text_background_separation(gray: np.ndarray) -> float:
        if gray.size == 0 or gray.std() == 0:
            return 0.0
        _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        fg = gray[mask == 255]
        bg = gray[mask == 0]
        if fg.size == 0 or bg.size == 0:
            return 0.0
        return float(abs(fg.mean() - bg.mean()))

    @staticmethod
    def _perspective_distortion_indicator(gray: np.ndarray) -> float:
        edges = cv2.Canny(gray, 60, 150)
        coords = cv2.findNonZero(edges)
        if coords is None or len(coords) < 5:
            return 0.0
        rect = cv2.minAreaRect(coords)
        (_, _), (rw, rh), angle = rect
        return float(min(abs(angle), abs(90 - abs(angle))))

    def extract_readability_features(
        self,
        crop: np.ndarray,
        text: str,
        ocr_confidence: float = 0.90
    ) -> Dict[str, Any]:
        """Extracts exact 15 readability features defined in notebook Section 15."""
        if crop is None or crop.size == 0:
            crop = np.zeros((4, 4, 3), dtype=np.uint8)
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop

        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        contrast_std = float(gray.std())
        edge_density = self._edge_density(gray)
        noise_est = self._noise_estimate(gray)
        text_bg_sep = self._text_background_separation(gray)
        perspective_ind = self._perspective_distortion_indicator(gray)

        crop_h, crop_w = gray.shape[:2]
        t = str(text) if text else ""
        char_count = max(len(t.replace(" ", "")), 1)
        pixels_per_char = (crop_w * crop_h) / char_count
        blur_score = float(1.0 / (1.0 + laplacian_var / 100.0))

        return {
            "sharpness_laplacian_var": laplacian_var,
            "contrast_std": contrast_std,
            "edge_density": edge_density,
            "grayscale_mean": float(gray.mean()),
            "grayscale_std": contrast_std,
            "noise_estimate": noise_est,
            "text_background_separation": text_bg_sep,
            "perspective_distortion_indicator": perspective_ind,
            "ocr_confidence": float(ocr_confidence),
            "crop_width": crop_w,
            "crop_height": crop_h,
            "crop_resolution": crop_w * crop_h,
            "pixels_per_char": pixels_per_char,
            "char_density": char_count / max(crop_w * crop_h, 1),
            "blur_score": blur_score,
        }

    def _compute_crop_metrics(self, crop: np.ndarray) -> Tuple[float, float]:
        """
        Computes local blur score (Laplacian variance) and Michelson contrast on crop.
        Returns: (blur_score, contrast_ratio)
        """
        if crop is None or crop.size == 0 or crop.shape[0] < 3 or crop.shape[1] < 3:
            return 0.0, 0.0

        if crop.ndim == 3:
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        else:
            gray = crop

        # 1. Local Blur Score
        _, blur_score, _ = estimate_blur(gray, threshold=50.0)

        # 2. Local Contrast
        min_v = float(np.min(gray))
        max_v = float(np.max(gray))
        if (max_v + min_v) > 0:
            contrast = (max_v - min_v) / (max_v + min_v)
        else:
            contrast = 0.0

        return round(float(blur_score), 2), round(float(contrast), 3)

    def analyze_readability(
        self,
        field_name: str,
        extracted_value: Optional[str] = None,
        bounding_box: Optional[List[int]] = None,
        ocr_confidence: float = 0.0,
        source_image_id: Optional[str] = None,
        image_input: Optional[Union[str, Path, np.ndarray]] = None,
        image_path_or_array: Optional[Any] = None,
        extracted_text: Optional[str] = None
    ) -> DeclarationReadabilityResult:
        """
        Evaluates declaration-level legibility and readability.
        """
        if extracted_value is None and extracted_text is not None:
            extracted_value = extracted_text
        if image_input is None and image_path_or_array is not None:
            image_input = image_path_or_array

        # Case 1: Declaration missing / not observed
        if not extracted_value or not str(extracted_value).strip():
            return DeclarationReadabilityResult(
                field_name=field_name,
                image_id=source_image_id,
                bounding_box=None,
                ocr_confidence=0.0,
                local_blur_score=0.0,
                local_contrast_score=0.0,
                text_visibility_score=0.0,
                readability_status="NOT_OBSERVABLE",
                is_sufficiently_observable=False,
                requires_manual_verification=True,
                explanation=f"{field_name.replace('_', ' ').title()} text was not recognized by OCR on any captured image."
            )

        # Case 2: Bounding box missing
        if not bounding_box or len(bounding_box) < 4:
            # Evaluate using OCR confidence alone
            if ocr_confidence >= 0.85:
                status = "READABLE"
                req_manual = False
                exp = "Declaration text extracted with high confidence, though spatial bounding box was not localized."
            elif ocr_confidence >= 0.50:
                status = "UNCERTAIN"
                req_manual = True
                exp = f"Moderate OCR confidence ({ocr_confidence:.2f}) without localized bounding box. Manual review recommended."
            else:
                status = "POOR_READABILITY"
                req_manual = True
                exp = f"Low OCR confidence ({ocr_confidence:.2f}) without spatial coordinates. Manual verification required."

            return DeclarationReadabilityResult(
                field_name=field_name,
                image_id=source_image_id,
                bounding_box=None,
                ocr_confidence=ocr_confidence,
                local_blur_score=0.0,
                local_contrast_score=0.0,
                text_visibility_score=ocr_confidence,
                readability_status=status,
                is_sufficiently_observable=(ocr_confidence >= 0.70),
                requires_manual_verification=req_manual,
                explanation=exp
            )

        # Case 3: Local Image Crop Analysis
        local_blur = 0.0
        local_contrast = 0.0
        has_crop_metrics = False
        crop = None
        read_feats = None
        ml_model_name = self._model_name if self._read_model is not None else None
        ml_conf = None
        ml_pred_label = None

        if image_input is not None:
            try:
                img_arr = None
                if isinstance(image_input, np.ndarray):
                    img_arr = image_input
                elif isinstance(image_input, (str, Path)):
                    p = str(image_input)
                    if Path(p).exists():
                        img_arr = cv2.imread(p)

                if img_arr is not None and img_arr.size > 0:
                    h, w = img_arr.shape[:2]
                    x1, y1, x2, y2 = bounding_box
                    # Clip coordinates to image boundary with 4px padding
                    cx1 = max(0, min(w - 1, x1 - 4))
                    cy1 = max(0, min(h - 1, y1 - 4))
                    cx2 = max(cx1 + 1, min(w, x2 + 4))
                    cy2 = max(cy1 + 1, min(h, y2 + 4))

                    crop = img_arr[cy1:cy2, cx1:cx2]
                    if crop.size > 0:
                        local_blur, local_contrast = self._compute_crop_metrics(crop)
                        has_crop_metrics = True
                        read_feats = self.extract_readability_features(
                            crop=crop,
                            text=str(extracted_value),
                            ocr_confidence=ocr_confidence
                        )
            except Exception:
                pass

        # Quality Gate Check: Crop resolution threshold from notebook Section 21
        crop_res = (crop.shape[0] * crop.shape[1]) if (crop is not None and crop.size > 0) else 0
        if has_crop_metrics and crop_res < self.MIN_TRUSTED_CROP_PIXELS:
            return DeclarationReadabilityResult(
                field_name=field_name,
                image_id=source_image_id,
                bounding_box=bounding_box,
                ocr_confidence=round(float(ocr_confidence), 2),
                local_blur_score=local_blur,
                local_contrast_score=local_contrast,
                text_visibility_score=round(float(ocr_confidence * 0.5), 2),
                readability_status="READABILITY_UNCERTAIN",
                is_sufficiently_observable=False,
                requires_manual_verification=True,
                explanation=f"Crop resolution ({crop_res}px) is below trusted threshold ({self.MIN_TRUSTED_CROP_PIXELS}px). Routed to manual verification.",
                ml_model_name=ml_model_name,
                ml_confidence=None,
                ml_predicted_label=None,
                ml_features=read_feats
            )

        # ML Model Inference
        if self._read_model is not None and read_feats is not None:
            try:
                feature_cols = self._read_features or list(read_feats.keys())
                df_in = pd.DataFrame([read_feats])[feature_cols]
                if self._read_scaler is not None:
                    df_in_sc = self._read_scaler.transform(df_in)
                else:
                    df_in_sc = df_in

                ml_pred_label = self._read_model.predict(df_in_sc)[0]
                if hasattr(self._read_model, "predict_proba"):
                    proba = self._read_model.predict_proba(df_in_sc)[0]
                    ml_conf = round(float(proba.max()), 3)
            except Exception:
                pass

        # Calculate composite visibility score: combines OCR confidence and local contrast
        if has_crop_metrics:
            # Contrast weighting: contrast between 0.30 - 0.90 is optimal
            contrast_weight = min(1.0, local_contrast / 0.40)
            blur_weight = 1.0 if local_blur >= 40.0 else (local_blur / 40.0)
            visibility_score = round(float(0.55 * ocr_confidence + 0.25 * contrast_weight + 0.20 * blur_weight), 2)
        else:
            visibility_score = round(float(ocr_confidence), 2)

        # Classification & Routing
        if ocr_confidence >= 0.80 and (not has_crop_metrics or local_blur >= 35.0):
            readability_status = "READABLE"
            is_observable = True
            requires_manual = False
            explanation = (
                f"Declaration is clearly legible (OCR confidence: {ocr_confidence:.2f}"
                + (f", local sharpness: {local_blur:.1f}, contrast: {local_contrast:.2f})" if has_crop_metrics else ")")
                + (f" [ML Model {ml_model_name}: {ml_pred_label} (conf: {ml_conf})]" if ml_pred_label else "")
                + ". Conforms to Rule 7 legibility standards."
            )
        elif ml_pred_label == "READABLE" and ocr_confidence >= 0.70 and (ml_conf is None or ml_conf >= self.MIN_MODEL_CONFIDENCE):
            readability_status = "READABLE"
            is_observable = True
            requires_manual = False
            explanation = (
                f"Declaration classified as READABLE by {ml_model_name} (confidence: {ml_conf}, OCR confidence: {ocr_confidence:.2f}). "
                f"Conforms to Rule 7 legibility standards."
            )
        elif ml_conf is not None and ml_conf < self.MIN_MODEL_CONFIDENCE and has_crop_metrics:
            readability_status = "MANUAL_VERIFICATION_REQUIRED"
            is_observable = True
            requires_manual = True
            explanation = (
                f"ML model confidence ({ml_conf:.2f}) below threshold ({self.MIN_MODEL_CONFIDENCE}). "
                f"Field inspector physical verification required."
            )
        elif ocr_confidence >= 0.50 and (not has_crop_metrics or local_blur >= 15.0):
            readability_status = "UNCERTAIN"
            is_observable = True
            requires_manual = True
            explanation = (
                f"Declaration has moderate legibility (OCR confidence: {ocr_confidence:.2f}"
                + (f", local sharpness: {local_blur:.1f}, contrast: {local_contrast:.2f})" if has_crop_metrics else ")")
                + (f" [ML Model {ml_model_name}: {ml_pred_label}]" if ml_pred_label else "")
                + ". Inspector manual verification recommended."
            )
        elif ocr_confidence >= 0.30 or ml_pred_label == "PARTIALLY_READABLE":
            readability_status = "POOR_READABILITY"
            is_observable = False
            requires_manual = True
            explanation = (
                f"Declaration exhibits poor optical clarity (OCR confidence: {ocr_confidence:.2f}"
                + (f", local sharpness: {local_blur:.1f})" if has_crop_metrics else ")")
                + (f" [ML Model {ml_model_name}: {ml_pred_label}]" if ml_pred_label else "")
                + ". Flagged for manual inspector review. Not an automatic legal violation."
            )
        else:
            readability_status = "UNREADABLE"
            is_observable = False
            requires_manual = True
            explanation = (
                f"Declaration text is unreadable or severely degraded (confidence: {ocr_confidence:.2f}). "
                f"Routed to manual verification. Not an automatic violation."
            )

        return DeclarationReadabilityResult(
            field_name=field_name,
            image_id=source_image_id,
            bounding_box=bounding_box,
            ocr_confidence=round(float(ocr_confidence), 2),
            local_blur_score=local_blur,
            local_contrast_score=local_contrast,
            text_visibility_score=visibility_score,
            readability_status=readability_status,
            is_sufficiently_observable=is_observable,
            requires_manual_verification=requires_manual,
            explanation=explanation,
            ml_model_name=ml_model_name,
            ml_confidence=ml_conf,
            ml_predicted_label=ml_pred_label,
            ml_features=read_feats
        )


readability_analyzer = DeclarationReadabilityAnalyzer()
