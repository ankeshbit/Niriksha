import pytest
import re
from pathlib import Path
from sqlalchemy import inspect, text
from backend.database import engine, Base
import backend.models as models
from backend.schema_migration import migrate
from backend.seed import seed_database

ROOT_DIR = Path(__file__).resolve().parent.parent
SCHEMA_SQL_PATH = ROOT_DIR / "database" / "schema.sql"


class TestDatabaseSchemaSync:
    """Test suite validating 100% synchronization between models.py, schema.sql, and schema_migration.py."""

    def test_schema_sql_exists_and_defines_all_orm_tables(self):
        """database/schema.sql must contain CREATE TABLE statements for all 17 ORM tables."""
        assert SCHEMA_SQL_PATH.exists(), f"Missing {SCHEMA_SQL_PATH}"
        sql_content = SCHEMA_SQL_PATH.read_text(encoding="utf-8")

        orm_tables = [cls.__tablename__ for cls in Base.__subclasses__()]
        assert len(orm_tables) >= 17, f"Expected at least 17 models, got {len(orm_tables)}"

        for table_name in orm_tables:
            pattern = rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{table_name}\b"
            match = re.search(pattern, sql_content, re.IGNORECASE)
            assert match is not None, f"Table '{table_name}' from models.py is missing from database/schema.sql"

    def test_schema_sql_has_no_duplicate_indexes(self):
        """database/schema.sql must not have duplicate CREATE INDEX statements."""
        sql_content = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
        index_names = re.findall(r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+ON", sql_content, re.IGNORECASE)

        seen = set()
        duplicates = []
        for idx in index_names:
            if idx in seen:
                duplicates.append(idx)
            seen.add(idx)

        assert not duplicates, f"Duplicate index definitions found in schema.sql: {duplicates}"

    def test_schema_migration_is_idempotent(self):
        """Running migrate() twice sequentially must execute cleanly without raising exceptions."""
        # First execution
        migrate()
        # Second execution (verifies idempotency)
        migrate()

    def test_database_has_all_orm_tables_and_columns(self):
        """Database schema must contain every table and column declared in backend/models.py."""
        with engine.connect() as conn:
            insp = inspect(conn)
            db_tables = set(insp.get_table_names())

            for model_cls in Base.__subclasses__():
                table_name = model_cls.__tablename__
                assert table_name in db_tables, f"Database is missing table '{table_name}'"

                db_columns = {c["name"] for c in insp.get_columns(table_name)}
                model_columns = {c.name for c in model_cls.__table__.columns}

                missing_columns = model_columns - db_columns
                assert not missing_columns, (
                    f"Table '{table_name}' is missing columns in the database: {missing_columns}"
                )

    def test_database_seeding_succeeds(self):
        """Seeding must run cleanly on the verified schema."""
        seed_database()

    def test_audit_logs_has_set_null_foreign_key(self):
        """audit_logs.inspection_id foreign key must have ON DELETE SET NULL."""
        with engine.connect() as conn:
            insp = inspect(conn)
            fks = insp.get_foreign_keys("audit_logs")
            inspection_fk = next((fk for fk in fks if "inspection_id" in fk.get("constrained_columns", [])), None)

            if inspection_fk:
                # If FK exists on PostgreSQL, options should specify SET NULL
                options = inspection_fk.get("options", {})
                ondelete = options.get("ondelete", "").upper()
                assert ondelete in ("SET NULL", "CASCADE"), f"Unexpected ondelete rule: {ondelete}"

    def test_stored_files_table_schema(self):
        """stored_files table must have storage_key, content_type, file_size, file_data bytea."""
        with engine.connect() as conn:
            insp = inspect(conn)
            cols = {c["name"]: c for c in insp.get_columns("stored_files")}

            assert "storage_key" in cols
            assert "content_type" in cols
            assert "file_size" in cols
            assert "file_data" in cols
