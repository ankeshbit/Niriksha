import cv2
import numpy as np
from pathlib import Path
from typing import Dict, Any, List, Tuple

class ImageQualityResult:
    def __init__(
        self,
        quality_status: str,
        quality_score: float,
        blur_score: float,
        blur_ok: bool,
        brightness_score: float,
        brightness_ok: bool,
        contrast_score: float,
        contrast_ok: bool,
        resolution_ok: bool,
        width: int,
        height: int,
        warnings: List[str],
        recommendation: str
    ):
        self.quality_status = quality_status
        self.quality_score = quality_score
        self.blur_score = blur_score
        self.blur_ok = blur_ok
        self.brightness_score = brightness_score
        self.brightness_ok = brightness_ok
        self.contrast_score = contrast_score
        self.contrast_ok = contrast_ok
        self.resolution_ok = resolution_ok
        self.width = width
        self.height = height
        self.warnings = warnings
        self.recommendation = recommendation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quality_status": self.quality_status,
            "quality_score": round(self.quality_score, 2),
            "blur_score": round(self.blur_score, 2),
            "blur_ok": self.blur_ok,
            "brightness_score": round(self.brightness_score, 2),
            "brightness_ok": self.brightness_ok,
            "contrast_score": round(self.contrast_score, 2),
            "contrast_ok": self.contrast_ok,
            "resolution_ok": self.resolution_ok,
            "width": self.width,
            "height": self.height,
            "warnings": self.warnings,
            "recommendation": self.recommendation
        }


def assess_image_quality(image_path: str) -> ImageQualityResult:
    """
    Deterministic pre-OCR quality assessment.
    Evaluates resolution, Laplacian variance (blur), mean intensity (brightness/glare),
    and standard deviation (contrast).
    """
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found at path: {image_path}")

    # Read image using OpenCV
    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"Could not decode image at path: {image_path}")

    height, width = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    warnings: List[str] = []

    # 1. Resolution Check
    min_dimension = 400
    resolution_ok = width >= min_dimension and height >= min_dimension
    if not resolution_ok:
        warnings.append(f"Image resolution ({width}x{height}) is lower than recommended ({min_dimension}x{min_dimension}).")
        res_norm = min(1.0, (width * height) / (min_dimension * min_dimension))
    else:
        res_norm = 1.0

    # 2. Blur / Sharpness Check (Laplacian Variance)
    laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    blur_threshold = 70.0
    if laplacian_var >= 120.0:
        blur_ok = True
        blur_norm = 1.0
    elif laplacian_var >= blur_threshold:
        blur_ok = True
        blur_norm = 0.75
    elif laplacian_var >= 40.0:
        blur_ok = True
        blur_norm = 0.50
        warnings.append("Image is slightly blurry; text detection might be degraded.")
    else:
        blur_ok = False
        blur_norm = 0.20
        warnings.append("Image is noticeably blurry / out of focus.")

    # 3. Brightness / Exposure Check (Mean Intensity & Glare Ratio)
    mean_brightness = float(np.mean(gray))
    glare_pixels = np.sum(gray >= 252)
    total_pixels = width * height
    glare_ratio = float(glare_pixels) / float(total_pixels) if total_pixels > 0 else 0.0

    if mean_brightness < 35.0:
        brightness_ok = False
        bright_norm = 0.30
        warnings.append("Image is too dark / underexposed.")
    elif mean_brightness > 248.0 or glare_ratio > 0.40:
        brightness_ok = False
        bright_norm = 0.35
        warnings.append("Glare or overexposure detected on the package label.")
    elif glare_ratio > 0.20:
        brightness_ok = True
        bright_norm = 0.70
        warnings.append("Moderate glare detected; some text areas may have reduced clarity.")
    else:
        brightness_ok = True
        bright_norm = 1.0

    # 4. Contrast Check (Standard Deviation of Intensity)
    contrast_std = float(np.std(gray))
    if contrast_std < 20.0:
        contrast_ok = False
        contrast_norm = 0.30
        warnings.append("Low contrast between text and package background.")
    elif contrast_std < 35.0:
        contrast_ok = True
        contrast_norm = 0.70
    else:
        contrast_ok = True
        contrast_norm = 1.0

    # 5. Composite Quality Score
    # Weights: Blur (40%), Brightness (25%), Contrast (20%), Resolution (15%)
    quality_score = (
        (blur_norm * 0.40) +
        (bright_norm * 0.25) +
        (contrast_norm * 0.20) +
        (res_norm * 0.15)
    )

    # 6. Quality Status Classification
    if not blur_ok or not brightness_ok or quality_score < 0.50:
        quality_status = "POOR"
        recommendation = "Image quality is insufficient. Please capture or upload a clearer image."
    elif len(warnings) > 0 or quality_score < 0.78:
        quality_status = "WARNING"
        recommendation = "Image may affect text extraction. Consider capturing a clearer image."
    else:
        quality_status = "GOOD"
        recommendation = "Image quality is sufficient for analysis."

    return ImageQualityResult(
        quality_status=quality_status,
        quality_score=quality_score,
        blur_score=laplacian_var,
        blur_ok=blur_ok,
        brightness_score=mean_brightness,
        brightness_ok=brightness_ok,
        contrast_score=contrast_std,
        contrast_ok=contrast_ok,
        resolution_ok=resolution_ok,
        width=width,
        height=height,
        warnings=warnings,
        recommendation=recommendation
    )
