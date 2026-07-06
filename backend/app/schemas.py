"""Pydantic response models — the JSON contract consumed by the frontend.

All monetary values are normalized to USD floats so the frontend can format
and aggregate them directly. Raw SDK enum strings are kept alongside a
humanized label for display.
"""

from __future__ import annotations

from pydantic import BaseModel


class OrderSummary(BaseModel):
    """A single open order on one contract."""

    id: str
    market_slug: str
    side: str | None = None
    side_label: str | None = None
    type: str | None = None
    state: str | None = None
    state_label: str | None = None
    intent: str | None = None
    tif: str | None = None
    price: float | None = None
    avg_px: float | None = None
    quantity: int = 0
    cum_quantity: int = 0
    leaves_quantity: int = 0
    notional: float = 0.0
    create_time: str | None = None


class PositionSummary(BaseModel):
    """Current net position on one contract."""

    market_slug: str
    net_position: float = 0.0
    qty_bought: float = 0.0
    qty_sold: float = 0.0
    qty_available: float = 0.0
    cost: float = 0.0
    realized: float = 0.0
    cash_value: float = 0.0
    expired: bool = False
    update_time: str | None = None


class TradeSummary(BaseModel):
    """A single filled trade on one contract."""

    id: str
    market_slug: str
    state: str | None = None
    price: float | None = None
    qty: float = 0.0
    cost_basis: float = 0.0
    realized_pnl: float = 0.0
    is_aggressor: bool | None = None
    create_time: str | None = None


class ResolutionSummary(BaseModel):
    """A position that settled at market resolution/expiry.

    When a market resolves the payout is booked here rather than as a trade,
    so ``realized_pnl`` is the delta of the position's own realized counter
    across the resolution (``afterPosition.realized - beforePosition.realized``).
    """

    market_slug: str
    side: str | None = None
    side_label: str | None = None
    net_position: float = 0.0
    cost: float = 0.0
    payout: float = 0.0
    realized_pnl: float = 0.0
    resolved_time: str | None = None


class ContractStats(BaseModel):
    """Aggregated metrics for a single contract."""

    open_order_count: int = 0
    open_buy_count: int = 0
    open_sell_count: int = 0
    open_order_notional: float = 0.0
    net_position: float = 0.0
    position_cost: float = 0.0
    position_value: float = 0.0
    realized_pnl: float = 0.0
    trade_count: int = 0
    resolution_count: int = 0


class ContractGroup(BaseModel):
    """A single market/contract with all of the user's activity on it."""

    market_slug: str
    title: str | None = None
    outcome: str | None = None
    icon: str | None = None
    event_slug: str | None = None
    team: dict | None = None
    orders: list[OrderSummary] = []
    position: PositionSummary | None = None
    trades: list[TradeSummary] = []
    resolutions: list[ResolutionSummary] = []
    stats: ContractStats = ContractStats()


class EventStats(BaseModel):
    """Aggregated metrics for an event (rolled up from its contracts)."""

    contract_count: int = 0
    open_order_count: int = 0
    open_order_notional: float = 0.0
    position_value: float = 0.0
    position_cost: float = 0.0
    realized_pnl: float = 0.0
    trade_count: int = 0
    resolution_count: int = 0


class EventGroup(BaseModel):
    """An event grouping one or more contracts."""

    event_slug: str
    title: str
    contracts: list[ContractGroup] = []
    stats: EventStats = EventStats()


class BalanceSummary(BaseModel):
    """A subset of the account balance fields relevant to the dashboard."""

    currency: str | None = None
    current_balance: float | None = None
    buying_power: float | None = None
    asset_notional: float | None = None
    asset_available: float | None = None
    open_orders: float | None = None
    unsettled_funds: float | None = None
    pending_credit: float | None = None
    last_updated: str | None = None


class DashboardTotals(BaseModel):
    """Top-level totals across the whole dashboard."""

    event_count: int = 0
    contract_count: int = 0
    open_order_count: int = 0
    open_order_notional: float = 0.0
    position_value: float = 0.0
    position_cost: float = 0.0
    realized_pnl: float = 0.0
    trade_count: int = 0
    resolution_count: int = 0


class DashboardResponse(BaseModel):
    """The full grouped dashboard payload."""

    generated_at: str
    credentials_configured: bool
    balances: list[BalanceSummary] = []
    events: list[EventGroup] = []
    totals: DashboardTotals = DashboardTotals()
