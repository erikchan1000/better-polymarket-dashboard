"""Raw pass-through endpoints for orders, positions, activities and balances.

These return the SDK responses as-is. They're handy for debugging and for
clients that want the ungrouped data; the grouped view lives at
``/api/dashboard``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from polymarket_us import PolymarketUS

from app.routers.deps import get_client

router = APIRouter(prefix="/api", tags=["raw"])


@router.get("/orders")
def list_open_orders(client: PolymarketUS = Depends(get_client)) -> dict[str, Any]:
    """List all open orders."""
    return client.orders.list()


@router.get("/portfolio/positions")
def list_positions(client: PolymarketUS = Depends(get_client)) -> dict[str, Any]:
    """List current positions (first page)."""
    return client.portfolio.positions()


@router.get("/portfolio/activities")
def list_activities(
    limit: int = Query(100, ge=1, le=500),
    client: PolymarketUS = Depends(get_client),
) -> dict[str, Any]:
    """List recent activity (trades, resolutions, transfers), newest first."""
    return client.portfolio.activities(
        {"limit": limit, "sortOrder": "SORT_ORDER_DESCENDING"}
    )


@router.get("/account/balances")
def get_balances(client: PolymarketUS = Depends(get_client)) -> dict[str, Any]:
    """Get account balances."""
    return client.account.balances()
