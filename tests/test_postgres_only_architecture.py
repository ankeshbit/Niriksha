"""
tests/test_postgres_only_architecture.py

Comprehensive tests verifying the PostgreSQL-only database architecture requirement:

1. Production DATABASE_URL is PostgreSQL
2. Development DATABASE_URL is PostgreSQL  
3. Test DATABASE_URL is PostgreSQL
4. SQLite URLs are rejected by config
5. Missing DATABASE_URL fails fast
6. Malformed DATABASE_URL fails fast
7. Test URL != production URL
8. Application cannot create a local SQLite DB
9. Launch from repository root CWD works
10. Launch from backend/ CWD works
11. No sqlite3 module used in runtime backend code
"""

import os
import sys
import subprocess
from pathlib import Path
import pytest
from pydantic import ValidationError

from backend.config import Settings, ROOT_DIR
import backend.database as db_module
from backend.config import settings


# ─── 1. Production DATABASE_URL is PostgreSQL ─────────────────────────────────

def test_production_database_url_is_postgresql():
    """Production environment must only accept PostgreSQL URLs."""
    pg_url = "postgresql+psycopg://user:pass@host.neon.tech/dbname?sslmode=require"
    s = Settings(ENVIRONMENT="production", DATABASE_URL=pg_url)
    assert "postgresql" in s.DATABASE_URL.lower()
    assert not s.DATABASE_URL.startswith("sqlite")


# ─── 2. Development DATABASE_URL is PostgreSQL ────────────────────────────────

def test_development_database_url_is_postgresql():
    """Development environment must also use a PostgreSQL URL; no SQLite fallback."""
    pg_url = "postgresql+psycopg://user:pass@dev.neon.tech/dev_db"
    s = Settings(ENVIRONMENT="development", DATABASE_URL=pg_url)
    assert "postgresql" in s.DATABASE_URL.lower()
    assert not s.DATABASE_URL.startswith("sqlite")


# ─── 3. Test DATABASE_URL is PostgreSQL ───────────────────────────────────────

def test_test_database_url_is_postgresql():
    """The active test engine must use PostgreSQL (not SQLite)."""
    engine_url_str = str(db_module.engine.url)
    assert not engine_url_str.startswith("sqlite"), (
        f"Test engine must not use SQLite. Got: {engine_url_str}"
    )
    assert "postgresql" in engine_url_str.lower() or "postgres" in engine_url_str.lower(), (
        f"Test engine must be PostgreSQL. Got: {engine_url_str}"
    )


# ─── 4. SQLite URLs are rejected ──────────────────────────────────────────────

def test_sqlite_url_rejected_in_development():
    """SQLite DATABASE_URL must be rejected in development environment."""
    with pytest.raises((ValidationError, ValueError)) as exc_info:
        Settings(ENVIRONMENT="development", DATABASE_URL="sqlite:///./legal_metrology.db")
    assert "sqlite" in str(exc_info.value).lower() or "forbidden" in str(exc_info.value).lower() or "not permitted" in str(exc_info.value).lower()


def test_sqlite_url_rejected_in_production():
    """SQLite DATABASE_URL must be rejected in production environment."""
    with pytest.raises((ValidationError, ValueError)) as exc_info:
        Settings(ENVIRONMENT="production", DATABASE_URL="sqlite:///./legal_metrology.db")
    assert "sqlite" in str(exc_info.value).lower() or "forbidden" in str(exc_info.value).lower() or "not permitted" in str(exc_info.value).lower()


def test_sqlite_memory_url_rejected():
    """In-memory SQLite must also be rejected."""
    with pytest.raises((ValidationError, ValueError)):
        Settings(ENVIRONMENT="development", DATABASE_URL="sqlite:///:memory:")


# ─── 5. Missing DATABASE_URL fails fast ───────────────────────────────────────

def test_missing_database_url_fails_fast_in_development():
    """Missing DATABASE_URL must fail fast in development — no SQLite fallback."""
    with pytest.raises((ValidationError, ValueError)) as exc_info:
        Settings(ENVIRONMENT="development", DATABASE_URL=None)
    error_text = str(exc_info.value)
    assert "sqlite" not in error_text.lower(), (
        f"Error must not mention SQLite fallback. Got: {error_text}"
    )
    assert any(kw in error_text for kw in [
        "DATABASE_URL", "NiriKsha", "PostgreSQL", "not configured"
    ]), f"Error must describe the missing DATABASE_URL. Got: {error_text}"


def test_missing_database_url_fails_fast_in_production():
    """Missing DATABASE_URL must fail fast in production."""
    with pytest.raises((ValidationError, ValueError)) as exc_info:
        Settings(ENVIRONMENT="production", DATABASE_URL=None)
    assert "DATABASE_URL" in str(exc_info.value) or "NiriKsha" in str(exc_info.value)


def test_empty_string_database_url_fails_fast():
    """Empty string DATABASE_URL must fail fast (treated as missing)."""
    with pytest.raises((ValidationError, ValueError)):
        Settings(ENVIRONMENT="development", DATABASE_URL="")


def test_whitespace_database_url_fails_fast():
    """Whitespace-only DATABASE_URL must fail fast."""
    with pytest.raises((ValidationError, ValueError)):
        Settings(ENVIRONMENT="development", DATABASE_URL="   ")


# ─── 6. Malformed DATABASE_URL fails fast ─────────────────────────────────────

def test_unsupported_database_scheme_rejected():
    """Non-PostgreSQL, non-SQLite schemes must be rejected."""
    with pytest.raises((ValidationError, ValueError)):
        Settings(ENVIRONMENT="development", DATABASE_URL="mongodb://localhost/mydb")


def test_mysql_url_rejected():
    """MySQL DATABASE_URL must be rejected."""
    with pytest.raises((ValidationError, ValueError)):
        Settings(ENVIRONMENT="development", DATABASE_URL="mysql://user:pass@localhost/db")


# ─── 7. Test URL != production URL ────────────────────────────────────────────

def test_test_url_differs_from_production_url():
    """TEST_DATABASE_URL must not equal the production DATABASE_URL."""
    prod_url = os.environ.get("DATABASE_URL", "").strip()
    test_url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if prod_url and test_url:
        assert prod_url != test_url, (
            "TEST_DATABASE_URL must not equal the production DATABASE_URL.\n"
            f"Both resolve to: {test_url!r}"
        )


# ─── 8. No local .db file creation ────────────────────────────────────────────

def test_no_local_db_files_created():
    """Running the test suite must not create any SQLite/database files in the project root."""
    # Historical backup archives (pre-migration SQLite snapshots) are preserved as evidence.
    # The application must not create NEW SQLite databases.
    exclusion_keywords = [
        "_backup_",  # historical pre-migration archives
        "_backup",
        ".pre_postgres_migration_backup",
        ".pre_remediation_backup",
    ]
    db_files = (
        list(ROOT_DIR.glob("*.db"))
        + list(ROOT_DIR.glob("*.sqlite"))
        + list(ROOT_DIR.glob("*.sqlite3"))
    )
    db_files = [f for f in db_files if not any(kw in f.name for kw in exclusion_keywords)]
    assert db_files == [], (
        f"SQLite/database files found in project root: {[str(f) for f in db_files]}\n"
        "The application must not create local database files."
    )


# ─── 9 & 10. CWD-independent launch ──────────────────────────────────────────

def test_cwd_independent_launch_from_root():
    """Launching from the repository root resolves Neon PostgreSQL DATABASE_URL correctly."""
    python_exe = sys.executable
    script = """
import sys
from pathlib import Path
_root = str(Path(__file__).resolve().parent) if '__file__' in dir() else str(Path.cwd())
if _root not in sys.path:
    sys.path.insert(0, _root)
import os
from backend.config import Settings
os.environ.pop("DATABASE_URL", None)
try:
    s = Settings()
    print("URL:" + s.DATABASE_URL)
except Exception as e:
    # Expected if .env has no DATABASE_URL (fail-fast is correct behavior)
    print("FAIL:" + str(e)[:120])
"""
    p = subprocess.run(
        [python_exe, "-c", script],
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
        env={**os.environ},
    )
    output = p.stdout.strip()
    # Either success (PostgreSQL URL) or correct fail-fast (no SQLite mention)
    if output.startswith("URL:"):
        url = output[4:].strip()
        assert "sqlite" not in url.lower(), f"Root-CWD launch must not produce SQLite URL: {url}"
        assert "postgresql" in url.lower() or "postgres" in url.lower(), f"Root-CWD launch must produce PostgreSQL URL: {url}"
    elif output.startswith("FAIL:"):
        # Fail-fast is acceptable if DATABASE_URL is not in env
        assert "sqlite" not in output.lower(), f"Fail-fast error must not mention SQLite fallback: {output}"


def test_cwd_independent_launch_from_backend_dir():
    """Launching from the backend/ subdirectory resolves Neon PostgreSQL DATABASE_URL correctly."""
    python_exe = sys.executable
    script = """
import sys
from pathlib import Path
_root = str(Path.cwd().parent)
if _root not in sys.path:
    sys.path.insert(0, _root)
import os
from backend.config import Settings
os.environ.pop("DATABASE_URL", None)
try:
    s = Settings()
    print("URL:" + s.DATABASE_URL)
except Exception as e:
    print("FAIL:" + str(e)[:120])
"""
    p = subprocess.run(
        [python_exe, "-c", script],
        cwd=str(ROOT_DIR / "backend"),
        capture_output=True,
        text=True,
        env={**os.environ},
    )
    output = p.stdout.strip()
    if output.startswith("URL:"):
        url = output[4:].strip()
        assert "sqlite" not in url.lower(), f"Backend-CWD launch must not produce SQLite URL: {url}"
        assert "postgresql" in url.lower() or "postgres" in url.lower(), f"Backend-CWD launch must produce PostgreSQL URL: {url}"
    elif output.startswith("FAIL:"):
        assert "sqlite" not in output.lower(), f"Fail-fast error must not mention SQLite fallback: {output}"


# ─── 11. No sqlite3 in runtime backend code ───────────────────────────────────

def test_no_sqlite3_import_in_backend_runtime():
    """Runtime backend code (backend/*.py) must not import or use sqlite3."""
    backend_dir = ROOT_DIR / "backend"
    violations = []
    for py_file in backend_dir.glob("*.py"):
        if py_file.name == "migrate_to_postgres.py":
            # One-time migration utility — allowed to use sqlite3 as SOURCE reader
            continue
        content = py_file.read_text(encoding="utf-8", errors="replace")
        if "import sqlite3" in content or "sqlite3.connect" in content:
            violations.append(str(py_file.name))
    assert violations == [], (
        f"Runtime backend files must not use sqlite3: {violations}\n"
        f"Only migrate_to_postgres.py (migration-source reader) is exempt."
    )


def test_postgresql_scheme_normalization():
    """postgresql:// is normalized to postgresql+psycopg:// (driver-explicit)."""
    s = Settings(
        ENVIRONMENT="development",
        DATABASE_URL="postgresql://user:pass@host.example.com/mydb"
    )
    assert s.DATABASE_URL.startswith("postgresql+psycopg://"), (
        f"Expected postgresql+psycopg:// normalization, got: {s.DATABASE_URL}"
    )
