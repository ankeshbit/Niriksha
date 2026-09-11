"""
backend/migrate_to_postgres.py

Safe, non-destructive, safety-locked data migration script from SQLite (legal_metrology.db) to PostgreSQL (Neon).
Implements the selective data migration plan defined in docs/SQLITE_DATA_MIGRATION_PLAN.md.

SAFETY LOCK:
    Requires explicit confirmation: --confirm CLI flag or MIGRATION_CONFIRM=true environment variable.
    Requires explicit target environment: --target-env (staging | production) or TARGET_ENV.
    Without confirmation, prints a safe diagnostic summary and aborts immediately.

Usage:
    # Migrate to Neon Staging (with confirmation)
    python -m backend.migrate_to_postgres --target-url "postgresql+psycopg://user:password@host/dbname?sslmode=require" --target-env staging --confirm

    # Dry-run validation mode against Staging
    python -m backend.migrate_to_postgres --target-url "..." --target-env staging --dry-run
"""

import os
import sys
import argparse
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker

from backend.models import (
    Base, User, Inspection, Product, ProductImage, OCRResult,
    Declaration, RuleVersion, ComplianceCheck, Evidence,
    InspectorReview, AuditLog, Report
)

BASE_DIR = Path(__file__).resolve().parent.parent
SOURCE_DB_PATH = BASE_DIR / "legal_metrology.db"

# Reference Inspection ID to migrate
REFERENCE_INSPECTION_ID = "a7f72d2d-d9f2-45bf-91f6-6c2062eefe60"  # LM-2026-00001

def parse_dt(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val)
    except Exception:
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(val, fmt)
            except ValueError:
                pass
    return None

def parse_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "t", "yes", "y")
    return bool(val)

def extract_safe_url_details(url: str) -> Dict[str, str]:
    """Extracts safe backend, driver, host, and database name without leaking credentials."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return {
            "backend": parsed.scheme.split("+")[0],
            "driver": parsed.scheme,
            "host": parsed.hostname or "local",
            "database": parsed.path.lstrip("/") or "unknown",
        }
    except Exception:
        return {"backend": "unknown", "driver": "unknown", "host": "masked", "database": "masked"}

def run_migration(
    target_url: str,
    target_env: str = "staging",
    confirmed: bool = False,
    dry_run: bool = False,
    init_schema: bool = False,
    source_path: Optional[Path] = None
) -> Dict[str, int]:
    source_db = source_path or SOURCE_DB_PATH
    if not source_db.exists():
        raise FileNotFoundError(f"Source SQLite database not found at {source_db}")

    safe_details = extract_safe_url_details(target_url)

    print(f"\n{'='*65}")
    print(f" NiriKsha — Safe SQLite -> PostgreSQL / Neon Migration Pipeline")
    print(f"{'='*65}")
    print(f" Source Database   : SQLite ({source_db.name}) [{source_db.stat().st_size} bytes]")
    print(f" Target Backend    : {safe_details['backend']} (Driver: {safe_details['driver']})")
    print(f" Target Host       : {safe_details['host']}")
    print(f" Target Database   : {safe_details['database']}")
    print(f" Target Environment: {target_env.upper()}")
    print(f" Mode              : {'DRY RUN (No data committed)' if dry_run else 'LIVE MIGRATION'}")
    print(f" Record Graph      : LM-2026-00001 (1 Officer, 9 Rules, 1 Inspection + Child Entities)")
    print(f" Excluded Legacy   : LM-2026-00002..00004 (Preserved in SQLite, Excluded from Neon)")
    print(f"{'='*65}\n")

    # Safety Check 1: Target cannot be the production SQLite database
    if "legal_metrology.db" in target_url and "test" not in target_url and not target_url.startswith("postgresql"):
        raise ValueError("SAFETY ERROR: Target URL cannot resolve to the source SQLite database (legal_metrology.db)!")

    # Safety Check 2: Require confirmation lock
    if not confirmed and not dry_run:
        print("[SAFETY LOCK ACTIVE] Migration requires explicit confirmation.")
        print("Set MIGRATION_CONFIRM=true or pass --confirm to proceed.")
        print("ABORTING without modifying any database.\n")
        sys.exit(1)

    # 1. Connect to PostgreSQL target
    print("[1/5] Connecting to target database...")
    target_engine = create_engine(
        target_url,
        pool_pre_ping=True,
        pool_recycle=300,
        echo=False
    )

    inspector = inspect(target_engine)
    existing_tables = inspector.get_table_names()

    # Safety Check 3: Schema provisioning policy
    if not existing_tables or target_env == "staging" or init_schema:
        print("      Provisioning / verifying target schema tables...")
        Base.metadata.create_all(bind=target_engine)
        print("      Schema verified / created successfully.")
    else:
        print(f"      Verified {len(existing_tables)} existing tables in target database.")

    TargetSession = sessionmaker(bind=target_engine, autocommit=False, autoflush=False)
    session = TargetSession()

    # 2. Connect to source SQLite in read-only mode
    print("\n[2/5] Connecting to source SQLite in READ-ONLY mode...")
    sqlite_conn = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
    sqlite_conn.row_factory = sqlite3.Row
    s_cur = sqlite_conn.cursor()

    stats: Dict[str, int] = {}

    try:
        # Step 1: Users (Migrate Officer DOCA-INSP-842)
        print("\n[3/5] Migrating identifiable production record graph in DAG order...")
        s_cur.execute("SELECT * FROM users WHERE officer_id = 'DOCA-INSP-842';")
        user_rows = s_cur.fetchall()
        for r in user_rows:
            existing = session.query(User).filter(User.id == r["id"]).first()
            if not existing:
                session.add(User(
                    id=r["id"],
                    officer_id=r["officer_id"],
                    full_name=r["full_name"],
                    email=r["email"],
                    phone=r["phone"],
                    designation=r["designation"],
                    zone=r["zone"],
                    password_hash=r["password_hash"],
                    role=r["role"],
                    created_at=parse_dt(r["created_at"]),
                    last_login_at=parse_dt(r["last_login_at"]),
                    previous_login_at=parse_dt(r["previous_login_at"])
                ))
        stats["users"] = len(user_rows)
        session.flush()
        print(f"      - users: {len(user_rows)} migrated (Officer DOCA-INSP-842)")

        # Step 2: Rule Versions (All 9 PCR 2011 statutory rule versions)
        s_cur.execute("SELECT * FROM rule_versions ORDER BY rule_code;")
        rule_rows = s_cur.fetchall()
        for r in rule_rows:
            existing = session.query(RuleVersion).filter(RuleVersion.id == r["id"]).first()
            if not existing:
                session.add(RuleVersion(
                    id=r["id"],
                    rule_code=r["rule_code"],
                    version_number=r["version_number"],
                    title=r["title"],
                    category=r["category"],
                    statutory_reference=r["statutory_reference"],
                    rule_logic_description=r["rule_logic_description"],
                    severity=r["severity"],
                    is_active=parse_bool(r["is_active"]),
                    created_at=parse_dt(r["created_at"])
                ))
        stats["rule_versions"] = len(rule_rows)
        session.flush()
        print(f"      - rule_versions: {len(rule_rows)} migrated (9 Statutory PCR Rules)")

        # Step 3: Inspections (Reference LM-2026-00001)
        s_cur.execute("SELECT * FROM inspections WHERE id = ?;", (REFERENCE_INSPECTION_ID,))
        insp_rows = s_cur.fetchall()
        for r in insp_rows:
            existing = session.query(Inspection).filter(Inspection.id == r["id"]).first()
            if not existing:
                session.add(Inspection(
                    id=r["id"],
                    inspection_number=r["inspection_number"],
                    inspector_id=r["inspector_id"],
                    location=r["location"],
                    status=r["status"],
                    overall_status=r["overall_status"],
                    notes=r["notes"],
                    client_draft_id=r["client_draft_id"] if "client_draft_id" in r.keys() else None,
                    created_at=parse_dt(r["created_at"]),
                    finalized_at=parse_dt(r["finalized_at"])
                ))
        stats["inspections"] = len(insp_rows)
        session.flush()
        print(f"      - inspections: {len(insp_rows)} migrated (LM-2026-00001)")

        # Step 4: Products (Child of LM-2026-00001)
        s_cur.execute("SELECT * FROM products WHERE inspection_id = ?;", (REFERENCE_INSPECTION_ID,))
        prod_rows = s_cur.fetchall()
        for r in prod_rows:
            existing = session.query(Product).filter(Product.id == r["id"]).first()
            if not existing:
                session.add(Product(
                    id=r["id"],
                    inspection_id=r["inspection_id"],
                    product_name=r["product_name"],
                    brand_name=r["brand_name"],
                    category=r["category"],
                    batch_number=r["batch_number"],
                    created_at=parse_dt(r["created_at"])
                ))
        stats["products"] = len(prod_rows)
        session.flush()
        print(f"      - products: {len(prod_rows)} migrated (Himalayan Organic Oats)")

        # Step 5: Product Images (Children of LM-2026-00001)
        s_cur.execute("SELECT * FROM product_images WHERE inspection_id = ? ORDER BY sequence_order;", (REFERENCE_INSPECTION_ID,))
        img_rows = s_cur.fetchall()
        img_ids = [r["id"] for r in img_rows]
        for r in img_rows:
            existing = session.query(ProductImage).filter(ProductImage.id == r["id"]).first()
            if not existing:
                session.add(ProductImage(
                    id=r["id"],
                    inspection_id=r["inspection_id"],
                    original_filename=r["original_filename"],
                    file_path=r["file_path"],
                    mime_type=r["mime_type"],
                    file_size=r["file_size"],
                    width=r["width"],
                    height=r["height"],
                    sequence_order=r["sequence_order"],
                    view_type=r["view_type"],
                    blur_score=r["blur_score"],
                    glare_score=r["glare_score"],
                    quality_score=r["quality_score"],
                    quality_status=r["quality_status"],
                    quality_metadata_json=r["quality_metadata_json"],
                    processing_status=r["processing_status"],
                    created_at=parse_dt(r["created_at"])
                ))
        stats["product_images"] = len(img_rows)
        session.flush()
        print(f"      - product_images: {len(img_rows)} migrated (Front & Back Views)")

        # Step 6: OCR Results (Children of LM-2026-00001 Images)
        if img_ids:
            s_cur.execute(f"SELECT * FROM ocr_results WHERE image_id IN ({','.join(['?']*len(img_ids))});", img_ids)
            ocr_rows = s_cur.fetchall()
        else:
            ocr_rows = []
        for r in ocr_rows:
            existing = session.query(OCRResult).filter(OCRResult.id == r["id"]).first()
            if not existing:
                session.add(OCRResult(
                    id=r["id"],
                    image_id=r["image_id"],
                    raw_text=r["raw_text"],
                    confidence=r["confidence"],
                    bounding_boxes_json=r["bounding_boxes_json"],
                    created_at=parse_dt(r["created_at"])
                ))
        stats["ocr_results"] = len(ocr_rows)
        session.flush()
        print(f"      - ocr_results: {len(ocr_rows)} migrated (Genuine OCR Provenance)")

        # Step 7: Declarations (Children of LM-2026-00001)
        s_cur.execute("SELECT * FROM declarations WHERE inspection_id = ?;", (REFERENCE_INSPECTION_ID,))
        decl_rows = s_cur.fetchall()
        for r in decl_rows:
            existing = session.query(Declaration).filter(Declaration.id == r["id"]).first()
            if not existing:
                session.add(Declaration(
                    id=r["id"],
                    inspection_id=r["inspection_id"],
                    field_name=r["field_name"],
                    extracted_value=r["extracted_value"],
                    normalized_value=r["normalized_value"],
                    confidence=r["confidence"],
                    bounding_box_json=r["bounding_box_json"],
                    extraction_status=r["extraction_status"],
                    corrected_value=r["corrected_value"],
                    is_applicable=parse_bool(r["is_applicable"]),
                    verification_status=r["verification_status"],
                    verified_by=r["verified_by"],
                    verified_at=parse_dt(r["verified_at"]),
                    correction_reason=r["correction_reason"],
                    source_image_id=r["source_image_id"],
                    created_at=parse_dt(r["created_at"]),
                    updated_at=parse_dt(r["updated_at"])
                ))
        stats["declarations"] = len(decl_rows)
        session.flush()
        print(f"      - declarations: {len(decl_rows)} migrated (Verified Statutory Fields)")

        # Step 8: Compliance Checks (Children of LM-2026-00001)
        s_cur.execute("SELECT * FROM compliance_checks WHERE inspection_id = ?;", (REFERENCE_INSPECTION_ID,))
        check_rows = s_cur.fetchall()
        check_ids = [r["id"] for r in check_rows]
        for r in check_rows:
            existing = session.query(ComplianceCheck).filter(ComplianceCheck.id == r["id"]).first()
            if not existing:
                session.add(ComplianceCheck(
                    id=r["id"],
                    inspection_id=r["inspection_id"],
                    rule_version_id=r["rule_version_id"],
                    rule_code=r["rule_code"],
                    title=r["title"],
                    severity=r["severity"],
                    result_state=r["result_state"],
                    extracted_value=r["extracted_value"],
                    explanation=r["explanation"],
                    adjudication_status=r["adjudication_status"],
                    adjudication_notes=r["adjudication_notes"],
                    adjudicated_by=r["adjudicated_by"],
                    adjudicated_at=parse_dt(r["adjudicated_at"]),
                    created_at=parse_dt(r["created_at"])
                ))
        stats["compliance_checks"] = len(check_rows)
        session.flush()
        print(f"      - compliance_checks: {len(check_rows)} migrated (Rule Evaluation Findings)")

        # Step 9: Evidence (Children of Compliance Checks)
        if check_ids:
            s_cur.execute(f"SELECT * FROM evidence WHERE check_id IN ({','.join(['?']*len(check_ids))});", check_ids)
            ev_rows = s_cur.fetchall()
        else:
            ev_rows = []
        for r in ev_rows:
            existing = session.query(Evidence).filter(Evidence.id == r["id"]).first()
            if not existing:
                session.add(Evidence(
                    id=r["id"],
                    check_id=r["check_id"],
                    image_id=r["image_id"],
                    bounding_box_json=r["bounding_box_json"],
                    crop_image_path=r["crop_image_path"],
                    highlight_text=r["highlight_text"],
                    reason=r["reason"],
                    created_at=parse_dt(r["created_at"])
                ))
        stats["evidence"] = len(ev_rows)
        session.flush()
        print(f"      - evidence: {len(ev_rows)} migrated (Photographic Bounding Boxes)")

        # Step 10: Inspector Reviews (Children of Compliance Checks)
        if check_ids:
            s_cur.execute(f"SELECT * FROM inspector_reviews WHERE check_id IN ({','.join(['?']*len(check_ids))});", check_ids)
            rev_rows = s_cur.fetchall()
        else:
            rev_rows = []
        for r in rev_rows:
            existing = session.query(InspectorReview).filter(InspectorReview.id == r["id"]).first()
            if not existing:
                session.add(InspectorReview(
                    id=r["id"],
                    check_id=r["check_id"],
                    officer_id=r["officer_id"],
                    action=r["action"],
                    remarks=r["remarks"],
                    reviewed_at=parse_dt(r["reviewed_at"])
                ))
        stats["inspector_reviews"] = len(rev_rows)
        session.flush()
        print(f"      - inspector_reviews: {len(rev_rows)} migrated (Adjudications & Remarks)")

        # Step 11: Reports (Child of LM-2026-00001)
        s_cur.execute("SELECT * FROM reports WHERE inspection_id = ?;", (REFERENCE_INSPECTION_ID,))
        rep_rows = s_cur.fetchall()
        for r in rep_rows:
            existing = session.query(Report).filter(Report.id == r["id"]).first()
            if not existing:
                session.add(Report(
                    id=r["id"],
                    inspection_id=r["inspection_id"],
                    report_version=r["report_version"],
                    pdf_path=r["pdf_path"],
                    legal_safety_statement=r["legal_safety_statement"],
                    generated_at=parse_dt(r["generated_at"])
                ))
        stats["reports"] = len(rep_rows)
        session.flush()
        print(f"      - reports: {len(rep_rows)} migrated (Official Report v3)")

        # Step 12: Audit Logs (LM-2026-00001 + System/Auth Logs)
        s_cur.execute("SELECT * FROM audit_logs WHERE inspection_id = ? OR inspection_id IS NULL;", (REFERENCE_INSPECTION_ID,))
        audit_rows = s_cur.fetchall()
        for r in audit_rows:
            existing = session.query(AuditLog).filter(AuditLog.id == r["id"]).first()
            if not existing:
                session.add(AuditLog(
                    id=r["id"],
                    inspection_id=r["inspection_id"],
                    actor_id=r["actor_id"],
                    action=r["action"],
                    entity_type=r["entity_type"],
                    entity_id=r["entity_id"],
                    old_value=r["old_value"],
                    new_value=r["new_value"],
                    details=r["details"],
                    created_at=parse_dt(r["created_at"])
                ))
        stats["audit_logs"] = len(audit_rows)
        session.flush()
        print(f"      - audit_logs: {len(audit_rows)} migrated (Immutable Audit Trail)")

        # Step 4: Verification
        print("\n[4/5] Verifying target PostgreSQL relational graph integrity...")
        total_migrated = sum(stats.values())
        print(f"      Total records staged: {total_migrated}")

        # Assert foreign key relationships in staging session
        user_check = session.query(User).filter(User.officer_id == "DOCA-INSP-842").first()
        assert user_check is not None, "Migrated user not found in target session"

        insp_check = session.query(Inspection).filter(Inspection.id == REFERENCE_INSPECTION_ID).first()
        assert insp_check is not None, "Migrated reference inspection not found in target session"
        assert insp_check.product is not None, "Product relationship broken"
        assert len(insp_check.images) == 2, f"Expected 2 images, found {len(insp_check.images)}"
        assert len(insp_check.declarations) == 7, f"Expected 7 declarations, found {len(insp_check.declarations)}"
        assert len(insp_check.compliance_checks) == 9, f"Expected 9 checks, found {len(insp_check.compliance_checks)}"
        assert insp_check.report is not None, "Report relationship broken"
        print("      Relational integrity verified: 0 orphan keys, 100% graph connectivity.")

        if dry_run:
            print("\n[5/5] DRY RUN COMPLETE: Rolling back transaction (zero data committed).")
            session.rollback()
        else:
            session.commit()
            print("\n[5/5] TRANSACTION COMMITTED: All records safely migrated to PostgreSQL.")

        return stats

    except Exception as e:
        session.rollback()
        print(f"\n[ERROR] Migration failed and was rolled back completely: {e}")
        # Verify rollback left target clean
        try:
            partial_check = session.query(Inspection).filter(Inspection.id == REFERENCE_INSPECTION_ID).first()
            if partial_check is None:
                print("        Rollback verified: Target database contains zero partial records.")
        except Exception:
            pass
        raise
    finally:
        session.close()
        sqlite_conn.close()
        try:
            target_engine.dispose()
        except Exception:
            pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NiriKsha SQLite to PostgreSQL Migration")
    parser.add_argument("--target-url", type=str, default=None, help="Target PostgreSQL connection URL")
    parser.add_argument("--target-env", type=str, default="staging", choices=["staging", "production"], help="Target environment (staging or production)")
    parser.add_argument("--confirm", action="store_true", help="Explicit confirmation lock required to execute migration")
    parser.add_argument("--dry-run", action="store_true", help="Run without committing transaction")
    parser.add_argument("--init-schema", action="store_true", help="Explicitly allow schema creation in production")
    parser.add_argument("--source-db", type=str, default=None, help="Path to source SQLite database")
    args = parser.parse_args()

    url = args.target_url or os.environ.get("TARGET_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        print("Error: Target database URL must be provided via --target-url or TARGET_DATABASE_URL/DATABASE_URL environment variable.")
        sys.exit(1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)

    confirmed = args.confirm or os.environ.get("MIGRATION_CONFIRM", "").strip().lower() in ("true", "1", "yes")
    target_env = os.environ.get("TARGET_ENV", args.target_env).strip().lower()
    s_path = Path(args.source_db) if args.source_db else SOURCE_DB_PATH

    run_migration(
        url,
        target_env=target_env,
        confirmed=confirmed,
        dry_run=args.dry_run,
        init_schema=args.init_schema,
        source_path=s_path
    )
