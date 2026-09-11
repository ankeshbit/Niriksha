"""
backend/barcode_service.py

Barcode and QR Code Evidence Detection & Decoding Engine.
Uses pyzbar with OpenCV fallback to decode EAN-13, UPC-A, Code 128, QR Codes, and other standard package formats.

CRITICAL STATUTORY INVARIANTS:
1. Barcode/QR information must NOT replace OCR. It is an additional evidence channel.
2. Confidence score is None (null) unless provided by the decoder. Never invent confidence.
3. OCR cross-validation: If OCR sees a barcode/GTIN-like number, compare with decoded barcode.
   - Match: Corroborating evidence
   - Disagree: EVIDENCE_CONFLICT (sent to inspector review)
4. Multi-image consolidation:
   - Same barcode across images -> consolidated evidence
   - Different barcodes -> conflict
5. Legal rule engine: Barcode does NOT prove legal compliance unless explicitly required by law.
"""

import os
import sys
import re
import cv2
import time
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field

# Ensure Windows finds DLLs for pyzbar if needed
pyzbar_dir = Path(sys.prefix) / "lib" / "site-packages" / "pyzbar"
if pyzbar_dir.exists() and hasattr(os, "add_dll_directory"):
    try:
        os.add_dll_directory(str(pyzbar_dir))
    except Exception:
        pass


class BarcodeItem(BaseModel):
    """Structured Barcode / QR Code Evidence Item."""
    type: str                                    # e.g., 'EAN13', 'QRCODE', 'CODE128', 'UPCA'
    value: str                                   # Decoded string or digits
    confidence: Optional[float] = None           # Strict invariant: null unless decoder provides one
    source_image_id: Optional[str] = None        # ID of image where detected
    source_image_path: Optional[str] = None
    bbox: Optional[List[int]] = None             # [x1, y1, x2, y2]
    timestamp: Optional[str] = None
    decoder: str = "pyzbar"                      # 'pyzbar' or 'opencv'
    ocr_corroboration: Optional[str] = None      # 'CORROBORATING', 'EVIDENCE_CONFLICT', 'NO_OCR_BARCODE'
    conflicting_ocr_value: Optional[str] = None


class BarcodeInspectionSummary(BaseModel):
    """Consolidated Barcode Evidence across an entire inspection."""
    detected: bool = False
    items: List[BarcodeItem] = []
    has_conflict: bool = False
    conflict_description: Optional[str] = None
    consolidated_value: Optional[str] = None
    barcode_type: Optional[str] = None


def _is_pyzbar_available() -> bool:
    try:
        from pyzbar.pyzbar import decode
        return True
    except Exception:
        return False


class BarcodeService:
    """
    Decodes barcodes and QR codes from package images.
    Supports pyzbar with automatic OpenCV barcode/QR detector fallback.
    """
    def __init__(self):
        self.pyzbar_available = _is_pyzbar_available()

    def detect_and_decode(
        self,
        image_input: Any,
        source_image_id: Optional[str] = None,
        source_image_path: Optional[str] = None
    ) -> List[BarcodeItem]:
        """
        Detects and decodes all barcodes and QR codes present in the image.
        Returns empty list if none detected or image is damaged.
        """
        if isinstance(image_input, (str, Path)):
            img_path = str(image_input)
            source_image_path = source_image_path or img_path
            if not os.path.isfile(img_path):
                return []
            img = cv2.imread(img_path)
        elif isinstance(image_input, np.ndarray):
            img = image_input
        else:
            return []

        if img is None or img.size == 0:
            return []

        results: List[BarcodeItem] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        # Engine 1: pyzbar (Primary)
        if self.pyzbar_available:
            try:
                from pyzbar.pyzbar import decode as pyzbar_decode
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
                decoded_objects = pyzbar_decode(gray)

                for obj in decoded_objects:
                    val = obj.data.decode("utf-8", errors="replace").strip()
                    if not val:
                        continue

                    # Bounding box calculation [x1, y1, x2, y2]
                    rect = obj.rect
                    bbox = [int(rect.left), int(rect.top), int(rect.left + rect.width), int(rect.top + rect.height)]

                    results.append(BarcodeItem(
                        type=obj.type.upper(),
                        value=val,
                        confidence=None,  # Do not invent confidence
                        source_image_id=source_image_id,
                        source_image_path=source_image_path,
                        bbox=bbox,
                        timestamp=now_iso,
                        decoder="pyzbar"
                    ))
            except Exception:
                pass

        # Engine 2: OpenCV Fallback (if pyzbar found nothing or is unavailable)
        if not results:
            cv_results = self._decode_with_opencv(img, source_image_id, source_image_path, now_iso)
            results.extend(cv_results)

        return results

    def _decode_with_opencv(
        self,
        img: np.ndarray,
        source_image_id: Optional[str],
        source_image_path: Optional[str],
        timestamp: str
    ) -> List[BarcodeItem]:
        items: List[BarcodeItem] = []

        # 1. Try OpenCV QR Code detector
        try:
            qr_detector = cv2.QRCodeDetector()
            val, points, _ = qr_detector.detectAndDecode(img)
            if val and val.strip():
                bbox = None
                if points is not None and len(points) > 0:
                    pts = points[0]
                    x1 = int(np.min(pts[:, 0]))
                    y1 = int(np.min(pts[:, 1]))
                    x2 = int(np.max(pts[:, 0]))
                    y2 = int(np.max(pts[:, 1]))
                    bbox = [x1, y1, x2, y2]
                items.append(BarcodeItem(
                    type="QRCODE",
                    value=val.strip(),
                    confidence=None,
                    source_image_id=source_image_id,
                    source_image_path=source_image_path,
                    bbox=bbox,
                    timestamp=timestamp,
                    decoder="opencv_qr"
                ))
        except Exception:
            pass

        # 2. Try OpenCV 1D Barcode detector
        if not items and hasattr(cv2, "barcode_BarcodeDetector"):
            try:
                bardet = cv2.barcode_BarcodeDetector()
                ok, decoded_info, decoded_type, corners = bardet.detectAndDecode(img)
                if ok:
                    for info, b_type, corner in zip(decoded_info, decoded_type, corners):
                        if info and info.strip():
                            x1 = int(np.min(corner[:, 0]))
                            y1 = int(np.min(corner[:, 1]))
                            x2 = int(np.max(corner[:, 0]))
                            y2 = int(np.max(corner[:, 1]))
                            items.append(BarcodeItem(
                                type=b_type.upper() if b_type else "EAN13",
                                value=info.strip(),
                                confidence=None,
                                source_image_id=source_image_id,
                                source_image_path=source_image_path,
                                bbox=[x1, y1, x2, y2],
                                timestamp=timestamp,
                                decoder="opencv_barcode"
                            ))
            except Exception:
                pass

        return items

    def cross_validate_with_ocr(
        self,
        barcode_items: List[BarcodeItem],
        ocr_text: str
    ) -> List[BarcodeItem]:
        """
        Cross-validates decoded barcodes against OCR text.
        If OCR contains a GTIN-like sequence (8, 12, 13, 14 digits):
        - Same -> CORROBORATING
        - Different -> EVIDENCE_CONFLICT (flagged for inspector review)
        """
        if not barcode_items:
            return []

        # Find potential barcode/GTIN digit strings in OCR text
        ocr_digits_list = re.findall(r'\b([0-9]{8}|[0-9]{12}|[0-9]{13}|[0-9]{14})\b', ocr_text)

        for item in barcode_items:
            b_val = re.sub(r'[^0-9]', '', item.value)
            if not b_val:
                item.ocr_corroboration = "NO_OCR_BARCODE"
                continue

            if not ocr_digits_list:
                item.ocr_corroboration = "NO_OCR_BARCODE"
                continue

            # Check if any OCR number matches
            if any(b_val == d or b_val in d or d in b_val for d in ocr_digits_list):
                item.ocr_corroboration = "CORROBORATING"
            else:
                # Disagreement between pyzbar and OCR number
                item.ocr_corroboration = "EVIDENCE_CONFLICT"
                item.conflicting_ocr_value = ocr_digits_list[0]

        return barcode_items

    def consolidate_multi_image_barcodes(
        self,
        per_image_barcodes: Dict[str, List[BarcodeItem]]
    ) -> BarcodeInspectionSummary:
        """
        Consolidates barcodes across multiple package views:
        - Same value on multiple images -> consolidated evidence
        - Different values on images -> conflict
        """
        all_items: List[BarcodeItem] = []
        for img_id, items in per_image_barcodes.items():
            all_items.extend(items)

        if not all_items:
            return BarcodeInspectionSummary(detected=False, items=[])

        # Group by decoded value
        distinct_values: Dict[str, List[BarcodeItem]] = {}
        for it in all_items:
            distinct_values.setdefault(it.value.strip(), []).append(it)

        if len(distinct_values) == 1:
            val = list(distinct_values.keys())[0]
            first_item = distinct_values[val][0]
            return BarcodeInspectionSummary(
                detected=True,
                items=all_items,
                has_conflict=False,
                consolidated_value=val,
                barcode_type=first_item.type
            )
        else:
            # Different barcode numbers detected on different panels
            vals = list(distinct_values.keys())
            return BarcodeInspectionSummary(
                detected=True,
                items=all_items,
                has_conflict=True,
                conflict_description=f"Conflicting barcodes detected across images: {' vs '.join(vals)}",
                consolidated_value=vals[0],
                barcode_type=all_items[0].type
            )


barcode_service = BarcodeService()
