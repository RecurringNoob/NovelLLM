"""
app/config.py — Application settings via pydantic-settings.
All values read from environment variables (or .env file).
"""
from __future__ import annotations

from typing import List

from pydantic import AnyUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────
    environment: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # ── Database ─────────────────────────────────────────────────
    database_url: str = (
        "postgresql+asyncpg://notelm:notelm_secret@localhost:5432/notelm"
    )

    # ── Redis ────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Gemini ───────────────────────────────────────────────────
    gemini_api_key: str = ""

    # ── Auth (Phase 9 — stubs for now) ───────────────────────────
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # ── Hocuspocus (Phase 6) ─────────────────────────────────────
    hocuspocus_secret: str = "change-me-hocuspocus-secret"
    hocuspocus_url: str = "ws://localhost:1234"

    # ── Cost defaults ────────────────────────────────────────────
    default_cost_budget_cents: int = 500

    # ── Dev user (Phase 1 stub — replaced by real auth in Phase 9)
    dev_user_id: str = "00000000-0000-0000-0000-000000000001"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


settings = Settings()
