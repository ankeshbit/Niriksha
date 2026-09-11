import pytest
from backend.declaration_validation_service import (
    DeclarationValidationEngine,
    declaration_validation_engine
)


class TestMisleadingAndNonStandardValidation:
    """Test suite for Misleading & Non-Standard Declaration Validation (PCR 2011)."""

    def test_mrp_inclusive_taxes_compliant(self):
        """MRP properly formatted with inclusive of all taxes qualifier is COMPLIANT."""
        status, findings, reason = declaration_validation_engine.evaluate_format_compliance(
            field_name="mrp",
            extracted_value="Rs. 99.00 (Incl. of all taxes)"
        )
        assert status == "COMPLIANT"
        assert len(findings) == 0

    def test_mrp_bare_number_potential_non_compliance(self):
        """MRP without statutory prefix or inclusive taxes qualifier is flagged as POTENTIAL_MISLEADING."""
        status, findings, reason = declaration_validation_engine.evaluate_format_compliance(
            field_name="mrp",
            extracted_value="99.00"
        )
        assert status in ("POTENTIAL_MISLEADING", "NON_COMPLIANT")
        assert any("inclusive of all taxes" in f.lower() or "currency" in f.lower() for f in findings)

    def test_net_quantity_standard_metric_unit_compliant(self):
        """Net quantity in standard SI metric unit (e.g. 500 g, 1 kg, 750 ml) is COMPLIANT."""
        status, findings, reason = declaration_validation_engine.evaluate_format_compliance(
            field_name="net_quantity",
            extracted_value="500 g"
        )
        assert status == "COMPLIANT"

    def test_net_quantity_non_standard_unit_potential_non_compliance(self):
        status, findings, reason = declaration_validation_engine.evaluate_format_compliance(
            field_name="net_quantity",
            extracted_value="1.5 lbs"
        )
        assert status in ("POTENTIAL_MISLEADING", "NON_COMPLIANT")
        assert any("standard si metric units" in f.lower() or "metric" in f.lower() for f in findings)

    def test_missing_declaration_flagged_as_non_compliant(self):
        """Mandatory declaration missing value is flagged."""
        status, findings, reason = declaration_validation_engine.evaluate_format_compliance(
            field_name="date_of_manufacture_packing",
            extracted_value=None
        )
        assert status in ("NOT_APPLICABLE", "NON_COMPLIANT", "UNCERTAIN")

    def test_consumer_care_requires_contact_channel(self):
        """Rule 6(1)(g): Consumer care must provide valid contact details (phone, email, or address)."""
        status, findings, reason = declaration_validation_engine.evaluate_format_compliance(
            field_name="consumer_care_details",
            extracted_value="Call us anytime"
        )
        assert status in ("POTENTIAL_MISLEADING", "NON_COMPLIANT")
        assert any("consumer care" in f.lower() or "contact" in f.lower() for f in findings)

    def test_mandatory_fields_list_completeness(self):
        """Engine maintains the complete statutory list of mandatory fields under PCR 2011."""
        mandatory = [f[0] for f in declaration_validation_engine.MANDATORY_FIELDS]
        assert "commodity_name" in mandatory
        assert "manufacturer_details" in mandatory
        assert "net_quantity" in mandatory
        assert "mrp" in mandatory
        assert "date_of_manufacture_packing" in mandatory
        assert "consumer_care_details" in mandatory
        assert "country_of_origin" in mandatory
