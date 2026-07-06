"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from polymarket_us import PolymarketUS

from app.client import build_client, require_credentials
from app.config import get_settings


def get_client() -> Iterator[PolymarketUS]:
    """Yield an authenticated SDK client, failing loudly if unconfigured.

    Raises ``MissingCredentialsError`` (mapped to HTTP 503) when credentials are
    absent, so authenticated routes never silently proceed with a half-built
    client.
    """
    settings = get_settings()
    require_credentials(settings)
    client = build_client(settings)
    try:
        yield client
    finally:
        client.close()
