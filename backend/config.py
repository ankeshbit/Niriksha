import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core App Settings
    PROJECT_NAME: str = "NiriKsha — AI-Assisted Legal Metrology Inspection System"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    DATABASE_URL: str = "sqlite:///./legal_metrology.db"
    
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

    # File Storage Paths
    UPLOAD_DIR: str = "./uploads"
    REPORTS_DIR: str = "./generated_reports"

    # OCR & AI Providers
    OCR_ENGINE: str = "auto"
    GEMINI_API_KEY: Optional[str] = None

    # Supabase Configuration
    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None
    SUPABASE_BUCKET_IMAGES: str = "inspection-images"
    SUPABASE_BUCKET_REPORTS: str = "inspection-reports"

settings = Settings()
