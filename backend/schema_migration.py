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


def column_exists(conn, table: str, column: str) -> bool:
    """Check if a column exists in a given table."""
    try:
        result = conn.execute(text(f"SELECT {column} FROM {table} LIMIT 0"))
        result.close()
        return True
    except Exception:
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

    print("\nMigration complete.")


if __name__ == "__main__":
    print("Running Legal Metrology DB Schema Migration...")
    migrate()
