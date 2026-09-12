import os
from typing import Dict, Any
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from backend.config import settings


def build_engine(database_url: str):
    """Constructs a PostgreSQL-only SQLAlchemy engine.

    SQLite is strictly forbidden: config.py rejects it before this function
    is ever reached, but we add a second guard here for belt-and-suspenders
    defence-in-depth.
    """
    if not database_url or database_url.strip().startswith("sqlite"):
        raise RuntimeError(
            f"SQLite database URL is not permitted in NiriKsha.\n"
            f"Received: {database_url!r}\n"
            f"Only Neon PostgreSQL (postgresql+psycopg://...) is supported."
        )

    # PostgreSQL / Neon Serverless configuration:
    # pool_pre_ping=True ensures resilience across serverless compute wake-up.
    # pool_recycle=300 prevents stale idle connections on long-lived processes.
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=300,
        echo=False,
    )


engine = build_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_database_backend_info() -> Dict[str, Any]:
    """Safely returns metadata about the active database backend without leaking credentials."""
    url = engine.url
    driver = url.drivername
    host = url.host or "unknown"
    is_neon = "neon.tech" in host.lower() or "neon" in host.lower()

    return {
        "database_backend": "PostgreSQL",
        "database_driver": driver,
        "database_host": "Neon" if is_neon else host,
        "is_neon": is_neon,
        "is_sqlite": False,
    }


def normalize_db_identity(url_str: str) -> Dict[str, str]:
    """Parses and normalizes a database URL into host, database name, and normalized identity.
    
    Rejects:
    - Missing / None / empty / whitespace URLs
    - SQLite or :memory: databases
    - Unsupported database engines (MySQL, MongoDB, etc.)
    """
    from urllib.parse import urlparse

    if not url_str or not str(url_str).strip():
        raise ValueError("Database URL cannot be empty or whitespace.")

    clean_url = str(url_str).strip()
    clean_lower = clean_url.lower()

    if "sqlite" in clean_lower or ":memory:" in clean_lower:
        raise ValueError(f"SQLite / in-memory database is strictly forbidden in NiriKsha: {clean_url!r}")

    unsupported_schemes = ["mysql", "mongodb", "oracle", "mssql", "redis"]
    for scheme in unsupported_schemes:
        if clean_lower.startswith(scheme):
            raise ValueError(f"Unsupported database scheme '{scheme}'. Only PostgreSQL/Neon is supported.")

    parsed = urlparse(clean_url.replace("postgresql+psycopg", "postgresql"))
    driver_scheme = parsed.scheme.split("+")[0]
    if driver_scheme not in ("postgresql", "postgres"):
        raise ValueError(f"Unsupported database scheme '{driver_scheme}'. Only PostgreSQL/Neon is supported.")

    host = (parsed.hostname or parsed.netloc.split("@")[-1].split(":")[0]).lower().strip()
    database = parsed.path.lstrip("/").split("?")[0].lower().strip()

    if not host:
        raise ValueError(f"Invalid PostgreSQL URL: missing host in {clean_url!r}")
    if not database:
        raise ValueError(f"Invalid PostgreSQL URL: missing database name in {clean_url!r}")

    return {
        "host": host,
        "database": database,
        "identity": f"{host}/{database}"
    }


def verify_test_database_safety(prod_url: str, test_url: str) -> None:
    """Explicitly verifies test database identity against production database identity.
    
    Fails fast if:
    - Either URL is missing, empty, whitespace, or points to SQLite/unsupported databases
    - Both URLs resolve to the same host and database identity
    """
    prod_info = normalize_db_identity(prod_url)
    test_info = normalize_db_identity(test_url)

    if prod_info["identity"] == test_info["identity"]:
        raise RuntimeError(
            f"[CRITICAL SAFETY VIOLATION] Test database resolves to the same physical Neon database as production!\n"
            f"Production: {prod_info['identity']}\n"
            f"Test:       {test_info['identity']}\n"
            f"Tests MUST use a separate Neon database."
        )

