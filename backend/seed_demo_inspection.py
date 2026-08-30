"""
backend/seed_demo_inspection.py

Clears all historical inspection records and seeds exactly ONE complete, finalized reference
inspection and its statutory report to ensure consistent MVP demo data.
"""

import sys
import uuid
import json
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session
from backend.database import SessionLocal, engine, Base
from backend.models import (
    User, RuleVersion, Inspection, Product, ProductImage,
    OCRResult, Declaration, ComplianceCheck, Evidence, AuditLog, Report
)
from backend.report_service import report_generator
from backend.config import settings

def seed_single_demo_inspection():
    db = SessionLocal()
    try:
        # 1. Verify Seed Officer exists
        officer = db.query(User).filter(User.officer_id == settings.SEED_OFFICER_ID).first()
        if not officer:
            print("[Error] Seed officer account not found. Please run seed_database first.")
            return

        # 2. Clear all existing inspections and child tables to keep exactly ONE reference
        print("[Demo Seed] Cleaning up all existing inspection records...")
        db.query(Report).delete()
        db.query(AuditLog).delete()
        db.query(Evidence).delete()
        db.query(ComplianceCheck).delete()
        db.query(Declaration).delete()
        db.query(OCRResult).delete()
        db.query(ProductImage).delete()
        db.query(Product).delete()
        db.query(Inspection).delete()
        db.commit()

        # 3. Create the ONE reference inspection
        inspection_id = str(uuid.uuid4())
        inspection_number = "LM-2026-00001"
        print(f"[Demo Seed] Seeding reference inspection {inspection_number}...")

        inspection = Inspection(
            id=inspection_id,
            inspection_number=inspection_number,
            inspector_id=officer.id,
            location="Azadpur Wholesale Mandi, Delhi",
            status="COMPLETED",
            overall_status="POTENTIAL_NON_COMPLIANCE",
            notes="Regular statutory inspection of packaged commodity. Detected potential non-compliance on consumer care email format.",
            created_at=datetime.utcnow()
        )
        db.add(inspection)

        # 4. Create Product details
        product = Product(
            id=str(uuid.uuid4()),
            inspection_id=inspection_id,
            product_name="Premium Basmati Rice 5kg",
            brand_name="Royal Harvest",
            category="Packaged Food",
            batch_number="B-RH9876",
            created_at=datetime.utcnow()
        )
        db.add(product)

        # 5. Create default package images
        front_image_id = str(uuid.uuid4())
        back_image_id = str(uuid.uuid4())

        front_image = ProductImage(
            id=front_image_id,
            inspection_id=inspection_id,
            original_filename="front_label.jpg",
            file_path="/uploads/inspections/default/front_label.jpg",
            mime_type="image/jpeg",
            file_size=1024 * 340,
            width=800,
            height=800,
            sequence_order=1,
            view_type="front",
            blur_score=0.98,
            glare_score=0.97,
            quality_score=0.98,
            quality_status="GOOD",
            quality_metadata_json=json.dumps({"blur_ok": True, "brightness_ok": True, "resolution_ok": True, "warnings": []}),
            processing_status="QUALITY_CHECKED",
            created_at=datetime.utcnow()
        )
        db.add(front_image)

        back_image = ProductImage(
            id=back_image_id,
            inspection_id=inspection_id,
            original_filename="back_label.jpg",
            file_path="/uploads/inspections/default/back_label.jpg",
            mime_type="image/jpeg",
            file_size=1024 * 280,
            width=800,
            height=800,
            sequence_order=2,
            view_type="back",
            blur_score=0.95,
            glare_score=0.96,
            quality_score=0.95,
            quality_status="GOOD",
            quality_metadata_json=json.dumps({"blur_ok": True, "brightness_ok": True, "resolution_ok": True, "warnings": []}),
            processing_status="QUALITY_CHECKED",
            created_at=datetime.utcnow()
        )
        db.add(back_image)

        # 6. Create Declarations (both original and corrected)
        declarations = [
            ("commodity_name", "Basmati Rice"),
            ("manufacturer_details", "Royal Food Products, 12 Industrial Area, Azadpur, Delhi - 110033"),
            ("net_quantity", "5 kg"),
            ("mrp", "Rs. 450.00 (Incl. of all taxes)"),
            ("date_of_manufacture_packing", "08/2026"),
            ("consumer_care_details", "Phone: 1800-11-2233, Email: support_royalhouse.com"), # Missing @ in email
            ("country_of_origin", "India")
        ]

        for field, value in declarations:
            decl = Declaration(
                id=str(uuid.uuid4()),
                inspection_id=inspection_id,
                field_name=field,
                extracted_value=value,
                corrected_value=value,
                created_at=datetime.utcnow()
            )
            db.add(decl)

        # 7. Create Compliance Checks
        rules = db.query(RuleVersion).all()
        rule_map = {r.rule_code: r for r in rules}

        # List of expected compliance checks
        checks_data = [
            ("PCR_RULE_06_1_E", "PASS", "Rs. 450.00 (Incl. of all taxes)", "MRP declared in compliance with Rule 6(1)(e)."),
            ("PCR_RULE_06_1_A", "PASS", "Royal Food Products, 12 Industrial Area, Azadpur, Delhi - 110033", "Manufacturer name and address declared in compliance with Rule 6(1)(a)."),
            ("PCR_RULE_06_1_C", "PASS", "5 kg", "Net quantity declared in standard metric units."),
            ("PCR_RULE_06_1_D", "PASS", "08/2026", "Month and year of packing declared in compliance with Rule 6(1)(d)."),
            ("PCR_RULE_06_1_G", "FAIL", "Phone: 1800-11-2233, Email: support_royalhouse.com", "Consumer care details found, but contact email lacks '@' symbol."),
            ("PCR_RULE_06_1_F", "PASS", "Basmati Rice", "Commodity identity declared on Principal Display Panel."),
            ("PCR_RULE_06_1_B", "PASS", "India", "Country of origin declared in compliance with Rule 6(1)(b)."),
            ("DATA_QUAL_PHONE_SYNTAX", "PASS", "1800-11-2233", "Toll-free consumer care format is valid."),
            ("DATA_QUAL_DATE_PLAUSIBILITY", "PASS", "08/2026", "Packing date is plausible and not future-dated.")
        ]

        compliance_checks = []
        for code, res, val, exp in checks_data:
            rule_ver = rule_map.get(code)
            rule_ver_id = rule_ver.id if rule_ver else "rule-ver-placeholder"
            check = ComplianceCheck(
                id=str(uuid.uuid4()),
                inspection_id=inspection_id,
                rule_version_id=rule_ver_id,
                rule_code=code,
                title=rule_ver.title if rule_ver else code,
                severity=rule_ver.category if rule_ver else "MAJOR",
                result_state=res,
                extracted_value=val,
                explanation=exp,
                adjudication_status="CONFIRMED" if res == "FAIL" else "PENDING",
                adjudication_notes="Confirmed by inspector. Email format is invalid." if res == "FAIL" else None,
                adjudicated_by=officer.officer_id if res == "FAIL" else None,
                adjudicated_at=datetime.utcnow() if res == "FAIL" else None,
                created_at=datetime.utcnow()
            )
            db.add(check)
            compliance_checks.append(check)

            # If failed, add Evidence / Finding record
            if res == "FAIL":
                evidence = Evidence(
                    id=str(uuid.uuid4()),
                    check_id=check.id,
                    image_id=back_image_id,
                    bounding_box_json=json.dumps([0.1, 0.2, 0.4, 0.3]),
                    crop_image_path="/uploads/inspections/default/back_label_crop.jpg",
                    highlight_text=val,
                    reason="Consumer care email lacks standard domain formatting.",
                    created_at=datetime.utcnow()
                )
                db.add(evidence)

        # 8. Create statutory PDF report
        print("[Demo Seed] Generating PDF report...")
        db.flush()  # Push changes to generate report dependencies

        pdf_path = report_generator.generate_pdf(
            inspection=inspection,
            product=product,
            inspector=officer,
            declarations=db.query(Declaration).filter(Declaration.inspection_id == inspection_id).all(),
            compliance_checks=compliance_checks,
            evidence_items=db.query(Evidence).join(ComplianceCheck).filter(ComplianceCheck.inspection_id == inspection_id).all(),
            report_version=1
        )

        safety_statement = (
            "This official inspection report was generated by the AI-Assisted Legal Metrology Packaged-Commodity Inspection System (DoCA). "
            "Compliance evaluations were executed via deterministic PCR 2011 rule verification under designated inspecting officer authority."
        )

        report_record = Report(
            id=str(uuid.uuid4()),
            inspection_id=inspection_id,
            report_version=1,
            pdf_path=pdf_path,
            legal_safety_statement=safety_statement,
            generated_at=datetime.utcnow()
        )
        db.add(report_record)

        # 9. Audit trail logging
        log = AuditLog(
            id=str(uuid.uuid4()),
            actor_id=officer.officer_id,
            action="INSPECTION_FINALIZED",
            entity_type="inspection",
            entity_id=inspection_id,
            inspection_id=inspection_id,
            details=f"Demo reference inspection {inspection_number} finalized with statutory compliance status.",
            created_at=datetime.utcnow()
        )
        db.add(log)

        db.commit()
        print(f"[Demo Seed] Successfully seeded exactly ONE reference inspection with ID: {inspection_id}")

    except Exception as e:
        db.rollback()
        print(f"[Demo Seed Error] {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_single_demo_inspection()
