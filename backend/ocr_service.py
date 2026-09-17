import os
import re
import cv2
import time
import shutil
import logging
import unicodedata
import subprocess
import numpy as np
from datetime import datetime, timezone
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from pydantic import BaseModel

from backend.config import settings

logger = logging.getLogger("backend.ocr_service")

class OCRTextBox(BaseModel):
    text: str
    confidence: float
    bbox: List[int]  # [x1, y1, x2, y2]
    sequence: int = 1
    image_id: Optional[str] = None
    engine: Optional[str] = None
    timestamp: Optional[str] = None

class OCRResultData(BaseModel):
    raw_text: str
    mean_confidence: float
    text_boxes: List[OCRTextBox]
    processing_time_ms: float
    engine_used: str
    normalized_text: Optional[str] = ""
    error: Optional[str] = None
    ocr_status: str = "OCR_SUCCESS"  # 'OCR_SUCCESS', 'OCR_UNAVAILABLE', 'OCR_FAILED'
    timestamp: Optional[str] = None

def find_tesseract_binary() -> Optional[str]:
    """
    Locates the Tesseract OCR executable across environment variables,
    system PATH, and standard Windows/Unix installation directories.
    """
    cmd_env = getattr(settings, "TESSERACT_CMD", None) or os.environ.get("TESSERACT_CMD")
    if cmd_env and os.path.isfile(cmd_env):
        return cmd_env

    which_path = shutil.which("tesseract")
    if which_path:
        return which_path

    # Standard Windows and Unix locations
    candidates = [
        r"C:\Program Files\PDF24\tesseract\tesseract.exe",
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

def is_paddleocr_available() -> bool:
    """Checks whether PaddleOCR and PaddlePaddle are installed and functional."""
    try:
        import paddle
        from paddleocr import PaddleOCR
        return True
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
    def extract_text_boxes(self, *args, **kwargs) -> List[OCRTextBox]:
        """Extracts text regions and bounding boxes from an image."""
        pass

class MorphologicalOpenCVOCREngine(BaseOCREngine):
    """
    Deterministic OpenCV text region segmenter.
    Identifies high-contrast horizontal text lines and calculates exact bounding boxes [x1, y1, x2, y2].
    CRITICAL STATUTORY INVARIANT:
    OpenCV morphological processing alone detects geometric regions, but NEVER manufactures
    or hallucinates character text. Text is strictly empty when no OCR engine runs.
    """
    def extract_text_boxes(
        self,
        image_input: Any,
        orig_shape: Optional[Tuple[int, int]] = None,
        scale_factors: Tuple[float, float] = (1.0, 1.0)
    ) -> List[OCRTextBox]:
        if isinstance(image_input, str):
            img = cv2.imread(image_input)
            if img is None:
                return []
        elif isinstance(image_input, np.ndarray):
            img = image_input
        else:
            return []

        height, width = img.shape[:2]
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img

        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 8
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 3))
        dilated = cv2.dilate(thresh, kernel, iterations=1)
        contours, _ = cv2.findContours(dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

        raw_boxes = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if 40 < w < (width * 0.95) and 8 < h < (height * 0.25):
                raw_boxes.append([x, y, x + w, y + h])

        boxes = []
        for b in sorted(raw_boxes, key=lambda x: x[1]):
            if not any(abs(b[1] - ex[1]) < 12 and abs(b[0] - ex[0]) < 20 for ex in boxes):
                boxes.append(b)

        boxes.sort(key=lambda b: b[1])

        results: List[OCRTextBox] = []
        for idx, bbox in enumerate(boxes):
            results.append(OCRTextBox(
                text="",
                confidence=0.0,
                bbox=bbox,
                sequence=idx + 1
            ))
        return results

class TesseractOCREngine(BaseOCREngine):
    """
    Production Pytesseract OCR engine with automated binary auto-detection.
    Supports configurable TESSERACT_CMD, PATH discovery, and Windows/Linux standard paths.
    """
    def __init__(self):
        self.cmd_path: Optional[str] = None
        self._detect_tesseract()

    def _detect_tesseract(self):
        self.cmd_path = find_tesseract_binary()
        if self.cmd_path and os.path.isfile(self.cmd_path):
            try:
                import pytesseract
                pytesseract.pytesseract.tesseract_cmd = self.cmd_path
            except Exception:
                pass

        # Configure TESSDATA_PREFIX
        tessdata_dir = getattr(settings, "TESSDATA_PREFIX", None) or os.environ.get("TESSDATA_PREFIX")
        if not tessdata_dir:
            local_tessdata = Path(__file__).resolve().parent / "tessdata"
            if local_tessdata.exists() and (local_tessdata / "eng.traineddata").exists():
                tessdata_dir = str(local_tessdata)
        if tessdata_dir and os.path.isdir(tessdata_dir):
            os.environ["TESSDATA_PREFIX"] = tessdata_dir

    def is_available(self) -> bool:
        if not self.cmd_path or not os.path.isfile(self.cmd_path):
            self._detect_tesseract()
        return is_tesseract_available()

    def extract_text_boxes(
        self,
        image_input: Any,
        orig_shape: Optional[Tuple[int, int]] = None,
        scale_factors: Tuple[float, float] = (1.0, 1.0)
    ) -> List[OCRTextBox]:
        if not self.is_available():
            return []

        try:
            import pytesseract
            from pytesseract import Output
        except ImportError:
            return []

        if isinstance(image_input, str):
            img = cv2.imread(image_input)
            if img is None:
                return []
            orig_h, orig_w = img.shape[:2]
            scale_x, scale_y = 1.0, 1.0
        elif isinstance(image_input, np.ndarray):
            img = image_input
            if orig_shape:
                orig_h, orig_w = orig_shape
            else:
                orig_h, orig_w = img.shape[:2]
            scale_x, scale_y = scale_factors
        else:
            return []

        try:
            data = pytesseract.image_to_data(img, output_type=Output.DICT)
        except Exception:
            return []

        n_entries = len(data.get("text", []))
        if n_entries == 0:
            return []

        lines_dict: Dict[Tuple[int, int, int], List[Dict[str, Any]]] = {}
        for i in range(n_entries):
            raw_t = data["text"][i]
            if raw_t is None:
                continue
            text = str(raw_t).strip()
            conf = float(data["conf"][i])
            if text and conf > 0:
                key = (
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

        sorted_keys = sorted(lines_dict.keys(), key=lambda k: (
            min(t["top"] for t in lines_dict[k]),
            min(t["left"] for t in lines_dict[k])
        ))

        for key in sorted_keys:
            tokens = lines_dict[key]
            line_text = " ".join(t["text"] for t in tokens).strip()
            if not line_text:
                continue

            prep_x1 = min(t["left"] for t in tokens)
            prep_y1 = min(t["top"] for t in tokens)
            prep_x2 = max(t["left"] + t["width"] for t in tokens)
            prep_y2 = max(t["top"] + t["height"] for t in tokens)

            orig_x1 = int(round(prep_x1 / scale_x))
            orig_y1 = int(round(prep_y1 / scale_y))
            orig_x2 = int(round(prep_x2 / scale_x))
            orig_y2 = int(round(prep_y2 / scale_y))

            orig_x1 = max(0, min(orig_w, orig_x1))
            orig_y1 = max(0, min(orig_h, orig_y1))
            orig_x2 = max(orig_x1, min(orig_w, orig_x2))
            orig_y2 = max(orig_y1, min(orig_h, orig_y2))

            avg_conf = sum(t["conf"] for t in tokens) / len(tokens)
            norm_conf = round(max(0.0, min(1.0, avg_conf / 100.0)), 2)

            now_iso = datetime.now(timezone.utc).isoformat()
            boxes.append(OCRTextBox(
                text=line_text,
                confidence=norm_conf,
                bbox=[orig_x1, orig_y1, orig_x2, orig_y2],
                sequence=seq,
                engine="tesseract",
                timestamp=now_iso
            ))
            seq += 1

        return boxes

class PaddleOCREngine(BaseOCREngine):
    """
    Production PaddleOCR 3.x engine with lazy loading and singleton instance.
    Supports CPU inference with textline orientation classification and multi-language models.
    Converts 4-point polygon bounding boxes to normalized [x1, y1, x2, y2] coordinates.

    PaddleOCR 3.x API compatibility notes:
    - PaddleOCR 3.x removed: use_angle_cls, show_log parameters from __init__
    - PaddleOCR 3.x uses: use_textline_orientation=True instead of use_angle_cls
    - PaddleOCR 3.x primary call: predict(img) returning list of result dicts
    - Backward-compat: ocr(img) without cls parameter is accepted in 3.x
    - Result format: Both predict() and ocr() return [[poly, (text, conf)], ...] per page

    CRITICAL STATUTORY INVARIANT:
    Never manufactures or hallucinates character text. Derives text strictly from model
    inference on actual image pixels. Returns empty list on any inference failure.
    """
    _instance: Optional[Any] = None
    _init_error: Optional[str] = None  # Tracks initialization failure reason

    @classmethod
    def reset_engine(cls):
        """Resets engine instance and error state to allow recovery."""
        cls._instance = None
        cls._init_error = None

    def __init__(self):
        self._enabled = getattr(settings, "PADDLE_OCR_ENABLED", True)
        self._use_angle_cls = getattr(settings, "PADDLE_OCR_USE_ANGLE_CLS", True)
        self._lang = getattr(settings, "PADDLE_OCR_LANG", "en")
        self._ocr_version = getattr(settings, "PADDLE_OCR_VERSION", "PP-OCRv4")

    def is_available(self) -> bool:
        if not getattr(settings, "PADDLE_OCR_ENABLED", True):
            return False
        if PaddleOCREngine._init_error is not None:
            # A previous initialization attempt failed — do not retry per process.
            return False
        return is_paddleocr_available()

    def _get_ocr_instance(self):
        """
        Lazy-initializes PaddleOCR singleton using PaddleOCR 3.x API.
        Falls back through multiple initialization strategies in order:
          1. PaddleOCR 3.x with mobile model version: PaddleOCR(ocr_version='PP-OCRv4', lang=..., use_textline_orientation=...)
          2. PaddleOCR 3.x standard: PaddleOCR(lang=..., use_textline_orientation=...)
          3. PaddleOCR 2.x legacy: PaddleOCR(lang=..., use_angle_cls=...)
          4. Minimal: PaddleOCR(lang=...)
        Sets _init_error on permanent failure to prevent repeated initialization attempts.
        """
        if PaddleOCREngine._instance is not None:
            logger.info("[PADDLE_SINGLETON] Hit existing PaddleOCR instance (no re-initialization needed)")
            return PaddleOCREngine._instance

        if PaddleOCREngine._init_error is not None:
            logger.warning(f"[PADDLE_SINGLETON] Skipping init due to previous failure: {PaddleOCREngine._init_error}")
            return None

        t_init_start = time.time()
        logger.info(f"[PADDLE_INIT_START] Starting PaddleOCR model load (lang={self._lang}, version={self._ocr_version})")
        from paddleocr import PaddleOCR

        # Strategy 1: PaddleOCR 3.7+ native API with mobile model version and CPU OneDNN workaround
        try:
            PaddleOCREngine._instance = PaddleOCR(
                ocr_version=self._ocr_version,
                lang=self._lang,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=self._use_angle_cls,
                enable_mkldnn=False,
            )
            init_sec = time.time() - t_init_start
            logger.info(f"[PADDLE_INIT_END] PaddleOCR Strategy 1 ({self._ocr_version}) initialized successfully in {init_sec:.2f}s")
            return PaddleOCREngine._instance
        except (TypeError, ValueError, Exception) as e1:
            logger.debug(f"[PADDLE_INIT] Strategy 1 fallback: {e1}")

        # Strategy 2: PaddleOCR 3.x native API (use_textline_orientation replaces use_angle_cls)
        try:
            PaddleOCREngine._instance = PaddleOCR(
                lang=self._lang,
                use_textline_orientation=self._use_angle_cls
            )
            init_sec = time.time() - t_init_start
            logger.info(f"[PADDLE_INIT_END] PaddleOCR Strategy 2 initialized successfully in {init_sec:.2f}s")
            return PaddleOCREngine._instance
        except (TypeError, ValueError, Exception) as e2:
            logger.debug(f"[PADDLE_INIT] Strategy 2 fallback: {e2}")

        # Strategy 3: PaddleOCR 2.x legacy API
        try:
            PaddleOCREngine._instance = PaddleOCR(
                use_angle_cls=self._use_angle_cls,
                lang=self._lang
            )
            init_sec = time.time() - t_init_start
            logger.info(f"[PADDLE_INIT_END] PaddleOCR Strategy 3 initialized successfully in {init_sec:.2f}s")
            return PaddleOCREngine._instance
        except (TypeError, ValueError, Exception) as e3:
            logger.debug(f"[PADDLE_INIT] Strategy 3 fallback: {e3}")

        # Strategy 4: Absolute minimal initialization
        try:
            PaddleOCREngine._instance = PaddleOCR(lang=self._lang)
            init_sec = time.time() - t_init_start
            logger.info(f"[PADDLE_INIT_END] PaddleOCR Strategy 4 initialized successfully in {init_sec:.2f}s")
            return PaddleOCREngine._instance
        except Exception as e:
            init_sec = time.time() - t_init_start
            PaddleOCREngine._init_error = str(e)
            logger.error(f"[PADDLE_INIT_FAILED] All strategies failed after {init_sec:.2f}s: {e}")
            return None

    def _parse_paddle_result_page(self, page_results: Any, orig_w: int, orig_h: int,
                                   scale_x: float, scale_y: float) -> List[OCRTextBox]:
        """
        Parses a single page result from PaddleOCR (both 2.x and 3.x format).
        Expected input: list of [[poly_4pt], (text, conf)] items.
        Output: list of OCRTextBox with [x1, y1, x2, y2] bounding boxes in original image coordinates.
        """
        if not isinstance(page_results, list):
            return []

        boxes: List[OCRTextBox] = []
        seq = 1

        for line in page_results:
            if not line or not isinstance(line, (list, tuple)) or len(line) < 2:
                continue

            poly = line[0]
            text_conf = line[1]

            if not isinstance(text_conf, (list, tuple)) or len(text_conf) < 2:
                continue

            raw_text, raw_conf = text_conf[0], text_conf[1]
            if raw_text is None:
                continue
            text = str(raw_text).strip()
            if not text:
                continue

            try:
                conf = float(raw_conf)
                norm_conf = round(max(0.0, min(1.0, conf)), 2)
            except (ValueError, TypeError):
                norm_conf = 0.0

            # Convert 4-point polygon [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] to [xmin,ymin,xmax,ymax]
            try:
                xs = [pt[0] for pt in poly]
                ys = [pt[1] for pt in poly]
                prep_x1 = min(xs)
                prep_y1 = min(ys)
                prep_x2 = max(xs)
                prep_y2 = max(ys)
            except Exception:
                continue

            # Scale back to original image coordinates
            orig_x1 = int(round(prep_x1 / scale_x))
            orig_y1 = int(round(prep_y1 / scale_y))
            orig_x2 = int(round(prep_x2 / scale_x))
            orig_y2 = int(round(prep_y2 / scale_y))

            # Clamp to image bounds
            orig_x1 = max(0, min(orig_w, orig_x1))
            orig_y1 = max(0, min(orig_h, orig_y1))
            orig_x2 = max(orig_x1, min(orig_w, orig_x2))
            orig_y2 = max(orig_y1, min(orig_h, orig_y2))

            boxes.append(OCRTextBox(
                text=text,
                confidence=norm_conf,
                bbox=[orig_x1, orig_y1, orig_x2, orig_y2],
                sequence=seq
            ))
            seq += 1

        return boxes

    def extract_text_boxes(
        self,
        image_input: Any,
        orig_shape: Optional[Tuple[int, int]] = None,
        scale_factors: Tuple[float, float] = (1.0, 1.0)
    ) -> List[OCRTextBox]:
        if not self.is_available():
            return []

        if isinstance(image_input, str):
            img = cv2.imread(image_input)
            if img is None:
                return []
            orig_h, orig_w = img.shape[:2]
            scale_x, scale_y = 1.0, 1.0
        elif isinstance(image_input, np.ndarray):
            img = image_input
            if orig_shape:
                orig_h, orig_w = orig_shape
            else:
                orig_h, orig_w = img.shape[:2]
            scale_x, scale_y = scale_factors
        else:
            return []

        ocr = self._get_ocr_instance()
        if ocr is None:
            return []

        raw_results = None
        now_iso = datetime.now(timezone.utc).isoformat()

        # Attempt 1: PaddleOCR 3.x primary API — predict()
        try:
            predict_result = ocr.predict(img)
            if predict_result:
                first = predict_result[0]
                # Check for PaddleX 3.7+ OCRResult format
                if hasattr(first, "__getitem__") and "rec_texts" in first and "rec_boxes" in first:
                    rec_texts = first["rec_texts"]
                    rec_scores = first["rec_scores"]
                    rec_boxes = first["rec_boxes"]
                    boxes: List[OCRTextBox] = []
                    for idx, (t, s, b) in enumerate(zip(rec_texts, rec_scores, rec_boxes)):
                        t_str = str(t).strip()
                        if not t_str:
                            continue
                        conf = round(max(0.0, min(1.0, float(s))), 2)
                        x1 = max(0, min(orig_w, int(round(b[0] / scale_x))))
                        y1 = max(0, min(orig_h, int(round(b[1] / scale_y))))
                        x2 = max(x1, min(orig_w, int(round(b[2] / scale_x))))
                        y2 = max(y1, min(orig_h, int(round(b[3] / scale_y))))
                        boxes.append(OCRTextBox(
                            text=t_str,
                            confidence=conf,
                            bbox=[x1, y1, x2, y2],
                            sequence=idx + 1,
                            engine="paddleocr",
                            timestamp=now_iso
                        ))
                    boxes.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
                    for idx, b in enumerate(boxes):
                        b.sequence = idx + 1
                    return boxes

                elif isinstance(first, dict):
                    rec_texts = first.get("rec_texts", []) or first.get("text", [])
                    rec_scores = first.get("rec_scores", []) or first.get("score", [])
                    det_polys = first.get("det_polys", []) or first.get("boxes", [])
                    if rec_texts and det_polys:
                        classic_lines = []
                        for i, poly in enumerate(det_polys):
                            text = rec_texts[i] if i < len(rec_texts) else ""
                            conf = rec_scores[i] if i < len(rec_scores) else 0.0
                            classic_lines.append([poly, (text, conf)])
                        raw_results = [classic_lines]
                elif isinstance(first, list):
                    raw_results = predict_result
        except Exception:
            raw_results = None

        # Attempt 2: PaddleOCR backward-compat ocr() method (3.x: no cls parameter)
        if not raw_results:
            try:
                result = ocr.ocr(img)
                if result:
                    raw_results = result
            except Exception as e:
                ocr_exc = e
                raw_results = None

        # If both inference paths failed with exceptions, return empty so ModularOCRService
        # falls back cleanly to Tesseract for this image. Do not permanently brick the engine
        # with _init_error, allowing recovery on subsequent images (Critical Fix #13).
        if not raw_results:
            return []

        # Extract page 0 results (one image = one page)
        page_results = (
            raw_results[0]
            if isinstance(raw_results, list) and len(raw_results) > 0 and raw_results[0] is not None
            else raw_results
        )

        boxes = self._parse_paddle_result_page(page_results, orig_w, orig_h, scale_x, scale_y)
        now_iso = datetime.now(timezone.utc).isoformat()
        for b in boxes:
            b.engine = "paddleocr"
            b.timestamp = now_iso

        boxes.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
        for idx, b in enumerate(boxes):
            b.sequence = idx + 1

        return boxes

class ModularOCRService:
    """
    Modular OCR coordinator.
    Validates images, coordinates PaddleOCR as primary engine with Tesseract OCR fallback,
    aggregates and deduplicates bounding boxes, and returns standardized structured OCR outputs
    without fabricating any character text.
    """
    def __init__(self):
        self.paddle_engine = PaddleOCREngine()
        self.tesseract_engine = TesseractOCREngine()
        self.morph_engine = MorphologicalOpenCVOCREngine()

    def warmup_inference(self) -> None:
        """
        Runs a tiny synthetic image through PaddleOCR to amortize JIT/kernel-compilation cost
        before the first real inspection request. This ensures subsequent requests run at warm
        (~15-20s) rather than cold (~70s) inference speed.

        Uses a 100x50 white image generated entirely in memory — no disk I/O, no file writes.
        Only calls the PaddleOCR predict() path; does NOT run Tesseract, extraction, or any
        business logic. Safe to call at server startup in a background thread.
        """
        if not self.paddle_engine.is_available():
            logger.info("[OCR_WARMUP_SKIP] PaddleOCR not available, skipping warmup")
            return
        try:
            t0 = time.time()
            logger.info("[OCR_WARMUP_START] Running synthetic warmup inference to amortize JIT cost")
            ocr = self.paddle_engine._get_ocr_instance()
            if ocr is None:
                logger.warning("[OCR_WARMUP_SKIP] PaddleOCR instance could not be obtained")
                return
            # Create a minimal 100x50 pure-white BGR image in memory (no disk I/O)
            dummy_img = np.full((50, 100, 3), 255, dtype=np.uint8)
            # Run inference — result may be empty (no text), which is correct and expected
            try:
                ocr.predict(dummy_img)
            except Exception:
                try:
                    ocr.ocr(dummy_img)
                except Exception:
                    pass  # Warmup failure is non-fatal; real requests will handle their own errors
            elapsed = time.time() - t0
            logger.info(f"[OCR_WARMUP_COMPLETE] PaddleOCR JIT warmup finished in {elapsed:.2f}s")
        except Exception as e:
            logger.warning(f"[OCR_WARMUP_ERROR] Warmup raised unexpected error (non-fatal): {e}")

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
                    break

        return best_boxes

    def process_image(self, image_path: str, image_id: Optional[str] = None) -> OCRResultData:
        start_time = time.time()

        # 1. Validate file existence
        if not os.path.exists(image_path):
            elapsed_ms = (time.time() - start_time) * 1000.0
            return OCRResultData(
                raw_text="",
                normalized_text="",
                mean_confidence=0.0,
                text_boxes=[],
                processing_time_ms=round(elapsed_ms, 2),
                engine_used="error",
                error=f"File not found: {image_path}",
                ocr_status="OCR_FAILED"
            )

        # 2. Load image safely
        t_decode_start = time.time()
        try:
            img = cv2.imread(image_path)
        except Exception:
            img = None
        t_decode = time.time() - t_decode_start

        if img is None or img.size == 0:
            elapsed_ms = (time.time() - start_time) * 1000.0
            return OCRResultData(
                raw_text="",
                normalized_text="",
                mean_confidence=0.0,
                text_boxes=[],
                processing_time_ms=round(elapsed_ms, 2),
                engine_used="error",
                error=f"Could not load or decode image at {image_path}",
                ocr_status="OCR_FAILED"
            )

        orig_h, orig_w = img.shape[:2]
        filesize = os.path.getsize(image_path) if os.path.exists(image_path) else 0

        # Safe maximum resolution cap for CPU OCR inference to avoid multi-minute stalls
        t_resize_start = time.time()
        max_dim = getattr(settings, "MAX_OCR_DIMENSION", 1024)
        if max(orig_h, orig_w) > max_dim:
            scale = float(max_dim) / float(max(orig_h, orig_w))
            proc_w = int(round(orig_w * scale))
            proc_h = int(round(orig_h * scale))
            proc_img = cv2.resize(img, (proc_w, proc_h), interpolation=cv2.INTER_AREA)
            scale_factors = (proc_w / float(orig_w), proc_h / float(orig_h))
        else:
            proc_img = img
            proc_w, proc_h = orig_w, orig_h
            scale_factors = (1.0, 1.0)
        t_resize = time.time() - t_resize_start

        filename = os.path.basename(image_path)
        logger.info(
            f"[OCR_IMAGE_METRICS] filename={filename} image_id={image_id} filesize={filesize}B "
            f"decoded_dimensions={orig_w}x{orig_h} processed_dimensions={proc_w}x{proc_h} "
            f"scale={scale_factors[0]:.4f} decode_time={t_decode:.3f}s resize_time={t_resize:.3f}s"
        )

        # 3. Inspect resolution: detect extremely small images
        if orig_h < 30 or orig_w < 30:
            elapsed_ms = (time.time() - start_time) * 1000.0
            return OCRResultData(
                raw_text="",
                normalized_text="",
                mean_confidence=0.0,
                text_boxes=[],
                processing_time_ms=round(elapsed_ms, 2),
                engine_used="error",
                error="Image resolution too low for readable text",
                ocr_status="OCR_FAILED"
            )

        # 4. Check engine availability
        preferred_engine = getattr(settings, "OCR_ENGINE", "auto").lower()
        paddle_available = self.paddle_engine.is_available()
        tesseract_available = is_tesseract_available() and self.tesseract_engine.is_available()

        if not paddle_available and not tesseract_available:
            elapsed_ms = (time.time() - start_time) * 1000.0
            return OCRResultData(
                raw_text="",
                normalized_text="",
                mean_confidence=0.0,
                text_boxes=[],
                processing_time_ms=round(elapsed_ms, 2),
                engine_used="tesseract_unavailable" if preferred_engine == "tesseract" else "ocr_unavailable",
                error="No OCR engine is available (PaddleOCR and Tesseract are unavailable)",
                ocr_status="OCR_UNAVAILABLE"
            )

        all_boxes: List[OCRTextBox] = []
        engine_used = ""

        # 5. Primary Engine: PaddleOCR (when preferred or auto)
        if preferred_engine in ("auto", "paddleocr") and paddle_available:
            t_paddle_0 = time.time()
            try:
                paddle_boxes = self.paddle_engine.extract_text_boxes(
                    proc_img, orig_shape=(orig_h, orig_w), scale_factors=scale_factors
                )
                paddle_dur = time.time() - t_paddle_0
                if paddle_boxes:
                    all_boxes = paddle_boxes
                    engine_used = "PaddleOCR"
                    logger.info(
                        f"[OCR_PADDLE_SUCCESS] image_id={image_id} filename={filename} "
                        f"boxes={len(all_boxes)} duration={paddle_dur:.2f}s"
                    )
                else:
                    logger.info(
                        f"[OCR_PADDLE_EMPTY] image_id={image_id} filename={filename} "
                        f"duration={paddle_dur:.2f}s - falling back to Tesseract"
                    )
            except Exception as pe:
                paddle_dur = time.time() - t_paddle_0
                logger.warning(
                    f"[OCR_PADDLE_ERROR] image_id={image_id} filename={filename} "
                    f"duration={paddle_dur:.2f}s err={pe}"
                )
                all_boxes = []

        # 6. Secondary Fallback: Tesseract OCR (if primary yielded no text or was bypassed)
        if not all_boxes and tesseract_available:
            logger.info(f"[TESSERACT_FALLBACK_TRIGGERED] image_id={image_id} filename={filename}")
            variants = self._prepare_variants(proc_img)
            primary_name, primary_img, scale_x, scale_y = variants[0]
            # Combine scale factors for Tesseract variants
            comb_scale_x = scale_x * scale_factors[0]
            comb_scale_y = scale_y * scale_factors[1]
            primary_boxes = self.tesseract_engine.extract_text_boxes(
                primary_img, (orig_h, orig_w), (comb_scale_x, comb_scale_y)
            )

            if len(primary_boxes) >= 4 and np.mean([b.confidence for b in primary_boxes]) >= 0.70:
                all_boxes = primary_boxes
            else:
                all_boxes.extend(primary_boxes)
                for v_name, v_img, s_x, s_y in variants[1:]:
                    v_boxes = self.tesseract_engine.extract_text_boxes(
                        v_img, (orig_h, orig_w), (s_x * scale_factors[0], s_y * scale_factors[1])
                    )
                    all_boxes.extend(v_boxes)
                all_boxes = self._deduplicate_boxes(all_boxes)

            if len(all_boxes) == 0:
                rot_boxes = self._try_rotation_orientations(proc_img, orig_h, orig_w)
                if rot_boxes:
                    all_boxes = rot_boxes

            engine_used = "Tesseract"
            logger.info(f"[TESSERACT_FALLBACK_COMPLETE] image_id={image_id} boxes={len(all_boxes)}")
        elif all_boxes:
            logger.info(f"[TESSERACT_FALLBACK_SKIPPED] PaddleOCR succeeded with {len(all_boxes)} boxes")
        elif not all_boxes and not engine_used:
            # Genuinely empty / no text detected by available engine
            engine_used = "PaddleOCR" if paddle_available else "Tesseract"

        # 7. Preserve source image ID, engine, and timestamp
        now_iso = datetime.now(timezone.utc).isoformat()
        for b in all_boxes:
            b.image_id = image_id
            if not b.engine:
                b.engine = engine_used.lower()
            if not b.timestamp:
                b.timestamp = now_iso

        # 8. Calculate authentic mean confidence
        if all_boxes:
            mean_conf = float(np.mean([b.confidence for b in all_boxes]))
        else:
            mean_conf = 0.0

        # 9. Format raw and normalized text
        t_norm_start = time.time()
        raw_text = "\n".join([b.text for b in all_boxes if b.text.strip()])
        norm_text = normalize_ocr_text(raw_text)
        t_norm = time.time() - t_norm_start

        elapsed_ms = (time.time() - start_time) * 1000.0
        logger.info(
            f"[OCR_PERF_BREAKDOWN] image_id={image_id} filename={filename} "
            f"decode={t_decode:.3f}s resize={t_resize:.3f}s engine={engine_used} "
            f"boxes={len(all_boxes)} mean_conf={mean_conf:.2f} norm={t_norm:.3f}s "
            f"total_img_elapsed={elapsed_ms/1000.0:.3f}s"
        )

        return OCRResultData(
            raw_text=raw_text,
            normalized_text=norm_text,
            mean_confidence=round(mean_conf, 2),
            text_boxes=all_boxes,
            processing_time_ms=round(elapsed_ms, 2),
            engine_used=engine_used,
            ocr_status="OCR_SUCCESS",
            timestamp=now_iso
        )

ocr_service = ModularOCRService()
