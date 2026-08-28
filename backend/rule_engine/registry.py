from typing import Dict, List, Optional
from backend.rule_engine.models import StatutoryRuleDefinition, SeverityLevel

STATUTORY_RULE_REGISTRY: Dict[str, StatutoryRuleDefinition] = {
    "PCR_RULE_06_1_E": StatutoryRuleDefinition(
        rule_code="PCR_RULE_06_1_E",
        rule_version=1,
        title="Maximum Retail Price (MRP) Declaration",
        category="CATEGORY_A_LEGAL",
        statutory_reference="Rule 6(1)(e), Legal Metrology (Packaged Commodities) Rules, 2011",
        description="Mandatory declaration of retail sale price in Indian Rupees inclusive of all taxes.",
        severity=SeverityLevel.CRITICAL,
        required_fields=["mrp"]
    ),
    "PCR_RULE_06_1_A": StatutoryRuleDefinition(
        rule_code="PCR_RULE_06_1_A",
        rule_version=1,
        title="Name & Address of Manufacturer / Packer / Importer",
        category="CATEGORY_A_LEGAL",
        statutory_reference="Rule 6(1)(a), Legal Metrology (Packaged Commodities) Rules, 2011",
        description="Mandatory declaration of the name and complete address of the manufacturer, packer, or importer.",
        severity=SeverityLevel.CRITICAL,
        required_fields=["manufacturer_details"]
    ),
    "PCR_RULE_06_1_C": StatutoryRuleDefinition(
        rule_code="PCR_RULE_06_1_C",
        rule_version=1,
        title="Net Quantity Declaration in Standard Metric Units",
        category="CATEGORY_A_LEGAL",
        statutory_reference="Rule 6(1)(c), Legal Metrology (Packaged Commodities) Rules, 2011",
        description="Mandatory declaration of net weight, volume, or measure in standard SI units (kg, g, L, ml, count).",
        severity=SeverityLevel.CRITICAL,
        required_fields=["net_quantity"]
    ),
    "PCR_RULE_06_1_D": StatutoryRuleDefinition(
        rule_code="PCR_RULE_06_1_D",
        rule_version=1,
        title="Month and Year of Manufacture / Packing",
        category="CATEGORY_A_LEGAL",
        statutory_reference="Rule 6(1)(d), Legal Metrology (Packaged Commodities) Rules, 2011",
        description="Mandatory declaration of the month and year in which the commodity is manufactured, packed, or imported.",
        severity=SeverityLevel.MAJOR,
        required_fields=["date_of_manufacture_packing"]
    ),
    "PCR_RULE_06_1_G": StatutoryRuleDefinition(
        rule_code="PCR_RULE_06_1_G",
        rule_version=1,
        title="Consumer Care Grievance Redressal Details",
        category="CATEGORY_A_LEGAL",
        statutory_reference="Rule 6(1)(g), Legal Metrology (Packaged Commodities) Rules, 2011",
        description="Mandatory declaration of name, address, telephone number, and e-mail of contact person for consumer complaints.",
        severity=SeverityLevel.MAJOR,
        required_fields=["consumer_care_details"]
    ),
    "PCR_RULE_06_1_F": StatutoryRuleDefinition(
        rule_code="PCR_RULE_06_1_F",
        rule_version=1,
        title="Generic Name or Commodity Identification",
        category="CATEGORY_A_LEGAL",
        statutory_reference="Rule 6(1)(f), Legal Metrology (Packaged Commodities) Rules, 2011",
        description="Mandatory declaration of common or generic name of commodity on Principal Display Panel.",
        severity=SeverityLevel.MAJOR,
        required_fields=["commodity_name"]
    ),
    "PCR_RULE_06_1_B": StatutoryRuleDefinition(
        rule_code="PCR_RULE_06_1_B",
        rule_version=1,
        title="Country of Origin Declaration",
        category="CATEGORY_A_LEGAL",
        statutory_reference="Rule 6(1)(b), Legal Metrology (Packaged Commodities) Rules, 2011",
        description="Mandatory declaration of the country of origin for imported commodities or where mandated by law.",
        severity=SeverityLevel.MAJOR,
        required_fields=["country_of_origin"]
    ),
    "DATA_QUAL_PHONE_SYNTAX": StatutoryRuleDefinition(
        rule_code="DATA_QUAL_PHONE_SYNTAX",
        rule_version=1,
        title="Consumer Care Telephone Syntax Verification",
        category="CATEGORY_B_DATA_QUALITY",
        statutory_reference="DoCA Consumer Grievance Standards & Rule 6(1)(g)",
        description="Verifies that telephone numbers conform to 10-digit mobile/landline or 1800 toll-free formats.",
        severity=SeverityLevel.MINOR,
        required_fields=["consumer_care_details"]
    ),
    "DATA_QUAL_DATE_PLAUSIBILITY": StatutoryRuleDefinition(
        rule_code="DATA_QUAL_DATE_PLAUSIBILITY",
        rule_version=1,
        title="Manufacturing Date Plausibility & Syntax Check",
        category="CATEGORY_B_DATA_QUALITY",
        statutory_reference="PCR 2011 General Standards & Rule 6(1)(d)",
        description="Verifies that manufacturing date is structurally plausible and not future-dated beyond statutory limits.",
        severity=SeverityLevel.MINOR,
        required_fields=["date_of_manufacture_packing"]
    )
}

def get_all_rules() -> List[StatutoryRuleDefinition]:
    return list(STATUTORY_RULE_REGISTRY.values())

def get_rule_by_code(rule_code: str) -> Optional[StatutoryRuleDefinition]:
    return STATUTORY_RULE_REGISTRY.get(rule_code)
