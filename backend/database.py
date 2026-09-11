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

