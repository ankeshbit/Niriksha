import pytest
from backend.rule_engine import rule_engine, get_all_rules, get_rule_by_code, RuleResultState
from tests.test_phase5 import *

def test_ecommerce_rules_require_listing_comparison_when_applicable():
    """Verify that e-commerce applicable inspections do not silently PASS without comparison rows."""
    product_data = {
        "product_name": "Test Almonds",
        "inspection_type": "ONLINE_LISTING",
        "has_ecommerce_listing": True
    }
    decls = [
        {"field_name": "product_name", "extracted_value": "Test Almonds", "extraction_status": "EXTRACTED"},
        {"field_name": "mrp", "extracted_value": "Rs. 100", "extraction_status": "EXTRACTED"}
    ]

    # Without listing comparisons
    results = rule_engine.evaluate_inspection("INSP-ECOM-1", product_data, decls, [], listing_comparisons=[])
    res_map = {r.rule_code: r for r in results}

    rule_6_10 = res_map["PCR_RULE_06_10_ECOMMERCE_DECLARATION"]
    rule_18_2a = res_map["PCR_RULE_18_2A_ONLINE_PRICE_OVERCHARGING"]

    assert rule_6_10.result_state == RuleResultState.NEEDS_MANUAL_VERIFICATION
    assert "listing comparison has not yet been run" in rule_6_10.explanation.lower()
    assert rule_18_2a.result_state == RuleResultState.NEEDS_MANUAL_VERIFICATION
    assert "listing comparison has not yet been run" in rule_18_2a.explanation.lower()

def test_ecommerce_rules_discrepancy_returns_needs_manual_verification():
    """Verify that discrepancies return NEEDS_MANUAL_VERIFICATION (not POTENTIAL_NON_COMPLIANCE)."""
    product_data = {
        "product_name": "Test Almonds",
        "inspection_type": "ONLINE_LISTING",
        "has_ecommerce_listing": True
    }
    decls = [
        {"field_name": "product_name", "extracted_value": "Test Almonds", "extraction_status": "EXTRACTED"},
        {"field_name": "mrp", "extracted_value": "Rs. 100", "extraction_status": "EXTRACTED"}
    ]
    comps = [
        {
            "applicable_rule_code": "PCR_RULE_18_2A_ONLINE_PRICE_OVERCHARGING",
            "field_name": "mrp",
            "comparison_status": "MISMATCH",
            "inspector_status": "PENDING_REVIEW",
            "listing_value": "120",
            "package_value": "100",
            "difference_explanation": "Online price exceeds package MRP"
        },
        {
            "applicable_rule_code": "PCR_RULE_06_10_ECOMMERCE_DECLARATION",
            "field_name": "consumer_care_details",
            "comparison_status": "MISSING_ON_LISTING",
            "inspector_status": "PENDING_REVIEW",
            "listing_value": None,
            "package_value": "care@test.com",
            "difference_explanation": "Consumer care missing on listing"
        }
    ]

    results = rule_engine.evaluate_inspection("INSP-ECOM-2", product_data, decls, [], listing_comparisons=comps)
    res_map = {r.rule_code: r for r in results}

    rule_6_10 = res_map["PCR_RULE_06_10_ECOMMERCE_DECLARATION"]
    rule_18_2a = res_map["PCR_RULE_18_2A_ONLINE_PRICE_OVERCHARGING"]

    assert rule_6_10.result_state == RuleResultState.NEEDS_MANUAL_VERIFICATION
    assert "detected discrepancies" in rule_6_10.explanation
    assert rule_18_2a.result_state == RuleResultState.NEEDS_MANUAL_VERIFICATION
    assert "detected discrepancies" in rule_18_2a.explanation

def test_ecommerce_rules_all_matched_or_adjudicated_returns_pass():
    """Verify that when all comparison rows are MATCH or VERIFIED_MATCH / DISMISSED_DISCREPANCY, PASS is returned."""
    product_data = {
        "product_name": "Test Almonds",
        "inspection_type": "ONLINE_LISTING",
        "has_ecommerce_listing": True
    }
    decls = [
        {"field_name": "product_name", "extracted_value": "Test Almonds", "extraction_status": "EXTRACTED"},
        {"field_name": "mrp", "extracted_value": "Rs. 100", "extraction_status": "EXTRACTED"}
    ]
    comps = [
        {
            "applicable_rule_code": "PCR_RULE_18_2A_ONLINE_PRICE_OVERCHARGING",
            "field_name": "mrp",
            "comparison_status": "MATCH",
            "inspector_status": "PENDING_REVIEW"
        },
        {
            "applicable_rule_code": "PCR_RULE_06_10_ECOMMERCE_DECLARATION",
            "field_name": "consumer_care_details",
            "comparison_status": "MISMATCH",
            "inspector_status": "DISMISSED_DISCREPANCY"
        }
    ]

    results = rule_engine.evaluate_inspection("INSP-ECOM-3", product_data, decls, [], listing_comparisons=comps)
    res_map = {r.rule_code: r for r in results}

    rule_6_10 = res_map["PCR_RULE_06_10_ECOMMERCE_DECLARATION"]
    rule_18_2a = res_map["PCR_RULE_18_2A_ONLINE_PRICE_OVERCHARGING"]

    assert rule_6_10.result_state == RuleResultState.PASS
    assert "verified" in rule_6_10.explanation.lower()
    assert rule_18_2a.result_state == RuleResultState.PASS
    assert "verified" in rule_18_2a.explanation.lower()
