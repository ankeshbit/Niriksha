"""
backend/listing_service.py

Product Information & Online Listing Compliance Engine (PS 26034)
Compares online listing data against physical package evidence (OCR declarations).

Statutory references:
- Rule 6(10), Legal Metrology (Packaged Commodities) Rules, 2011 (GSR 629(E)):
  Mandatory disclosure of declarations on e-commerce platforms.
- Rule 18(2A), Legal Metrology (Packaged Commodities) Rules, 2011:
  Strict prohibition against online sale prices exceeding the physical package MRP.

ANTI-FABRICATION GUARANTEES:
- Listing values are never synthesized, guessed, or inferred.
- Country of origin is never inferred from manufacturer addresses.
- OCR uncertainty is preserved as UNCERTAIN, never assumed as fact.
- Discrepancies are flagged as reviewable evidence, NOT automatic legal violations.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.orm import Session

from backend.models import (
    Inspection,
    ProductListing,
    ListingComparison,
    Declaration,
    ProductImage,
    OCRResult,
)

logger = logging.getLogger("listing_service")

# Statutory Rule Codes
RULE_ECOMMERCE_DECLARATION = "PCR_RULE_06_10_ECOMMERCE_DECLARATION"
RULE_PRICE_OVERCHARGING = "PCR_RULE_18_2A_ONLINE_PRICE_OVERCHARGING"
RULE_MRP_GENERAL = "PCR_RULE_06_1_E"
RULE_NET_QUANTITY = "PCR_RULE_06_1_C"
RULE_MANUFACTURER = "PCR_RULE_06_1_A"
RULE_COUNTRY_OF_ORIGIN = "PCR_RULE_06_1_B"
RULE_CONSUMER_CARE = "PCR_RULE_06_1_G"
RULE_COMMODITY_NAME = "PCR_RULE_06_1_F"


def _clean_str(val: Optional[str]) -> Optional[str]:
    """Clean string whitespace without hallucinating values."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _parse_currency_amount(val: Optional[str]) -> Optional[float]:
    """Extract numeric price from text like '₹55', 'Rs. 50.00', 'MRP: 120'."""
    if not val:
        return None
    cleaned = re.sub(r"[₹$,\s]|Rs\.?|INR", "", str(val), flags=re.IGNORECASE)
    match = re.search(r"(\d+(?:\.\d{1,2})?)", cleaned)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _normalize_quantity(val: Optional[str]) -> Tuple[Optional[float], Optional[str]]:
    """
    Parse numerical quantity and normalize standard metric units to base units (g or ml).
    Example: '500 g' -> (500.0, 'g'), '0.5 kg' -> (500.0, 'g').
    """
    if not val:
        return None, None
    s = val.lower().strip()
    match = re.search(r"(\d+(?:\.\d+)?)\s*([a-z]+)", s)
    if not match:
        return None, None
    try:
        qty = float(match.group(1))
        unit = match.group(2).strip()
    except ValueError:
        return None, None

    if unit in ("kg", "kilogram", "kilograms"):
        return qty * 1000.0, "g"
    elif unit in ("g", "gram", "grams", "gm", "gms"):
        return qty, "g"
    elif unit in ("l", "liter", "liters", "litre", "litres"):
        return qty * 1000.0, "ml"
    elif unit in ("ml", "milliliter", "milliliters"):
        return qty, "ml"
    elif unit in ("unit", "units", "n", "u", "pcs", "piece", "pieces", "count"):
        return qty, "count"
    return qty, unit


def _normalize_origin(val: Optional[str]) -> Optional[str]:
    """Normalize common country strings (e.g. 'India', 'IND', 'Made in India')."""
    if not val:
        return None
    s = val.strip().lower()
    s = re.sub(r"^(made\s+in|product\s+of|country\s+of\s+origin:?)\s*", "", s).strip()
    if s in ("in", "ind", "india", "bharat"):
        return "india"
    return s


def compare_single_field(
    field_name: str,
    listing_raw: Optional[str],
    decl: Optional[Declaration],
) -> Dict[str, Any]:
    """
    Compare a single field between Online Listing and Package Declaration evidence.
    Returns comparison result with status, explanation, applicable rule, and evidence.
    """
    listing_val = _clean_str(listing_raw)
    package_val = _clean_str(decl.effective_value) if decl else None
    ocr_evidence = decl.extracted_value if decl else None
    ocr_conf = float(decl.confidence or 0.0) if decl else 0.0
    image_id = decl.source_image_id if decl else None
    bbox = decl.bounding_box_json if decl else None
    package_prov = (
        "INSPECTOR_CORRECTED"
        if (decl and decl.corrected_value)
        else ("PACKAGE_OCR" if (decl and decl.extracted_value) else "NOT_APPLICABLE")
    )

    # 1. Both absent
    if not listing_val and not package_val:
        return {
            "field_name": field_name,
            "listing_value": None,
            "package_value": None,
            "comparison_status": "MATCH",
            "difference_explanation": "Field is not declared on either online listing or physical package.",
            "package_ocr_evidence": None,
            "ocr_confidence": 0.0,
            "source_image_id": None,
            "bounding_box_json": None,
            "applicable_rule_code": None,
            "listing_provenance": "MANUAL_LISTING_INPUT",
            "package_provenance": package_prov,
        }

    # 2. Present on package, missing on online listing -> Rule 6(10) e-commerce disclosure issue
    if not listing_val and package_val:
        return {
            "field_name": field_name,
            "listing_value": None,
            "package_value": package_val,
            "comparison_status": "MISSING_ON_LISTING",
            "difference_explanation": (
                f"Declaration '{field_name}' is established on physical package ({package_val}) "
                f"but missing from online product listing."
            ),
            "package_ocr_evidence": ocr_evidence,
            "ocr_confidence": ocr_conf,
            "source_image_id": image_id,
            "bounding_box_json": bbox,
            "applicable_rule_code": RULE_ECOMMERCE_DECLARATION,
            "listing_provenance": "MANUAL_LISTING_INPUT",
            "package_provenance": package_prov,
        }

    # 3. Present on listing, missing on package -> listing claims unestablished on package
    if listing_val and not package_val:
        return {
            "field_name": field_name,
            "listing_value": listing_val,
            "package_value": None,
            "comparison_status": "MISSING_ON_PACKAGE",
            "difference_explanation": (
                f"Online listing claims '{listing_val}' for '{field_name}', but physical package "
                f"OCR evidence does not establish this declaration."
            ),
            "package_ocr_evidence": None,
            "ocr_confidence": 0.0,
            "source_image_id": None,
            "bounding_box_json": None,
            "applicable_rule_code": RULE_ECOMMERCE_DECLARATION,
            "listing_provenance": "MANUAL_LISTING_INPUT",
            "package_provenance": package_prov,
        }

    # 4. Low OCR confidence (< 0.50) when not corrected by inspector -> UNCERTAIN
    if decl and not decl.corrected_value and ocr_conf < 0.50:
        return {
            "field_name": field_name,
            "listing_value": listing_val,
            "package_value": package_val,
            "comparison_status": "UNCERTAIN",
            "difference_explanation": (
                f"Package OCR evidence confidence ({ocr_conf:.2f}) is below verification threshold (0.50). "
                f"Requires manual inspector verification."
            ),
            "package_ocr_evidence": ocr_evidence,
            "ocr_confidence": ocr_conf,
            "source_image_id": image_id,
            "bounding_box_json": bbox,
            "applicable_rule_code": RULE_ECOMMERCE_DECLARATION,
            "listing_provenance": "MANUAL_LISTING_INPUT",
            "package_provenance": package_prov,
        }

    # 5. Field-specific comparison logic
    if field_name == "mrp":
        p_price = _parse_currency_amount(package_val)
        l_price = _parse_currency_amount(listing_val)

        if p_price is not None and l_price is not None:
            if abs(p_price - l_price) < 0.01:
                return {
                    "field_name": field_name,
                    "listing_value": listing_val,
                    "package_value": package_val,
                    "comparison_status": "MATCH",
                    "difference_explanation": f"Online listing price matches package MRP (₹{p_price:0.2f}).",
                    "package_ocr_evidence": ocr_evidence,
                    "ocr_confidence": ocr_conf,
                    "source_image_id": image_id,
                    "bounding_box_json": bbox,
                    "applicable_rule_code": RULE_MRP_GENERAL,
                    "listing_provenance": "MANUAL_LISTING_INPUT",
                    "package_provenance": package_prov,
                }
            elif l_price > p_price:
                # Online price higher than package MRP -> Rule 18(2A) conflict
                return {
                    "field_name": field_name,
                    "listing_value": listing_val,
                    "package_value": package_val,
                    "comparison_status": "MISMATCH",
                    "difference_explanation": (
                        f"Online price (₹{l_price:0.2f}) exceeds physical package MRP (₹{p_price:0.2f}). "
                        f"Potential overcharging discrepancy under Rule 18(2A)."
                    ),
                    "package_ocr_evidence": ocr_evidence,
                    "ocr_confidence": ocr_conf,
                    "source_image_id": image_id,
                    "bounding_box_json": bbox,
                    "applicable_rule_code": RULE_PRICE_OVERCHARGING,
                    "listing_provenance": "MANUAL_LISTING_INPUT",
                    "package_provenance": package_prov,
                }
            else:
                # Online price lower than package MRP (discounted) -> permitted, but mismatch in printed number
                return {
                    "field_name": field_name,
                    "listing_value": listing_val,
                    "package_value": package_val,
                    "comparison_status": "MISMATCH",
                    "difference_explanation": (
                        f"Online listing price (₹{l_price:0.2f}) is discounted below package MRP (₹{p_price:0.2f}). "
                        f"Permitted discount, verified for inspector awareness."
                    ),
                    "package_ocr_evidence": ocr_evidence,
                    "ocr_confidence": ocr_conf,
                    "source_image_id": image_id,
                    "bounding_box_json": bbox,
                    "applicable_rule_code": RULE_MRP_GENERAL,
                    "listing_provenance": "MANUAL_LISTING_INPUT",
                    "package_provenance": package_prov,
                }

    elif field_name == "net_quantity":
        l_qty, l_unit = _normalize_quantity(listing_val)
        p_qty, p_unit = _normalize_quantity(package_val)

        if l_qty is not None and p_qty is not None and l_unit == p_unit:
            if abs(l_qty - p_qty) < 0.001:
                return {
                    "field_name": field_name,
                    "listing_value": listing_val,
                    "package_value": package_val,
                    "comparison_status": "MATCH",
                    "difference_explanation": f"Net quantity consistent across listing and package ({package_val}).",
                    "package_ocr_evidence": ocr_evidence,
                    "ocr_confidence": ocr_conf,
                    "source_image_id": image_id,
                    "bounding_box_json": bbox,
                    "applicable_rule_code": RULE_NET_QUANTITY,
                    "listing_provenance": "MANUAL_LISTING_INPUT",
                    "package_provenance": package_prov,
                }
            else:
                return {
                    "field_name": field_name,
                    "listing_value": listing_val,
                    "package_value": package_val,
                    "comparison_status": "MISMATCH",
                    "difference_explanation": (
                        f"Net quantity differs: online claims '{listing_val}' while physical package indicates '{package_val}'."
                    ),
                    "package_ocr_evidence": ocr_evidence,
                    "ocr_confidence": ocr_conf,
                    "source_image_id": image_id,
                    "bounding_box_json": bbox,
                    "applicable_rule_code": RULE_NET_QUANTITY,
                    "listing_provenance": "MANUAL_LISTING_INPUT",
                    "package_provenance": package_prov,
                }

    elif field_name == "country_of_origin":
        l_org = _normalize_origin(listing_val)
        p_org = _normalize_origin(package_val)
        if l_org and p_org and l_org == p_org:
            return {
                "field_name": field_name,
                "listing_value": listing_val,
                "package_value": package_val,
                "comparison_status": "MATCH",
                "difference_explanation": f"Country of origin matches ({package_val}).",
                "package_ocr_evidence": ocr_evidence,
                "ocr_confidence": ocr_conf,
                "source_image_id": image_id,
                "bounding_box_json": bbox,
                "applicable_rule_code": RULE_COUNTRY_OF_ORIGIN,
                "listing_provenance": "MANUAL_LISTING_INPUT",
                "package_provenance": package_prov,
            }
        else:
            return {
                "field_name": field_name,
                "listing_value": listing_val,
                "package_value": package_val,
                "comparison_status": "MISMATCH",
                "difference_explanation": (
                    f"Country of origin differs: online listing states '{listing_val}' "
                    f"while package states '{package_val}'."
                ),
                "package_ocr_evidence": ocr_evidence,
                "ocr_confidence": ocr_conf,
                "source_image_id": image_id,
                "bounding_box_json": bbox,
                "applicable_rule_code": RULE_COUNTRY_OF_ORIGIN,
                "listing_provenance": "MANUAL_LISTING_INPUT",
                "package_provenance": package_prov,
            }

    # General text comparison (product name, brand, manufacturer, consumer care)
    l_tokens = set(re.findall(r"\w+", listing_val.lower()))
    p_tokens = set(re.findall(r"\w+", package_val.lower()))

    # Check exact match or significant token overlap
    if listing_val.strip().lower() == package_val.strip().lower():
        status = "MATCH"
        desc = f"Values match identically for {field_name}."
    elif l_tokens and p_tokens and (l_tokens.issubset(p_tokens) or p_tokens.issubset(l_tokens)):
        status = "MATCH"
        desc = f"Substantial textual match between listing and package for {field_name}."
    else:
        # Overlap ratio
        overlap = len(l_tokens.intersection(p_tokens))
        total = max(len(l_tokens), len(p_tokens), 1)
        ratio = overlap / total
        if ratio >= 0.6:
            status = "MATCH"
            desc = f"Textual content is consistent ({ratio*100:.0f}% overlap) for {field_name}."
        else:
            status = "MISMATCH"
            desc = f"Discrepancy detected between online listing ('{listing_val}') and package ('{package_val}')."

    # Assign applicable statutory rule based on field
    rule_map = {
        "product_name": RULE_COMMODITY_NAME,
        "brand_name": RULE_COMMODITY_NAME,
        "manufacturer_details": RULE_MANUFACTURER,
        "importer_details": RULE_MANUFACTURER,
        "consumer_care_details": RULE_CONSUMER_CARE,
    }
    app_rule = rule_map.get(field_name, RULE_ECOMMERCE_DECLARATION)

    return {
        "field_name": field_name,
        "listing_value": listing_val,
        "package_value": package_val,
        "comparison_status": status,
        "difference_explanation": desc,
        "package_ocr_evidence": ocr_evidence,
        "ocr_confidence": ocr_conf,
        "source_image_id": image_id,
        "bounding_box_json": bbox,
        "applicable_rule_code": app_rule,
        "listing_provenance": "MANUAL_LISTING_INPUT",
        "package_provenance": package_prov,
    }


def execute_listing_comparison(
    db: Session,
    inspection_id: str,
) -> List[ListingComparison]:
    """
    Execute full comparison between online listing and package declarations for an inspection.
    Deletes any existing comparison records for this inspection and persists new ones.
    Does NOT automatically create legal violations; produces reviewable comparison records.
    """
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise ValueError(f"Inspection {inspection_id} not found.")

    listing = db.query(ProductListing).filter(ProductListing.inspection_id == inspection_id).first()
    if not listing:
        raise ValueError(f"No product listing found for inspection {inspection_id}. Enter product information first.")

    # Fetch declarations indexed by field_name
    declarations = db.query(Declaration).filter(Declaration.inspection_id == inspection_id).all()
    decl_map = {d.field_name: d for d in declarations}

    # Map listing fields to declaration field names
    fields_to_compare = [
        ("product_name", listing.product_name, decl_map.get("commodity_name")),
        ("brand_name", listing.brand_name, decl_map.get("brand_name") or decl_map.get("commodity_name")),
        ("mrp", listing.mrp, decl_map.get("mrp")),
        ("net_quantity", listing.net_quantity, decl_map.get("net_quantity")),
        ("manufacturer_details", listing.manufacturer_details, decl_map.get("manufacturer_details")),
        ("importer_details", listing.importer_details, decl_map.get("importer_details")),
        ("country_of_origin", listing.country_of_origin, decl_map.get("country_of_origin")),
        ("consumer_care_details", listing.consumer_care_details, decl_map.get("consumer_care_details")),
        ("date_information", listing.date_information, decl_map.get("date_of_manufacture_packing")),
    ]

    # Clear prior comparisons
    db.query(ListingComparison).filter(ListingComparison.inspection_id == inspection_id).delete()
    db.flush()

    comparison_records: List[ListingComparison] = []
    for field_name, listing_raw, decl in fields_to_compare:
        res = compare_single_field(field_name, listing_raw, decl)
        comp = ListingComparison(
            inspection_id=inspection_id,
            listing_id=listing.id,
            field_name=res["field_name"],
            listing_value=res["listing_value"],
            package_value=res["package_value"],
            comparison_status=res["comparison_status"],
            difference_explanation=res["difference_explanation"],
            package_ocr_evidence=res["package_ocr_evidence"],
            ocr_confidence=res["ocr_confidence"],
            source_image_id=res["source_image_id"],
            bounding_box_json=res["bounding_box_json"],
            applicable_rule_code=res["applicable_rule_code"],
            inspector_status="PENDING_REVIEW",
            inspector_remarks=None,
            listing_provenance=res["listing_provenance"],
            package_provenance=res["package_provenance"],
        )
        db.add(comp)
        comparison_records.append(comp)

    db.commit()
    for c in comparison_records:
        db.refresh(c)

    return comparison_records
