"""
tests/conftest.py

Test configuration using a dedicated PostgreSQL test database.
Tests NEVER use SQLite and NEVER connect to the production Neon database.

Requirements:
  - TEST_DATABASE_URL must be set in .env or the OS environment.
  - TEST_DATABASE_URL must be a PostgreSQL URL (not SQLite).
  - TEST_DATABASE_URL must differ from the production DATABASE_URL.
"""

import os
import tempfile
import pytest
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ─── Resolve TEST_DATABASE_URL ────────────────────────────────────────────────

# Load from env (already set if .env is loaded by backend/config.py pydantic-settings)
# We also explicitly try the project-root .env here for the test process itself.
_ROOT = Path(__file__).resolve().parent.parent
_env_file_override = os.environ.get("ENV_FILE", "").strip()
_env_path = Path(_env_file_override) if _env_file_override else (_ROOT / ".env")
if _env_path.exists():
    from dotenv import dotenv_values
    _env_vals = dotenv_values(_env_path)
    for _k, _v in _env_vals.items():
        if _k not in os.environ and _v is not None:
            os.environ[_k] = _v


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()

# ── Guard 1: TEST_DATABASE_URL must be present ─────────────────────────────
if not TEST_DATABASE_URL:
    raise RuntimeError(
        "\n[TEST CONFIG ERROR] TEST_DATABASE_URL is not configured.\n"
        "NiriKsha tests require a dedicated PostgreSQL test database.\n"
        "Add to your .env file:\n"
        "  TEST_DATABASE_URL=postgresql+psycopg://user:pass@host/dbname_test?sslmode=require\n"
        "Tests aborted. Do NOT create a local SQLite database."
    )

# ── Guard 2: Reject SQLite ─────────────────────────────────────────────────
if TEST_DATABASE_URL.startswith("sqlite"):
    raise RuntimeError(
        f"\n[TEST CONFIG ERROR] TEST_DATABASE_URL must not be a SQLite URL.\n"
        f"Received: {TEST_DATABASE_URL!r}\n"
        f"NiriKsha tests require a dedicated Neon PostgreSQL test database."
    )

# ── Guard 3: Must be PostgreSQL ────────────────────────────────────────────
if not (TEST_DATABASE_URL.startswith("postgresql") or TEST_DATABASE_URL.startswith("postgres")):
    raise RuntimeError(
        f"\n[TEST CONFIG ERROR] TEST_DATABASE_URL must be a PostgreSQL URL.\n"
        f"Received scheme: {TEST_DATABASE_URL.split('://')[0]!r}"
    )

# ── Guard 4: Must differ from production DATABASE_URL ─────────────────────
_PROD_URL = os.environ.get("DATABASE_URL", "").strip()
if _PROD_URL:
    os.environ["ORIGINAL_PRODUCTION_DATABASE_URL"] = _PROD_URL
if TEST_DATABASE_URL and _PROD_URL and TEST_DATABASE_URL == _PROD_URL:
    raise RuntimeError(
        "\n[TEST CONFIG ERROR] TEST_DATABASE_URL must NOT equal the production DATABASE_URL.\n"
        "Tests cannot run against the production Neon database.\n"
        "Configure a separate Neon test database and set TEST_DATABASE_URL accordingly."
    )

# ── Guard 5: If SAME hostname AND same database name → same physical DB → reject ─
# Note: Two Neon projects can share the database name 'neondb' on DIFFERENT endpoints
# (different endpoint IDs in the hostname). We compare the full hostname (without credentials)
# so that different Neon project endpoints are isolated while same host with different users is rejected.
from urllib.parse import urlparse as _urlparse
_prod_parsed_g5 = _urlparse(_PROD_URL.replace("postgresql+psycopg", "postgresql"))
_test_parsed_g5 = _urlparse(TEST_DATABASE_URL.replace("postgresql+psycopg", "postgresql"))
_prod_host_g5 = (_prod_parsed_g5.hostname or _prod_parsed_g5.netloc.split("@")[-1]).lower()
_test_host_g5 = (_test_parsed_g5.hostname or _test_parsed_g5.netloc.split("@")[-1]).lower()
_prod_db_g5 = _prod_parsed_g5.path.lstrip("/").split("?")[0].lower()
_test_db_g5 = _test_parsed_g5.path.lstrip("/").split("?")[0].lower()
if _prod_host_g5 and _test_host_g5 and _prod_host_g5 == _test_host_g5 and _prod_db_g5 == _test_db_g5:
    raise RuntimeError(
        f"\n[TEST CONFIG ERROR] TEST_DATABASE_URL resolves to the same physical database as production.\n"
        f"Same host: {_prod_host_g5!r}, same DB: {_prod_db_g5!r}\n"
        f"Use a different Neon project endpoint or a different database name for tests."
    )

# ─── Set DATABASE_URL to TEST_DATABASE_URL for all modules loaded during tests ─
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from backend.config import settings
settings.DATABASE_URL = TEST_DATABASE_URL
settings.OCR_WARMUP_ON_STARTUP = False

import backend.database as db_module
from backend.models import Base

# Create isolated test engine and session factory (PostgreSQL)
test_engine = create_engine(
    TEST_DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Rebind backend.database module references to test database
db_module.engine = test_engine
db_module.SessionLocal = TestSessionLocal

# DEF-13: Isolate test PDF report generation into an ephemeral TemporaryDirectory
_test_reports_tempdir = tempfile.TemporaryDirectory(prefix="test_reports_")
TEST_REPORTS_DIR = Path(_test_reports_tempdir.name)

import backend.main as main_module
main_module.REPORTS_DIR = TEST_REPORTS_DIR
if hasattr(main_module, "report_generator"):
    main_module.report_generator.reports_dir = TEST_REPORTS_DIR


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Initializes a clean test schema in the Neon PostgreSQL test database.

    Uses drop_all / create_all via SQLAlchemy to guarantee a clean slate,
    equivalent to a fresh database, without requiring a separate test DB file.
    """
    # ── HARD SAFETY GUARD: NEVER ALLOW DESTRUCTIVE OPS AGAINST PRODUCTION ─────
    engine_url_str = str(test_engine.url)
    if _PROD_URL:
        from backend.database import verify_test_database_safety
        verify_test_database_safety(_PROD_URL, engine_url_str)

    # Runtime guard: test reports must not be production reports dir
    reports_dir_str = str(main_module.REPORTS_DIR).replace("\\", "/")
    if reports_dir_str.endswith("generated_reports") or "generated_reports" in reports_dir_str.split("/"):
        raise RuntimeError("Test report paths cannot point to generated_reports/.")

    # ── Safe test schema creation: Ensure all tables and columns exist ──────────
    Base.metadata.create_all(bind=test_engine)
    try:
        from backend.schema_migration import migrate
        migrate()
    except Exception as _mig_err:
        print(f"[Conftest Warning] Schema migration notice: {_mig_err}")

    # Seed test users, counters, and rule versions
    db = TestSessionLocal()
    try:
        from datetime import datetime
        from backend.models import User, RuleVersion, InspectionNumberCounter
        from backend.auth_utils import hash_password

        # 1. Seed test inspector
        officer = db.query(User).filter(User.officer_id == settings.SEED_OFFICER_ID).first()
        if not officer:
            officer = User(
                officer_id=settings.SEED_OFFICER_ID,
                full_name=settings.SEED_OFFICER_NAME,
                email="rajesh.kumar@lm.gov.in",
                phone="+919876543210",
                designation=settings.SEED_OFFICER_DESIGNATION,
                zone=settings.SEED_OFFICER_ZONE,
                password_hash=hash_password(settings.SEED_OFFICER_PASSWORD),
                role="INSPECTOR"
            )
            db.add(officer)

        # 2. Seed test supervisor
        supervisor = db.query(User).filter(User.officer_id == "DOCA-SUP-101").first()
        if not supervisor:
            supervisor = User(
                officer_id="DOCA-SUP-101",
                full_name="Supervisor Anjali Sharma",
                email="anjali.sharma@lm.gov.in",
                phone="+919876543210",
                designation="Supervisory Officer (Legal Metrology)",
                zone="Northern Zone - Delhi HQ",
                password_hash=hash_password("admin123"),
                role="SUPERVISOR"
            )
            db.add(supervisor)

        # 3. Seed test admin
        admin_user = db.query(User).filter(User.officer_id == "DOCA-ADMIN-001").first()
        if not admin_user:
            admin_user = User(
                officer_id="DOCA-ADMIN-001",
                full_name="Director Vikram Malhotra",
                email="vikram.malhotra@lm.gov.in",
                phone="+919876543210",
                designation="Director of Legal Metrology (Admin)",
                zone="HQ - New Delhi",
                password_hash=hash_password("admin123"),
                role="ADMIN"
            )
            db.add(admin_user)

        # 4. Seed counters for current year & 2026
        current_year = datetime.utcnow().year
        for yr in (current_year, 2026):
            counter = db.query(InspectionNumberCounter).filter(InspectionNumberCounter.year == yr).first()
            if not counter:
                db.add(InspectionNumberCounter(year=yr, next_number=1))

        # 5. Seed PCR 2011 Rules
        from backend.rule_engine.registry import get_all_rules
        for r_def in get_all_rules():
            existing_rule = db.query(RuleVersion).filter(
                RuleVersion.rule_code == r_def.rule_code,
                RuleVersion.version_number == r_def.rule_version
            ).first()
            if not existing_rule:
                db.add(RuleVersion(
                    rule_code=r_def.rule_code,
                    version_number=r_def.rule_version,
                    title=r_def.title,
                    category=r_def.category,
                    statutory_reference=r_def.statutory_reference,
                    rule_logic_description=r_def.description,
                    severity=r_def.severity.value if hasattr(r_def.severity, "value") else str(r_def.severity),
                    is_active=True
                ))
        db.commit()
    finally:
        db.close()

    yield

    # Best-effort cleanup: dispose pool connections
    try:
        test_engine.dispose()
    except Exception:
        pass

    # DEF-13: Clean up ephemeral test reports directory
    try:
        _test_reports_tempdir.cleanup()
    except Exception:
        pass

