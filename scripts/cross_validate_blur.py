"""
scripts/cross_validate_blur.py

Cross-validation script to compare blur detection scores between:
  1. Google Colab reference implementation (Python / OpenCV)
  2. NiriKsha Android / React Native implementation

Usage:
  python scripts/cross_validate_blur.py [optional_image_path]

Algorithm validated in Colab:
  - Convert image to grayscale (cv2.COLOR_BGR2GRAY / Rec.601 integer fixed-point)
  - If width > 800: downscale to width=800 preserving aspect ratio (never upscale)
  - cv2.Laplacian(gray, cv2.CV_64F) with 3x3 kernel [0, 1, 0; 1, -4, 1; 0, 1, 0]
  - Population variance of Laplacian values
  - Threshold: 150.0 (score < 150.0 -> BLURRY; score >= 150.0 -> ACCEPTABLE)
"""

import sys
import os
from pathlib import Path
import cv2
import numpy as np

BLUR_THRESHOLD = 150.0
TARGET_WIDTH = 800

def compute_colab_blur_score(image_path: str, target_width: int = TARGET_WIDTH):
    """
    Exact reference function from Google Colab notebook.
    """
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Could not load image at: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    downscaled = False
    if w > target_width:
        scale = target_width / w
        target_h = int(h * scale)
        gray = cv2.resize(gray, (target_width, target_h), interpolation=cv2.INTER_LINEAR)
        downscaled = True

    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    score = float(laplacian.var())
    is_blurry = score < BLUR_THRESHOLD

    return {
        "score": score,
        "is_blurry": is_blurry,
        "orig_width": w,
        "orig_height": h,
        "final_width": gray.shape[1],
        "final_height": gray.shape[0],
        "downscaled": downscaled,
        "threshold": BLUR_THRESHOLD,
    }


def main():
    base_dir = Path(__file__).resolve().parent.parent
    fixtures_dir = base_dir / "tests" / "fixtures"

    test_files = [
        "clear_package.jpg",
        "good_package.jpg",
        "blurry_package.jpg",
        "dark_package.jpg",
        "low_res_package.jpg",
    ]

    if len(sys.argv) > 1:
        custom_path = sys.argv[1]
        print(f"\n========================================================")
        print(f"Colab Cross-Validation Single Image: {custom_path}")
        print(f"========================================================")
        res = compute_colab_blur_score(custom_path)
        print(f"Original dimensions : {res['orig_width']} x {res['orig_height']}")
        print(f"Downscaled          : {res['downscaled']} -> {res['final_width']} x {res['final_height']}")
        print(f"Laplacian Variance  : {res['score']:.4f}")
        print(f"Threshold           : {res['threshold']:.1f}")
        print(f"Status              : {'BLURRY (Reject/Retake)' if res['is_blurry'] else 'ACCEPTABLE (Proceed)'}")
        return

    print("=" * 78)
    print("NiriKsha vs Google Colab Blur Detection Reference Cross-Validation")
    print(f"Threshold: {BLUR_THRESHOLD:.1f}  |  Downscale threshold: width > {TARGET_WIDTH} px")
    print("=" * 78)
    print(f"{'Image Fixture':<28} | {'Orig Res':<11} | {'Downscaled':<10} | {'Score':<10} | {'Decision'}")
    print("-" * 78)

    for fname in test_files:
        fpath = fixtures_dir / fname
        if not fpath.exists():
            continue
        res = compute_colab_blur_score(str(fpath))
        orig_res = f"{res['orig_width']}x{res['orig_height']}"
        down_str = f"Yes({res['final_width']}w)" if res['downscaled'] else "No"
        decision = "BLURRY (< 150)" if res['is_blurry'] else "ACCEPTABLE (>= 150)"
        print(f"{fname:<28} | {orig_res:<11} | {down_str:<10} | {res['score']:<10.2f} | {decision}")

    print("=" * 78)


if __name__ == "__main__":
    main()
