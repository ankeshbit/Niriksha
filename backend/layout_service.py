"""
backend/layout_service.py

PP-Structure Package Layout Understanding Engine for NiriKsha.
Detects, clusters, and analyzes package semantic layout regions:
- TABLE_REGION (e.g., nutrition facts tables, serving guidelines, ingredient grids)
- PRICE_DATE_REGION (e.g., MRP, unit sale price, date stamps, batch codes)
- QUANTITY_REGION (e.g., net weight, promotional quantity declarations)
- MANUFACTURER_ADDRESS_REGION (e.g., corporate office, factory units, license numbers)
- CONSUMER_CARE_REGION (e.g., customer grievance cell, toll-free numbers, emails)
- COMMODITY_TITLE_REGION (e.g., prominent brand and generic product title)

Provides spatial proximity pairing (e.g., associating label "MRP" with adjacent "Rs. 50.00",
and "NET WEIGHT" with adjacent "55 g") and prevents nutrition table text from contaminating
commodity name extraction.
"""
import re
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel

from backend.ocr_service import OCRTextBox


class LayoutRegion(BaseModel):
    region_type: str  # TABLE_REGION, PRICE_DATE_REGION, QUANTITY_REGION, MANUFACTURER_ADDRESS_REGION, CONSUMER_CARE_REGION, COMMODITY_TITLE_REGION, TEXT_BLOCK
    bbox: List[int]   # Enclosing [x1, y1, x2, y2]
    confidence: float
    text_boxes: List[Any]
    summary_text: str


class LayoutAnalysisResult(BaseModel):
    regions: List[LayoutRegion]
    table_regions: List[LayoutRegion]
    price_date_regions: List[LayoutRegion]
    quantity_regions: List[LayoutRegion]
    address_regions: List[LayoutRegion]
    care_regions: List[LayoutRegion]
    title_regions: List[LayoutRegion]
    total_boxes: int

    @property
    def manufacturer_address_regions(self) -> List[LayoutRegion]:
        return self.address_regions


def _get_bbox(b: Any) -> List[int]:
    if hasattr(b, "bbox") and b.bbox:
        return b.bbox
    if isinstance(b, dict) and "bbox" in b and b["bbox"]:
        return b["bbox"]
    return [0, 0, 0, 0]


def _get_text(b: Any) -> str:
    if hasattr(b, "text") and b.text:
        return b.text
    if isinstance(b, dict) and "text" in b and b["text"]:
        return b["text"]
    return ""


def _get_conf(b: Any, default: float = 0.90) -> float:
    if hasattr(b, "confidence") and b.confidence is not None:
        return float(b.confidence)
    if isinstance(b, dict) and "confidence" in b and b["confidence"] is not None:
        return float(b["confidence"])
    return default


def _enclosing_bbox(boxes: List[Any]) -> List[int]:
    """Computes minimum bounding box that encloses all given text boxes."""
    if not boxes:
        return [0, 0, 0, 0]
    bboxes = [_get_bbox(b) for b in boxes]
    x1 = min(b[0] for b in bboxes)
    y1 = min(b[1] for b in bboxes)
    x2 = max(b[2] for b in bboxes)
    y2 = max(b[3] for b in bboxes)
    return [int(x1), int(y1), int(x2), int(y2)]


def _is_horizontally_adjacent(box_a: Any, box_b: Any, max_gap: int = 200) -> bool:
    """
    Checks if box_b is immediately to the right of box_a on the same horizontal line.
    Requires significant vertical overlap (>= 35% of height).
    """
    a_x1, a_y1, a_x2, a_y2 = _get_bbox(box_a)
    b_x1, b_y1, b_x2, b_y2 = _get_bbox(box_b)

    # Vertical overlap check
    overlap_y = max(0, min(a_y2, b_y2) - max(a_y1, b_y1))
    min_h = min(a_y2 - a_y1, b_y2 - b_y1)
    if min_h <= 0 or (overlap_y / min_h) < 0.35:
        return False

    # Horizontal position: box_b must be to the right of box_a
    gap = b_x1 - a_x2
    return -15 <= gap <= max_gap


def _is_vertically_adjacent(box_a: Any, box_b: Any, max_gap: int = 80) -> bool:
    """
    Checks if box_b is immediately below box_a with horizontal overlap.
    """
    a_x1, a_y1, a_x2, a_y2 = _get_bbox(box_a)
    b_x1, b_y1, b_x2, b_y2 = _get_bbox(box_b)

    # Horizontal overlap check
    overlap_x = max(0, min(a_x2, b_x2) - max(a_x1, b_x1))
    min_w = min(a_x2 - a_x1, b_x2 - b_x1)
    if min_w <= 0 or (overlap_x / min_w) < 0.25:
        return False

    # Vertical position: box_b must be below box_a
    gap = b_y1 - a_y2
    return -10 <= gap <= max_gap


class PPStructureLayoutAnalyzer:
    """
    PP-Structure Document & Package Layout Analyzer.
    Organizes unstructured OCR text boxes into semantically clustered functional regions.
    Uses lazy caching and fast spatial grouping without unnecessary deep-learning overhead.
    """

    NUTRITION_TABLE_KEYWORDS = re.compile(
        r'(?:NUTRITION|NUTRITIONAL|SERVING\s*SIZE|PER\s*100|ENERGY|PROTEIN|CARBOHYDRATE|'
        r'TOTAL\s*FAT|SATURATED\s*FAT|ADDED\s*SUGAR|SODIUM|CALCIUM|\(%\)\s*RDA|DIETARY|'
        r'APPROX\s*VALUES|INGREDIENTS?|CONTAINS\s*WHEAT|VEGETABLE\s*FAT)',
        re.IGNORECASE
    )

    PRICE_DATE_KEYWORDS = re.compile(
        r'(?:MRP|INCL|TAXES|PKD|MFD|USE\s*BY|EXP|EXPIRY|LOT|BATCH|RS\.|\₹|/\s*g\b|/\s*kg\b)',
        re.IGNORECASE
    )

    QUANTITY_KEYWORDS = re.compile(
        r'(?:NET\s*(?:WEIGHT|QTY|QUANTITY|CONTENT|VOL|VOLUME)|MET\s*WEIGHT|METWEIGHT|PROMO\s*PACK)',
        re.IGNORECASE
    )

    ADDRESS_KEYWORDS = re.compile(
        r'(?:MANUFACTURED|PACKED\s*BY|MARKETED\s*BY|MFG\s*BY|PLOT\s*NO|SECTOR|INDUSTRIAL\s*AREA|'
        r'GROWTH\s*CENTRE|PANCHAYAT|DIST|LIC\s*NO|FSSAI|KOLKATA|BENGAL|ENTERPRISE|LIMITED|LTD|PVT)',
        re.IGNORECASE
    )

    CARE_KEYWORDS = re.compile(
        r'(?:FEEDBACK|CONSUMER\s*CARE|CARE\s*CELL|TOLL\s*FREE|1800|1-800|EXECUTIVE|@|EMAIL)',
        re.IGNORECASE
    )

    def analyze(self, text_boxes: List[Any], image_shape: Optional[Tuple[int, int]] = None) -> LayoutAnalysisResult:
        """
        Segments a list of OCRTextBox items into structured LayoutRegions.
        """
        if not text_boxes:
            return LayoutAnalysisResult(
                regions=[],
                table_regions=[],
                price_date_regions=[],
                quantity_regions=[],
                address_regions=[],
                care_regions=[],
                title_regions=[],
                total_boxes=0
            )

        table_boxes: List[Any] = []
        price_date_boxes: List[Any] = []
        quantity_boxes: List[Any] = []
        address_boxes: List[Any] = []
        care_boxes: List[Any] = []
        other_boxes: List[Any] = []

        for b in text_boxes:
            t = _get_text(b).strip()
            if not t:
                continue

            # Check for Table / Nutrition region
            if self.NUTRITION_TABLE_KEYWORDS.search(t):
                table_boxes.append(b)
            # Check for Consumer Care region
            elif self.CARE_KEYWORDS.search(t):
                care_boxes.append(b)
            # Check for Manufacturer Address region
            elif self.ADDRESS_KEYWORDS.search(t):
                address_boxes.append(b)
            # Check for Price & Date region
            elif self.PRICE_DATE_KEYWORDS.search(t):
                price_date_boxes.append(b)
            # Check for Quantity region
            elif self.QUANTITY_KEYWORDS.search(t):
                quantity_boxes.append(b)
            else:
                other_boxes.append(b)

        # Spatial expansion: merge physically adjacent unlabeled boxes into respective regions
        for ob in list(other_boxes):
            # 1. Check if adjacent to table grid (e.g. nutrition numbers or nutrient values next to labels)
            if any(_is_horizontally_adjacent(tb, ob) or _is_vertically_adjacent(tb, ob) for tb in table_boxes) or (table_boxes and self._is_spatially_inside_cluster(ob, table_boxes)):
                table_boxes.append(ob)
                other_boxes.remove(ob)
            # 2. Check if adjacent to price/date (e.g. date numbers or price value without prefix)
            elif any(_is_horizontally_adjacent(pb, ob) or _is_vertically_adjacent(pb, ob) for pb in price_date_boxes):
                price_date_boxes.append(ob)
                other_boxes.remove(ob)
            # 3. Check if adjacent to quantity (e.g. "55 g" next to "NET WEIGHT")
            elif any(_is_horizontally_adjacent(qb, ob) or _is_vertically_adjacent(qb, ob) for qb in quantity_boxes):
                quantity_boxes.append(ob)
                other_boxes.remove(ob)
            # 4. Check if adjacent to address details
            elif any(_is_horizontally_adjacent(ab, ob) or _is_vertically_adjacent(ab, ob) for ab in address_boxes):
                address_boxes.append(ob)
                other_boxes.remove(ob)
            # 5. Check if adjacent to care details
            elif any(_is_horizontally_adjacent(cb, ob) or _is_vertically_adjacent(cb, ob) for cb in care_boxes):
                care_boxes.append(ob)
                other_boxes.remove(ob)

        regions: List[LayoutRegion] = []
        table_regions: List[LayoutRegion] = []
        price_date_regions: List[LayoutRegion] = []
        quantity_regions: List[LayoutRegion] = []
        address_regions: List[LayoutRegion] = []
        care_regions: List[LayoutRegion] = []
        title_regions: List[LayoutRegion] = []

        if table_boxes:
            r = LayoutRegion(
                region_type="TABLE_REGION",
                bbox=_enclosing_bbox(table_boxes),
                confidence=round(float(np.mean([_get_conf(b) for b in table_boxes])), 2),
                text_boxes=table_boxes,
                summary_text=" ".join(_get_text(b) for b in table_boxes)
            )
            regions.append(r)
            table_regions.append(r)

        if price_date_boxes:
            r = LayoutRegion(
                region_type="PRICE_DATE_REGION",
                bbox=_enclosing_bbox(price_date_boxes),
                confidence=round(float(np.mean([_get_conf(b) for b in price_date_boxes])), 2),
                text_boxes=price_date_boxes,
                summary_text=" ".join(_get_text(b) for b in price_date_boxes)
            )
            regions.append(r)
            price_date_regions.append(r)

        if quantity_boxes:
            r = LayoutRegion(
                region_type="QUANTITY_REGION",
                bbox=_enclosing_bbox(quantity_boxes),
                confidence=round(float(np.mean([_get_conf(b) for b in quantity_boxes])), 2),
                text_boxes=quantity_boxes,
                summary_text=" ".join(_get_text(b) for b in quantity_boxes)
            )
            regions.append(r)
            quantity_regions.append(r)

        if address_boxes:
            r = LayoutRegion(
                region_type="MANUFACTURER_ADDRESS_REGION",
                bbox=_enclosing_bbox(address_boxes),
                confidence=round(float(np.mean([_get_conf(b) for b in address_boxes])), 2),
                text_boxes=address_boxes,
                summary_text=" ".join(_get_text(b) for b in address_boxes)
            )
            regions.append(r)
            address_regions.append(r)

        if care_boxes:
            r = LayoutRegion(
                region_type="CONSUMER_CARE_REGION",
                bbox=_enclosing_bbox(care_boxes),
                confidence=round(float(np.mean([_get_conf(b) for b in care_boxes])), 2),
                text_boxes=care_boxes,
                summary_text=" ".join(_get_text(b) for b in care_boxes)
            )
            regions.append(r)
            care_regions.append(r)

        # Remaining top/prominent boxes may form title region
        if other_boxes:
            title_candidates = [b for b in other_boxes if _get_bbox(b)[1] < 300]
            if title_candidates:
                r = LayoutRegion(
                    region_type="COMMODITY_TITLE_REGION",
                    bbox=_enclosing_bbox(title_candidates),
                    confidence=round(float(np.mean([_get_conf(b) for b in title_candidates])), 2),
                    text_boxes=title_candidates,
                    summary_text=" ".join(_get_text(b) for b in title_candidates)
                )
                regions.append(r)
                title_regions.append(r)

        return LayoutAnalysisResult(
            regions=regions,
            table_regions=table_regions,
            price_date_regions=price_date_regions,
            quantity_regions=quantity_regions,
            address_regions=address_regions,
            care_regions=care_regions,
            title_regions=title_regions,
            total_boxes=len(text_boxes)
        )

    def _is_spatially_inside_cluster(self, box: Any, cluster: List[Any]) -> bool:
        """Checks if a box falls within the bounding envelope of an existing cluster."""
        if not cluster:
            return False
        env = _enclosing_bbox(cluster)
        bx = _get_bbox(box)
        # Horizontal and vertical bounds with small padding
        return (
            bx[0] >= env[0] - 30 and
            bx[2] <= env[2] + 30 and
            bx[1] >= env[1] - 20 and
            bx[3] <= env[3] + 20
        )

    def find_spatially_associated_value(
        self,
        label_pattern: str,
        text_boxes: List[Any],
        value_pattern: Optional[str] = None,
        max_gap_x: int = 240,
        max_gap_y: int = 90
    ) -> Optional[Tuple[Any, Any]]:
        """
        Locates a label box matching label_pattern and returns the pair (label_box, value_box)
        where value_box is horizontally adjacent (to right), vertically adjacent (below),
        or adjacent to a label continuation modifier (e.g. "MRP" above "(INCL. OF ALL TAXES)" next to price).
        """
        regex = re.compile(label_pattern, re.IGNORECASE)
        val_reg = re.compile(value_pattern, re.IGNORECASE) if value_pattern else None

        for label_box in text_boxes:
            l_text = _get_text(label_box)
            if regex.search(l_text):
                l_bbox = _get_bbox(label_box)
                # 1. Search for right-adjacent value box matching value_pattern
                right_candidates = []
                for val_box in text_boxes:
                    if val_box == label_box:
                        continue
                    if _is_horizontally_adjacent(label_box, val_box, max_gap=max_gap_x):
                        v_text = _get_text(val_box)
                        if not val_reg or val_reg.search(v_text):
                            v_bbox = _get_bbox(val_box)
                            dist = v_bbox[0] - l_bbox[2]
                            right_candidates.append((dist, val_box))
                if right_candidates:
                    right_candidates.sort(key=lambda x: x[0])
                    return label_box, right_candidates[0][1]

                # 2. Search for below-adjacent value box
                below_candidates = []
                for val_box in text_boxes:
                    if val_box == label_box:
                        continue
                    if _is_vertically_adjacent(label_box, val_box, max_gap=max_gap_y):
                        v_text = _get_text(val_box)
                        if val_reg and val_reg.search(v_text):
                            v_bbox = _get_bbox(val_box)
                            dist = v_bbox[1] - l_bbox[3]
                            below_candidates.append((dist, val_box))
                        elif not val_reg:
                            v_bbox = _get_bbox(val_box)
                            dist = v_bbox[1] - l_bbox[3]
                            below_candidates.append((dist, val_box))
                        else:
                            # 3. Label continuation check: val_box is a modifier (e.g. "(INCL., OF ALL TAXES)")
                            # Check if that continuation box has a right-adjacent box matching value_pattern
                            sub_right = []
                            for sub_v in text_boxes:
                                if sub_v not in (label_box, val_box) and _is_horizontally_adjacent(val_box, sub_v, max_gap=max_gap_x):
                                    if val_reg.search(_get_text(sub_v)):
                                        s_bbox = _get_bbox(sub_v)
                                        s_dist = s_bbox[0] - _get_bbox(val_box)[2]
                                        sub_right.append((s_dist, sub_v))
                            if sub_right:
                                sub_right.sort(key=lambda x: x[0])
                                return label_box, sub_right[0][1]

                if below_candidates:
                    below_candidates.sort(key=lambda x: x[0])
                    return label_box, below_candidates[0][1]

        return None


layout_analyzer = PPStructureLayoutAnalyzer()
