"""
tests/test_database_safety.py

Safety verification ensuring:
1. Automated tests run against a PostgreSQL test database (never SQLite, never production).
2. Test reports are written to an ephemeral directory (never to production generated_reports/).
3. No local SQLite database files exist in the project root after a test run.
4. The test engine URL differs from the production DATABASE_URL.
"""

import os
from pathlib import Path
from backend.config import settings
import backend.database as db_module
import backend.main as main_module

BASE_DIR = Path(__file__).resolve().parent.parent


def test_database_engine_is_postgresql():
    """Verify that the test engine uses PostgreSQL (not SQLite)."""
    engine_url_str = str(db_module.engine.url)
    assert not engine_url_str.startswith("sqlite"), (
        f"Test engine must not use SQLite. Got: {engine_url_str}"
    )
    assert "postgresql" in engine_url_str.lower() or "postgres" in engine_url_str.lower(), (
        f"Test engine must be PostgreSQL. Got: {engine_url_str}"
    )


def test_test_database_url_differs_from_production():
    """Verify the test database URL is different from the production DATABASE_URL."""
    from dotenv import dotenv_values
    env_vals = dotenv_values(BASE_DIR / ".env")
    prod_url = (
        os.environ.get("ORIGINAL_PRODUCTION_DATABASE_URL", "").strip()
        or env_vals.get("DATABASE_URL", "").strip()
    )
    test_url = (
        os.environ.get("TEST_DATABASE_URL", "").strip()
        or env_vals.get("TEST_DATABASE_URL", "").strip()
    )
    engine_url_str = str(db_module.engine.url)

    if prod_url and test_url:
        assert test_url != prod_url, (
            "TEST_DATABASE_URL must not equal the production DATABASE_URL.\n"
            "Tests cannot run against the production Neon database."
        )
    if prod_url:
        assert engine_url_str != prod_url, (
            "Test engine must not be connected to the production database."
        )


def test_reports_dir_is_not_production():
    """Verify test reports are written to an ephemeral directory, never to production generated_reports/."""
    reports_dir_str = str(main_module.REPORTS_DIR).replace("\\", "/")
    assert not (reports_dir_str.endswith("generated_reports") or "generated_reports" in reports_dir_str.split("/")), (
        "Test report paths cannot point to generated_reports/."
    )


def test_no_sqlite_db_files_in_project_root():
    """Verify no SQLite database files exist in the project root (application must not create them)."""
    db_files = (
        list(BASE_DIR.glob("*.db"))
        + list(BASE_DIR.glob("*.sqlite"))
        + list(BASE_DIR.glob("*.sqlite3"))
    )
    # Exclude intentional archived migration backup files
    exclusion_keywords = [".pre_postgres_migration_backup", ".pre_remediation_backup", "_backup_", "_backup"]
    db_files = [
        f for f in db_files
        if not any(kw in f.name for kw in exclusion_keywords)
    ]
    assert db_files == [], (
        f"Unexpected SQLite/database files found in project root: {[str(f) for f in db_files]}\n"
        f"The application must not create local database files."
    )


def test_settings_database_url_is_postgresql():
    """Verify the active settings DATABASE_URL is a PostgreSQL URL."""
    url = settings.DATABASE_URL or ""
    assert not url.startswith("sqlite"), (
        f"settings.DATABASE_URL must not be SQLite. Got: {url}"
    )
    assert "postgresql" in url.lower() or "postgres" in url.lower(), (
        f"settings.DATABASE_URL must be PostgreSQL. Got: {url}"
    )

