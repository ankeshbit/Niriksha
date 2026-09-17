"""
backend/schema_migration.py

Safe, idempotent schema migration helper.
Adds columns that were introduced during the Supabase integration phase.
Run this once against any existing SQLite or PostgreSQL database.

Usage:
    python -m backend.schema_migration
"""

import sys
from sqlalchemy import text, inspect
from backend.database import engine
from backend.models import Base


def column_exists(conn, table: str, column: str) -> bool:
    """Check if a column exists in a given table."""
    try:
        insp = inspect(conn)
        cols = [c["name"] for c in insp.get_columns(table)]
        return column in cols
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False


def migrate():
    migrations = [
        # Users: add email and phone (Phase: Supabase / Profile persistence)
        {
            "table": "users",
            "column": "email",
            "ddl": "ALTER TABLE users ADD COLUMN email TEXT",
        },
        {
            "table": "users",
            "column": "phone",
            "ddl": "ALTER TABLE users ADD COLUMN phone TEXT",
        },
        # Users: add password_updated_at (AUDIT-UI-01)
        {
            "table": "users",
            "column": "password_updated_at",
            "ddl": "ALTER TABLE users ADD COLUMN password_updated_at TIMESTAMP",
        },
        # Users: add role for RBAC (PS 26034)
        {
            "table": "users",
            "column": "role",
            "ddl": "ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'INSPECTOR'",
        },
        # Inspections: add client_draft_id for idempotent offline sync (DEF-08)
        {
            "table": "inspections",
            "column": "client_draft_id",
            "ddl": "ALTER TABLE inspections ADD COLUMN client_draft_id VARCHAR(100)",
        },
        # Reports: add docx_path for editable DOCX compliance report export (PS 26034)
        {
            "table": "reports",
            "column": "docx_path",
            "ddl": "ALTER TABLE reports ADD COLUMN docx_path VARCHAR(500)",
        },
        # Reports: add pdf_hash for PDF cryptographic integrity verification
        {
            "table": "reports",
            "column": "pdf_hash",
            "ddl": "ALTER TABLE reports ADD COLUMN pdf_hash VARCHAR(64)",
        },
        # Inspections: add inspection_type for Online Listing / Physical analysis modes (PS 26034)
        {
            "table": "inspections",
            "column": "inspection_type",
            "ddl": "ALTER TABLE inspections ADD COLUMN inspection_type VARCHAR(50) DEFAULT 'PHYSICAL'",
        },
        # Declarations: PS 26034 Extended Validation Attributes
        {
            "table": "declarations",
            "column": "placement_status",
            "ddl": "ALTER TABLE declarations ADD COLUMN placement_status VARCHAR(50) DEFAULT 'NOT_DETERMINABLE'",
        },
        {
            "table": "declarations",
            "column": "placement_details_json",
            "ddl": "ALTER TABLE declarations ADD COLUMN placement_details_json TEXT",
        },
        {
            "table": "declarations",
            "column": "font_size_status",
            "ddl": "ALTER TABLE declarations ADD COLUMN font_size_status VARCHAR(50) DEFAULT 'FONT_SIZE_UNDETERMINABLE'",
        },
        {
            "table": "declarations",
            "column": "font_size_details_json",
            "ddl": "ALTER TABLE declarations ADD COLUMN font_size_details_json TEXT",
        },
        {
            "table": "declarations",
            "column": "readability_status",
            "ddl": "ALTER TABLE declarations ADD COLUMN readability_status VARCHAR(50) DEFAULT 'NOT_OBSERVABLE'",
        },
        {
            "table": "declarations",
            "column": "readability_details_json",
            "ddl": "ALTER TABLE declarations ADD COLUMN readability_details_json TEXT",
        },
        {
            "table": "declarations",
            "column": "format_status",
            "ddl": "ALTER TABLE declarations ADD COLUMN format_status VARCHAR(50) DEFAULT 'COMPLIANT'",
        },
        {
            "table": "declarations",
            "column": "format_details_json",
            "ddl": "ALTER TABLE declarations ADD COLUMN format_details_json TEXT",
        },
        {
            "table": "declarations",
            "column": "validation_matrix_json",
            "ddl": "ALTER TABLE declarations ADD COLUMN validation_matrix_json TEXT",
        },
        # OCR Results: add derived normalized_text for downstream extraction pipeline
        {
            "table": "ocr_results",
            "column": "normalized_text",
            "ddl": "ALTER TABLE ocr_results ADD COLUMN normalized_text TEXT",
        },
    ]

    with engine.connect() as conn:
        for m in migrations:
            if not column_exists(conn, m["table"], m["column"]):
                print(f"  [APPLY] Adding {m['table']}.{m['column']}")
                conn.execute(text(m["ddl"]))
                conn.commit()
                print(f"  [OK]    {m['table']}.{m['column']} added.")
            else:
                print(f"  [SKIP]  {m['table']}.{m['column']} already exists.")

        # Ensure index on client_draft_id exists
        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_inspections_client_draft_id ON inspections (client_draft_id)"))
            conn.commit()
            print("  [OK]    Index ix_inspections_client_draft_id verified.")
        except Exception as e:
            print(f"  [WARN]  Index creation skipped: {e}")

        # AUDIT-CONCUR-01: Ensure inspection_number_counters table exists and is initialized
        migrate_inspection_number_counters(conn)

        # AUDIT-DEL-01: Ensure audit_logs.inspection_id foreign key has ON DELETE SET NULL
        migrate_audit_logs_foreign_key(conn)

        # Create any new tables (product_listings, listing_comparisons)
        try:
            Base.metadata.create_all(bind=conn)
            conn.commit()
            print("  [OK]    All ORM tables (including product_listings, listing_comparisons) verified.")
        except Exception as e:
            print(f"  [WARN]  Table creation note: {e}")

    print("\nMigration complete.")


def migrate_audit_logs_foreign_key(conn):
    """AUDIT-DEL-01: Ensure audit_logs.inspection_id foreign key constraint has ON DELETE SET NULL."""
    try:
        # Check if already exists with SET NULL to avoid exclusive table locks on startup
        check_query = text("""
            SELECT 1 FROM information_schema.referential_constraints rc
            JOIN information_schema.table_constraints tc ON rc.constraint_name = tc.constraint_name
            WHERE tc.table_name = 'audit_logs' AND tc.constraint_name = 'audit_logs_inspection_id_fkey'
            AND rc.delete_rule = 'SET NULL';
        """)
        exists = conn.execute(check_query).scalar()
        if exists:
            print("  [OK]    audit_logs_inspection_id_fkey verified with ON DELETE SET NULL.")
            return

        conn.execute(text("ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS audit_logs_inspection_id_fkey;"))
        conn.execute(text("""
            ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_inspection_id_fkey
            FOREIGN KEY (inspection_id) REFERENCES inspections(id) ON DELETE SET NULL;
        """))
        conn.commit()
        print("  [OK]    audit_logs_inspection_id_fkey verified with ON DELETE SET NULL.")
    except Exception as e:
        conn.rollback()
        print(f"  [WARN]  audit_logs FK constraint migration note: {e}")


def migrate_inspection_number_counters(conn):
    """AUDIT-CONCUR-01: Create inspection_number_counters table and initialize from existing inspections."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS inspection_number_counters (
            year INTEGER PRIMARY KEY,
            next_number INTEGER NOT NULL DEFAULT 1
        )
    """))
    conn.commit()

    try:
        rows = conn.execute(text("""
            SELECT inspection_number FROM inspections WHERE inspection_number LIKE 'LM-%'
        """)).fetchall()

        year_max = {}
        for (num,) in rows:
            if not num:
                continue
            parts = num.split("-")
            if len(parts) == 3 and parts[0] == "LM":
                try:
                    yr = int(parts[1])
                    seq = int(parts[2])
                    year_max[yr] = max(year_max.get(yr, 0), seq)
                except ValueError:
                    pass

        for yr, max_val in year_max.items():
            next_val = max_val + 1
            conn.execute(text("""
                INSERT INTO inspection_number_counters (year, next_number)
                VALUES (:year, :next_val)
                ON CONFLICT (year) DO NOTHING
            """), {"year": yr, "next_val": next_val})
        conn.commit()
        print(f"  [OK]    inspection_number_counters verified. Initialized years: {list(year_max.keys())}")
    except Exception as e:
        print(f"  [WARN]  Could not initialize counters from inspections: {e}")


if __name__ == "__main__":
    print("Running Legal Metrology DB Schema Migration...")
    migrate()
