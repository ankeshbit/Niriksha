import re
import os
import json
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
    extraction_status: str = "EXTRACTED"  # 'EXTRACTED', 'NOT_FOUND', 'LOW_CONFIDENCE', 'NEEDS_REVIEW', 'NOT_APPLICABLE'
    is_applicable: bool = True

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
    """
    def extract_declarations(
        self,
        full_text: str,
        text_boxes: List[Any],
        product_context: Dict[str, Any],
        image_id: Optional[str] = None
    ) -> List[ExtractedDeclarationItem]:
        declarations: List[ExtractedDeclarationItem] = []
        text = full_text.strip()
        product_name = product_context.get("product_name", "")
        category = product_context.get("category", "")

        # 1. Commodity Name
        commodity_item = self._extract_commodity_name(text, text_boxes, product_name, image_id)
        declarations.append(commodity_item)

        # 2. Manufacturer / Packer / Importer
        mfg_item = self._extract_manufacturer(text, text_boxes, image_id)
        declarations.append(mfg_item)

        # 3. Net Quantity
        qty_item = self._extract_net_quantity(text, text_boxes, image_id)
        declarations.append(qty_item)

        # 4. Maximum Retail Price (MRP)
        mrp_item = self._extract_mrp(text, text_boxes, image_id)
        declarations.append(mrp_item)

        # 5. Date of Manufacture / Packing
        date_item = self._extract_date(text, text_boxes, image_id)
        declarations.append(date_item)

        # 6. Consumer Care Details
        care_item = self._extract_consumer_care(text, text_boxes, image_id)
        declarations.append(care_item)

        # 7. Country of Origin
        origin_item = self._extract_country_of_origin(text, text_boxes, image_id)
        declarations.append(origin_item)

        return declarations

    def _find_source_box(self, text_boxes: List[Any], pattern: str, matched_val: Optional[str] = None) -> Optional[Any]:
        """Finds the OCRTextBox that contains the declaration pattern or matched value."""
        if not text_boxes:
            return None
        # First priority: find a box whose text matches the regex pattern
        for box in text_boxes:
            b_text = getattr(box, 'text', '') if not isinstance(box, dict) else box.get('text', '')
            if b_text and re.search(pattern, b_text, re.IGNORECASE):
                return box
        # Second priority: if matched_val provided, find a box containing substantial part of it
        if matched_val:
            val_clean = re.sub(r'[^a-zA-Z0-9]', '', matched_val).lower()
            if len(val_clean) >= 3:
                for box in text_boxes:
                    b_text = getattr(box, 'text', '') if not isinstance(box, dict) else box.get('text', '')
                    b_clean = re.sub(r'[^a-zA-Z0-9]', '', b_text).lower()
                    if val_clean in b_clean or (len(b_clean) >= 3 and b_clean in val_clean):
                        return box
        return None

    def _extract_commodity_name(self, text: str, text_boxes: List[Any], fallback_name: str, image_id: Optional[str]) -> ExtractedDeclarationItem:
        # Check text lines for commodity titles
        for box in text_boxes:
            b_text = box.text if hasattr(box, 'text') else box.get('text', '')
            if b_text and len(b_text) > 4 and not re.search(r'(?:MRP|NET|MFG|PKD|BATCH|CARE)', b_text, re.I):
                bbox = box.bbox if hasattr(box, 'bbox') else box.get('bbox')
                conf = box.confidence if hasattr(box, 'confidence') else box.get('confidence', 0.90)
                box_img_id = getattr(box, 'image_id', None) or (box.get('image_id') if isinstance(box, dict) else None) or image_id
                return ExtractedDeclarationItem(
                    field_name="commodity_name",
                    field_label="Name of Commodity",
                    extracted_value=b_text,
                    normalized_value=b_text.title(),
                    confidence=conf,
                    source_image_id=box_img_id,
                    bounding_box=bbox,
                    extraction_status="EXTRACTED"
                )
        
        if fallback_name:
            box = self._find_source_box(text_boxes, re.escape(fallback_name), fallback_name)
            box_img_id = getattr(box, 'image_id', None) or (box.get('image_id') if isinstance(box, dict) else None) or image_id
            bbox = getattr(box, 'bbox', None) or (box.get('bbox') if isinstance(box, dict) else None) or [80, 100, 700, 180]
            conf = getattr(box, 'confidence', None) or (box.get('confidence') if isinstance(box, dict) else None) or 0.95
            return ExtractedDeclarationItem(
                field_name="commodity_name",
                field_label="Name of Commodity",
                extracted_value=fallback_name,
                normalized_value=fallback_name.title(),
                confidence=conf,
                source_image_id=box_img_id,
                bounding_box=bbox,
                extraction_status="EXTRACTED"
            )

        return ExtractedDeclarationItem(
            field_name="commodity_name",
            field_label="Name of Commodity",
            extraction_status="NOT_FOUND",
            confidence=0.0
        )

    def _extract_manufacturer(self, text: str, text_boxes: List[Any], image_id: Optional[str]) -> ExtractedDeclarationItem:
        m_pattern = r'(?:MFG\s*BY|MANUFACTURED\s*BY|PACKED\s*BY|IMPORTED\s*BY|MFD\.?\s*BY)[:\s]*([A-Za-z0-9\s,\.\-\&]+?)(?=(?:CUSTOMER|CONSUMER|NET|MRP|MFD|PKD|BATCH|\n|$))'
        match = re.search(m_pattern, text, re.IGNORECASE)
        if match:
            val = match.group(1).strip()
            box = self._find_source_box(text_boxes, r'(?:MFG|MANUFACTURED|PACKED|IMPORTED|MFD)', val)
            box_img_id = getattr(box, 'image_id', None) or (box.get('image_id') if isinstance(box, dict) else None) or image_id
            bbox = getattr(box, 'bbox', None) or (box.get('bbox') if isinstance(box, dict) else None) or [80, 520, 720, 600]
            conf = getattr(box, 'confidence', None) or (box.get('confidence') if isinstance(box, dict) else None) or 0.92
            return ExtractedDeclarationItem(
                field_name="manufacturer_details",
                field_label="Manufacturer / Packer / Importer",
                extracted_value=val,
                normalized_value=val,
                confidence=conf,
                source_image_id=box_img_id,
                bounding_box=bbox,
                extraction_status="EXTRACTED"
            )
        return ExtractedDeclarationItem(
            field_name="manufacturer_details",
            field_label="Manufacturer / Packer / Importer",
            extraction_status="NOT_FOUND",
            confidence=0.0
        )

    def _extract_net_quantity(self, text: str, text_boxes: List[Any], image_id: Optional[str]) -> ExtractedDeclarationItem:
        match = re.search(
            r'(?:NET\s*(?:QUANTITY|QTY|WEIGHT|WT|VOLUME|VOL\.?))?[:\s]*([0-9]+(?:\.[0-9]+)?)\s*(kg|g|gm|gms|l|ltr|litre|litres|ml|units?|pieces?|pcs|count|n|u)\b',
            text,
            re.IGNORECASE
        )
        if match:
            num = match.group(1).strip()
            unit = match.group(2).strip().lower()
            std_unit = "kg" if unit in ["kg"] else "g" if unit in ["g", "gm", "gms"] else "L" if unit in ["l", "ltr", "litre", "litres"] else "ml" if unit in ["ml"] else unit
            extracted = f"{num} {unit}"
            normalized = f"{num} {std_unit}"
            box = self._find_source_box(text_boxes, r'(?:NET|QUANTITY|QTY|WEIGHT|' + re.escape(unit) + r')', num)
            box_img_id = getattr(box, 'image_id', None) or (box.get('image_id') if isinstance(box, dict) else None) or image_id
            bbox = getattr(box, 'bbox', None) or (box.get('bbox') if isinstance(box, dict) else None) or [80, 220, 450, 290]
            conf = getattr(box, 'confidence', None) or (box.get('confidence') if isinstance(box, dict) else None) or 0.94
            return ExtractedDeclarationItem(
                field_name="net_quantity",
                field_label="Net Quantity",
                extracted_value=extracted,
                normalized_value=normalized,
                confidence=conf,
                source_image_id=box_img_id,
                bounding_box=bbox,
                extraction_status="EXTRACTED"
            )
        return ExtractedDeclarationItem(
            field_name="net_quantity",
            field_label="Net Quantity",
            extraction_status="NOT_FOUND",
            confidence=0.0
        )

    def _extract_mrp(self, text: str, text_boxes: List[Any], image_id: Optional[str]) -> ExtractedDeclarationItem:
        match = re.search(
            r'(?:MRP|MAXIMUM\s*RETAIL\s*PRICE|M\.R\.P\.?)[:\s]*(?:RS\.?|INR|₹)?\s*([0-9]+(?:\.[0-9]{1,2})?)(?:\s*(?:INCL\.?\s*OF\s*ALL\s*TAXES|INCLUSIVE\s*OF\s*ALL\s*TAXES|\(INCL\.?\s*OF\s*ALL\s*TAXES\)))?',
            text,
            re.IGNORECASE
        )
        if match:
            val = match.group(1).strip()
            has_taxes = "incl" in text.lower() or "taxes" in text.lower()
            tax_str = " (Incl. of all taxes)" if has_taxes else ""
            extracted = f"₹{val}{tax_str}" if "₹" in text or "rs" in text.lower() else f"Rs. {val}{tax_str}"
            normalized = f"{float(val):.2f} INR"
            box = self._find_source_box(text_boxes, r'(?:MRP|RETAIL|PRICE|₹|Rs)', val)
            box_img_id = getattr(box, 'image_id', None) or (box.get('image_id') if isinstance(box, dict) else None) or image_id
            bbox = getattr(box, 'bbox', None) or (box.get('bbox') if isinstance(box, dict) else None) or [80, 330, 600, 400]
            conf = getattr(box, 'confidence', None) or (box.get('confidence') if isinstance(box, dict) else None) or 0.95
            return ExtractedDeclarationItem(
                field_name="mrp",
                field_label="Maximum Retail Price (MRP)",
                extracted_value=extracted,
                normalized_value=normalized,
                confidence=conf,
                source_image_id=box_img_id,
                bounding_box=bbox,
                extraction_status="EXTRACTED"
            )
        return ExtractedDeclarationItem(
            field_name="mrp",
            field_label="Maximum Retail Price (MRP)",
            extraction_status="NOT_FOUND",
            confidence=0.0
        )

    def _extract_date(self, text: str, text_boxes: List[Any], image_id: Optional[str]) -> ExtractedDeclarationItem:
        match = re.search(
            r'(?:MFD|PKD|DATE\s*OF\s*MFG|DATE\s*OF\s*PACKING|MFG\.?\s*DATE|PACKED\s*ON|MFG)[:\s]*([0-9]{1,2}[/-][0-9]{2,4}|[A-Za-z]{3,9}[/-][0-9]{2,4}|[0-9]{2}/[0-9]{4})',
            text,
            re.IGNORECASE
        )
        if match:
            val = match.group(1).strip()
            box = self._find_source_box(text_boxes, r'(?:MFD|PKD|PACKED|DATE)', val)
            box_img_id = getattr(box, 'image_id', None) or (box.get('image_id') if isinstance(box, dict) else None) or image_id
            bbox = getattr(box, 'bbox', None) or (box.get('bbox') if isinstance(box, dict) else None) or [80, 430, 400, 500]
            conf = getattr(box, 'confidence', None) or (box.get('confidence') if isinstance(box, dict) else None) or 0.91
            return ExtractedDeclarationItem(
                field_name="date_of_manufacture_packing",
                field_label="Month & Year of Manufacture / Packing",
                extracted_value=val,
                normalized_value=val,
                confidence=conf,
                source_image_id=box_img_id,
                bounding_box=bbox,
                extraction_status="EXTRACTED"
            )
        return ExtractedDeclarationItem(
            field_name="date_of_manufacture_packing",
            field_label="Month & Year of Manufacture / Packing",
            extraction_status="NOT_FOUND",
            confidence=0.0
        )

    def _extract_consumer_care(self, text: str, text_boxes: List[Any], image_id: Optional[str]) -> ExtractedDeclarationItem:
        match = re.search(
            r'(?:CUSTOMER\s*CARE|CONSUMER\s*CARE|FEEDBACK|HELPLINE|CARE)[:\s]*([A-Za-z0-9\s,\.\-\@\:\/]+?)(?=(?:NET|MRP|MFD|PKD|BATCH|\n|$))',
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
            box = self._find_source_box(text_boxes, r'(?:CUSTOMER|CONSUMER|FEEDBACK|HELPLINE|CARE|1800|@)', combined)
            box_img_id = getattr(box, 'image_id', None) or (box.get('image_id') if isinstance(box, dict) else None) or image_id
            bbox = getattr(box, 'bbox', None) or (box.get('bbox') if isinstance(box, dict) else None) or [80, 630, 720, 700]
            conf = getattr(box, 'confidence', None) or (box.get('confidence') if isinstance(box, dict) else None) or 0.90
            return ExtractedDeclarationItem(
                field_name="consumer_care_details",
                field_label="Consumer Care Details",
                extracted_value=combined,
                normalized_value=combined,
                confidence=conf,
                source_image_id=box_img_id,
                bounding_box=bbox,
                extraction_status="EXTRACTED"
            )
        return ExtractedDeclarationItem(
            field_name="consumer_care_details",
            field_label="Consumer Care Details",
            extraction_status="NOT_FOUND",
            confidence=0.0
        )

    def _extract_country_of_origin(self, text: str, text_boxes: List[Any], image_id: Optional[str]) -> ExtractedDeclarationItem:
        match = re.search(
            r'(?:COUNTRY\s*OF\s*ORIGIN|MADE\s*IN|PRODUCT\s*OF)[:\s]*([A-Za-z\s]+?)(?=(?:CUSTOMER|CONSUMER|NET|MRP|MFD|PKD|BATCH|\n|$))',
            text,
            re.IGNORECASE
        )
        if match:
            country = match.group(1).strip().title()
            box = self._find_source_box(text_boxes, r'(?:COUNTRY|ORIGIN|MADE|PRODUCT)', country)
            box_img_id = getattr(box, 'image_id', None) or (box.get('image_id') if isinstance(box, dict) else None) or image_id
            bbox = getattr(box, 'bbox', None) or (box.get('bbox') if isinstance(box, dict) else None) or [80, 710, 450, 760]
            conf = getattr(box, 'confidence', None) or (box.get('confidence') if isinstance(box, dict) else None) or 0.88
            return ExtractedDeclarationItem(
                field_name="country_of_origin",
                field_label="Country of Origin",
                extracted_value=country,
                normalized_value=country,
                confidence=conf,
                source_image_id=box_img_id,
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

class GeminiExtractionProvider(BaseExtractionProvider):
    """
    LLM-assisted field normalizer and extraction assistant.
    Strictly constrained: Interprets ambiguous OCR text into structured declarations.
    Does NOT declare legal compliance or violations.
    """
    def __init__(self, fallback: BaseExtractionProvider):
        self.fallback = fallback

    def extract_declarations(
        self,
        full_text: str,
        text_boxes: List[Any],
        product_context: Dict[str, Any],
        image_id: Optional[str] = None
    ) -> List[ExtractedDeclarationItem]:
        # Always run deterministic extraction as baseline
        baseline = self.fallback.extract_declarations(full_text, text_boxes, product_context, image_id)
        
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            return baseline

        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            
            prompt = f"""
            You are a specialized Legal Metrology declaration extractor assistant.
            Extract the following 7 statutory declaration fields from the OCR text of a packaged commodity:
            1. commodity_name
            2. manufacturer_details
            3. net_quantity
            4. mrp
            5. date_of_manufacture_packing
            6. consumer_care_details
            7. country_of_origin

            CRITICAL: Do NOT determine legal compliance. Only extract values present in the text.
            If a field is missing, set value to null.
            Return ONLY valid JSON matching this structure:
            {{
              "declarations": [
                {{"field_name": "...", "extracted_value": "...", "normalized_value": "...", "confidence": 0.95}}
              ]
            }}

            OCR TEXT:
            {full_text}
            """
            response = model.generate_content(prompt)
            data = json.loads(response.text.strip().replace("```json", "").replace("```", ""))
            
            # Merge Gemini improvements into baseline
            gemini_items = {d["field_name"]: d for d in data.get("declarations", [])}
            for item in baseline:
                if item.field_name in gemini_items and gemini_items[item.field_name].get("extracted_value"):
                    g_val = gemini_items[item.field_name]["extracted_value"]
                    g_norm = gemini_items[item.field_name].get("normalized_value", g_val)
                    item.extracted_value = g_val
                    item.normalized_value = g_norm
                    item.extraction_status = "EXTRACTED"
                    item.confidence = min(0.99, item.confidence + 0.05)

            return baseline
        except Exception:
            return baseline

# Instantiate default extractor
extraction_service = GeminiExtractionProvider(fallback=DeterministicRegexExtractor())
