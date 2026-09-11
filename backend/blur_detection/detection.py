#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
BlurDetection2 detection module.
Source: https://github.com/WillBrennan/BlurDetection2

Provides:
- fix_image_size: normalizes resolution to ~2 megapixels (HD) for consistent scoring across camera sensors.
- estimate_blur: computes total variance of the Laplacian of the image.
- pretty_blur_map: generates a smoothed logarithmic blur map for visualization.
"""
import cv2
import numpy as np


def fix_image_size(image: np.ndarray, expected_pixels: float = 2e6) -> np.ndarray:
    """
    Normalizes the image dimensions to approximately expected_pixels (default 2MP)
    preserving aspect ratio. Prevents score inflation or deflation caused purely
    by sensor pixel density.
    """
    if image is None or image.size == 0:
        return image

    h, w = image.shape[:2]
    if h <= 0 or w <= 0:
        return image

    current_pixels = float(h * w)
    if current_pixels <= 0:
        return image

    ratio = np.sqrt(expected_pixels / current_pixels)
    return cv2.resize(image, (0, 0), fx=ratio, fy=ratio, interpolation=cv2.INTER_LINEAR)


def estimate_blur(image: np.ndarray, threshold: float = 100.0):
    """
    Computes the Laplacian variance of the image using BlurDetection2 algorithm.

    Args:
        image: Input image array (BGR, RGB, or Grayscale).
        threshold: Threshold below which an image is considered blurry (default 100.0).

    Returns:
        tuple: (blur_map, score, blurry_boolean)
    """
    if image is None or image.size == 0:
        return np.array([]), 0.0, True

    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    elif image.ndim == 2:
        gray = image
    else:
        return np.array([]), 0.0, True

    h, w = gray.shape[:2]
    if h < 3 or w < 3:
        return np.array([]), 0.0, True

    blur_map = cv2.Laplacian(gray, cv2.CV_64F)
    score = float(np.var(blur_map))
    is_blurry = bool(score < threshold)
    return blur_map, score, is_blurry


def pretty_blur_map(blur_map: np.ndarray, sigma: int = 5, min_abs: float = 0.5) -> np.ndarray:
    """
    Generates a human-interpretable logarithmic blur map visualization.
    """
    if blur_map is None or blur_map.size == 0:
        return np.array([])

    abs_image = np.abs(blur_map).astype(np.float32)
    abs_image[abs_image < min_abs] = min_abs

    abs_image = np.log(abs_image)
    cv2.blur(abs_image, (sigma, sigma))
    return cv2.medianBlur(abs_image, sigma)
