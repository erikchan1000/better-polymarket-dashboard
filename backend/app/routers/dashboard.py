"""Grouped dashboard endpoint — the primary view."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from polymarket_us import PolymarketUS

from app.routers.deps import get_client
from app.schemas import DashboardResponse
from app.services.dashboard import build_dashboard

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    max_activities: int = Query(
        300, ge=0, le=2000, description="Max recent activity records to pull for trade grouping."
    ),
    enrich_events: bool = Query(
        True, description="Look up human event titles via the public events API."
    ),
    client: PolymarketUS = Depends(get_client),
) -> DashboardResponse:
    """Return all account activity grouped by event -> market/contract."""
    return build_dashboard(
        client,
        max_activities=max_activities,
        enrich_events=enrich_events,
    )
