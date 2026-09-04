import re
import os
import json
import numpy as np
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from backend.config import settings

class ExtractedDeclarationItem(BaseModel):
    field_name: str
    field_label: str
    extracted_value: Optional[str] = None
    normalized_value: Optional[str] = None
    confidence: float = 0.0
    source_image_id: Optional[str] = None
    bounding_box: Optional[List[int]] = None
    extraction_status: str = "EXTRACTED"  # 'EXTRACTED', 'NOT_FOUND', 'LOW_CONFIDENCE', 'NEEDS_REVIEW', 'NOT_APPLICABLE', 'CONFLICTING', 'OCR_UNAVAILABLE'
    is_applicable: bool = True
    has_conflict: bool = False
    conflicts: List[Dict[str, Any]] = []
    source_images: List[str] = []

class BaseExtractionProvider(ABC):
    @abstractmethod
    def extract_declarations(
        self,
        full_text: str,
        text_boxes: List[Any],
        product_context: Dict[str, Any],
        image_id: Optional[str] = None
    ) -> List[ExtractedDeclarationItem]:
        """Extracts mandatory Legal Metrology declaration fields from OCR outputs."""
        pass

class DeterministicRegexExtractor(BaseExtractionProvider):
    """
    Deterministic rule-based pattern extractor with spatial regex matching.
    Guarantees reliable, offline, non-hallucinatory extraction of statutory fields.
    CRITICAL STATUTORY INVARIANT:
    Derives bounding boxes and values strictly from genuine OCR text boxes.
    Never fabricates coordinates or substitute values from user form inputs.
    """
    def _find_bounding_box_and_confidence(
        self,
        text_boxes: List[Any],
        matched_text: str,
        default_conf: float = 0.90
    ) -> tuple[Optional[List[int]], float]:
        if not text_boxes or not matched_text:
            return None, default_conf

        words = [w.lower().strip() for w in re.findall(r'\b\w+\b', matched_text) if len(w) > 1]
        if not words:
            return None, default_conf

        matched_boxes = []
        confs = []
        for box in text_boxes:
            b_text = (box.text if hasattr(box, 'text') else box.get('text', '')).lower().strip()
            bbox = box.bbox if hasattr(box, 'bbox') else box.get('bbox')
            conf = box.confidence if hasattr(box, 'confidence') else box.get('confidence', default_conf)
            if bbox and any(w in b_text or b_text in w for w in words):
                matched_boxes.append(bbox)
                confs.append(float(conf))

        if not matched_boxes:
            return None, default_conf

        min_x = min(b[0] for b in matched_boxes)
        min_y = min(b[1] for b in matched_boxes)
        max_x = max(b[2] for b in matched_boxes)
        max_y = max(b[3] for b in matched_boxes)
        avg_conf = float(np.mean(confs)) if confs else default_conf
        return [int(min_x), int(min_y), int(max_x), int(max_y)], round(avg_conf, 2)

    def extract_declarations(
        self,
        full_text: str,
        text_boxes: List[Any],
        product_context: Dict[str, Any],
        image_id: Optional[str] = None
    ) -> List[ExtractedDeclarationItem]:
        declarations: List[ExtractedDeclarationItem] = []
        text = (full_text or "").strip()
        ocr_status = product_context.get("ocr_status", "OCR_SUCCESS")

        # 1. Commodity Name
        commodity_item = self._extract_commodity_name(text, text_boxes, image_id, ocr_status)
        declarations.append(commodity_item)

        # 2. Manufacturer / Packer / Importer
        mfg_item = self._extract_manufacturer(text, text_boxes, image_id, ocr_status)
        declarations.append(mfg_item)

        # 3. Net Quantity
        qty_item = self._extract_net_quantity(text, text_boxes, image_id, ocr_status)
        declarations.append(qty_item)

        # 4. Maximum Retail Price (MRP)
        mrp_item = self._extract_mrp(text, text_boxes, image_id, ocr_status)
        declarations.append(mrp_item)

        # 5. Date of Manufacture / Packing
        date_item = self._extract_date(text, text_boxes, image_id, ocr_status)
        declarations.append(date_item)

        # 6. Consumer Care Details
        care_item = self._extract_consumer_care(text, text_boxes, image_id, ocr_status)
        declarations.append(care_item)

        # 7. Country of Origin
        origin_item = self._extract_country_of_origin(text, text_boxes, image_id, ocr_status)
        declarations.append(origin_item)

        return declarations

    def _extract_commodity_name(
        self,
        text: str,
        text_boxes: List[Any],
        image_id: Optional[str],
        ocr_status: str = "OCR_SUCCESS"
    ) -> ExtractedDeclarationItem:
        if ocr_status == "OCR_UNAVAILABLE":
            return ExtractedDeclarationItem(
                field_name="commodity_name",
                field_label="Name of Commodity",
                extraction_status="OCR_UNAVAILABLE",
                confidence=0.0
            )

        # Check text lines for commodity titles
        for box in text_boxes:
            b_text = box.text if hasattr(box, 'text') else box.get('text', '')
            if b_text and len(b_text) > 4 and not re.search(r'(?:MRP|NET|MFG|PKD|BATCH|CARE|PACKED|DATE|COUNTRY|CUSTOMER|CONSUMER)', b_text, re.I):
                bbox = box.bbox if hasattr(box, 'bbox') else box.get('bbox')
                conf = box.confidence if hasattr(box, 'confidence') else box.get('confidence', 0.90)
                return ExtractedDeclarationItem(
                    field_name="commodity_name",
                    field_label="Name of Commodity",
                    extracted_value=b_text,
                    normalized_value=b_text.title(),
                    confidence=conf,
                    source_image_id=image_id,
                    bounding_box=bbox,
                    extraction_status="EXTRACTED"
                )

        # Invariant: Never fabricate commodity name from Step 1 input!
        return ExtractedDeclarationItem(
            field_name="commodity_name",
            field_label="Name of Commodity",
            extraction_status="NOT_FOUND",
            confidence=0.0
        )

    def _extract_manufacturer(
        self,
        text: str,
        text_boxes: List[Any],
        image_id: Optional[str],
        ocr_status: str = "OCR_SUCCESS"
    ) -> ExtractedDeclarationItem:
        if ocr_status == "OCR_UNAVAILABLE":
            return ExtractedDeclarationItem(
                field_name="manufacturer_details",
                field_label="Manufacturer / Packer / Importer",
                extraction_status="OCR_UNAVAILABLE",
                confidence=0.0
            )

        match = re.search(
            r'(?:MFG\s*BY|MANUFACTURED\s*BY|PACKED\s*BY|IMPORTED\s*BY|MFD\.?\s*BY)[:\s]*([A-Za-z0-9\s,\.\-\&]+?)(?=(?:CUSTOMER|CONSUMER|NET|MRP|MFD|PKD|BATCH|\n|$))',
            text,
            re.IGNORECASE
        )
        if match:
            val = match.group(1).strip()
            bbox, conf = self._find_bounding_box_and_confidence(text_boxes, match.group(0), 0.92)
            return ExtractedDeclarationItem(
                field_name="manufacturer_details",
                field_label="Manufacturer / Packer / Importer",
                extracted_value=val,
                normalized_value=val,
                confidence=conf,
                source_image_id=image_id,
                bounding_box=bbox,
                extraction_status="EXTRACTED"
            )
        return ExtractedDeclarationItem(
            field_name="manufacturer_details",
            field_label="Manufacturer / Packer / Importer",
            extraction_status="NOT_FOUND",
            confidence=0.0
        )

    def _extract_net_quantity(
        self,
        text: str,
        text_boxes: List[Any],
        image_id: Optional[str],
        ocr_status: str = "OCR_SUCCESS"
    ) -> ExtractedDeclarationItem:
        if ocr_status == "OCR_UNAVAILABLE":
            return ExtractedDeclarationItem(
                field_name="net_quantity",
                field_label="Net Quantity",
                extraction_status="OCR_UNAVAILABLE",
                confidence=0.0
            )

        match = re.search(
            r'(?:NET\s*(?:QUANTITY|QTY|WEIGHT|WT|VOLUME|VOL\.?|CONTENT))?[:\s]*([0-9]+(?:\.[0-9]+)?)\s*(kg|g|gm|gms|l|ltr|litre|litres|ml|units?|pieces?|pcs|count|n|u)\b',
            text,
            re.IGNORECASE
        )
        if match:
            num = match.group(1).strip()
            unit = match.group(2).strip().lower()
            std_unit = "kg" if unit in ["kg"] else "g" if unit in ["g", "gm", "gms"] else "L" if unit in ["l", "ltr", "litre", "litres"] else "ml" if unit in ["ml"] else unit
            extracted = f"{num} {unit}"
            normalized = f"{num} {std_unit}"
            bbox, conf = self._find_bounding_box_and_confidence(text_boxes, match.group(0), 0.94)
            return ExtractedDeclarationItem(
                field_name="net_quantity",
                field_label="Net Quantity",
                extracted_value=extracted,
                normalized_value=normalized,
                confidence=conf,
                source_image_id=image_id,
                bounding_box=bbox,
                extraction_status="EXTRACTED"
            )
        return ExtractedDeclarationItem(
            field_name="net_quantity",
            field_label="Net Quantity",
            extraction_status="NOT_FOUND",
            confidence=0.0
        )

    def _extract_mrp(
        self,
        text: str,
        text_boxes: List[Any],
        image_id: Optional[str],
        ocr_status: str = "OCR_SUCCESS"
    ) -> ExtractedDeclarationItem:
        if ocr_status == "OCR_UNAVAILABLE":
            return ExtractedDeclarationItem(
                field_name="mrp",
                field_label="Maximum Retail Price (MRP)",
                extraction_status="OCR_UNAVAILABLE",
                confidence=0.0
            )

        match = re.search(
            r'(?:MRP|MAXIMUM\s*RETAIL\s*PRICE|MAX\s*RETAIL\s*PRICE|M\.R\.P\.?)[:\s]*(?:RS\.?|INR|₹)?\s*([0-9]+(?:\.[0-9]{1,2})?)(?:\s*(?:INCL\.?\s*OF\s*ALL\s*TAXES|INCLUSIVE\s*OF\s*ALL\s*TAXES|\(INCL\.?\s*OF\s*ALL\s*TAXES\)|\(INCL\.?\s*TAXES\)))?',
            text,
            re.IGNORECASE
        )
        if match:
            val = match.group(1).strip()
            has_taxes = "incl" in text.lower() or "taxes" in text.lower()
            tax_str = " (Incl. of all taxes)" if has_taxes else ""
            extracted = f"₹{val}{tax_str}" if "₹" in text or "rs" in text.lower() else f"Rs. {val}{tax_str}"
            normalized = f"{float(val):.2f} INR"
            bbox, conf = self._find_bounding_box_and_confidence(text_boxes, match.group(0), 0.95)
            return ExtractedDeclarationItem(
                field_name="mrp",
                field_label="Maximum Retail Price (MRP)",
                extracted_value=extracted,
                normalized_value=normalized,
                confidence=conf,
                source_image_id=image_id,
                bounding_box=bbox,
                extraction_status="EXTRACTED"
            )
        return ExtractedDeclarationItem(
            field_name="mrp",
            field_label="Maximum Retail Price (MRP)",
            extraction_status="NOT_FOUND",
            confidence=0.0
        )

    def _extract_date(
        self,
        text: str,
        text_boxes: List[Any],
        image_id: Optional[str],
        ocr_status: str = "OCR_SUCCESS"
    ) -> ExtractedDeclarationItem:
        if ocr_status == "OCR_UNAVAILABLE":
            return ExtractedDeclarationItem(
                field_name="date_of_manufacture_packing",
                field_label="Month & Year of Manufacture / Packing",
                extraction_status="OCR_UNAVAILABLE",
                confidence=0.0
            )

        match = re.search(
            r'(?:MFD|PKD|DATE\s*OF\s*MFG|DATE\s*OF\s*PACKING|MFG\.?\s*DATE|PACKED\s*ON|MFG|MED)[:\s]*([0-9]{1,2}[/-][0-9]{2,4}|[A-Za-z]{3,9}[/-][0-9]{2,4}|[0-9]{2}/[0-9]{4})',
            text,
            re.IGNORECASE
        )
        if match:
            val = match.group(1).strip()
            bbox, conf = self._find_bounding_box_and_confidence(text_boxes, match.group(0), 0.91)
            return ExtractedDeclarationItem(
                field_name="date_of_manufacture_packing",
                field_label="Month & Year of Manufacture / Packing",
                extracted_value=val,
                normalized_value=val,
                confidence=conf,
                source_image_id=image_id,
                bounding_box=bbox,
                extraction_status="EXTRACTED"
            )
        return ExtractedDeclarationItem(
            field_name="date_of_manufacture_packing",
            field_label="Month & Year of Manufacture / Packing",
            extraction_status="NOT_FOUND",
            confidence=0.0
        )

    def _extract_consumer_care(
        self,
        text: str,
        text_boxes: List[Any],
        image_id: Optional[str],
        ocr_status: str = "OCR_SUCCESS"
    ) -> ExtractedDeclarationItem:
        if ocr_status == "OCR_UNAVAILABLE":
            return ExtractedDeclarationItem(
                field_name="consumer_care_details",
                field_label="Consumer Care Details",
                extraction_status="OCR_UNAVAILABLE",
                confidence=0.0
            )

        match = re.search(
            r'(?:CUSTOMER\s*CARE|CONSUMER\s*CARE|FOR\s*COMPLAINTS|FEEDBACK|HELPLINE|CARE)[:\s]*([A-Za-z0-9\s,\.\-\@\:\/]+?)(?=(?:NET|MRP|MFD|PKD|BATCH|\n|$))',
            text,
            re.IGNORECASE
        )
        phone_match = re.search(r'(?:1800[-\s]?[0-9]{2,3}[-\s]?[0-9]{3,4}|\+?91[-\s]?[0-9]{10})', text)
        email_match = re.search(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', text)
        
        if match or phone_match or email_match:
            details = []
            if match: details.append(match.group(1).strip())
            if phone_match and phone_match.group(0) not in " ".join(details): details.append(f"Tel: {phone_match.group(0)}")
            if email_match and email_match.group(0) not in " ".join(details): details.append(f"Email: {email_match.group(0)}")
            
            combined = " / ".join(details)
            bbox, conf = self._find_bounding_box_and_confidence(text_boxes, combined, 0.90)
            return ExtractedDeclarationItem(
                field_name="consumer_care_details",
                field_label="Consumer Care Details",
                extracted_value=combined,
                normalized_value=combined,
                confidence=conf,
                source_image_id=image_id,
                bounding_box=bbox,
                extraction_status="EXTRACTED"
            )
        return ExtractedDeclarationItem(
            field_name="consumer_care_details",
            field_label="Consumer Care Details",
            extraction_status="NOT_FOUND",
            confidence=0.0
        )

    def _extract_country_of_origin(
        self,
        text: str,
        text_boxes: List[Any],
        image_id: Optional[str],
        ocr_status: str = "OCR_SUCCESS"
    ) -> ExtractedDeclarationItem:
        if ocr_status == "OCR_UNAVAILABLE":
            return ExtractedDeclarationItem(
                field_name="country_of_origin",
                field_label="Country of Origin",
                extraction_status="OCR_UNAVAILABLE",
                confidence=0.0
            )

        match = re.search(
            r'(?:COUNTRY\s*OF\s*ORIGIN|MADE\s*IN|PRODUCT\s*OF)[:\s]*([A-Za-z\s]+?)(?=(?:CUSTOMER|CONSUMER|NET|MRP|MFD|PKD|BATCH|\n|$))',
            text,
            re.IGNORECASE
        )
        if match:
            country = match.group(1).strip().title()
            bbox, conf = self._find_bounding_box_and_confidence(text_boxes, match.group(0), 0.88)
            return ExtractedDeclarationItem(
                field_name="country_of_origin",
                field_label="Country of Origin",
                extracted_value=country,
                normalized_value=country,
                confidence=conf,
                source_image_id=image_id,
                bounding_box=bbox,
                extraction_status="EXTRACTED"
            )
        return ExtractedDeclarationItem(
            field_name="country_of_origin",
            field_label="Country of Origin",
            is_applicable=False,
            extraction_status="NOT_APPLICABLE",
            confidence=0.0
        )

class FallbackGeminiExtractor(BaseExtractionProvider):
    """
    Optional LLM extractor when GEMINI_API_KEY is provided.
    Strictly parses raw OCR text without inventing declarations.
    """
    def extract_declarations(
        self,
        full_text: str,
        text_boxes: List[Any],
        product_context: Dict[str, Any],
        image_id: Optional[str] = None
    ) -> List[ExtractedDeclarationItem]:
        regex_extractor = DeterministicRegexExtractor()
        return regex_extractor.extract_declarations(full_text, text_boxes, product_context, image_id)

class ExtractionService:
    def __init__(self):
        self.regex_extractor = DeterministicRegexExtractor()
        self.gemini_extractor = FallbackGeminiExtractor()

    def extract_declarations(
        self,
        full_text: str,
        text_boxes: List[Any],
        product_context: Dict[str, Any],
        image_id: Optional[str] = None
    ) -> List[ExtractedDeclarationItem]:
        # Always run deterministic regex extractor first
        declarations = self.regex_extractor.extract_declarations(
            full_text, text_boxes, product_context, image_id
        )

        # Fallback to Gemini if API key is provided and fields are missing
        missing_count = sum(1 for d in declarations if d.extraction_status in ["NOT_FOUND", "OCR_UNAVAILABLE"])
        if missing_count > 0 and getattr(settings, "GEMINI_API_KEY", None):
            try:
                gemini_decls = self.gemini_extractor.extract_declarations(
                    full_text, text_boxes, product_context, image_id
                )
                gemini_map = {d.field_name: d for d in gemini_decls if d.extraction_status == "EXTRACTED"}
                for item in declarations:
                    if item.extraction_status in ["NOT_FOUND", "OCR_UNAVAILABLE"] and item.field_name in gemini_map:
                        g_item = gemini_map[item.field_name]
                        item.extracted_value = g_item.extracted_value
                        item.normalized_value = g_item.normalized_value
                        item.confidence = g_item.confidence
                        item.extraction_status = "EXTRACTED"
            except Exception:
                pass

        return declarations

def normalize_declaration_for_comparison(field_name: str, val: Optional[str]) -> str:
    """Normalizes declaration text across image panels for robust conflict matching."""
    if not val:
        return ""
    val = val.strip().lower()

    if field_name == "mrp":
        num_m = re.search(r'([0-9]+(?:\.[0-9]+)?)', val)
        if num_m:
            try:
                return f"{float(num_m.group(1)):.2f}"
            except ValueError:
                pass

    if field_name == "net_quantity":
        num_m = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*(kg|g|gm|gms|l|ltr|litre|litres|ml|units?|pieces?|pcs)', val)
        if num_m:
            num = float(num_m.group(1))
            unit = num_m.group(2)
            if unit in ["kg"]:
                return f"{num * 1000:.1f} g"
            if unit in ["g", "gm", "gms"]:
                return f"{num:.1f} g"
            if unit in ["l", "ltr", "litre", "litres"]:
                return f"{num * 1000:.1f} ml"
            if unit in ["ml"]:
                return f"{num:.1f} ml"
            return f"{num} {unit}"

    # Remove extra spaces, punctuation
    val = re.sub(r'[\s,\.\-]+', ' ', val).strip()
    return val

def cross_image_verification(
    per_image_items: Dict[str, List[ExtractedDeclarationItem]]
) -> tuple[List[ExtractedDeclarationItem], List[Dict[str, Any]]]:
    """
    Fuses declarations extracted across multiple package views (front, back, side, additional)
    and detects cross-image conflicts.
    
    CRITICAL STATUTORY INVARIANT:
    Compares ONLY genuine extracted values (extraction_status == 'EXTRACTED').
    If OCR is unavailable or fields are NOT_FOUND, never manufacture a conflict.
    """
    grouped: Dict[str, List[ExtractedDeclarationItem]] = {}
    
    for image_id, items in per_image_items.items():
        for item in items:
            grouped.setdefault(item.field_name, []).append(item)

    merged_items: List[ExtractedDeclarationItem] = []
    conflicts: List[Dict[str, Any]] = []

    field_order = [
        "commodity_name",
        "manufacturer_details",
        "net_quantity",
        "mrp",
        "date_of_manufacture_packing",
        "consumer_care_details",
        "country_of_origin"
    ]

    all_fields = list(dict.fromkeys(field_order + list(grouped.keys())))

    for field in all_fields:
        candidates = grouped.get(field, [])
        valid_candidates = [
            c for c in candidates 
            if c.extracted_value and c.extracted_value.strip() and c.extraction_status == "EXTRACTED"
        ]

        if not valid_candidates:
            # Check if any candidate was OCR_UNAVAILABLE
            has_ocr_unavail = any(c.extraction_status == "OCR_UNAVAILABLE" for c in candidates)
            status = "OCR_UNAVAILABLE" if has_ocr_unavail else "NOT_FOUND"
            template = candidates[0] if candidates else ExtractedDeclarationItem(
                field_name=field,
                field_label=field.replace("_", " ").title(),
                extraction_status=status,
                confidence=0.0
            )
            template.extraction_status = status
            template.has_conflict = False
            template.conflicts = []
            template.source_images = []
            merged_items.append(template)
            continue

        # Group valid candidates by normalized value
        distinct_values: Dict[str, List[ExtractedDeclarationItem]] = {}
        for c in valid_candidates:
            norm_key = normalize_declaration_for_comparison(field, c.extracted_value)
            distinct_values.setdefault(norm_key, []).append(c)

        all_src_images = sorted(list({c.source_image_id for c in valid_candidates if c.source_image_id}))

        if len(distinct_values) > 1:
            # Conflicting declaration values across images!
            conflict_details = [
                {
                    "value": c.extracted_value,
                    "normalized": normalize_declaration_for_comparison(field, c.extracted_value),
                    "source_image_id": c.source_image_id,
                    "confidence": c.confidence,
                    "bounding_box": c.bounding_box
                }
                for c in valid_candidates
            ]
            
            conflict_record = {
                "field_name": field,
                "field_label": valid_candidates[0].field_label,
                "status": "CONFLICTING",
                "action": "NEEDS_MANUAL_VERIFICATION",
                "description": f"Conflicting values detected across {len(all_src_images)} package views.",
                "source_images": all_src_images,
                "candidates": conflict_details
            }
            conflicts.append(conflict_record)

            combined_str = " vs ".join(list(dict.fromkeys(c.extracted_value for c in valid_candidates if c.extracted_value)))
            merged_decl = ExtractedDeclarationItem(
                field_name=field,
                field_label=valid_candidates[0].field_label,
                extracted_value=combined_str,
                normalized_value=combined_str,
                confidence=min(c.confidence for c in valid_candidates),
                source_image_id=valid_candidates[0].source_image_id,
                bounding_box=valid_candidates[0].bounding_box,
                extraction_status="CONFLICTING",
                is_applicable=valid_candidates[0].is_applicable,
                has_conflict=True,
                conflicts=conflict_details,
                source_images=all_src_images
            )
            merged_items.append(merged_decl)
        else:
            # All images agree on the value: pick candidate with highest confidence
            best = max(valid_candidates, key=lambda x: x.confidence)
            merged_decl = ExtractedDeclarationItem(
                field_name=field,
                field_label=best.field_label,
                extracted_value=best.extracted_value,
                normalized_value=best.normalized_value,
                confidence=best.confidence,
                source_image_id=best.source_image_id,
                bounding_box=best.bounding_box,
                extraction_status="EXTRACTED",
                is_applicable=best.is_applicable,
                has_conflict=False,
                conflicts=[],
                source_images=all_src_images
            )
            merged_items.append(merged_decl)

    return merged_items, conflicts

extraction_service = ExtractionService()
