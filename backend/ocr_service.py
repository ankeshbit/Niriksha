import os
import cv2
import numpy as np
import time
import shutil
import subprocess
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pathlib import Path
from pydantic import BaseModel
from backend.config import settings

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
    ocr_status: str = "OCR_SUCCESS"  # 'OCR_SUCCESS', 'OCR_UNAVAILABLE', 'OCR_FAILED'

class BaseOCREngine(ABC):
    @abstractmethod
    def extract_text_boxes(self, image_path: str) -> List[OCRTextBox]:
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
    def extract_text_boxes(self, image_path: str) -> List[OCRTextBox]:
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Could not load image at {image_path}")

        height, width = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Adaptive thresholding to segment text regions
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 8
        )
        
        # Morphological horizontal dilation to merge letter contours into line blocks
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 3))
        dilated = cv2.dilate(thresh, kernel, iterations=1)
        
        contours, _ = cv2.findContours(dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        
        raw_boxes = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            # Filter text lines: width > 40px, height between 8px and 120px
            if 40 < w < (width * 0.95) and 8 < h < (height * 0.25):
                raw_boxes.append([x, y, x + w, y + h])
        
        # Deduplicate overlapping boxes
        boxes = []
        for b in sorted(raw_boxes, key=lambda x: x[1]):
            if not any(abs(b[1] - ex[1]) < 12 and abs(b[0] - ex[0]) < 20 for ex in boxes):
                boxes.append(b)

        # Sort top-to-bottom
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
        # 1. Check settings or environment variable
        candidate = getattr(settings, "TESSERACT_CMD", None) or os.environ.get("TESSERACT_CMD")
        
        # 2. Check system PATH
        if not candidate:
            candidate = shutil.which("tesseract")
            
        # 3. Check known standard Windows/Linux installation paths
        if not candidate:
            common_paths = [
                r"C:\Program Files\PDF24\tesseract\tesseract.exe",
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                str(Path.home() / "AppData" / "Local" / "Programs" / "Tesseract-OCR" / "tesseract.exe"),
                "/usr/bin/tesseract",
                "/usr/local/bin/tesseract",
            ]
            for p in common_paths:
                if os.path.isfile(p):
                    candidate = p
                    break

        if candidate and os.path.isfile(candidate):
            self.cmd_path = candidate
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
        if not self.cmd_path:
            return False
        try:
            res = subprocess.run([self.cmd_path, "--version"], capture_output=True, text=True, timeout=3)
            return res.returncode == 0
        except Exception:
            return False

    def extract_text_boxes(self, image_path: str) -> List[OCRTextBox]:
        if not self.is_available():
            return []
        try:
            import pytesseract
            from pytesseract import Output
            img = cv2.imread(image_path)
            if img is None:
                return []
                
            data = pytesseract.image_to_data(img, output_type=Output.DICT)
            
            # Group words by line block (block_num, par_num, line_num)
            lines_dict: Dict[tuple, List[tuple]] = {}
            n_boxes = len(data.get('text', []))
            for i in range(n_boxes):
                text = str(data['text'][i]).strip()
                conf_val = float(data['conf'][i])
                if text and conf_val > 0:
                    key = (int(data['block_num'][i]), int(data['par_num'][i]), int(data['line_num'][i]))
                    x, y, w, h = int(data['left'][i]), int(data['top'][i]), int(data['width'][i]), int(data['height'][i])
                    lines_dict.setdefault(key, []).append((text, conf_val, [x, y, x + w, y + h]))

            boxes: List[OCRTextBox] = []
            seq = 1
            for key, words in lines_dict.items():
                line_text = " ".join([w[0] for w in words])
                min_x = min(w[2][0] for w in words)
                min_y = min(w[2][1] for w in words)
                max_x = max(w[2][2] for w in words)
                max_y = max(w[2][3] for w in words)
                avg_conf = sum(w[1] for w in words) / (len(words) * 100.0)
                boxes.append(OCRTextBox(
                    text=line_text,
                    confidence=round(avg_conf, 2),
                    bbox=[min_x, min_y, max_x, max_y],
                    sequence=seq
                ))
                seq += 1

            return boxes
        except Exception:
            return []

class ModularOCRService:
    """
    Modular OCR coordinator.
    Preprocesses images, runs real OCR, aggregates bounding boxes,
    and returns standardized structured OCR outputs with explicit status.
    """
    def __init__(self):
        self.tesseract_engine = TesseractOCREngine()
        self.morph_engine = MorphologicalOpenCVOCREngine()

    def preprocess_image(self, image_path: str) -> str:
        """
        Creates a contrast-enhanced, non-destructive derived image for OCR reading.
        Original image is untouched.
        """
        img = cv2.imread(image_path)
        if img is None:
            return image_path
        
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        limg = cv2.merge((cl, a, b))
        enhanced = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
        
        derived_path = image_path.replace(".", "_ocr_prep.")
        cv2.imwrite(derived_path, enhanced)
        return derived_path

    def process_image(self, image_path: str, image_id: Optional[str] = None) -> OCRResultData:
        start_time = time.time()
        
        if not self.tesseract_engine.is_available():
            elapsed_ms = (time.time() - start_time) * 1000.0
            return OCRResultData(
                raw_text="",
                mean_confidence=0.0,
                text_boxes=[],
                processing_time_ms=round(elapsed_ms, 2),
                engine_used="None",
                ocr_status="OCR_UNAVAILABLE"
            )

        # Preprocessing on derived copy
        prep_path = self.preprocess_image(image_path)
        boxes: List[OCRTextBox] = []
        ocr_status = "OCR_SUCCESS"
        engine_used = "Tesseract"
        
        try:
            boxes = self.tesseract_engine.extract_text_boxes(prep_path)
        except Exception:
            ocr_status = "OCR_FAILED"
            boxes = []

        if prep_path != image_path and os.path.exists(prep_path):
            try:
                os.remove(prep_path)
            except Exception:
                pass

        for b in boxes:
            b.image_id = image_id
            
        confs = [b.confidence for b in boxes if b.text]
        mean_conf = float(np.mean(confs)) if confs else (0.0 if not boxes else 0.5)
        raw_text = "\n".join([b.text for b in boxes if b.text])

        elapsed_ms = (time.time() - start_time) * 1000.0

        return OCRResultData(
            raw_text=raw_text,
            mean_confidence=round(mean_conf, 2),
            text_boxes=boxes,
            processing_time_ms=round(elapsed_ms, 2),
            engine_used=engine_used,
            ocr_status=ocr_status
        )

ocr_service = ModularOCRService()
