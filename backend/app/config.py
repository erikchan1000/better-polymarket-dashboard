"""Application configuration loaded from the repo-root `.env` file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The `.env` lives at the repository root (one level above `backend/`).
REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Typed application settings.

    Credentials are intentionally required (no silent defaults): if they are
    missing the app should refuse to talk to authenticated endpoints and say so
    loudly, rather than pretending to work.
    """

    polymarket_key_id: str = ""
    polymarket_secret_key: str = ""

    polymarket_gateway_base_url: str = "https://gateway.polymarket.us"
    polymarket_api_base_url: str = "https://api.polymarket.us"

    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    cors_allow_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def has_credentials(self) -> bool:
        """True only when both credential halves are present."""
        return bool(self.polymarket_key_id and self.polymarket_secret_key)

    @property
    def cors_origins(self) -> list[str]:
        """Parse the comma-separated CORS origins into a clean list."""
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
