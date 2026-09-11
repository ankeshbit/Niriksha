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
import numpy as np
from typing import List, Dict, Any, Optional, Tuple, Union
from pydantic import BaseModel
from pathlib import Path

from backend.blur_detection import estimate_blur


class DeclarationReadabilityResult(BaseModel):
    field_name: str
    image_id: Optional[str] = None
    bounding_box: Optional[List[int]] = None
    ocr_confidence: float = 0.0
    local_blur_score: float = 0.0
    local_contrast_score: float = 0.0
    text_visibility_score: float = 0.0
    readability_status: str  # READABLE, POOR_READABILITY, UNREADABLE, UNCERTAIN, NOT_OBSERVABLE, MANUAL_VERIFICATION_REQUIRED
    is_sufficiently_observable: bool = False
    requires_manual_verification: bool = False
    explanation: str
    statutory_reference: str = "Rule 7(2) Legibility Mandate, Legal Metrology (Packaged Commodities) Rules, 2011"
    provenance: str = "DECLARATION_CROP_VISION_PIPELINE"


class DeclarationReadabilityAnalyzer:
    """
    Evaluates declaration-level readability and optical legibility on localized image regions.
    """

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

        # Classification
        if ocr_confidence >= 0.80 and (not has_crop_metrics or local_blur >= 35.0):
            readability_status = "READABLE"
            is_observable = True
            requires_manual = False
            explanation = (
                f"Declaration is clearly legible (OCR confidence: {ocr_confidence:.2f}"
                + (f", local sharpness: {local_blur:.1f}, contrast: {local_contrast:.2f})" if has_crop_metrics else ")")
                + f". Conforms to Rule 7 legibility standards."
            )
        elif ocr_confidence >= 0.50 and (not has_crop_metrics or local_blur >= 15.0):
            readability_status = "UNCERTAIN"
            is_observable = True
            requires_manual = True
            explanation = (
                f"Declaration has moderate legibility (OCR confidence: {ocr_confidence:.2f}"
                + (f", local sharpness: {local_blur:.1f}, contrast: {local_contrast:.2f})" if has_crop_metrics else ")")
                + f". Inspector manual verification recommended."
            )
        elif ocr_confidence >= 0.30:
            readability_status = "POOR_READABILITY"
            is_observable = False
            requires_manual = True
            explanation = (
                f"Declaration exhibits poor optical clarity (OCR confidence: {ocr_confidence:.2f}"
                + (f", local sharpness: {local_blur:.1f})" if has_crop_metrics else ")")
                + f". Flagged for manual inspector review. Not an automatic legal violation."
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
            explanation=explanation
        )


readability_analyzer = DeclarationReadabilityAnalyzer()
