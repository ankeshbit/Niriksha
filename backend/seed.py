from backend.database import SessionLocal, engine, Base
from backend.models import User, RuleVersion
from backend.config import settings
from backend.auth_utils import hash_password

def seed_database():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # 1. Seed Development Officer Account
        existing_officer = db.query(User).filter(User.officer_id == settings.SEED_OFFICER_ID).first()
        if not existing_officer:
            officer = User(
                officer_id=settings.SEED_OFFICER_ID,
                full_name=settings.SEED_OFFICER_NAME,
                designation=settings.SEED_OFFICER_DESIGNATION,
                zone=settings.SEED_OFFICER_ZONE,
                password_hash=hash_password(settings.SEED_OFFICER_PASSWORD),
                role="INSPECTOR"
            )
            db.add(officer)
            print(f"[Seed] Created development officer account: {settings.SEED_OFFICER_ID}")
        else:
            print(f"[Seed] Development officer account already exists: {settings.SEED_OFFICER_ID}")

        # 2. Seed Verified Legal Metrology PCR 2011 Rules (Version 1)
        seed_rules = [
            {
                "rule_code": "PCR_RULE_06_1_E",
                "version_number": 1,
                "title": "Maximum Retail Price (MRP) Declaration",
                "category": "CATEGORY_A_LEGAL",
                "statutory_reference": "Rule 6(1)(e), Legal Metrology (Packaged Commodities) Rules, 2011",
                "rule_logic_description": "Verify MRP is declared in standard format 'MRP Rs. XX' or '₹ XX' and includes 'inclusive of all taxes' or 'incl. of all taxes'."
            },
            {
                "rule_code": "PCR_RULE_06_1_A",
                "version_number": 1,
                "title": "Name & Address of Manufacturer / Packer / Importer",
                "category": "CATEGORY_A_LEGAL",
                "statutory_reference": "Rule 6(1)(a), Legal Metrology (Packaged Commodities) Rules, 2011",
                "rule_logic_description": "Verify complete name and physical address of the manufacturer, packer, or importer is declared on the package."
            },
            {
                "rule_code": "PCR_RULE_06_1_C",
                "version_number": 1,
                "title": "Net Quantity & Standard SI Unit",
                "category": "CATEGORY_A_LEGAL",
                "statutory_reference": "Rule 6(1)(c) & Rule 12, Legal Metrology (Packaged Commodities) Rules, 2011",
                "rule_logic_description": "Verify net quantity uses standard SI units (g, kg, ml, l, m, cm, No./U) without non-standard prefixes."
            },
            {
                "rule_code": "PCR_RULE_06_1_D",
                "version_number": 1,
                "title": "Month & Year of Manufacture / Packing",
                "category": "CATEGORY_A_LEGAL",
                "statutory_reference": "Rule 6(1)(d), Legal Metrology (Packaged Commodities) Rules, 2011",
                "rule_logic_description": "Verify month and year of manufacture, packing, or import is clearly declared in recognizable format (MM/YYYY or Month YYYY)."
            },
            {
                "rule_code": "PCR_RULE_06_1_G",
                "version_number": 1,
                "title": "Consumer Care Information",
                "category": "CATEGORY_A_LEGAL",
                "statutory_reference": "Rule 6(1)(g), Legal Metrology (Packaged Commodities) Rules, 2011",
                "rule_logic_description": "Verify contact details for consumer complaints (name, address, telephone/mobile number, and email) are present."
            },
            {
                "rule_code": "PCR_RULE_06_1_F",
                "version_number": 1,
                "title": "Country of Origin (Imported Commodities)",
                "category": "CATEGORY_A_LEGAL",
                "statutory_reference": "Rule 6(1)(f), Legal Metrology (Packaged Commodities) Rules, 2011",
                "rule_logic_description": "Verify country of origin is clearly declared on packages containing imported commodities."
            },
            {
                "rule_code": "DATA_QUAL_PHONE_SYNTAX",
                "version_number": 1,
                "title": "Consumer Care Telephone Format Validator",
                "category": "CATEGORY_B_DATA_QUALITY",
                "statutory_reference": "Quality Metric / Standard Indian Telecom Format",
                "rule_logic_description": "Check if extracted telephone number complies with valid 10-digit mobile or standard landline/toll-free format."
            },
            {
                "rule_code": "DATA_QUAL_DATE_PLAUSIBILITY",
                "version_number": 1,
                "title": "Manufacture Date Plausibility Check",
                "category": "CATEGORY_B_DATA_QUALITY",
                "statutory_reference": "Quality Metric / Date Timeline Validator",
                "rule_logic_description": "Check that manufacture/packing date is a plausible date not set in the future."
            }
        ]

        for r_data in seed_rules:
            existing_rule = db.query(RuleVersion).filter(
                RuleVersion.rule_code == r_data["rule_code"],
                RuleVersion.version_number == r_data["version_number"]
            ).first()
            if not existing_rule:
                rule_obj = RuleVersion(**r_data)
                db.add(rule_obj)
                print(f"[Seed] Added rule: {r_data['rule_code']} (v{r_data['version_number']})")

        db.commit()
        print("[Seed] Database initialization and seeding completed successfully.")

    except Exception as e:
        db.rollback()
        print(f"[Seed Error] {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
