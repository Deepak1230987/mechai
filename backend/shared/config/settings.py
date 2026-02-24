"""
Centralised configuration loaded from environment variables.
Each service imports get_settings() – the same Settings object is reused (lru_cache).
"""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── General ───────────────────────────────────────────────────────────────
    PROJECT_NAME: str = "AI-CAM-RFQ Platform"
    ENV: str = "development"  # development | staging | production
    DEBUG: bool = True

    # ── Database (shared PostgreSQL instance) ─────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/mechai"
    DATABASE_ECHO: bool = False

    # ── JWT / Auth ────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "CHANGE-ME-in-production-use-secrets-manager"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ── GCP ───────────────────────────────────────────────────────────────────
    GCP_PROJECT_ID: str = ""
    GCS_BUCKET_NAME: str = "mechai-cad-uploads"
    PUBSUB_TOPIC: str = "cad-processing"
    PUBSUB_SUBSCRIPTION: str = "cad-processing-sub"

    # ── Service URLs (used by API Gateway for proxying) ───────────────────────
    AUTH_SERVICE_URL: str = "http://localhost:8001"
    CAD_SERVICE_URL: str = "http://localhost:8002"

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
