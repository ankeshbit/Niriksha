"""
tests/test_pp_structure_layout_acceptance.py

Comprehensive acceptance and regression test suite for PP-Structure package layout understanding in NiriKsha:
1. MRP region extraction and spatial label-value association.
2. Quantity region extraction and promotional additive formula pairing.
3. Manufacturer/address region clustering and bounding box calculation.
4. Date region extraction and spatial pairing.
5. Nutrition text rejection: nutrition table lines are never mistaken for commodity name.
6. Commodity extraction safety: returns EXTRACTED, UNCERTAIN, or NOT_FOUND without ever inventing names.
7. Multi-image layout evidence preservation in cross_image_verification.
8. Bounding box and layout region coordinate preservation.
9. Real Britannia package tests using supplied panel images.
"""

import os
import pytest
from pathlib import Path
from typing import List

from backend.ocr_service import OCRTextBox
from backend.layout_service import (
    layout_analyzer,
    LayoutAnalysisResult,
    LayoutRegion,
    _enclosing_bbox,
    _is_horizontally_adjacent,
    _is_vertically_adjacent
)
from backend.extraction_service import (
    extraction_service,
    DeterministicRegexExtractor,
    ExtractedDeclarationItem,
    cross_image_verification
)

BASE_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = BASE_DIR / "tests" / "fixtures"
BRITANNIA_DIR = FIXTURES_DIR / "britannia"
BRITANNIA_1 = BRITANNIA_DIR / "britannia_panel_1.jpg"
BRITANNIA_2 = BRITANNIA_DIR / "britannia_panel_2.jpg"


# =====================================================================
# 1. MRP Region Extraction & Spatial Label-Value Association
# =====================================================================
def test_01_mrp_spatial_label_value_association():
    """
    Verifies that a decoupled MRP label box and adjacent price box
    are spatially associated and extracted with layout_region='PRICE_DATE_REGION'.
    """
    extractor = DeterministicRegexExtractor()

    # Synthetic decoupled text boxes: label on left, value on right
    boxes = [
        OCRTextBox(text="MRP.", bbox=[770, 60, 830, 85], confidence=0.96),
        OCRTextBox(text="(INCL., OF ALL TAXES)", bbox=[690, 85, 830, 110], confidence=0.92),
        OCRTextBox(text="50.00 Rs. 0.91/g", bbox=[870, 80, 980, 110], confidence=0.95),
    ]
    full_text = "\n".join(b.text for b in boxes)

    decls = extractor.extract_declarations(full_text, boxes, {}, image_id="img_mrp_test")
    mrp_decl = next((d for d in decls if d.field_name == "mrp"), None)

    assert mrp_decl is not None
    assert mrp_decl.extraction_status == "EXTRACTED"
    assert "50.00" in mrp_decl.extracted_value
    assert "taxes" in mrp_decl.extracted_value.lower()
    assert mrp_decl.layout_region == "PRICE_DATE_REGION"
    assert mrp_decl.raw_text is not None
    assert "MRP" in mrp_decl.raw_text and "50.00" in mrp_decl.raw_text
    assert mrp_decl.bounding_box is not None
    assert mrp_decl.bounding_box[0] <= 770
    assert mrp_decl.bounding_box[2] >= 980


# =====================================================================
# 2. Quantity Region Extraction & Promotional Additive Pairing
# =====================================================================
def test_02_net_quantity_spatial_pairing_and_formula():
    """
    Verifies that a NET WEIGHT label paired with '50 g + 5 g EXTRA = 55 g'
    correctly associates, resolves to total 55 g, and preserves QUANTITY_REGION.
    """
    extractor = DeterministicRegexExtractor()

    boxes = [
        OCRTextBox(text="NET WEIGHT", bbox=[740, 20, 835, 45], confidence=0.97),
        OCRTextBox(text="50 g + 5 g EXTRA# = 55 g", bbox=[850, 20, 1015, 50], confidence=0.94),
    ]
    full_text = "\n".join(b.text for b in boxes)

    decls = extractor.extract_declarations(full_text, boxes, {}, image_id="img_qty_test")
    qty_decl = next((d for d in decls if d.field_name == "net_quantity"), None)

    assert qty_decl is not None
    assert qty_decl.extraction_status == "EXTRACTED"
    assert "55" in qty_decl.extracted_value
    assert "g" in qty_decl.extracted_value.lower()
    assert qty_decl.layout_region == "QUANTITY_REGION"
    assert qty_decl.raw_text is not None
    assert "NET WEIGHT" in qty_decl.raw_text or "55 g" in qty_decl.raw_text
    assert qty_decl.bounding_box is not None
    assert qty_decl.bounding_box[0] <= 750
    assert qty_decl.bounding_box[2] >= 1000


# =====================================================================
# 3. Manufacturer / Address Region Clustering
# =====================================================================
def test_03_manufacturer_address_region_clustering():
    """
    Verifies that multi-line manufacturer and factory address boxes are grouped
    into a MANUFACTURER_ADDRESS_REGION with composite bounding box.
    """
    extractor = DeterministicRegexExtractor()

    boxes = [
        OCRTextBox(text="Manufactured & Packed by:", bbox=[100, 200, 300, 220], confidence=0.95),
        OCRTextBox(text="Britannia Industries Limited", bbox=[100, 225, 320, 245], confidence=0.98),
        OCRTextBox(text="Plot No. 1, Industrial Area, Bidadi", bbox=[100, 250, 380, 270], confidence=0.93),
        OCRTextBox(text="Ramanagara, Karnataka - 562109", bbox=[100, 275, 350, 295], confidence=0.96),
    ]
    full_text = "\n".join(b.text for b in boxes)

    # Layout analysis
    res = layout_analyzer.analyze(boxes)
    assert len(res.manufacturer_address_regions) >= 1
    mfg_reg = res.manufacturer_address_regions[0]
    assert mfg_reg.region_type == "MANUFACTURER_ADDRESS_REGION"
    assert mfg_reg.bbox[0] <= 100 and mfg_reg.bbox[2] >= 350
    assert mfg_reg.bbox[1] <= 200 and mfg_reg.bbox[3] >= 295

    # Extraction
    decls = extractor.extract_declarations(full_text, boxes, {}, image_id="img_mfg_test")
    mfg_decl = next((d for d in decls if d.field_name == "manufacturer_details"), None)
    assert mfg_decl is not None
    assert mfg_decl.extraction_status == "EXTRACTED"
    assert "Britannia" in mfg_decl.extracted_value
    assert "562109" in mfg_decl.extracted_value or "Karnataka" in mfg_decl.extracted_value
    assert mfg_decl.layout_region == "MANUFACTURER_ADDRESS_REGION"


# =====================================================================
# 4. Date Region Extraction & Spatial Pairing
# =====================================================================
def test_04_date_spatial_pairing():
    """
    Verifies spatial pairing of PKD. label with date value box.
    """
    extractor = DeterministicRegexExtractor()

    boxes = [
        OCRTextBox(text="PKD.", bbox=[790, 115, 830, 135], confidence=0.93),
        OCRTextBox(text="17/04/26", bbox=[875, 115, 935, 135], confidence=0.96),
    ]
    full_text = "\n".join(b.text for b in boxes)

    decls = extractor.extract_declarations(full_text, boxes, {}, image_id="img_date_test")
    date_decl = next((d for d in decls if d.field_name == "date_of_manufacture_packing"), None)

    assert date_decl is not None
    assert date_decl.extraction_status == "EXTRACTED"
    assert "17/04/26" in date_decl.extracted_value or "04/2026" in date_decl.normalized_value or "2026" in date_decl.extracted_value
    assert date_decl.layout_region == "PRICE_DATE_REGION"
    assert date_decl.raw_text is not None


# =====================================================================
# 5. Nutrition Text Never Mistaken for Commodity Name
# =====================================================================
def test_05_nutrition_text_rejected_from_commodity_name():
    """
    Verifies that nutrition table lines (Protein, Energy, Carbohydrates, Total Fat)
    and statutory address lines are never selected as the commodity name.
    When only nutrition and secondary panels are present, commodity name must be NOT_FOUND.
    """
    extractor = DeterministicRegexExtractor()

    nutrition_boxes = [
        OCRTextBox(text="NUTRITIONAL INFORMATION", bbox=[50, 50, 250, 75], confidence=0.98),
        OCRTextBox(text="Approx. Values per 100g", bbox=[50, 80, 230, 100], confidence=0.94),
        OCRTextBox(text="Energy (kcal) 450", bbox=[50, 105, 200, 125], confidence=0.95),
        OCRTextBox(text="Protein 3.7 g", bbox=[50, 130, 180, 150], confidence=0.96),
        OCRTextBox(text="Total Fat 18 g", bbox=[50, 155, 180, 175], confidence=0.95),
        OCRTextBox(text="Carbohydrate 68 g", bbox=[50, 180, 220, 200], confidence=0.95),
        OCRTextBox(text="Total Sugars 24 g", bbox=[50, 205, 210, 225], confidence=0.94),
        OCRTextBox(text="Added Sugars 22 g", bbox=[50, 230, 210, 250], confidence=0.94),
        OCRTextBox(text="Sodium 280 mg", bbox=[50, 255, 190, 275], confidence=0.93),
    ]
    full_text = "\n".join(b.text for b in nutrition_boxes)

    # Layout analysis must cluster this as TABLE_REGION
    res = layout_analyzer.analyze(nutrition_boxes)
    assert len(res.table_regions) >= 1
    assert res.table_regions[0].region_type == "TABLE_REGION"

    decls = extractor.extract_declarations(full_text, nutrition_boxes, {}, image_id="img_nutr")
    comm_decl = next((d for d in decls if d.field_name == "commodity_name"), None)

    assert comm_decl is not None
    # Must NOT be extracted as 'Protein', 'Energy', or 'Carbohydrate'
    assert comm_decl.extraction_status in ("NOT_FOUND", "UNCERTAIN")
    assert comm_decl.extracted_value is None or comm_decl.extracted_value == ""


# =====================================================================
# 6. Commodity Extraction: Legitimate Front Title vs Unknown Panel
# =====================================================================
def test_06_commodity_extraction_behavior():
    """
    Tests that a clear, non-table, non-statutory title is extracted as EXTRACTED,
    while random boilerplate text without product identifiers is marked NOT_FOUND.
    Never invents names.
    """
    extractor = DeterministicRegexExtractor()

    # Front panel with clear product title
    front_boxes = [
        OCRTextBox(text="BRITANNIA", bbox=[100, 50, 300, 100], confidence=0.98),
        OCRTextBox(text="BOURBON CHOCOLATE BISCUITS", bbox=[80, 120, 450, 170], confidence=0.97),
        OCRTextBox(text="THE ORIGINAL CHOCO DELIGHT", bbox=[120, 180, 400, 210], confidence=0.91),
    ]
    front_text = "\n".join(b.text for b in front_boxes)

    decls_front = extractor.extract_declarations(front_text, front_boxes, {}, image_id="img_front")
    comm_front = next((d for d in decls_front if d.field_name == "commodity_name"), None)

    assert comm_front is not None
    assert comm_front.extraction_status == "EXTRACTED"
    assert "BOURBON" in comm_front.extracted_value.upper() or "BISCUITS" in comm_front.extracted_value.upper()

    # Panel with only barcode / statutory gibberish
    noise_boxes = [
        OCRTextBox(text="STORE IN A COOL DRY PLACE", bbox=[50, 50, 300, 70], confidence=0.92),
        OCRTextBox(text="KEEP AWAY FROM DIRECT SUNLIGHT", bbox=[50, 75, 320, 95], confidence=0.91),
    ]
    noise_text = "\n".join(b.text for b in noise_boxes)
    decls_noise = extractor.extract_declarations(noise_text, noise_boxes, {}, image_id="img_noise")
    comm_noise = next((d for d in decls_noise if d.field_name == "commodity_name"), None)

    assert comm_noise is not None
    assert comm_noise.extraction_status in ("NOT_FOUND", "UNCERTAIN")
    assert comm_noise.extracted_value is None or comm_noise.extracted_value == ""


# =====================================================================
# 7. Multi-Image Layout Evidence Preservation
# =====================================================================
def test_07_multi_image_layout_evidence_in_cross_image_verification():
    """
    Verifies that cross_image_verification retains raw_text, layout_region,
    and layout_bbox on consolidated declarations and conflict records.
    """
    item_img1 = ExtractedDeclarationItem(
        field_name="mrp",
        field_label="Maximum Retail Price (MRP)",
        extracted_value="₹50.00 (Incl. of all taxes)",
        normalized_value="50.00 INR",
        confidence=0.95,
        source_image_id="img_side_1",
        bounding_box=[770, 60, 980, 110],
        extraction_status="EXTRACTED",
        raw_text="MRP. 50.00 Rs. 0.91/g",
        layout_region="PRICE_DATE_REGION",
        layout_bbox=[690, 60, 1020, 180]
    )

    item_img2 = ExtractedDeclarationItem(
        field_name="mrp",
        field_label="Maximum Retail Price (MRP)",
        extracted_value="₹50.00 (Incl. of all taxes)",
        normalized_value="50.00 INR",
        confidence=0.92,
        source_image_id="img_side_2",
        bounding_box=[760, 55, 970, 105],
        extraction_status="EXTRACTED",
        raw_text="MRP. 50.00",
        layout_region="PRICE_DATE_REGION",
        layout_bbox=[680, 55, 1010, 175]
    )

    per_image = {
        "img_side_1": [item_img1],
        "img_side_2": [item_img2]
    }

    merged_items, conflicts = cross_image_verification(per_image)
    mrp_merged = next((m for m in merged_items if m.field_name == "mrp"), None)

    assert mrp_merged is not None
    assert mrp_merged.extraction_status == "EXTRACTED"
    assert mrp_merged.source_image_id == "img_side_1"  # highest confidence
    assert mrp_merged.raw_text == "MRP. 50.00 Rs. 0.91/g"
    assert mrp_merged.layout_region == "PRICE_DATE_REGION"
    assert mrp_merged.layout_bbox == [690, 60, 1020, 180]
    assert len(conflicts) == 0


# =====================================================================
# 8. Real Package Test Using Supplied Britannia Images
# =====================================================================
def test_08_real_britannia_package_layout_and_extraction():
    """
    End-to-end test on the actual real-world Britannia package images.
    Verifies that:
    1. PP-Structure detects the nutrition TABLE_REGION on the left side of Panel 2.
    2. Spatial association extracts MRP=50.00 and Net Qty=55g on the right side.
    3. USP is extracted as Rs. 0.91/g.
    4. Commodity name on side panel is correctly NOT_FOUND (rejects nutrition/address text).
    5. Coordinates, raw_text, and layout_region are preserved.
    """
    if not BRITANNIA_2.exists():
        pytest.skip(f"Britannia package image not found at {BRITANNIA_2}")

    from backend.ocr_service import ocr_service

    # Step 1: Run OCR on panel 2
    ocr_res = ocr_service.process_image(str(BRITANNIA_2), image_id="britannia_p2")
    assert ocr_res.ocr_status == "OCR_SUCCESS"
    assert len(ocr_res.text_boxes) > 20

    # Step 2: Run Layout Analysis
    layout_res = layout_analyzer.analyze(ocr_res.text_boxes)

    # Verify detected regions
    assert len(layout_res.regions) > 0
    # Must have detected TABLE_REGION (Nutrition table on left)
    table_regions = [r for r in layout_res.regions if r.region_type == "TABLE_REGION"]
    assert len(table_regions) >= 1, "Expected at least one TABLE_REGION for nutrition table"
    # Left nutrition table should contain nutrition keywords
    nutr_texts = [b.text for b in table_regions[0].text_boxes]
    assert any("PROTEIN" in t.upper() or "ENERGY" in t.upper() or "FAT" in t.upper() or "CARB" in t.upper() for t in nutr_texts)

    # Step 3: Run Declaration Extraction
    extractor = DeterministicRegexExtractor()
    decls = extractor.extract_declarations(
        ocr_res.raw_text,
        ocr_res.text_boxes,
        {},
        image_id="britannia_p2"
    )

    decl_map = {d.field_name: d for d in decls}

    # Verify MRP
    mrp_d = decl_map.get("mrp")
    assert mrp_d is not None
    assert mrp_d.extraction_status == "EXTRACTED"
    assert "50.00" in mrp_d.extracted_value
    assert mrp_d.layout_region in ("PRICE_DATE_REGION", "PRICE_REGION")
    assert mrp_d.bounding_box is not None
    assert mrp_d.raw_text is not None

    # Verify Net Quantity
    qty_d = decl_map.get("net_quantity")
    assert qty_d is not None
    assert qty_d.extraction_status == "EXTRACTED"
    assert "55" in qty_d.extracted_value
    assert "g" in qty_d.extracted_value.lower()
    assert qty_d.layout_region == "QUANTITY_REGION"

    # Verify Unit Sale Price
    usp_d = decl_map.get("unit_sale_price")
    assert usp_d is not None
    assert usp_d.extraction_status == "EXTRACTED"
    assert "0.91" in usp_d.extracted_value

    # Verify Commodity Name is NOT hallucinated from nutrition text
    comm_d = decl_map.get("commodity_name")
    assert comm_d is not None
    assert comm_d.extraction_status in ("NOT_FOUND", "UNCERTAIN")
    # Make sure nutrition table line wasn't taken
    if comm_d.extracted_value:
        assert "protein" not in comm_d.extracted_value.lower()
        assert "energy" not in comm_d.extracted_value.lower()
        assert "taxes" not in comm_d.extracted_value.lower()
