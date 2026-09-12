"""
tests/test_database_configuration.py

Comprehensive tests verifying:
1. Deterministic CWD-independent .env and database resolution (root vs backend/ cwd).
2. Fail-fast guards: missing, empty, SQLite, or non-PostgreSQL DATABASE_URLs are all rejected.
3. No SQLite fallback exists in any environment (dev or production).
4. Dialect normalization (postgresql:// -> postgresql+psycopg://).
5. Strict test database isolation (PostgreSQL test DB != production DB).
6. Prevention of silent database provider switching.
"""

import os
import sys
import subprocess
from pathlib import Path
import pytest
from pydantic import ValidationError

from backend.config import Settings, ROOT_DIR


def test_cwd_independent_env_resolution():
    """Verify that Settings resolves the project root .env regardless of whether
    the process current working directory is the repository root or backend/.
    """
    python_exe = sys.executable
    script = """
import sys
from pathlib import Path
_root = str(Path(__file__).resolve().parent.parent) if '__file__' in locals() else str(Path.cwd().parent if Path.cwd().name == 'backend' else Path.cwd())
if _root not in sys.path:
    sys.path.insert(0, _root)

import os
from backend.config import Settings

# Clear any override so that the on-disk .env is strictly resolved
os.environ.pop("DATABASE_URL", None)
s = Settings()
print("HOST:" + str(s.DATABASE_URL))
"""
    # 1. Run with CWD = repository root
    p_root = subprocess.run(
        [python_exe, "-c", script],
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
        check=True
    )
    root_output = [line for line in p_root.stdout.splitlines() if line.startswith("HOST:")]
    assert len(root_output) == 1, f"Failed to get host from root run: {p_root.stderr}"
    root_url = root_output[0].replace("HOST:", "").strip()

    # 2. Run with CWD = backend subdirectory
    p_backend = subprocess.run(
        [python_exe, "-c", script],
        cwd=str(ROOT_DIR / "backend"),
        capture_output=True,
        text=True,
        check=True
    )
    backend_output = [line for line in p_backend.stdout.splitlines() if line.startswith("HOST:")]
    assert len(backend_output) == 1, f"Failed to get host from backend run: {p_backend.stderr}"
    backend_url = backend_output[0].replace("HOST:", "").strip()

    # Both must resolve to the identical Neon PostgreSQL connection string
    assert root_url == backend_url, f"Provider mismatch between CWDs! Root: {root_url}, Backend: {backend_url}"
    assert "neon.tech" in root_url.lower(), f"Expected Neon host in root run, got: {root_url}"
    assert root_url.startswith("postgresql+psycopg://"), f"Expected postgresql+psycopg driver, got: {root_url}"


def test_production_missing_database_url_fails_fast(monkeypatch):
    """If ENVIRONMENT=production and DATABASE_URL is missing or empty, fail fast immediately."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    # Missing / None
    with pytest.raises(ValidationError) as exc_info:
        Settings(ENVIRONMENT="production", DATABASE_URL=None)
    assert "DATABASE_URL environment variable is required in production" in str(exc_info.value)

    # Empty string
    with pytest.raises(ValidationError) as exc_info:
        Settings(ENVIRONMENT="production", DATABASE_URL="")
    assert "DATABASE_URL environment variable is required in production" in str(exc_info.value)

    # Whitespace only
    with pytest.raises(ValidationError) as exc_info:
        Settings(ENVIRONMENT="production", DATABASE_URL="   ")
    assert "DATABASE_URL environment variable is required in production" in str(exc_info.value)


def test_production_sqlite_database_url_rejected(monkeypatch):
    """In production, attempting to use SQLite must be rejected."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(ValidationError) as exc_info:
        Settings(ENVIRONMENT="production", DATABASE_URL="sqlite:///./legal_metrology.db")
    assert "SQLite DATABASE_URL is not permitted in production environment" in str(exc_info.value)


def test_development_missing_url_fails_fast(monkeypatch):
    """In ALL environments (including development), a missing DATABASE_URL must fail fast.
    There is NO SQLite fallback. NiriKsha requires PostgreSQL in every environment.
    """
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises((ValidationError, ValueError)) as exc_info:
        Settings(ENVIRONMENT="development", DATABASE_URL="")
    error_text = str(exc_info.value)
    assert any(msg in error_text for msg in [
        "DATABASE_URL environment variable is not configured",
        "NiriKsha requires Neon PostgreSQL",
    ]), f"Expected fail-fast error, got: {error_text}"

    # Verify the error does NOT contain SQLite path (no fallback)
    assert "sqlite" not in error_text.lower(), (
        f"Config must NOT fall back to SQLite. Got error: {error_text}"
    )


def test_postgres_scheme_normalization():
    """Verify that postgresql:// URLs are normalized to postgresql+psycopg://."""
    s = Settings(
        ENVIRONMENT="development",
        DATABASE_URL="postgresql://user:pass@host:5432/dbname"
    )
    assert s.DATABASE_URL.startswith("postgresql+psycopg://")


def test_test_database_isolation():
    """Verify that the test engine uses PostgreSQL and differs from the production Neon database."""
    from backend.config import settings
    from backend.database import engine

    # Test engine must be PostgreSQL, not SQLite
    engine_url_str = str(engine.url)
    assert not engine_url_str.startswith("sqlite"), (
        f"Test engine must not use SQLite. Got: {engine_url_str}"
    )
    assert "postgresql" in engine_url_str.lower() or "postgres" in engine_url_str.lower(), (
        f"Test engine must be PostgreSQL. Got: {engine_url_str}"
    )
    # Test DB must differ from production (different database identity)
    from backend.database import verify_test_database_safety
    prod_url = os.environ.get("ORIGINAL_PRODUCTION_DATABASE_URL", "")
    assert prod_url, "ORIGINAL_PRODUCTION_DATABASE_URL must be recorded by conftest"
    assert engine_url_str != prod_url, (
        "Test engine URL must not match the production DATABASE_URL."
    )
    # Explicit invariant check: CURRENT TEST DATABASE != PRODUCTION DATABASE
    verify_test_database_safety(prod_url, engine_url_str)


def test_no_silent_provider_switching():
    """Verify that when configured with a PostgreSQL URL, it remains PostgreSQL and does not switch."""
    fake_pg_url = "postgresql+psycopg://myuser:mypass@myhost.example.com/mydb"
    s = Settings(ENVIRONMENT="development", DATABASE_URL=fake_pg_url)
    assert s.DATABASE_URL == fake_pg_url
    assert not s.DATABASE_URL.startswith("sqlite")
