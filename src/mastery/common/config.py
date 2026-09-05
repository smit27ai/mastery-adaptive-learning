"""Application configuration. Everything comes from the environment - no hardcoded values."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    jwt_secret: str = "dev-only-secret-do-not-use-in-production"
    jwt_expire_minutes: int = 1440
    jwt_algorithm: str = "HS256"

    # Storage
    database_url: str = "sqlite+aiosqlite:///./mastery.db"
    redis_url: str = ""
    # Create tables at startup. Convenient locally; in production Alembic owns the
    # schema and runs once per deploy in the entrypoint, before any worker starts.
    auto_create_schema: bool = True

    # Models
    model_version: str = "bkt-v0.1.0"
    model_dir: Path = Path("./models/artifacts")

    # Tutor policy
    target_success_rate: float = 0.7
    exploration_rate: float = 0.15

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:8501"
    # Vercel gives every preview deployment its own hostname, so an exact allowlist
    # cannot cover them. This regex opts those in without widening the rule to "*".
    cors_origin_regex: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
