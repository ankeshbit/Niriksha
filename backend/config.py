import os
import logging
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from typing import Optional

logger = logging.getLogger("backend.config")

# Project directory anchors:
# ROOT_DIR points to the repository root regardless of current working directory
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent

_custom_env = os.environ.get("ENV_FILE")
_primary_env_file = Path(_custom_env) if _custom_env else (ROOT_DIR / ".env")

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_primary_env_file,
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core App Settings
    PROJECT_NAME: str = "NiriKsha — AI-Assisted Legal Metrology Inspection System"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    DATABASE_URL: Optional[str] = None

    @model_validator(mode="after")
    def validate_database_url(self):
        raw_url = (self.DATABASE_URL or "").strip()

        # ── Fail fast: DATABASE_URL is mandatory in every environment ──────────
        if not raw_url:
            if self.ENVIRONMENT == "production":
                raise ValueError(
                    "DATABASE_URL environment variable is required in production environment.\n"
                    "NiriKsha requires Neon PostgreSQL.\n"
                    "Set DATABASE_URL=postgresql+psycopg://... in your .env file.\n"
                    "Application startup aborted. Do NOT create a local database."
                )
            raise ValueError(
                "DATABASE_URL environment variable is not configured.\n"
                "NiriKsha requires Neon PostgreSQL.\n"
                "Set DATABASE_URL=postgresql+psycopg://... in your .env file.\n"
                "Application startup aborted. Do NOT create a local database."
            )

        # ── Reject SQLite in every environment (dev and production) ────────────
        if raw_url.startswith("sqlite"):
            if self.ENVIRONMENT == "production":
                raise ValueError(
                    f"SQLite DATABASE_URL is not permitted in production environment.\n"
                    f"Received: {raw_url!r}\n"
                    f"NiriKsha requires Neon PostgreSQL as its only database.\n"
                    f"Set DATABASE_URL=postgresql+psycopg://... in your .env file."
                )
            raise ValueError(
                f"SQLite DATABASE_URL is strictly forbidden in NiriKsha.\n"
                f"Received: {raw_url!r}\n"
                f"NiriKsha requires Neon PostgreSQL as its only database.\n"
                f"Set DATABASE_URL=postgresql+psycopg://... in your .env file."
            )

        # ── Reject non-PostgreSQL URLs ─────────────────────────────────────────
        if not (raw_url.startswith("postgresql") or raw_url.startswith("postgres")):
            raise ValueError(
                f"Unsupported DATABASE_URL scheme: {raw_url.split('://')[0]!r}.\n"
                f"NiriKsha requires a PostgreSQL (Neon) database URL.\n"
                f"Expected format: postgresql+psycopg://user:pass@host/dbname?sslmode=require"
            )

        # ── Normalize postgresql:// → postgresql+psycopg:// ───────────────────
        if raw_url.startswith("postgresql://"):
            self.DATABASE_URL = raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
        else:
            self.DATABASE_URL = raw_url

        return self

    
    # Auth & Security
    SECRET_KEY: str = "sih-2026-doca-legal-metrology-jwt-secret-key-32chars"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 Hours
    ALGORITHM: str = "HS256"
    CORS_ORIGINS: str = "*"

    # Default Demo Officer
    SEED_OFFICER_ID: str = "DOCA-INSP-842"
    SEED_OFFICER_PASSWORD: str = "admin123"
    SEED_OFFICER_NAME: str = "Inspector Rajesh Kumar"
    SEED_OFFICER_DESIGNATION: str = "Senior Inspector (Legal Metrology)"
    SEED_OFFICER_ZONE: str = "Northern Zone - Delhi HQ"

    # Supervisor Account Settings
    SEED_SUPERVISOR_ID: str = "DOCA-SUP-101"
    SEED_SUPERVISOR_PASSWORD: Optional[str] = None
    SEED_SUPERVISOR_NAME: str = "NiriKsha Supervisor"
    SEED_SUPERVISOR_DESIGNATION: str = "Supervisory Officer (Legal Metrology)"
    SEED_SUPERVISOR_ZONE: str = "Central HQ"

    # File Storage Paths
    UPLOAD_DIR: str = "./uploads"
    REPORTS_DIR: str = "./generated_reports"

    # OCR & AI Providers
    OCR_ENGINE: str = "auto"
    PADDLE_OCR_ENABLED: bool = True
    PADDLE_OCR_USE_ANGLE_CLS: bool = True
    PADDLE_OCR_LANG: str = "en"
    MAX_OCR_DIMENSION: int = 1024  # Max dimension for CPU OCR inference to prevent CPU stalls
    # Concurrent per-image OCR workers.
    # SAFETY NOTE: PaddleOCR CPU inference uses shared BLAS thread pools on its singleton.
    # Benchmarking showed concurrent=2 degrades accuracy (corrupted text, lost boxes) and
    # is 15% SLOWER than warm sequential inference on this CPU.  Keep at 1 (sequential).
    OCR_CONCURRENT_IMAGES: int = 1
    # Run a tiny warmup inference at startup to amortize PaddleOCR JIT cost before first request
    OCR_WARMUP_ON_STARTUP: bool = True
    TESSERACT_CMD: Optional[str] = None
    TESSDATA_PREFIX: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None

    # Qwen2.5-VL Vision-Language Model Configuration
    VLM_ENABLED: bool = False
    VLM_PROVIDER: str = "mock"  # 'openai_compatible', 'local', 'mock'
    VLM_MODEL: str = "Qwen/Qwen2.5-VL-7B-Instruct"
    VLM_ENDPOINT: Optional[str] = None  # e.g., 'http://localhost:8000/v1'
    VLM_API_KEY: Optional[str] = None
    VLM_TIMEOUT_SECONDS: float = 15.0
    VLM_CONFIDENCE_THRESHOLD: float = 0.70

    # Supabase Configuration
    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None
    SUPABASE_BUCKET_IMAGES: str = "inspection-images"
    SUPABASE_BUCKET_REPORTS: str = "inspection-reports"

settings = Settings()
