import os
import re
import cv2
import time
import shutil
import unicodedata
import numpy as np
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from pydantic import BaseModel

class OCRTextBox(BaseModel):
    text: str
    confidence: float
    bbox: List[int]  # [x1, y1, x2, y2]
    sequence: int
    image_id: Optional[str] = None

class OCRResultData(BaseModel):
    raw_text: str
    mean_confidence: float
    text_boxes: List[OCRTextBox]
    processing_time_ms: float
    engine_used: str
    normalized_text: Optional[str] = ""
    error: Optional[str] = None

def find_tesseract_binary() -> Optional[str]:
    """
    Locates the Tesseract OCR executable across environment variables,
    system PATH, and standard Windows/Unix installation directories.
    """
    cmd_env = os.environ.get("TESSERACT_CMD")
    if cmd_env and os.path.isfile(cmd_env):
        return cmd_env

    which_path = shutil.which("tesseract")
    if which_path:
        return which_path

    # Standard Windows and Unix locations
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        str(Path.home() / "AppData" / "Local" / "Programs" / "Tesseract-OCR" / "tesseract.exe"),
        "/usr/bin/tesseract",
        "/usr/local/bin/tesseract",
        "/opt/homebrew/bin/tesseract",
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None

def is_tesseract_available() -> bool:
    """Checks whether Tesseract OCR is installed, configured, and executable."""
    try:
        import pytesseract
        bin_path = find_tesseract_binary()
        if bin_path:
            pytesseract.pytesseract.tesseract_cmd = bin_path
        ver = pytesseract.get_tesseract_version()
        return ver is not None
    except Exception:
        return False

def normalize_ocr_text(text: str) -> str:
    """
    Normalizes OCR text without altering numbers, prices, dates, or statutory meaning.
    - Cleans redundant horizontal whitespace per line
    - Normalizes Unicode characters (NFKC)
    - Normalizes typographic quotes, dashes, and hyphens
    - Preserves statutory keywords, decimal points, dates, emails, and phone numbers
    """
    if not text:
        return ""
    norm = unicodedata.normalize("NFKC", text)
    # Standardize unicode hyphens/dashes to standard ASCII hyphen
    norm = re.sub(r'[\u2010\u2011\u2012\u2013\u2014\u2015]', '-', norm)
    # Standardize quotes
    norm = re.sub(r'[\u2018\u2019]', "'", norm)
    norm = re.sub(r'[\u201C\u201D]', '"', norm)
    # Line by line whitespace cleanup
    cleaned_lines = []
    for line in norm.splitlines():
        l = re.sub(r'[ \t]+', ' ', line).strip()
        if l:
            cleaned_lines.append(l)
    return "\n".join(cleaned_lines)

def calculate_box_overlap(b1: List[int], b2: List[int]) -> float:
    """Calculates intersection over minimum area between two bounding boxes [x1, y1, x2, y2]."""
    x1 = max(b1[0], b2[0])
    y1 = max(b1[1], b2[1])
    x2 = min(b1[2], b2[2])
    y2 = min(b1[3], b2[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    a1 = max(1, (b1[2] - b1[0]) * (b1[3] - b1[1]))
    a2 = max(1, (b2[2] - b2[0]) * (b2[3] - b2[1]))
    return inter / min(a1, a2)

class BaseOCREngine(ABC):
    @abstractmethod
    def extract_text_boxes(
        self,
        img: np.ndarray,
        orig_shape: Tuple[int, int],
        scale_factors: Tuple[float, float]
    ) -> List[OCRTextBox]:
        """Extracts text regions and bounding boxes from an image."""
        pass

class MorphologicalOpenCVOCREngine(BaseOCREngine):
    """
    Deterministic OpenCV text region segmenter.
    Retained for architectural compatibility. All fabricated declaration text arrays
    and filename heuristics have been permanently removed.
    Returns empty box list because morphological contour detection alone cannot
    read character tokens without an authentic OCR engine.
    """
    def extract_text_boxes(
        self,
        img: np.ndarray,
        orig_shape: Tuple[int, int],
        scale_factors: Tuple[float, float]
    ) -> List[OCRTextBox]:
        return []

class TesseractOCREngine(BaseOCREngine):
    """
    Real Tesseract OCR integration.
    Extracts authentic text lines, token bounding boxes, and per-line confidence scores.
    """
    def __init__(self):
        self._configured = False
        self._init_tesseract()

    def _init_tesseract(self):
        try:
            import pytesseract
            bin_path = find_tesseract_binary()
            if bin_path:
                pytesseract.pytesseract.tesseract_cmd = bin_path
            self._configured = True
        except Exception:
            self._configured = False

    def extract_text_boxes(
        self,
        img: np.ndarray,
        orig_shape: Tuple[int, int],
        scale_factors: Tuple[float, float]
    ) -> List[OCRTextBox]:
        if not self._configured:
            self._init_tesseract()

        try:
            import pytesseract
            from pytesseract import Output
        except ImportError:
            return []

        orig_h, orig_w = orig_shape
        scale_x, scale_y = scale_factors

        try:
            data = pytesseract.image_to_data(img, output_type=Output.DICT)
        except Exception:
            return []

        n_entries = len(data.get("text", []))
        if n_entries == 0:
            return []

        # Group valid tokens into lines by (page_num, block_num, par_num, line_num)
        lines_dict: Dict[Tuple[int, int, int, int], List[Dict[str, Any]]] = {}
        for i in range(n_entries):
            raw_t = data["text"][i]
            if raw_t is None:
                continue
            text = str(raw_t).strip()
            conf = float(data["conf"][i])
            # Keep tokens with non-empty text and non-negative confidence
            if text and conf >= 0:
                key = (
                    int(data["page_num"][i]),
                    int(data["block_num"][i]),
                    int(data["par_num"][i]),
                    int(data["line_num"][i])
                )
                if key not in lines_dict:
                    lines_dict[key] = []
                lines_dict[key].append({
                    "text": text,
                    "conf": conf,
                    "left": int(data["left"][i]),
                    "top": int(data["top"][i]),
                    "width": int(data["width"][i]),
                    "height": int(data["height"][i]),
                })

        boxes: List[OCRTextBox] = []
        seq = 1

        # Sort lines top-to-bottom, left-to-right
        sorted_keys = sorted(lines_dict.keys(), key=lambda k: (
            min(t["top"] for t in lines_dict[k]),
            min(t["left"] for t in lines_dict[k])
        ))

        for key in sorted_keys:
            tokens = lines_dict[key]
            line_text = " ".join(t["text"] for t in tokens).strip()
            if not line_text:
                continue

            # Bounding box in preprocessed image coordinates
            prep_x1 = min(t["left"] for t in tokens)
            prep_y1 = min(t["top"] for t in tokens)
            prep_x2 = max(t["left"] + t["width"] for t in tokens)
            prep_y2 = max(t["top"] + t["height"] for t in tokens)

            # Map back to original image coordinate frame
            orig_x1 = int(round(prep_x1 / scale_x))
            orig_y1 = int(round(prep_y1 / scale_y))
            orig_x2 = int(round(prep_x2 / scale_x))
            orig_y2 = int(round(prep_y2 / scale_y))

            # Clamp coordinates to original image bounds
            orig_x1 = max(0, min(orig_w, orig_x1))
            orig_y1 = max(0, min(orig_h, orig_y1))
            orig_x2 = max(orig_x1, min(orig_w, orig_x2))
            orig_y2 = max(orig_y1, min(orig_h, orig_y2))

            # Authentic mean confidence of tokens in this line (0.0 to 1.0)
            avg_conf = sum(t["conf"] for t in tokens) / len(tokens)
            norm_conf = round(max(0.0, min(1.0, avg_conf / 100.0)), 2)

            boxes.append(OCRTextBox(
                text=line_text,
                confidence=norm_conf,
                bbox=[orig_x1, orig_y1, orig_x2, orig_y2],
                sequence=seq
            ))
            seq += 1

        return boxes

class ModularOCRService:
    """
    Modular OCR coordinator.
    Validates images, executes intelligent in-memory preprocessing variants,
    runs real Tesseract OCR, aggregates and deduplicates bounding boxes,
    and returns standardized structured OCR outputs without fabricating any text.
    """
    def __init__(self):
        self.tesseract_engine = TesseractOCREngine()
        self.morph_engine = MorphologicalOpenCVOCREngine()

    def _prepare_variants(self, img: np.ndarray) -> List[Tuple[str, np.ndarray, float, float]]:
        """
        Creates in-memory preprocessing variants:
        A. Grayscale + Otsu thresholding
        B. Grayscale + CLAHE (Contrast Limited Adaptive Histogram Equalization)
        C. Grayscale + Adaptive Gaussian thresholding
        D. Grayscale + Inverted Otsu (for light text on dark packaging)
        Returns list of (variant_name, image_array, scale_x, scale_y).
        Original image is untouched and no temporary files are written to disk.
        """
        orig_h, orig_w = img.shape[:2]

        # Determine upscale factor if image is small
        scale = 1.0
        if orig_w < 600 or orig_h < 400:
            scale = max(1.5, min(3.0, 800.0 / max(orig_w, orig_h, 1)))

        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()

        if scale != 1.0:
            scaled = cv2.resize(gray, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        else:
            scaled = gray

        variants: List[Tuple[str, np.ndarray, float, float]] = []

        # 1. Otsu Thresholding (Primary)
        _, otsu = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(("otsu", otsu, scale, scale))

        # 2. CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cl = clahe.apply(scaled)
        variants.append(("clahe", cl, scale, scale))

        # 3. Adaptive Thresholding
        adaptive = cv2.adaptiveThreshold(
            scaled, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 10
        )
        variants.append(("adaptive", adaptive, scale, scale))

        # 4. Inverted Otsu
        inverted = cv2.bitwise_not(otsu)
        variants.append(("inverted_otsu", inverted, scale, scale))

        return variants

    def _deduplicate_boxes(self, boxes: List[OCRTextBox]) -> List[OCRTextBox]:
        """
        Deduplicates text boxes across preprocessing variants using spatial overlap
        and normalized text similarity, preferring higher-confidence readings.
        """
        if not boxes:
            return []

        sorted_boxes = sorted(boxes, key=lambda b: b.confidence, reverse=True)
        unique_boxes: List[OCRTextBox] = []

        for candidate in sorted_boxes:
            duplicate = False
            for existing in unique_boxes:
                overlap = calculate_box_overlap(candidate.bbox, existing.bbox)
                if overlap > 0.60:
                    c_clean = re.sub(r'\W+', '', candidate.text.lower())
                    e_clean = re.sub(r'\W+', '', existing.text.lower())
                    if c_clean in e_clean or e_clean in c_clean or not c_clean or not e_clean:
                        duplicate = True
                        break
            if not duplicate:
                unique_boxes.append(candidate)

        # Sort top-to-bottom
        unique_boxes.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
        for idx, b in enumerate(unique_boxes):
            b.sequence = idx + 1
        return unique_boxes

    def _try_rotation_orientations(
        self,
        img: np.ndarray,
        orig_h: int,
        orig_w: int
    ) -> List[OCRTextBox]:
        """
        Attempts limited rotations (90, 180, 270) when standard orientation yields no text.
        Maps recovered bounding boxes back to the original unrotated image coordinates.
        """
        rotations = [
            (90, cv2.ROTATE_90_CLOCKWISE),
            (180, cv2.ROTATE_180),
            (270, cv2.ROTATE_90_COUNTERCLOCKWISE)
        ]

        best_boxes: List[OCRTextBox] = []
        best_conf = 0.0

        for angle, rot_code in rotations:
            rot_img = cv2.rotate(img, rot_code)
            r_h, r_w = rot_img.shape[:2]
            variants = self._prepare_variants(rot_img)
            _, v_img, s_x, s_y = variants[0]
            r_boxes = self.tesseract_engine.extract_text_boxes(v_img, (r_h, r_w), (s_x, s_y))
            if r_boxes:
                r_conf = float(np.mean([b.confidence for b in r_boxes]))
                if r_conf > best_conf and len(r_boxes) >= 2:
                    best_conf = r_conf
                    # Map rotated boxes back to original coordinate system
                    mapped_boxes = []
                    for b in r_boxes:
                        rx1, ry1, rx2, ry2 = b.bbox
                        if angle == 90:
                            ox1 = ry1
                            ox2 = ry2
                            oy1 = orig_h - rx2
                            oy2 = orig_h - rx1
                        elif angle == 180:
                            ox1 = orig_w - rx2
                            ox2 = orig_w - rx1
                            oy1 = orig_h - ry2
                            oy2 = orig_h - ry1
                        else:  # 270
                            ox1 = orig_w - ry2
                            ox2 = orig_w - rx1
                            oy1 = rx1
                            oy2 = rx2

                        ox1 = max(0, min(orig_w, ox1))
                        oy1 = max(0, min(orig_h, oy1))
                        ox2 = max(ox1, min(orig_w, ox2))
                        oy2 = max(oy1, min(orig_h, oy2))

                        b.bbox = [ox1, oy1, ox2, oy2]
                        mapped_boxes.append(b)
                    best_boxes = mapped_boxes
                    break  # Found high-quality rotated text

        return best_boxes

    def process_image(self, image_path: str, image_id: Optional[str] = None) -> OCRResultData:
        start_time = time.time()

        # 1. Check Tesseract availability - NEVER fabricate text if unavailable
        if not is_tesseract_available():
            elapsed_ms = (time.time() - start_time) * 1000.0
            return OCRResultData(
                raw_text="",
                normalized_text="",
                mean_confidence=0.0,
                text_boxes=[],
                processing_time_ms=round(elapsed_ms, 2),
                engine_used="tesseract_unavailable",
                error="Tesseract OCR engine is unavailable"
            )

        # 2. Validate file existence
        if not os.path.exists(image_path):
            elapsed_ms = (time.time() - start_time) * 1000.0
            return OCRResultData(
                raw_text="",
                normalized_text="",
                mean_confidence=0.0,
                text_boxes=[],
                processing_time_ms=round(elapsed_ms, 2),
                engine_used="error",
                error=f"File not found: {image_path}"
            )

        # 3. Load image safely
        try:
            img = cv2.imread(image_path)
        except Exception as e:
            img = None

        if img is None or img.size == 0:
            elapsed_ms = (time.time() - start_time) * 1000.0
            return OCRResultData(
                raw_text="",
                normalized_text="",
                mean_confidence=0.0,
                text_boxes=[],
                processing_time_ms=round(elapsed_ms, 2),
                engine_used="error",
                error=f"Could not load or decode image at {image_path}"
            )

        orig_h, orig_w = img.shape[:2]

        # 4. Inspect resolution: detect extremely small images
        if orig_h < 30 or orig_w < 30:
            elapsed_ms = (time.time() - start_time) * 1000.0
            return OCRResultData(
                raw_text="",
                normalized_text="",
                mean_confidence=0.0,
                text_boxes=[],
                processing_time_ms=round(elapsed_ms, 2),
                engine_used="Tesseract",
                error="Image resolution too low for readable text"
            )

        # 5. Preprocessing variants (in-memory only, original image untouched)
        variants = self._prepare_variants(img)
        all_boxes: List[OCRTextBox] = []

        # Run primary variant (Otsu)
        primary_name, primary_img, scale_x, scale_y = variants[0]
        primary_boxes = self.tesseract_engine.extract_text_boxes(
            primary_img, (orig_h, orig_w), (scale_x, scale_y)
        )

        # Intelligent variant selection:
        # If primary yielded good boxes with strong confidence, use it directly.
        # Otherwise, run additional variants (CLAHE, Adaptive, Inverted) and deduplicate.
        if len(primary_boxes) >= 4 and np.mean([b.confidence for b in primary_boxes]) >= 0.70:
            all_boxes = primary_boxes
        else:
            all_boxes.extend(primary_boxes)
            for v_name, v_img, s_x, s_y in variants[1:]:
                v_boxes = self.tesseract_engine.extract_text_boxes(
                    v_img, (orig_h, orig_w), (s_x, s_y)
                )
                all_boxes.extend(v_boxes)
            all_boxes = self._deduplicate_boxes(all_boxes)

        # 6. Orientation fallback if standard orientation produced no text
        if len(all_boxes) == 0:
            rot_boxes = self._try_rotation_orientations(img, orig_h, orig_w)
            if rot_boxes:
                all_boxes = rot_boxes

        # 7. Preserve source image ID
        for b in all_boxes:
            b.image_id = image_id

        # 8. Calculate authentic mean confidence
        if all_boxes:
            mean_conf = float(np.mean([b.confidence for b in all_boxes]))
        else:
            mean_conf = 0.0

        # 9. Format raw and normalized text
        raw_text = "\n".join([b.text for b in all_boxes if b.text.strip()])
        norm_text = normalize_ocr_text(raw_text)

        elapsed_ms = (time.time() - start_time) * 1000.0

        return OCRResultData(
            raw_text=raw_text,
            normalized_text=norm_text,
            mean_confidence=round(mean_conf, 2),
            text_boxes=all_boxes,
            processing_time_ms=round(elapsed_ms, 2),
            engine_used="Tesseract"
        )

ocr_service = ModularOCRService()
