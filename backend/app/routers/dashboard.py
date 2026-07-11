"""Grouped dashboard endpoint — the primary view.

A short-TTL in-process cache sits in front of the upstream fetch. Polymarket is
rate-limited, and the frontend polls on an interval from possibly several tabs;
without a cache each of those triggers a full fan-out of upstream calls. The
cache guarantees that within ``dashboard_cache_ttl_seconds`` all callers share a
single built response, and a single in-flight refresh is coalesced under a lock
so concurrent misses don't stampede. On an upstream failure (e.g. a rate-limit
burst) we serve the last good response if we have one, so a transient limit
degrades to slightly-stale data instead of an error screen.
"""

from __future__ import annotations

import logging
import threading
import time

from fastapi import APIRouter, Query

from app.client import build_client, require_credentials
from app.config import get_settings
from app.schemas import DashboardResponse
from app.services.dashboard import build_dashboard

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["dashboard"])

# Cache key -> (monotonic timestamp, response). Module-level so it survives
# across requests within a single worker process.
_CacheKey = tuple[int, bool]
_cache: dict[_CacheKey, tuple[float, DashboardResponse]] = {}
# Serializes upstream refreshes so concurrent cache misses coalesce into one
# fetch rather than each hitting the (rate-limited) upstream.
_refresh_lock = threading.Lock()


def _fresh(entry: tuple[float, DashboardResponse] | None, ttl: float) -> bool:
    return entry is not None and (time.monotonic() - entry[0]) < ttl


def _fetch(max_activities: int, enrich_events: bool) -> DashboardResponse:
    require_credentials()
    client = build_client()
    try:
        return build_dashboard(
            client, max_activities=max_activities, enrich_events=enrich_events
        )
    finally:
        client.close()


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    max_activities: int = Query(
        0,
        ge=0,
        le=100_000,
        description=(
            "Cap on trade/resolution records pulled for grouping. "
            "0 (the default) pulls the complete history by paging to the end of the feed."
        ),
    ),
    enrich_events: bool = Query(
        True, description="Look up human event titles via the public events API."
    ),
) -> DashboardResponse:
    """Return all account activity grouped by event -> market/contract."""
    settings = get_settings()
    ttl = settings.dashboard_cache_ttl_seconds
    key: _CacheKey = (max_activities, enrich_events)

    # Fast path: a fresh cached response needs no lock and no upstream call.
    if ttl > 0 and _fresh(_cache.get(key), ttl):
        return _cache[key][1]

    # Miss: coalesce concurrent refreshes so only one thread hits upstream.
    with _refresh_lock:
        if ttl > 0 and _fresh(_cache.get(key), ttl):
            return _cache[key][1]  # refreshed while we waited for the lock

        try:
            response = _fetch(max_activities, enrich_events)
        except Exception:
            # Serve the last good response if we have one — a transient upstream
            # failure (rate limit / 5xx) shouldn't blank the dashboard. Missing
            # credentials and the like still propagate (nothing cached to serve).
            stale = _cache.get(key)
            if stale is not None:
                age = time.monotonic() - stale[0]
                logger.warning(
                    "Dashboard upstream fetch failed; serving cached response "
                    "(%.0fs old).",
                    age,
                )
                return stale[1]
            raise

        if ttl > 0:
            _cache[key] = (time.monotonic(), response)
        return response
