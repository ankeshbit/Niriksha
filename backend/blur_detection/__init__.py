#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
BlurDetection2 package (Will Brennan).
Total variance of the Laplacian of an image with resolution normalization.
"""
from .detection import fix_image_size, estimate_blur, pretty_blur_map

__all__ = ["fix_image_size", "estimate_blur", "pretty_blur_map"]
