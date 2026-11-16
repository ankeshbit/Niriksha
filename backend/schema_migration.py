"""
backend/schema_migration.py

Safe, idempotent schema migration helper.
Adds columns that were introduced during the Supabase integration phase.
Run this once against any existing SQLite or PostgreSQL database.

Usage:
    python -m backend.schema_migration
"""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

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
        # Users: add login timestamps
        {
            "table": "users",
            "column": "last_login_at",
            "ddl": "ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP",
        },
        {
            "table": "users",
            "column": "previous_login_at",
            "ddl": "ALTER TABLE users ADD COLUMN previous_login_at TIMESTAMP",
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
        # Inspections: add finalized_at timestamp
        {
            "table": "inspections",
            "column": "finalized_at",
            "ddl": "ALTER TABLE inspections ADD COLUMN finalized_at TIMESTAMP",
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
        # Product Images: metadata and processing status columns
        {
            "table": "product_images",
            "column": "original_filename",
            "ddl": "ALTER TABLE product_images ADD COLUMN original_filename VARCHAR(255)",
        },
        {
            "table": "product_images",
            "column": "mime_type",
            "ddl": "ALTER TABLE product_images ADD COLUMN mime_type VARCHAR(100) DEFAULT 'image/jpeg'",
        },
        {
            "table": "product_images",
            "column": "file_size",
            "ddl": "ALTER TABLE product_images ADD COLUMN file_size INTEGER DEFAULT 0",
        },
        {
            "table": "product_images",
            "column": "width",
            "ddl": "ALTER TABLE product_images ADD COLUMN width INTEGER DEFAULT 0",
        },
        {
            "table": "product_images",
            "column": "height",
            "ddl": "ALTER TABLE product_images ADD COLUMN height INTEGER DEFAULT 0",
        },
        {
            "table": "product_images",
            "column": "quality_metadata_json",
            "ddl": "ALTER TABLE product_images ADD COLUMN quality_metadata_json TEXT",
        },
        {
            "table": "product_images",
            "column": "processing_status",
            "ddl": "ALTER TABLE product_images ADD COLUMN processing_status VARCHAR(50) DEFAULT 'UPLOADED'",
        },
        # Declarations: PS 26034 Extended Validation Attributes
        {
            "table": "declarations",
            "column": "normalized_value",
            "ddl": "ALTER TABLE declarations ADD COLUMN normalized_value TEXT",
        },
        {
            "table": "declarations",
            "column": "source_image_id",
            "ddl": "ALTER TABLE declarations ADD COLUMN source_image_id VARCHAR(36)",
        },
        {
            "table": "declarations",
            "column": "updated_at",
            "ddl": "ALTER TABLE declarations ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
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
        # Products: add persisted product_key for fast indexed grouping and pagination
        {
            "table": "products",
            "column": "product_key",
            "ddl": "ALTER TABLE products ADD COLUMN product_key VARCHAR(64)",
        },
    ]

    with engine.connect() as conn:
        # Step 1: Ensure all ORM tables are created if not already present
        try:
            Base.metadata.create_all(bind=conn)
            conn.commit()
            print("  [OK]    All ORM tables verified/created via metadata.")
        except Exception as e:
            print(f"  [WARN]  Table metadata creation notice: {e}")

        # Step 2: Ensure all additive columns exist on older tables
        insp = inspect(conn)
        table_cols = {}
        for m in migrations:
            tbl = m["table"]
            if tbl not in table_cols:
                try:
                    table_cols[tbl] = {c["name"] for c in insp.get_columns(tbl)}
                except Exception:
                    table_cols[tbl] = set()
            if m["column"] not in table_cols[tbl]:
                print(f"  [APPLY] Adding {m['table']}.{m['column']}")
                conn.execute(text(m["ddl"]))
                conn.commit()
                table_cols[tbl].add(m["column"])
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

        # Ensure foreign-key and composite performance indexes exist
        migrate_performance_indexes(conn)

        # Backfill product_key for any existing products missing it
        backfill_product_keys(conn)

        # AUDIT-CONCUR-01: Ensure inspection_number_counters table exists and is initialized
        migrate_inspection_number_counters(conn)

        # AUDIT-DEL-01: Ensure audit_logs.inspection_id foreign key has ON DELETE SET NULL
        migrate_audit_logs_foreign_key(conn)

        # Ensure partial unique index on active ocr_jobs exists
        migrate_ocr_jobs(conn)

        # Ensure persistent stored_files table exists
        migrate_stored_files(conn)

        # Ensure revoked_tokens table exists for JWT revocation
        migrate_revoked_tokens(conn)

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


def migrate_ocr_jobs(conn):
    """Ensure partial unique index on active ocr_jobs exists: strictly 1 active job per inspection."""
    try:
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_ocr_jobs_active_per_inspection 
            ON ocr_jobs (inspection_id) 
            WHERE status IN ('PENDING', 'PROCESSING');
        """))
        conn.commit()
        print("  [OK]    Partial unique index uq_ocr_jobs_active_per_inspection verified.")
    except Exception as e:
        conn.rollback()
        print(f"  [WARN]  ocr_jobs partial unique index note: {e}")


def migrate_stored_files(conn):
    """Ensure persistent stored_files table exists for crash-resilient image storage."""
    try:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stored_files (
                storage_key VARCHAR(500) PRIMARY KEY,
                content_type VARCHAR(100) NOT NULL DEFAULT 'image/jpeg',
                file_size INTEGER NOT NULL DEFAULT 0,
                file_data BYTEA NOT NULL,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.commit()
        print("  [OK]    Table stored_files verified.")
    except Exception as e:
        conn.rollback()
        print(f"  [WARN]  stored_files table creation note: {e}")


def migrate_revoked_tokens(conn):
    """Ensure revoked_tokens table exists for secure JWT token invalidation on logout."""
    try:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS revoked_tokens (
                token_hash VARCHAR(64) PRIMARY KEY,
                officer_id VARCHAR(50) NOT NULL,
                expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                revoked_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                reason VARCHAR(50) NOT NULL DEFAULT 'LOGOUT'
            );
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_revoked_tokens_officer_id ON revoked_tokens (officer_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_revoked_tokens_expires_at ON revoked_tokens (expires_at);"))
        conn.commit()
        print("  [OK]    Table revoked_tokens verified.")
    except Exception as e:
        conn.rollback()
        print(f"  [WARN]  revoked_tokens table creation note: {e}")


def migrate_performance_indexes(conn):
    """Ensures foreign key and composite query indexes exist for high-volume inspection tables."""
    index_statements = [
        ("ix_product_images_inspection_id", "CREATE INDEX IF NOT EXISTS ix_product_images_inspection_id ON product_images (inspection_id)"),
        ("ix_declarations_inspection_id", "CREATE INDEX IF NOT EXISTS ix_declarations_inspection_id ON declarations (inspection_id)"),
        ("ix_compliance_checks_inspection_id", "CREATE INDEX IF NOT EXISTS ix_compliance_checks_inspection_id ON compliance_checks (inspection_id)"),
        ("ix_evidence_check_id", "CREATE INDEX IF NOT EXISTS ix_evidence_check_id ON evidence (check_id)"),
        ("ix_ocr_results_image_id", "CREATE INDEX IF NOT EXISTS ix_ocr_results_image_id ON ocr_results (image_id)"),
        ("ix_inspector_reviews_check_id", "CREATE INDEX IF NOT EXISTS ix_inspector_reviews_check_id ON inspector_reviews (check_id)"),
        ("ix_audit_logs_inspection_id", "CREATE INDEX IF NOT EXISTS ix_audit_logs_inspection_id ON audit_logs (inspection_id)"),
        ("ix_listing_comparisons_inspection_id", "CREATE INDEX IF NOT EXISTS ix_listing_comparisons_inspection_id ON listing_comparisons (inspection_id)"),
        ("ix_compliance_checks_inspection_id_result_state_adjudication_status", "CREATE INDEX IF NOT EXISTS ix_compliance_checks_inspection_id_result_state_adjudication_status ON compliance_checks (inspection_id, result_state, adjudication_status)"),
        ("ix_products_product_key", "CREATE INDEX IF NOT EXISTS ix_products_product_key ON products (product_key)"),
    ]
    for idx_name, stmt in index_statements:
        try:
            conn.execute(text(stmt))
            conn.commit()
            print(f"  [OK]    Index {idx_name} verified.")
        except Exception as e:
            conn.rollback()
            print(f"  [WARN]  Index {idx_name} creation note: {e}")


def backfill_product_keys(conn):
    """Backfills product_key for any existing products missing it."""
    try:
        import hashlib
        rows = conn.execute(text("SELECT id, product_name, brand_name, category FROM products WHERE product_key IS NULL")).fetchall()
        if rows:
            print(f"  [APPLY] Backfilling product_key for {len(rows)} products...")
            for row in rows:
                p_id, p_name, b_name, cat = row[0], row[1], row[2], row[3]
                clean_p = (p_name or "").strip().lower()
                clean_b = (b_name or "").strip().lower()
                clean_c = (cat or "").strip().lower()
                pkey = hashlib.sha256(f"{clean_p}|{clean_b}|{clean_c}".encode("utf-8")).hexdigest()[:16]
                conn.execute(
                    text("UPDATE products SET product_key = :pkey WHERE id = :p_id"),
                    {"pkey": pkey, "p_id": p_id}
                )
            conn.commit()
            print(f"  [OK]    Backfilled {len(rows)} product keys.")
    except Exception as e:
        conn.rollback()
        print(f"  [WARN]  Product key backfill note: {e}")


if __name__ == "__main__":
    print("Running Legal Metrology DB Schema Migration...")
    migrate()

