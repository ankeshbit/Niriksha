"""
Legal Provenance Matrix for NiriKsha Legal Metrology Compliance System.
Authoritative Legal Source:
The Legal Metrology (Packaged Commodities) Rules, 2011
Notification GSR 202(E) dated 7th March 2011, Ministry of Consumer Affairs, Food and Public Distribution.
Published in the Gazette of India, Extraordinary, Part II, Section 3, Sub-section (i).
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel

class LegalRuleProvenance(BaseModel):
    rule_code: str
    field_name: str
    statutory_rule_number: str
    statutory_sub_rule: str
    exact_pdf_page: int
    exact_section: str
    legal_requirement_summary: str
    applicability_conditions: str
    statutory_exceptions: str
    evaluation_logic: str
    verification_status: str  # 'STATUTORY_VERIFIED' or 'NEEDS_LEGAL_VERIFICATION'

LEGAL_PROVENANCE_REGISTRY: Dict[str, LegalRuleProvenance] = {
    "PCR_RULE_06_1_A": LegalRuleProvenance(
        rule_code="PCR_RULE_06_1_A",
        field_name="manufacturer_details",
        statutory_rule_number="Rule 6(1)(a)",
        statutory_sub_rule="sub-rule (1), clause (a) & Explanations I-II; read with Rule 10",
        exact_pdf_page=5,
        exact_section="Chapter II, Rule 6(1)(a) & Explanations I, II (p. 5); Rule 10(1)-(2) (p. 10-11)",
        legal_requirement_summary=(
            "Every package shall bear the name and complete address of the manufacturer, "
            "or where the manufacturer is not the packer, the name and address of the manufacturer and packer, "
            "and for any imported package the name and address of the importer. Under Explanation II, if the brand "
            "owner appears as marketer, the brand owner is deemed manufacturer."
        ),
        applicability_conditions="Applicable to all pre-packaged commodities intended for retail sale (Rule 3).",
        statutory_exceptions="Packages of capacity 5 cubic cm or less may bear identifying mark/inscription (Rule 10(1) proviso, p. 11).",
        evaluation_logic="Verifies presence of manufacturer/packer/marketer name and complete postal address with PIN code or city/state.",
        verification_status="STATUTORY_VERIFIED"
    ),
    "PCR_RULE_06_1_F": LegalRuleProvenance(
        rule_code="PCR_RULE_06_1_F",
        field_name="commodity_name",
        statutory_rule_number="Rule 6(1)(b)",
        statutory_sub_rule="sub-rule (1), clause (b)",
        exact_pdf_page=5,
        exact_section="Chapter II, Rule 6(1)(b) (p. 5)",
        legal_requirement_summary=(
            "The common or generic names of the commodity contained in the package and in case of "
            "packages with more than one product, the name and number or quantity of each product shall be mentioned."
        ),
        applicability_conditions="Applicable to all retail packaged commodities.",
        statutory_exceptions="None for standard retail packages.",
        evaluation_logic="Verifies declaration of common or generic commodity name on the package / principal display panel.",
        verification_status="STATUTORY_VERIFIED"
    ),
    "PCR_RULE_06_1_C": LegalRuleProvenance(
        rule_code="PCR_RULE_06_1_C",
        field_name="net_quantity",
        statutory_rule_number="Rule 6(1)(c)",
        statutory_sub_rule="sub-rule (1), clause (c); read with Rules 11, 12, 13 & Second Schedule",
        exact_pdf_page=5,
        exact_section="Chapter II, Rule 6(1)(c) (p. 5); Rules 11-13 (p. 11-14); Second Schedule (p. 29-32)",
        legal_requirement_summary=(
            "The net quantity, in terms of standard unit of weight or measure, or number, "
            "excluding packaging/wrapper. Must use standard SI units (g, kg, ml, L, N, U). "
            "Must not use qualifiers like 'when packed' unless listed in Third Schedule."
        ),
        applicability_conditions="Applicable to all retail packages exceeding 10g/10ml (Rule 26(a), p. 24).",
        statutory_exceptions="Packages containing 10g or 10ml or less exempt under Rule 26(a) (p. 24).",
        evaluation_logic="Verifies numerical net quantity with standard SI metric unit. Checks against Second Schedule standard pack sizes where applicable.",
        verification_status="STATUTORY_VERIFIED"
    ),
    "PCR_RULE_06_1_D": LegalRuleProvenance(
        rule_code="PCR_RULE_06_1_D",
        field_name="date_of_manufacture_packing",
        statutory_rule_number="Rule 6(1)(d)",
        statutory_sub_rule="sub-rule (1), clause (d) & Explanation I",
        exact_pdf_page=5,
        exact_section="Chapter II, Rule 6(1)(d) (p. 5) & Explanation I (p. 7)",
        legal_requirement_summary=(
            "The month and year in which the commodity is manufactured or pre-packed or imported "
            "shall be mentioned. May be expressed in words or numerals indicating month and year or both."
        ),
        applicability_conditions="Applicable to all retail packaged commodities.",
        statutory_exceptions="Bidis, incense sticks, and domestic LPG cylinders exempt under Rule 6(1) proviso (A) (p. 6).",
        evaluation_logic="Verifies valid structural date representation for month and year of manufacture/packing.",
        verification_status="STATUTORY_VERIFIED"
    ),
    "PCR_RULE_06_1_E": LegalRuleProvenance(
        rule_code="PCR_RULE_06_1_E",
        field_name="mrp",
        statutory_rule_number="Rule 6(1)(e)",
        statutory_sub_rule="sub-rule (1), clause (e); read with Rule 2(m)",
        exact_pdf_page=6,
        exact_section="Chapter II, Rule 6(1)(e) (p. 6); Chapter I, Rule 2(m) (p. 3)",
        legal_requirement_summary=(
            "Retail sale price printed in the form 'Maximum or Max. retail price Rs/ ....inclusive of all taxes "
            "or in the form MRP Rs/ ....incl., of all taxes'."
        ),
        applicability_conditions="Applicable to all retail packages leaving premises of manufacturer (Rule 4 Explanation, p. 4).",
        statutory_exceptions="Bidi and domestic LPG under Administered Price Mechanism exempt under Rule 6(1) proviso (C) (p. 7).",
        evaluation_logic="Verifies numerical retail price accompanied by mandatory statutory tax qualifier 'inclusive of all taxes' / 'incl. of all taxes'.",
        verification_status="STATUTORY_VERIFIED"
    ),
    "PCR_RULE_06_1_G": LegalRuleProvenance(
        rule_code="PCR_RULE_06_1_G",
        field_name="consumer_care_details",
        statutory_rule_number="Rule 6(2)",
        statutory_sub_rule="sub-rule (2)",
        exact_pdf_page=7,
        exact_section="Chapter II, Rule 6(2) (p. 7)",
        legal_requirement_summary=(
            "Every package shall bear the name, address, telephone number, and e-mail address (if available) "
            "of the person or office that can be contacted in case of consumer complaints."
        ),
        applicability_conditions="Applicable to all retail pre-packaged commodities.",
        statutory_exceptions="E-mail address required 'if available' under Rule 6(2).",
        evaluation_logic="Verifies presence of contact person/office designation, phone number, and/or email address for consumer grievances.",
        verification_status="STATUTORY_VERIFIED"
    ),
    "PCR_RULE_06_1_B": LegalRuleProvenance(
        rule_code="PCR_RULE_06_1_B",
        field_name="country_of_origin",
        statutory_rule_number="Rule 6(1)(a) Proviso & Rule 10(1)",
        statutory_sub_rule="sub-rule (1), clause (a) proviso; Rule 10(1) second proviso",
        exact_pdf_page=5,
        exact_section="Chapter II, Rule 6(1)(a) (p. 5); Rule 10(1) (p. 11)",
        legal_requirement_summary=(
            "For any imported package, the name and address of the importer shall be mentioned. "
            "Where commodity manufactured outside India is packed in India, name and complete address of packer or importer in India must appear. "
            "Note: General country of origin for all goods was enacted in subsequent 2017 amendments (GSR 629(E)), not the 2011 principal notification."
        ),
        applicability_conditions="Mandatory for imported commodities. For domestic goods, not explicitly mandated by the principal 2011 PDF notification.",
        statutory_exceptions="Domestic commodities where manufacturer and packing occurred in India.",
        evaluation_logic="Checks if explicitly declared. An Indian address alone does NOT establish domestic origin. Missing declaration without import status requires inspector verification.",
        verification_status="NEEDS_LEGAL_VERIFICATION"
    ),
    "PCR_RULE_UNIT_SALE_PRICE": LegalRuleProvenance(
        rule_code="PCR_RULE_UNIT_SALE_PRICE",
        field_name="unit_sale_price",
        statutory_rule_number="Subsequent Amendment (GSR 779(E) 2021)",
        statutory_sub_rule="Rule 6(11) / Rule 6(1)(m) (Enacted 2021)",
        exact_pdf_page=0,
        exact_section="Not present in 2011 Notification GSR 202(E) (PDF pp. 1-43). Introduced in 2021 amendment.",
        legal_requirement_summary=(
            "Unit sale price declaration (e.g. Rs. per g/kg/ml) is mandated by 2021 amendment GSR 779(E). "
            "It does NOT appear in the attached authoritative 2011 Rules PDF."
        ),
        applicability_conditions="Applies to packages containing more than 1 kg / 1 L, or smaller packages as specified in 2021 amendment.",
        statutory_exceptions="Not applicable under original 2011 rules.",
        evaluation_logic="Extracted independently from OCR evidence. Flagged as NEEDS_LEGAL_VERIFICATION against the 2011 PDF source.",
        verification_status="NEEDS_LEGAL_VERIFICATION"
    )
}

def get_rule_provenance(rule_code: str) -> Optional[LegalRuleProvenance]:
    return LEGAL_PROVENANCE_REGISTRY.get(rule_code)

def get_all_provenance() -> List[LegalRuleProvenance]:
    return list(LEGAL_PROVENANCE_REGISTRY.values())
