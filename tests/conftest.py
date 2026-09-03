"""
tests/conftest.py

Test configuration and isolated SQLite test database fixtures.
Guarantees that test runs NEVER write to or mutate the development/demo database (legal_metrology.db).
"""

import os
import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Setup dedicated test database path
BASE_DIR = Path(__file__).resolve().parent.parent
TEST_DB_PATH = BASE_DIR / "test_legal_metrology.db"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"

# SAFETY GUARD: Ensure test database is explicitly isolated from legal_metrology.db
if "legal_metrology.db" in TEST_DATABASE_URL and "test_legal_metrology.db" not in TEST_DATABASE_URL:
    raise RuntimeError("SAFETY ERROR: Tests cannot run against the development database (legal_metrology.db). Tests must use test_legal_metrology.db.")

# Set environment variable before any modules load
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from backend.config import settings
settings.DATABASE_URL = TEST_DATABASE_URL

import backend.database as db_module
from backend.models import Base
from backend.seed import seed_database

# Create isolated test engine and session factory
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Rebind backend.database module references to test database
db_module.engine = test_engine
db_module.SessionLocal = TestSessionLocal

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Initializes a clean test database and tears it down after tests complete.

    On Windows, SQLite holds an open file handle as soon as the engine is
    created (above, at module-import time). Calling TEST_DB_PATH.unlink() at
    fixture time therefore silently fails.  Instead we drop-and-recreate all
    tables via SQLAlchemy metadata, which is equivalent to a fresh database
    but works even when the file is locked.
    """
    # Defensive Runtime Verification: Check engine connection URL
    engine_url_str = str(db_module.engine.url).replace("\\", "/")
    if engine_url_str.endswith("legal_metrology.db") and not engine_url_str.endswith("test_legal_metrology.db"):
        raise RuntimeError("SAFETY ERROR: Tests cannot run against the development database (legal_metrology.db). Tests must use test_legal_metrology.db.")

    # --- GUARANTEED CLEAN SLATE ---
    # Drop all existing tables (clears accumulated rows from previous runs),
    # then recreate them.  This always works even when the .db file is open.
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    # Run seed in test db
    db = TestSessionLocal()
    try:
        from backend.models import User, RuleVersion
        from backend.auth_utils import hash_password
        
        # 1. Seed Officer
        officer = db.query(User).filter(User.officer_id == settings.SEED_OFFICER_ID).first()
        if not officer:
            officer = User(
                officer_id=settings.SEED_OFFICER_ID,
                full_name=settings.SEED_OFFICER_NAME,
                email="rajesh.kumar@lm.gov.in",
                phone="+91 98765 43210",
                designation=settings.SEED_OFFICER_DESIGNATION,
                zone=settings.SEED_OFFICER_ZONE,
                password_hash=hash_password(settings.SEED_OFFICER_PASSWORD),
                role="INSPECTOR"
            )
            db.add(officer)
        
        # 2. Seed PCR 2011 Rules
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

    # Best-effort cleanup: dispose pool connections then delete the file.
    # On Windows the file may still be locked; that is acceptable — the
    # drop_all at the next session start guarantees a clean slate regardless.
    try:
        test_engine.dispose()
    except Exception:
        pass
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except Exception:
            pass
