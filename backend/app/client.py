"""Factory for the Polymarket US SDK client."""

from __future__ import annotations

import logging
import time
from typing import Any

from polymarket_us import PolymarketUS
from polymarket_us.errors import RateLimitError

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class MissingCredentialsError(RuntimeError):
    """Raised when an authenticated call is attempted without credentials."""


def _retry_after_seconds(exc: RateLimitError) -> float | None:
    """Parse a ``Retry-After`` header (delta-seconds form) off a 429, if any."""
    response = getattr(exc, "response", None)
    if response is None:
        return None
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None  # HTTP-date form is not worth parsing for our short waits


class _RetryingPolymarketUS(PolymarketUS):
    """``PolymarketUS`` that retries rate-limited (HTTP 429) requests.

    Polymarket is fronted by a rate limiter; a burst can briefly return 429
    (Cloudflare error 1015). Rather than fail the whole dashboard on a transient
    limit, we back off exponentially — honoring ``Retry-After`` when the server
    sends it — and retry a bounded number of times. This is deliberate, bounded
    recovery (not an open-ended fallback): after ``max_retries`` the error
    propagates so the caller can surface it or serve a cached response.
    """

    def __init__(
        self,
        *args: Any,
        max_retries: int,
        backoff_base: float,
        backoff_max: float,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        for attempt in range(self._max_retries + 1):
            try:
                return super()._request(method, path, **kwargs)
            except RateLimitError as exc:
                if attempt >= self._max_retries:
                    raise
                # Prefer the server's Retry-After; else exponential backoff.
                wait = _retry_after_seconds(exc)
                if wait is None:
                    wait = self._backoff_base * (2**attempt)
                wait = min(wait, self._backoff_max)
                logger.warning(
                    "Rate limited on %s %s; backing off %.1fs (attempt %d/%d)",
                    method,
                    path,
                    wait,
                    attempt + 1,
                    self._max_retries,
                )
                time.sleep(wait)
        # Unreachable: the loop either returns or raises.
        raise AssertionError("retry loop exited without returning")


def build_client(settings: Settings | None = None) -> PolymarketUS:
    """Construct a configured `PolymarketUS` client.

    The client is safe to use for public endpoints even without credentials;
    authenticated endpoints will raise inside the SDK if credentials are absent.
    We surface a clearer error earlier via `require_credentials`.

    Wrapped with bounded 429 retry/backoff so a transient rate limit degrades
    gracefully instead of failing the request outright.
    """
    settings = settings or get_settings()
    return _RetryingPolymarketUS(
        key_id=settings.polymarket_key_id or None,
        secret_key=settings.polymarket_secret_key or None,
        gateway_base_url=settings.polymarket_gateway_base_url,
        api_base_url=settings.polymarket_api_base_url,
        max_retries=settings.upstream_max_retries,
        backoff_base=settings.upstream_backoff_base_seconds,
        backoff_max=settings.upstream_backoff_max_seconds,
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
