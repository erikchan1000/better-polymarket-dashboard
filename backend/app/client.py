"""Factory for the Polymarket US SDK client."""

from __future__ import annotations

from polymarket_us import PolymarketUS

from app.config import Settings, get_settings


class MissingCredentialsError(RuntimeError):
    """Raised when an authenticated call is attempted without credentials."""


def build_client(settings: Settings | None = None) -> PolymarketUS:
    """Construct a configured `PolymarketUS` client.

    The client is safe to use for public endpoints even without credentials;
    authenticated endpoints will raise inside the SDK if credentials are absent.
    We surface a clearer error earlier via `require_credentials`.
    """
    settings = settings or get_settings()
    return PolymarketUS(
        key_id=settings.polymarket_key_id or None,
        secret_key=settings.polymarket_secret_key or None,
        gateway_base_url=settings.polymarket_gateway_base_url,
        api_base_url=settings.polymarket_api_base_url,
    )


def require_credentials(settings: Settings | None = None) -> None:
    """Fail loudly and early if credentials are not configured.

    Called by authenticated routes so the API returns a clear 503 instead of a
    confusing auth error from deep inside the SDK.
    """
    settings = settings or get_settings()
    if not settings.has_credentials:
        raise MissingCredentialsError(
            "Polymarket credentials are not configured. Set POLYMARKET_KEY_ID and "
            "POLYMARKET_SECRET_KEY in the repo-root .env file."
        )
