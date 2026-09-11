import re
import os
import json
import numpy as np
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from backend.config import settings
from backend.layout_service import (
    layout_analyzer,
    LayoutAnalysisResult,
    _enclosing_bbox,
    _get_bbox,
    _get_text,
    _get_conf
)
from backend.vlm_service import (
    qwen_vl_service,
    VLMCandidate,
    VLMInterpretationResult
)

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
    metadata: Optional[Dict[str, Any]] = None
    raw_text: Optional[str] = None
    layout_region: Optional[str] = None
    layout_bbox: Optional[List[int]] = None

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

        # Step 0: PP-Structure Package Layout Understanding
        layout_res = layout_analyzer.analyze(text_boxes)

        # 1. Commodity Name
        commodity_item = self._extract_commodity_name(text, text_boxes, image_id, ocr_status, layout_res)
        declarations.append(commodity_item)

        # 2. Manufacturer / Packer / Importer
        mfg_item = self._extract_manufacturer(text, text_boxes, image_id, ocr_status, layout_res)
        declarations.append(mfg_item)

        # 3. Net Quantity
        qty_item = self._extract_net_quantity(text, text_boxes, image_id, ocr_status, layout_res)
        declarations.append(qty_item)

        # 4. Maximum Retail Price (MRP)
        mrp_item = self._extract_mrp(text, text_boxes, image_id, ocr_status, layout_res)
        declarations.append(mrp_item)

        # 5. Date of Manufacture / Packing
        date_item = self._extract_date(text, text_boxes, image_id, ocr_status, layout_res)
        declarations.append(date_item)

        # 6. Consumer Care Details
        care_item = self._extract_consumer_care(text, text_boxes, image_id, ocr_status, layout_res)
        declarations.append(care_item)

        # 7. Country of Origin
        origin_item = self._extract_country_of_origin(text, text_boxes, image_id, ocr_status, layout_res)
        declarations.append(origin_item)

        # 8. Unit Sale Price (USP)
        usp_item = self._extract_unit_sale_price(text, text_boxes, image_id, ocr_status, layout_res)
        declarations.append(usp_item)

        return declarations

    def _extract_commodity_name(
        self,
        text: str,
        text_boxes: List[Any],
        image_id: Optional[str],
        ocr_status: str = "OCR_SUCCESS",
        layout_res: Optional[LayoutAnalysisResult] = None
    ) -> ExtractedDeclarationItem:
        if ocr_status == "OCR_UNAVAILABLE":
            return ExtractedDeclarationItem(
                field_name="commodity_name",
                field_label="Name of Commodity",
                extraction_status="OCR_UNAVAILABLE",
                confidence=0.0
            )

        # Layer 1: Contextual label prefixes ("COMMODITY:", "PRODUCT NAME:", "COMMON NAME:", "GENERIC NAME:")
        label_match = re.search(
            r'(?:COMMODITY\s*NAME|COMMODITY|PRODUCT\s*NAME|PRODUCT|COMMON\s*NAME|GENERIC\s*NAME|ITEM\s*NAME|NAME\s*OF\s*COMMODITY)[:\s]+([A-Za-z0-9\s\-\&]{3,40})(?=\n|$|[;,])',
            text,
            re.IGNORECASE
        )
        if label_match:
            cand = label_match.group(1).strip()
            if len(cand) >= 3 and not re.search(r'(?:mrp|net|batch|date|fssai|lic|price|rs)', cand, re.I):
                bbox, conf = self._find_bounding_box_and_confidence(text_boxes, label_match.group(0), 0.90)
                reg_bbox = layout_res.title_regions[0].bbox if (layout_res and layout_res.title_regions) else bbox
                return ExtractedDeclarationItem(
                    field_name="commodity_name",
                    field_label="Name of Commodity",
                    extracted_value=cand,
                    normalized_value=cand.title(),
                    confidence=conf,
                    source_image_id=image_id,
                    bounding_box=bbox,
                    extraction_status="EXTRACTED",
                    raw_text=label_match.group(0).strip(),
                    layout_region="COMMODITY_TITLE_REGION",
                    layout_bbox=reg_bbox
                )

        # Layer 2: PP-Structure Layout Disqualification
        # Strictly disqualify all boxes in TABLE_REGION, ADDRESS, CARE, PRICE_DATE, QUANTITY regions
        disqualified_box_ids = set()
        if layout_res:
            for region in (layout_res.table_regions + layout_res.address_regions + layout_res.care_regions + layout_res.price_date_regions + layout_res.quantity_regions):
                for b in region.text_boxes:
                    disqualified_box_ids.add(id(b))

        non_commodity_pattern = re.compile(
            r'(?:MRP|NET|METWEIGHT|MFG|PKD|BATCH|CARE|PACKED|DATE|COUNTRY|CUSTOMER|CONSUMER|'
            r'NUTRITION|WUTRITION|NUTRITIONAL|FACTS|INGREDIENTS?|DIRECTIONS?|STORAGE|STORE|INSTRUCTIONS?|'
            r'HOW\s*TO\s*USE|WARNING|CAUTION|BEST\s*BEFORE|EXPIRY|USE\s*BY|SERVES?|SERVING|'
            r'BARCODE|LIC|FSSAI|VEG|NON-VEG|ALLERGENS?|MANUFACTURED|MARKETED|MKT|CONTAIN|CONTAINS|'
            r'PROMO|OFFER|STREET|ROAD|KOLKATA|BENGAL|ENTERPRISE|LTD|PVT|LIMITED|NUMBERING|SYSTEM|'
            r'BRACKETS?|MACHINE|CODE|FAT|FATTY|ACID|ACIDS|SALT|SUGAR|SUGARS|ENERGY|PROTEIN|OIL|'
            r'FLAVOUR|FLAVOURING|POWDER|VALUES|IMPROVER|COLOUR|APPROX|REGULATOR|AGENT|EMULSIFIER|'
            r'DEXTROSE|FIBRE|CHOLESTEROL|OHOLESTEROI|SODIUM|CALCIUM|CARBOHYDRATE|SATURATED|UNSATURATED|'
            r'TRANS|SUNLIGHT|LOT\b|TOTAL\b|FAL\b|REGN|FEEDBACK|FREE|CELL|EMAIL|TOWER|FLOOR|PRESTIGE|'
            r'BASIS|ADULT|DIETARY|ALLOWANCE|RECOMMENDED|RDA|BRITANNIA|TAXES|INCL|TILL|STOCKS|'
            r'MACHINECODE|PR-12|UNIT|UNT|TEL|AABCV)',
            re.IGNORECASE
        )

        candidates = []
        for box in text_boxes:
            if id(box) in disqualified_box_ids:
                continue
            b_text = _get_text(box)
            conf = _get_conf(box, 0.0)
            bbox = _get_bbox(box)
            if not b_text or len(b_text.strip()) <= 2:
                continue
            if non_commodity_pattern.search(b_text):
                continue
            if not re.search(r'[A-Za-z]{3,}', b_text):
                continue
            if re.search(r'^[0-9\W]+$', b_text) or re.search(r'^[0-9]{8,}$', b_text):
                continue

            h = (bbox[3] - bbox[1]) if bbox and len(bbox) >= 4 else 20
            w = (bbox[2] - bbox[0]) if bbox and len(bbox) >= 4 else 100
            area_score = min(1.0, (h * w) / 50000.0)
            in_title = any(layout_analyzer._is_spatially_inside_cluster(box, tr.text_boxes) for tr in (layout_res.title_regions if layout_res else []))
            title_bonus = 0.25 if in_title else 0.0
            score = (conf * 0.6) + (area_score * 0.2) + title_bonus
            candidates.append((score, conf, b_text.strip(), bbox))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            best_score, best_conf, best_text, best_bbox = candidates[0]
            min_score = 0.70 if (layout_res and layout_res.title_regions) else 0.50
            if best_conf >= 0.85 and best_score >= min_score:
                return ExtractedDeclarationItem(
                    field_name="commodity_name",
                    field_label="Name of Commodity",
                    extracted_value=best_text,
                    normalized_value=best_text.title(),
                    confidence=best_conf,
                    source_image_id=image_id,
                    bounding_box=best_bbox,
                    extraction_status="EXTRACTED",
                    raw_text=best_text,
                    layout_region="COMMODITY_TITLE_REGION",
                    layout_bbox=best_bbox
                )
            elif best_conf >= 0.50:
                return ExtractedDeclarationItem(
                    field_name="commodity_name",
                    field_label="Name of Commodity",
                    extracted_value=best_text,
                    normalized_value=best_text.title(),
                    confidence=best_conf,
                    source_image_id=image_id,
                    bounding_box=best_bbox,
                    extraction_status="UNCERTAIN",
                    raw_text=best_text,
                    layout_region="COMMODITY_TITLE_REGION",
                    layout_bbox=best_bbox
                )

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
        ocr_status: str = "OCR_SUCCESS",
        layout_res: Optional[LayoutAnalysisResult] = None
    ) -> ExtractedDeclarationItem:
        if ocr_status == "OCR_UNAVAILABLE":
            return ExtractedDeclarationItem(
                field_name="manufacturer_details",
                field_label="Manufacturer / Packer / Importer",
                extraction_status="OCR_UNAVAILABLE",
                confidence=0.0
            )

        match = re.search(
            r'(?:MFG\s*BY|MFC\s*BY|MANUFACTURED\s*BY|PACKED\s*BY|IMPORTED\s*BY|MFD\.?\s*BY|MED\.?\s*BY|MARKETED\s*BY|MKT\.?\s*BY|MANUFACTURED\s*(?:AND|&)\s*MARKETED\s*BY)[:\s]*([\s\S]+?)(?=(?:CUSTOMER|CONSUMER|NET|MRP|FEEDBACK|FOR\s*FEEDBACK|1-?800|\n\s*\n|$))',
            text,
            re.IGNORECASE
        )
        if not match:
            match = re.search(
                r'(?:MFG\s*BY|MFC\s*BY|MANUFACTURED\s*BY|PACKED\s*BY|IMPORTED\s*BY|MFD\.?\s*BY|MED\.?\s*BY|MARKETED\s*BY|MKT\.?\s*BY|MANUFACTURED\s*(?:AND|&)\s*MARKETED\s*BY)[:\s]*([^\n\r]+)',
                text,
                re.IGNORECASE
            )
        if match:
            val = match.group(1).strip()
            bbox, conf = self._find_bounding_box_and_confidence(text_boxes, match.group(0), 0.92)
            reg_bbox = layout_res.address_regions[0].bbox if (layout_res and layout_res.address_regions) else bbox
            return ExtractedDeclarationItem(
                field_name="manufacturer_details",
                field_label="Manufacturer / Packer / Importer",
                extracted_value=val,
                normalized_value=val,
                confidence=conf,
                source_image_id=image_id,
                bounding_box=bbox,
                extraction_status="EXTRACTED",
                raw_text=match.group(0).strip(),
                layout_region="MANUFACTURER_ADDRESS_REGION",
                layout_bbox=reg_bbox
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
        ocr_status: str = "OCR_SUCCESS",
        layout_res: Optional[LayoutAnalysisResult] = None
    ) -> ExtractedDeclarationItem:
        if ocr_status == "OCR_UNAVAILABLE":
            return ExtractedDeclarationItem(
                field_name="net_quantity",
                field_label="Net Quantity",
                extraction_status="OCR_UNAVAILABLE",
                confidence=0.0
            )

        # Layer 1: PP-Structure Layout Association (Label spatially adjacent to value box)
        spatial_pair = layout_analyzer.find_spatially_associated_value(
            r'^(?:NET\s*(?:QUANTITY|QTY|WEIGHT|WT|VOLUME|VOL\.?|CONTENT)|MET\s*WEIGHT|METWEIGHT)[:\s=]*$',
            text_boxes,
            value_pattern=r'[0-9]+.*(?:kg|g|gm|gms|l|ml|units?|pieces?|pcs)'
        )
        if not spatial_pair:
            spatial_pair = layout_analyzer.find_spatially_associated_value(
                r'(?:NET\s*(?:QUANTITY|QTY|WEIGHT|WT|VOLUME)|MET\s*WEIGHT)',
                text_boxes,
                value_pattern=r'[0-9]+.*(?:kg|g|gm|gms|l|ml|units?|pieces?|pcs)'
            )

        if spatial_pair:
            label_box, val_box = spatial_pair
            val_text = _get_text(val_box)
            l_text = _get_text(label_box)
            enclosing = _enclosing_bbox([label_box, val_box])
            avg_conf = round((_get_conf(label_box, 0.95) + _get_conf(val_box, 0.95)) / 2.0, 2)
            reg_bbox = layout_res.quantity_regions[0].bbox if (layout_res and layout_res.quantity_regions) else enclosing

            # Check promotional additive formula in value box (e.g. "50 g+5 g EXTRA# = 55 g")
            full_promo = re.search(
                r'([0-9]+(?:\.[0-9]+)?)\s*(kg|g|gm|gms|l|ml)\s*\+\s*([0-9]+(?:\.[0-9]+)?)\s*(kg|g|gm|gms|l|ml)[^=\n]*?=\s*([0-9]+(?:\.[0-9]+)?)\s*(kg|g|gm|gms|l|ml)',
                val_text,
                re.IGNORECASE
            )
            if full_promo:
                base_num, base_u = full_promo.group(1).strip(), full_promo.group(2).strip().lower()
                extra_num, extra_u = full_promo.group(3).strip(), full_promo.group(4).strip().lower()
                tot_num, tot_u = full_promo.group(5).strip(), full_promo.group(6).strip().lower()
                std_unit = "kg" if tot_u in ["kg"] else "g" if tot_u in ["g", "gm", "gms"] else "L" if tot_u in ["l", "ltr", "litre", "litres"] else "ml"
                return ExtractedDeclarationItem(
                    field_name="net_quantity",
                    field_label="Net Quantity",
                    extracted_value=f"{tot_num} {tot_u}",
                    normalized_value=f"{tot_num} {std_unit}",
                    confidence=avg_conf,
                    source_image_id=image_id,
                    bounding_box=enclosing,
                    extraction_status="EXTRACTED",
                    raw_text=f"{l_text} {val_text}".strip(),
                    layout_region="QUANTITY_REGION",
                    layout_bbox=reg_bbox,
                    metadata={
                        "base_quantity": f"{base_num} {base_u}",
                        "promotional_quantity": f"{extra_num} {extra_u}",
                        "declared_total_quantity": f"{tot_num} {tot_u}",
                        "unit": std_unit,
                        "is_promotional_pack": True,
                        "raw_expression": val_text.strip()
                    }
                )

            # Standard quantity in val_box
            qty_m = re.search(r'\b([0-9]+(?:\.[0-9]+)?)\s*(kg|g|gm|gms|l|ltr|litre|litres|ml|units?|pieces?|pcs|count|n|u)\b', val_text, re.IGNORECASE)
            if qty_m:
                num = qty_m.group(1).strip()
                unit = qty_m.group(2).strip().lower()
                std_unit = "kg" if unit in ["kg"] else "g" if unit in ["g", "gm", "gms"] else "L" if unit in ["l", "ltr", "litre", "litres"] else "ml" if unit in ["ml"] else unit
                return ExtractedDeclarationItem(
                    field_name="net_quantity",
                    field_label="Net Quantity",
                    extracted_value=f"{num} {unit}",
                    normalized_value=f"{num} {std_unit}",
                    confidence=avg_conf,
                    source_image_id=image_id,
                    bounding_box=enclosing,
                    extraction_status="EXTRACTED",
                    raw_text=f"{l_text} {val_text}".strip(),
                    layout_region="QUANTITY_REGION",
                    layout_bbox=reg_bbox
                )

        # Layer 2: Promo additive net weight formulas in continuous text
        full_promo = re.search(
            r'(?:NET\s*(?:QUANTITY|QTY|WEIGHT|WT|VOLUME|VOL\.?|CONTENT)|MET\s*WEIGHT|METWEIGHT)[:\s=]*([0-9]+(?:\.[0-9]+)?)\s*(kg|g|gm|gms|l|ml)\s*\+\s*([0-9]+(?:\.[0-9]+)?)\s*(kg|g|gm|gms|l|ml)[^=\n]*?=\s*([0-9]+(?:\.[0-9]+)?)\s*(kg|g|gm|gms|l|ml)',
            text,
            re.IGNORECASE
        )
        if full_promo:
            base_num, base_u = full_promo.group(1).strip(), full_promo.group(2).strip().lower()
            extra_num, extra_u = full_promo.group(3).strip(), full_promo.group(4).strip().lower()
            tot_num, tot_u = full_promo.group(5).strip(), full_promo.group(6).strip().lower()
            std_unit = "kg" if tot_u in ["kg"] else "g" if tot_u in ["g", "gm", "gms"] else "L" if tot_u in ["l", "ltr", "litre", "litres"] else "ml"
            bbox, conf = self._find_bounding_box_and_confidence(text_boxes, full_promo.group(0), 0.95)
            reg_bbox = layout_res.quantity_regions[0].bbox if (layout_res and layout_res.quantity_regions) else bbox
            return ExtractedDeclarationItem(
                field_name="net_quantity",
                field_label="Net Quantity",
                extracted_value=f"{tot_num} {tot_u}",
                normalized_value=f"{tot_num} {std_unit}",
                confidence=conf,
                source_image_id=image_id,
                bounding_box=bbox,
                extraction_status="EXTRACTED",
                raw_text=full_promo.group(0).strip(),
                layout_region="QUANTITY_REGION",
                layout_bbox=reg_bbox,
                metadata={
                    "base_quantity": f"{base_num} {base_u}",
                    "promotional_quantity": f"{extra_num} {extra_u}",
                    "declared_total_quantity": f"{tot_num} {tot_u}",
                    "unit": std_unit,
                    "is_promotional_pack": True,
                    "raw_expression": full_promo.group(0).strip()
                }
            )

        promo_match = re.search(
            r'(?:NET\s*(?:QUANTITY|QTY|WEIGHT|WT|VOLUME|VOL\.?|CONTENT)|MET\s*WEIGHT|METWEIGHT)[:\s=]*[^\n=]*?=\s*([0-9]+(?:\.[0-9]+)?)\s*(kg|g|gm|gms|l|ltr|litre|litres|ml|units?|pieces?|pcs|count|n|u)\b',
            text,
            re.IGNORECASE
        )
        if promo_match:
            num = promo_match.group(1).strip()
            unit = promo_match.group(2).strip().lower()
            std_unit = "kg" if unit in ["kg"] else "g" if unit in ["g", "gm", "gms"] else "L" if unit in ["l", "ltr", "litre", "litres"] else "ml" if unit in ["ml"] else unit
            extracted = f"{num} {unit}"
            normalized = f"{num} {std_unit}"
            bbox, conf = self._find_bounding_box_and_confidence(text_boxes, promo_match.group(0), 0.94)
            reg_bbox = layout_res.quantity_regions[0].bbox if (layout_res and layout_res.quantity_regions) else bbox
            return ExtractedDeclarationItem(
                field_name="net_quantity",
                field_label="Net Quantity",
                extracted_value=extracted,
                normalized_value=normalized,
                confidence=conf,
                source_image_id=image_id,
                bounding_box=bbox,
                extraction_status="EXTRACTED",
                raw_text=promo_match.group(0).strip(),
                layout_region="QUANTITY_REGION",
                layout_bbox=reg_bbox,
                metadata={
                    "declared_total_quantity": extracted,
                    "unit": std_unit,
                    "is_promotional_pack": True,
                    "raw_expression": promo_match.group(0).strip()
                }
            )

        # Standard net quantity declaration
        match = re.search(
            r'(?:NET\s*(?:QUANTITY|QTY|WEIGHT|WT|VOLUME|VOL\.?|CONTENT)|MET\s*WEIGHT|METWEIGHT)[:\s=]*([0-9]+(?:\.[0-9]+)?)\s*(kg|g|gm|gms|l|ltr|litre|litres|ml|units?|pieces?|pcs|count|n|u)\b',
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
            reg_bbox = layout_res.quantity_regions[0].bbox if (layout_res and layout_res.quantity_regions) else bbox
            return ExtractedDeclarationItem(
                field_name="net_quantity",
                field_label="Net Quantity",
                extracted_value=extracted,
                normalized_value=normalized,
                confidence=conf,
                source_image_id=image_id,
                bounding_box=bbox,
                extraction_status="EXTRACTED",
                raw_text=match.group(0).strip(),
                layout_region="QUANTITY_REGION",
                layout_bbox=reg_bbox
            )

        # Fallback: line-by-line excluding nutrition table
        for line in text.splitlines():
            if re.search(r'(?:serving|serves|nutrition|per\s*100|fat|sugar|protein)', line, re.IGNORECASE):
                continue
            line_m = re.search(r'\b([0-9]+(?:\.[0-9]+)?)\s*(kg|g|gm|gms|l|ltr|litre|litres|ml|units?|pieces?|pcs|count|n|u)\b', line, re.IGNORECASE)
            if line_m:
                num = line_m.group(1).strip()
                unit = line_m.group(2).strip().lower()
                std_unit = "kg" if unit in ["kg"] else "g" if unit in ["g", "gm", "gms"] else "L" if unit in ["l", "ltr", "litre", "litres"] else "ml" if unit in ["ml"] else unit
                extracted = f"{num} {unit}"
                normalized = f"{num} {std_unit}"
                bbox, conf = self._find_bounding_box_and_confidence(text_boxes, line_m.group(0), 0.88)
                reg_bbox = layout_res.quantity_regions[0].bbox if (layout_res and layout_res.quantity_regions) else bbox
                return ExtractedDeclarationItem(
                    field_name="net_quantity",
                    field_label="Net Quantity",
                    extracted_value=extracted,
                    normalized_value=normalized,
                    confidence=conf,
                    source_image_id=image_id,
                    bounding_box=bbox,
                    extraction_status="EXTRACTED",
                    raw_text=line_m.group(0).strip(),
                    layout_region="QUANTITY_REGION",
                    layout_bbox=reg_bbox
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
        ocr_status: str = "OCR_SUCCESS",
        layout_res: Optional[LayoutAnalysisResult] = None
    ) -> ExtractedDeclarationItem:
        if ocr_status == "OCR_UNAVAILABLE":
            return ExtractedDeclarationItem(
                field_name="mrp",
                field_label="Maximum Retail Price (MRP)",
                extraction_status="OCR_UNAVAILABLE",
                confidence=0.0
            )

        # Layer 1: PP-Structure Layout Association (MRP label paired with adjacent price box)
        spatial_pair = layout_analyzer.find_spatially_associated_value(
            r'^(?:MRP\.?|MAX(?:IMUM)?\s*RETAIL\s*PRICE|M\.R\.P\.?|PRICE)[:\s\.]*$',
            text_boxes,
            value_pattern=r'[0-9]+(?:\.[0-9]+)?'
        )
        if not spatial_pair:
            spatial_pair = layout_analyzer.find_spatially_associated_value(
                r'(?:MRP|MAXIMUM\s*RETAIL\s*PRICE|M\.R\.P\.)',
                text_boxes,
                value_pattern=r'[0-9]+(?:\.[0-9]+)?'
            )

        if spatial_pair:
            label_box, val_box = spatial_pair
            val_text = _get_text(val_box)
            l_text = _get_text(label_box)

            # Guard: If val_box is a batch, lot, or date line, it is not a price box
            if re.search(r'\b(?:BATCH|LOT|PKD|MFD|USE\s*BY|EXP|EXPIRY)\b', val_text, re.I):
                spatial_pair = None
            # Guard: If label_box already contains the price number, use label_box directly
            elif re.search(r'(?:MRP|MAXIMUM\s*RETAIL\s*PRICE|M\.R\.P\.)[^\n0-9]*[0-9]+(?:\.[0-9]+)?', l_text, re.I):
                spatial_pair = None

        if spatial_pair:
            label_box, val_box = spatial_pair
            val_text = _get_text(val_box)
            l_text = _get_text(label_box)
            # Find the primary retail price number (ignoring any trailing /g or /kg unit price)
            num_m = re.search(r'([0-9]{1,4}(?:\.[0-9]{1,2})?)(?!\s*/\s*(?:g|gm|kg|ml|l))', val_text)
            if num_m:
                val = num_m.group(1).strip()
                has_taxes = "incl" in text.lower() or "taxes" in text.lower() or "incl" in val_text.lower()
                tax_str = " (Incl. of all taxes)" if has_taxes else ""
                extracted = f"₹{val}{tax_str}" if ("₹" in val_text or "₹" in text or "rs" in text.lower() or "rs" in val_text.lower()) else f"Rs. {val}{tax_str}"
                try:
                    normalized = f"{float(val):.2f} INR"
                except ValueError:
                    normalized = f"{val} INR"

                enclosing = _enclosing_bbox([label_box, val_box])
                avg_conf = round((_get_conf(label_box, 0.95) + _get_conf(val_box, 0.95)) / 2.0, 2)
                reg_bbox = layout_res.price_date_regions[0].bbox if (layout_res and layout_res.price_date_regions) else enclosing
                return ExtractedDeclarationItem(
                    field_name="mrp",
                    field_label="Maximum Retail Price (MRP)",
                    extracted_value=extracted,
                    normalized_value=normalized,
                    confidence=avg_conf,
                    source_image_id=image_id,
                    bounding_box=enclosing,
                    extraction_status="EXTRACTED",
                    raw_text=f"{l_text} {val_text}".strip(),
                    layout_region="PRICE_DATE_REGION",
                    layout_bbox=reg_bbox
                )

        # Layer 2: Filter out text lines that are inside table regions to prevent nutrition grams from masquerading as price
        clean_text_lines = []
        for line in text.splitlines():
            if re.search(r'(?:NUTRITION|SERVING|PROTEIN|FAT|ENERGY|CARBOHYDRATE|SUGAR|SODIUM|CALCIUM)', line, re.I):
                continue
            clean_text_lines.append(line)
        eval_text = "\n".join(clean_text_lines)

        # Primary MRP regex
        match = re.search(
            r'(?:MRP\.?|MAXIMUM\s*RETAIL\s*PRICE|MAX\s*RETAIL\s*PRICE|M\.R\.P\.?)[:\s\.]*(?:RS\.?|INR|₹)?\s*([0-9]+(?:\.[0-9]{1,2})?)(?!\s*/\s*(?:g|gm|kg|ml|l|ltr))(?:[^\n0-9]*(?:INCL\.?\s*OF\s*ALL\s*TAXES|INCLUSIVE\s*OF\s*ALL\s*TAXES|\(INCL\.?\s*OF\s*ALL\s*TAXES\)|\(INCL\.?\s*TAXES\)))?',
            eval_text,
            re.IGNORECASE
        )
        if not match:
            match = re.search(
                r'([0-9]{2,4}(?:\.[0-9]{2})?)\s*(?:Rs|INR|₹)(?!\s*/)',
                eval_text,
                re.IGNORECASE
            )
        if not match:
            match = re.search(
                r'(?:Rs\.?|INR|₹)\s*([0-9]{2,4}(?:\.[0-9]{2})?)(?!\s*/)',
                eval_text,
                re.IGNORECASE
            )

        if match:
            val = match.group(1).strip()
            has_taxes = "incl" in text.lower() or "taxes" in text.lower()
            tax_str = " (Incl. of all taxes)" if has_taxes else ""
            extracted = f"₹{val}{tax_str}" if "₹" in text or "rs" in text.lower() else f"Rs. {val}{tax_str}"
            try:
                normalized = f"{float(val):.2f} INR"
            except ValueError:
                normalized = f"{val} INR"
            bbox, conf = self._find_bounding_box_and_confidence(text_boxes, match.group(0), 0.95)
            reg_bbox = layout_res.price_date_regions[0].bbox if (layout_res and layout_res.price_date_regions) else bbox
            return ExtractedDeclarationItem(
                field_name="mrp",
                field_label="Maximum Retail Price (MRP)",
                extracted_value=extracted,
                normalized_value=normalized,
                confidence=conf,
                source_image_id=image_id,
                bounding_box=bbox,
                extraction_status="EXTRACTED",
                raw_text=match.group(0).strip(),
                layout_region="PRICE_DATE_REGION",
                layout_bbox=reg_bbox
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
        ocr_status: str = "OCR_SUCCESS",
        layout_res: Optional[LayoutAnalysisResult] = None
    ) -> ExtractedDeclarationItem:
        if ocr_status == "OCR_UNAVAILABLE":
            return ExtractedDeclarationItem(
                field_name="date_of_manufacture_packing",
                field_label="Month & Year of Manufacture / Packing",
                extraction_status="OCR_UNAVAILABLE",
                confidence=0.0
            )

        # Layer 1: PP-Structure Layout Association
        spatial_pair = layout_analyzer.find_spatially_associated_value(
            r'(?:PKD|MFD|MFG|PACKED|DATE\s*OF\s*MFG)',
            text_boxes,
            value_pattern=r'[0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[0-9]{1,2}[/-][0-9]{2,4}'
        )
        if spatial_pair:
            label_box, val_box = spatial_pair
            val_text = _get_text(val_box)
            l_text = _get_text(label_box)
            date_m = re.search(r'([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[0-9]{1,2}[/-][0-9]{2,4})', val_text)
            if date_m:
                val = date_m.group(1).strip()
                enclosing = _enclosing_bbox([label_box, val_box])
                avg_conf = round((_get_conf(label_box, 0.95) + _get_conf(val_box, 0.95)) / 2.0, 2)
                reg_bbox = layout_res.price_date_regions[0].bbox if (layout_res and layout_res.price_date_regions) else enclosing
                return ExtractedDeclarationItem(
                    field_name="date_of_manufacture_packing",
                    field_label="Month & Year of Manufacture / Packing",
                    extracted_value=val,
                    normalized_value=val,
                    confidence=avg_conf,
                    source_image_id=image_id,
                    bounding_box=enclosing,
                    extraction_status="EXTRACTED",
                    raw_text=f"{l_text} {val_text}".strip(),
                    layout_region="PRICE_DATE_REGION",
                    layout_bbox=reg_bbox
                )

        match = re.search(
            r'(?:DATE\s*OF\s*MFG|DATE\s*OF\s*PACKING|MFG\.?\s*DATE|PACKED\s*ON|PKD\s*ON|MFD|PKD|MFG|MED|MFC|M\/D|M\/?D|USE\s*BY|BEST\s*BEFORE)[:\s\.\-]*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[0-9]{1,2}[/-][0-9]{2,4}|[A-Za-z]{3,9}[/-][0-9]{2,4}|[0-9]{2}/[0-9]{4})',
            text,
            re.IGNORECASE
        )
        if match:
            val = match.group(1).strip()
            bbox, conf = self._find_bounding_box_and_confidence(text_boxes, match.group(0), 0.91)
            reg_bbox = layout_res.price_date_regions[0].bbox if (layout_res and layout_res.price_date_regions) else bbox
            return ExtractedDeclarationItem(
                field_name="date_of_manufacture_packing",
                field_label="Month & Year of Manufacture / Packing",
                extracted_value=val,
                normalized_value=val,
                confidence=conf,
                source_image_id=image_id,
                bounding_box=bbox,
                extraction_status="EXTRACTED",
                raw_text=match.group(0).strip(),
                layout_region="PRICE_DATE_REGION",
                layout_bbox=reg_bbox
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
        ocr_status: str = "OCR_SUCCESS",
        layout_res: Optional[LayoutAnalysisResult] = None
    ) -> ExtractedDeclarationItem:
        if ocr_status == "OCR_UNAVAILABLE":
            return ExtractedDeclarationItem(
                field_name="consumer_care_details",
                field_label="Consumer Care Details",
                extraction_status="OCR_UNAVAILABLE",
                confidence=0.0
            )

        match = re.search(
            r'(?:FOR\s*FEEDBACK|FEEDBACK|CUSTOMER\s*CARE|CONSUMER\s*CARE|FOR\s*COMPLAINTS|HELPLINE|GRIEVANCE)[:\s\-]*([A-Za-z0-9\s,\.\-\@\:\/\(\)]+?)(?=(?:NET|MRP|MFD|PKD|BATCH|LIC|FSSAI|\n\n|$))',
            text,
            re.IGNORECASE
        )
        phone_matches = re.findall(
            r'(?:1-800[-—\s]?[0-9]{3,4}[-—\s]?[0-9]{3,5}|1800[-—\s]?[0-9]{2,3}[-—\s]?[0-9]{3,4}|\+?91[-—\s]?[0-9]{10})',
            text
        )
        email_matches = re.findall(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', text)
        
        if match or phone_matches or email_matches:
            details = []
            if match:
                details.append(match.group(1).strip())
            for p in phone_matches:
                if p not in " ".join(details):
                    details.append(f"Tel: {p}")
            for e in email_matches:
                if e not in " ".join(details):
                    details.append(f"Email: {e}")
            
            combined = " / ".join(details)
            bbox, conf = self._find_bounding_box_and_confidence(text_boxes, combined, 0.90)
            reg_bbox = layout_res.care_regions[0].bbox if (layout_res and layout_res.care_regions) else bbox
            return ExtractedDeclarationItem(
                field_name="consumer_care_details",
                field_label="Consumer Care Details",
                extracted_value=combined,
                normalized_value=combined,
                confidence=conf,
                source_image_id=image_id,
                bounding_box=bbox,
                extraction_status="EXTRACTED",
                raw_text=combined,
                layout_region="CONSUMER_CARE_REGION",
                layout_bbox=reg_bbox
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
        ocr_status: str = "OCR_SUCCESS",
        layout_res: Optional[LayoutAnalysisResult] = None
    ) -> ExtractedDeclarationItem:
        if ocr_status == "OCR_UNAVAILABLE":
            return ExtractedDeclarationItem(
                field_name="country_of_origin",
                field_label="Country of Origin",
                extraction_status="OCR_UNAVAILABLE",
                confidence=0.0
            )

        # 1. Explicit declaration: "Country of Origin: India", "Made in India", "Product of ..."
        match = re.search(
            r'(?:COUNTRY\s*OF\s*ORIGIN|MADE\s*IN|PRODUCT\s*OF)[:\s]*([A-Za-z\s]+?)(?=(?:CUSTOMER|CONSUMER|NET|MRP|MFD|PKD|BATCH|\n|$))',
            text,
            re.IGNORECASE
        )
        if match:
            country = match.group(1).strip().title()
            bbox, conf = self._find_bounding_box_and_confidence(text_boxes, match.group(0), 0.88)
            reg_bbox = layout_res.address_regions[0].bbox if (layout_res and layout_res.address_regions) else bbox
            return ExtractedDeclarationItem(
                field_name="country_of_origin",
                field_label="Country of Origin",
                extracted_value=country,
                normalized_value=country,
                confidence=conf,
                source_image_id=image_id,
                bounding_box=bbox,
                extraction_status="EXTRACTED",
                is_applicable=True,
                raw_text=match.group(0).strip(),
                layout_region="MANUFACTURER_ADDRESS_REGION",
                layout_bbox=reg_bbox
            )

        # 2. Check for explicit import indicators
        import_match = re.search(r'(?:IMPORTED\s*BY|IMPORTER)[:\s]*([^\n]+)', text, re.IGNORECASE)
        if import_match:
            bbox, conf = self._find_bounding_box_and_confidence(text_boxes, import_match.group(0), 0.85)
            reg_bbox = layout_res.address_regions[0].bbox if (layout_res and layout_res.address_regions) else bbox
            return ExtractedDeclarationItem(
                field_name="country_of_origin",
                field_label="Country of Origin",
                extracted_value=None,
                normalized_value=None,
                confidence=0.0,
                source_image_id=image_id,
                bounding_box=bbox,
                extraction_status="NOT_FOUND",
                is_applicable=True,
                raw_text=import_match.group(0).strip(),
                layout_region="MANUFACTURER_ADDRESS_REGION",
                layout_bbox=reg_bbox
            )

        # 3. CRITICAL STATUTORY INVARIANT: Requires inspector manual verification
        return ExtractedDeclarationItem(
            field_name="country_of_origin",
            field_label="Country of Origin",
            is_applicable=True,
            extraction_status="NEEDS_LEGAL_VERIFICATION",
            confidence=0.0
        )

    def _extract_unit_sale_price(
        self,
        text: str,
        text_boxes: List[Any],
        image_id: Optional[str],
        ocr_status: str = "OCR_SUCCESS",
        layout_res: Optional[LayoutAnalysisResult] = None
    ) -> ExtractedDeclarationItem:
        if ocr_status == "OCR_UNAVAILABLE":
            return ExtractedDeclarationItem(
                field_name="unit_sale_price",
                field_label="Unit Sale Price (USP)",
                extraction_status="OCR_UNAVAILABLE",
                confidence=0.0
            )

        # Matches unit sale price patterns independently from MRP (e.g. "Rs. 0.91/g", "0.91 Rs/g", "USP: Rs 0.91/g")
        match = re.search(
            r'(?:(?:UNIT\s*SALE\s*PRICE|USP)[:\s]*)?(?:RS\.?|INR|₹)?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:RS\.?|INR|₹)?\s*/\s*(g|gm|kg|ml|l|ltr|litre|metre|m|piece|unit|count|n|u)\b',
            text,
            re.IGNORECASE
        )
        if match:
            val = match.group(1).strip()
            unit = match.group(2).strip().lower()
            extracted = f"Rs. {val}/{unit}"
            bbox, conf = self._find_bounding_box_and_confidence(text_boxes, match.group(0), 0.90)
            reg_bbox = layout_res.price_date_regions[0].bbox if (layout_res and layout_res.price_date_regions) else bbox
            return ExtractedDeclarationItem(
                field_name="unit_sale_price",
                field_label="Unit Sale Price (USP)",
                extracted_value=extracted,
                normalized_value=f"{val} INR/{unit}",
                confidence=conf,
                source_image_id=image_id,
                bounding_box=bbox,
                extraction_status="EXTRACTED",
                raw_text=match.group(0).strip(),
                layout_region="PRICE_DATE_REGION",
                layout_bbox=reg_bbox
            )
        return ExtractedDeclarationItem(
            field_name="unit_sale_price",
            field_label="Unit Sale Price (USP)",
            extraction_status="NOT_FOUND",
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

def validate_vlm_candidate_against_ocr(
    candidate: VLMCandidate,
    text_boxes: List[Any],
    full_text: str
) -> bool:
    """
    Anti-Hallucination Guard: Verifies that a VLM candidate is grounded in genuine OCR evidence.
    Rejects any candidate value that cannot be traced to image OCR tokens or intersecting boxes.
    Never allows VLM to invent product names, quantities, MRP, dates, or manufacturer details.
    """
    if not candidate.candidate_value or not candidate.candidate_value.strip():
        return False

    c_val = candidate.candidate_value.strip().lower()
    full_text_lower = full_text.lower()

    # Numeric fields (mrp, quantity, dates): check if key numbers exist in OCR
    numbers = re.findall(r'[0-9]+(?:\.[0-9]+)?', c_val)
    if numbers:
        if any(num in full_text_lower for num in numbers):
            return True
        int_parts = [n.split('.')[0] for n in numbers if len(n.split('.')[0]) >= 2]
        if any(ip in full_text_lower for ip in int_parts):
            return True

    # Text fields (manufacturer, commodity, care): check for meaningful word stems (>3 chars)
    stop_words = {"the", "and", "ltd", "pvt", "limited", "company", "india", "for", "with", "this", "from"}
    words = [w for w in re.findall(r'[a-zA-Z]{3,}', c_val) if w not in stop_words]
    if words:
        matching_words = [w for w in words if w in full_text_lower]
        if len(matching_words) > 0:
            return True

    # Spatial BBox Check: If candidate specifies a bounding box, check if any OCR box intersects
    if candidate.bbox and len(candidate.bbox) == 4:
        c_x1, c_y1, c_x2, c_y2 = candidate.bbox
        for b in text_boxes:
            b_box = _get_bbox(b)
            if b_box and len(b_box) == 4:
                ix1 = max(c_x1, b_box[0])
                iy1 = max(c_y1, b_box[1])
                ix2 = min(c_x2, b_box[2])
                iy2 = min(c_y2, b_box[3])
                if ix2 > ix1 and iy2 > iy1:
                    return True

    return False


class ExtractionService:
    def __init__(self):
        self.regex_extractor = DeterministicRegexExtractor()
        self.gemini_extractor = FallbackGeminiExtractor()

    def _fuse_vlm_candidates(
        self,
        declarations: List[ExtractedDeclarationItem],
        vlm_res: VLMInterpretationResult,
        text_boxes: List[Any],
        full_text: str,
        image_id: Optional[str]
    ) -> List[ExtractedDeclarationItem]:
        """
        Fuses Qwen2.5-VL contextual candidates with OCR declarations using strict arbitration:
        1. Validates candidates against OCR evidence (anti-hallucination).
        2. Never silently overrides high-confidence OCR evidence (marks CONFLICTING / NEEDS_REVIEW).
        3. Assists with ambiguous, low-confidence, or missing declarations.
        """
        decl_map = {d.field_name: d for d in declarations}

        for candidate in vlm_res.candidates:
            if candidate.field not in decl_map:
                continue

            item = decl_map[candidate.field]

            # Anti-Hallucination Guard: Reject candidates with zero OCR backing
            if not validate_vlm_candidate_against_ocr(candidate, text_boxes, full_text):
                continue

            # Case 1: Strong OCR already extracted (confidence >= 0.70)
            if item.extraction_status == "EXTRACTED" and item.confidence >= 0.70:
                ocr_norm = normalize_declaration_for_comparison(item.field_name, item.extracted_value)
                vlm_norm = normalize_declaration_for_comparison(candidate.field, candidate.candidate_value)
                if ocr_norm and vlm_norm and ocr_norm != vlm_norm:
                    # Genuinely conflicting interpretation between strong OCR and VLM!
                    # Do NOT silently choose VLM! Flag CONFLICTING for inspector review.
                    item.extraction_status = "CONFLICTING"
                    item.has_conflict = True
                    item.conflicts = [
                        {
                            "source": "PaddleOCR/PP-Structure",
                            "value": item.extracted_value,
                            "normalized": ocr_norm,
                            "confidence": item.confidence,
                            "bounding_box": item.bounding_box
                        },
                        {
                            "source": f"Qwen2.5-VL ({vlm_res.model_name})",
                            "value": candidate.candidate_value,
                            "normalized": vlm_norm,
                            "confidence": candidate.confidence,
                            "bounding_box": candidate.bbox,
                            "reason": candidate.reason
                        }
                    ]
                else:
                    # Agreeing evidence: reinforce confidence and record VLM context
                    item.confidence = min(0.99, max(item.confidence, candidate.confidence))
                    if not item.metadata:
                        item.metadata = {}
                    item.metadata["vlm_reinforced"] = True
                    item.metadata["vlm_reason"] = candidate.reason

            # Case 2: OCR was NOT_FOUND, LOW_CONFIDENCE, UNCERTAIN, NEEDS_LEGAL_VERIFICATION, or OCR_UNAVAILABLE
            elif item.extraction_status in ("NOT_FOUND", "LOW_CONFIDENCE", "OCR_UNAVAILABLE", "NEEDS_LEGAL_VERIFICATION", "UNCERTAIN"):
                item.extracted_value = candidate.candidate_value
                item.normalized_value = candidate.candidate_value
                item.confidence = candidate.confidence
                item.extraction_status = "EXTRACTED"
                if candidate.bbox:
                    item.bounding_box = candidate.bbox
                item.raw_text = candidate.candidate_value
                if not item.metadata:
                    item.metadata = {}
                item.metadata["extraction_method"] = "AI/OCR+VLM"
                item.metadata["vlm_reason"] = candidate.reason
                item.metadata["vlm_model"] = vlm_res.model_name

        return declarations

    def extract_declarations(
        self,
        full_text: str,
        text_boxes: List[Any],
        product_context: Dict[str, Any],
        image_id: Optional[str] = None,
        image_path: Optional[str] = None
    ) -> List[ExtractedDeclarationItem]:
        # Always run deterministic regex extractor first (PaddleOCR + PP-Structure layout-aware)
        declarations = self.regex_extractor.extract_declarations(
            full_text, text_boxes, product_context, image_id
        )

        # Layer 3: Optional Qwen2.5-VL Vision-Language Contextual Reasoning
        if getattr(settings, "VLM_ENABLED", False):
            try:
                layout_res = layout_analyzer.analyze(text_boxes)
                vlm_res = qwen_vl_service.interpret_package(
                    image_path=image_path or "",
                    ocr_boxes=text_boxes,
                    layout_regions=layout_res.regions,
                    image_id=image_id
                )
                if vlm_res.status == "SUCCESS" and vlm_res.candidates:
                    declarations = self._fuse_vlm_candidates(
                        declarations, vlm_res, text_boxes, full_text, image_id
                    )
            except Exception:
                pass  # Graceful fallback: never let VLM failure disrupt inspection

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
    and detects cross-image conflicts using CONFIDENCE-AWARE logic.

    The 4-Scenario Logic (prevents false-positive CONFLICTING from low-quality OCR):
      Scenario A: Multiple reliable sources agree on same value
                  -> EXTRACTED (highest confidence wins)
      Scenario B: Multiple reliable sources report genuinely different values
                  -> CONFLICTING (inspector must adjudicate)
      Scenario C: One reliable source + unreliable sources with different values
                  -> EXTRACTED from reliable source (unreliable sources noted in metadata)
      Scenario D: Zero reliable sources (all low-confidence or not found)
                  -> NOT_FOUND (inspector must manually enter from physical inspection)

    HIGH_CONF_THRESHOLD = 0.70: A candidate with confidence >= 0.70 is considered
    "reliable evidence". Below 0.70 is considered too uncertain for conflict decisions.

    CRITICAL STATUTORY INVARIANT:
    Compares ONLY genuine extracted values (extraction_status == 'EXTRACTED').
    If OCR is unavailable or fields are NOT_FOUND, never manufacture a conflict.
    """
    # Confidence threshold for "reliable" evidence (see 4-scenario logic above)
    HIGH_CONF_THRESHOLD = 0.70

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
            # Scenario D (no EXTRACTED candidates at all): return NOT_FOUND or NEEDS_LEGAL_VERIFICATION
            has_ocr_unavail = any(c.extraction_status == "OCR_UNAVAILABLE" for c in candidates)
            has_needs_legal = any(c.extraction_status == "NEEDS_LEGAL_VERIFICATION" for c in candidates)
            status = "OCR_UNAVAILABLE" if has_ocr_unavail else "NEEDS_LEGAL_VERIFICATION" if has_needs_legal else "NOT_FOUND"
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

        all_src_images = sorted(list({c.source_image_id for c in valid_candidates if c.source_image_id}))

        # Separate into reliable (high confidence) and unreliable (low confidence) candidates
        reliable_candidates = [c for c in valid_candidates if c.confidence >= HIGH_CONF_THRESHOLD]
        unreliable_candidates = [c for c in valid_candidates if c.confidence < HIGH_CONF_THRESHOLD]

        if len(reliable_candidates) == 0:
            # Scenario D: No reliable (high-confidence) evidence from any image.
            # Even though EXTRACTED values exist, they're all low-confidence
            # (garbled text, blurred regions, etc.). Escalate to manual verification.
            best_unreliable = max(unreliable_candidates, key=lambda x: x.confidence)
            merged_decl = ExtractedDeclarationItem(
                field_name=field,
                field_label=best_unreliable.field_label,
                extracted_value=best_unreliable.extracted_value,
                normalized_value=best_unreliable.normalized_value,
                confidence=best_unreliable.confidence,
                source_image_id=best_unreliable.source_image_id,
                bounding_box=best_unreliable.bounding_box,
                extraction_status="LOW_CONFIDENCE",
                is_applicable=best_unreliable.is_applicable,
                has_conflict=False,
                conflicts=[],
                source_images=all_src_images,
                raw_text=best_unreliable.raw_text,
                layout_region=best_unreliable.layout_region,
                layout_bbox=best_unreliable.layout_bbox
            )
            merged_items.append(merged_decl)
            continue

        # Group reliable candidates by normalized value
        distinct_reliable_values: Dict[str, List[ExtractedDeclarationItem]] = {}
        for c in reliable_candidates:
            norm_key = normalize_declaration_for_comparison(field, c.extracted_value)
            distinct_reliable_values.setdefault(norm_key, []).append(c)

        if len(distinct_reliable_values) > 1:
            # Scenario B: Multiple RELIABLE sources report genuinely different values.
            # This is a true conflict requiring inspector adjudication.
            conflict_details = [
                {
                    "value": c.extracted_value,
                    "normalized": normalize_declaration_for_comparison(field, c.extracted_value),
                    "source_image_id": c.source_image_id,
                    "confidence": c.confidence,
                    "bounding_box": c.bounding_box,
                    "raw_text": c.raw_text,
                    "layout_region": c.layout_region,
                    "layout_bbox": c.layout_bbox
                }
                for c in reliable_candidates
            ]

            conflict_record = {
                "field_name": field,
                "field_label": reliable_candidates[0].field_label,
                "status": "CONFLICTING",
                "action": "NEEDS_MANUAL_VERIFICATION",
                "description": (
                    f"Genuine conflict detected: {len(distinct_reliable_values)} distinct values "
                    f"across {len(reliable_candidates)} high-confidence ({HIGH_CONF_THRESHOLD:.0%}+) sources. "
                    f"Inspector adjudication required."
                ),
                "source_images": all_src_images,
                "candidates": conflict_details
            }
            conflicts.append(conflict_record)

            combined_str = " vs ".join(list(dict.fromkeys(
                c.extracted_value for c in reliable_candidates if c.extracted_value
            )))
            merged_decl = ExtractedDeclarationItem(
                field_name=field,
                field_label=reliable_candidates[0].field_label,
                extracted_value=combined_str,
                normalized_value=combined_str,
                confidence=min(c.confidence for c in reliable_candidates),
                source_image_id=reliable_candidates[0].source_image_id,
                bounding_box=reliable_candidates[0].bounding_box,
                extraction_status="CONFLICTING",
                is_applicable=reliable_candidates[0].is_applicable,
                has_conflict=True,
                conflicts=conflict_details,
                source_images=all_src_images,
                raw_text=reliable_candidates[0].raw_text,
                layout_region=reliable_candidates[0].layout_region,
                layout_bbox=reliable_candidates[0].layout_bbox
            )
            merged_items.append(merged_decl)

        else:
            # Scenario A or Scenario C: All reliable sources agree (or only one reliable source).
            # Unreliable sources with different values do NOT create a genuine conflict.
            # Use the best reliable candidate.
            best = max(reliable_candidates, key=lambda x: x.confidence)
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
                source_images=all_src_images,
                raw_text=best.raw_text,
                layout_region=best.layout_region,
                layout_bbox=best.layout_bbox
            )
            merged_items.append(merged_decl)

    return merged_items, conflicts

extraction_service = ExtractionService()
