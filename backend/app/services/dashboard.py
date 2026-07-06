"""Build the grouped dashboard payload from raw Polymarket US SDK data.

The SDK returns flat lists of orders / positions / trades, each carrying a
``marketSlug`` and (usually) an ``eventSlug`` inside ``marketMetadata``. This
service reshapes that flat data into a two-level hierarchy:

    Event  ->  Contract (market)  ->  {orders, position, trades} + stats

and rolls per-contract metrics up to the event and dashboard level.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from polymarket_us import PolymarketUS
from polymarket_us.errors import PolymarketUSError

from app.schemas import (
    BalanceSummary,
    ContractGroup,
    ContractStats,
    DashboardResponse,
    DashboardTotals,
    EventGroup,
    EventStats,
    OrderSummary,
    PositionSummary,
    ResolutionSummary,
    TradeSummary,
)

# Pagination guardrails so a large account can't loop unbounded.
_PAGE_SIZE = 100
_MAX_POSITION_PAGES = 25
_MAX_ACTIVITY_PAGES = 25
_MAX_EVENT_LOOKUPS = 60

_UNGROUPED_SLUG = "__ungrouped__"


# ---------------------------------------------------------------------------
# Parsing helpers (boundary code: the SDK dicts are loosely typed, so we coerce
# missing / blank fields deliberately here and assume clean data downstream).
# ---------------------------------------------------------------------------
def _to_float(value: Any) -> float | None:
    """Parse an SDK value (``Amount`` dict, string, or number) into a float."""
    if isinstance(value, dict):
        value = value.get("value")
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_float0(value: Any) -> float:
    """Like :func:`_to_float` but returns 0.0 instead of None (for sums)."""
    parsed = _to_float(value)
    return parsed if parsed is not None else 0.0


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _humanize_enum(value: str | None, *prefixes: str) -> str | None:
    """Strip a known SDK enum prefix and make it human readable.

    e.g. ``ORDER_SIDE_BUY`` -> ``buy``; ``ORDER_STATE_PARTIALLY_FILLED`` ->
    ``partially filled``.
    """
    if not value:
        return None
    result = value
    for prefix in prefixes:
        if result.startswith(prefix):
            result = result[len(prefix) :]
            break
    return result.replace("_", " ").strip().lower()


def _humanize_slug(slug: str) -> str:
    """Turn ``mlb-nyy-bos-2025-07-04`` into ``Mlb Nyy Bos 2025 07 04``."""
    return slug.replace("-", " ").replace("_", " ").strip().title()


# ---------------------------------------------------------------------------
# Raw data fetching
# ---------------------------------------------------------------------------
def _fetch_open_orders(client: PolymarketUS) -> list[dict[str, Any]]:
    response = client.orders.list()
    return list(response.get("orders") or [])


def _fetch_positions(client: PolymarketUS) -> dict[str, dict[str, Any]]:
    """Fetch every position, following the cursor until EOF."""
    positions: dict[str, dict[str, Any]] = {}
    cursor: str | None = None
    for _ in range(_MAX_POSITION_PAGES):
        params: dict[str, Any] = {"limit": _PAGE_SIZE}
        if cursor:
            params["cursor"] = cursor
        response = client.portfolio.positions(params)
        page = response.get("positions") or {}
        positions.update(page)
        if response.get("eof") or not response.get("nextCursor"):
            break
        cursor = response.get("nextCursor")
    return positions


def _fetch_activities(client: PolymarketUS, max_activities: int) -> list[dict[str, Any]]:
    """Fetch recent activities (trades + resolutions + transfers), newest first."""
    activities: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(_MAX_ACTIVITY_PAGES):
        params: dict[str, Any] = {
            "limit": _PAGE_SIZE,
            "sortOrder": "SORT_ORDER_DESCENDING",
        }
        if cursor:
            params["cursor"] = cursor
        response = client.portfolio.activities(params)
        page = response.get("activities") or []
        activities.extend(page)
        if len(activities) >= max_activities:
            return activities[:max_activities]
        if response.get("eof") or not response.get("nextCursor"):
            break
        cursor = response.get("nextCursor")
    return activities


def _fetch_balances(client: PolymarketUS) -> list[BalanceSummary]:
    response = client.account.balances()
    result: list[BalanceSummary] = []
    for bal in response.get("balances") or []:
        result.append(
            BalanceSummary(
                currency=bal.get("currency"),
                current_balance=_to_float(bal.get("currentBalance")),
                buying_power=_to_float(bal.get("buyingPower")),
                asset_notional=_to_float(bal.get("assetNotional")),
                asset_available=_to_float(bal.get("assetAvailable")),
                open_orders=_to_float(bal.get("openOrders")),
                unsettled_funds=_to_float(bal.get("unsettledFunds")),
                pending_credit=_to_float(bal.get("pendingCredit")),
                last_updated=bal.get("lastUpdated"),
            )
        )
    return result


# ---------------------------------------------------------------------------
# Contract assembly
# ---------------------------------------------------------------------------
class _ContractAccumulator:
    """Mutable working state for one contract while we bucket raw records."""

    def __init__(self, market_slug: str) -> None:
        self.market_slug = market_slug
        self.title: str | None = None
        self.outcome: str | None = None
        self.icon: str | None = None
        self.event_slug: str | None = None
        self.team: dict[str, Any] | None = None
        self.orders: list[OrderSummary] = []
        self.position: PositionSummary | None = None
        self.trades: list[TradeSummary] = []
        self.resolutions: list[ResolutionSummary] = []

    def absorb_metadata(self, metadata: dict[str, Any] | None) -> None:
        """Fill in display metadata from a ``marketMetadata`` blob if unset."""
        if not metadata:
            return
        self.title = self.title or metadata.get("title")
        self.outcome = self.outcome or metadata.get("outcome")
        self.icon = self.icon or metadata.get("icon")
        self.event_slug = self.event_slug or metadata.get("eventSlug")
        if self.team is None and metadata.get("team"):
            self.team = metadata.get("team")


def _order_summary(order: dict[str, Any]) -> OrderSummary:
    price = _to_float(order.get("price"))
    leaves = _to_int(order.get("leavesQuantity"))
    notional = (price or 0.0) * leaves
    return OrderSummary(
        id=order.get("id", ""),
        market_slug=order.get("marketSlug", ""),
        side=order.get("side"),
        side_label=_humanize_enum(order.get("side"), "ORDER_SIDE_"),
        type=_humanize_enum(order.get("type"), "ORDER_TYPE_"),
        state=order.get("state"),
        state_label=_humanize_enum(order.get("state"), "ORDER_STATE_"),
        intent=_humanize_enum(order.get("intent"), "ORDER_INTENT_"),
        tif=_humanize_enum(order.get("tif"), "TIME_IN_FORCE_"),
        price=price,
        avg_px=_to_float(order.get("avgPx")),
        quantity=_to_int(order.get("quantity")),
        cum_quantity=_to_int(order.get("cumQuantity")),
        leaves_quantity=leaves,
        notional=notional,
        create_time=order.get("createTime") or order.get("insertTime"),
    )


def _position_summary(slug: str, position: dict[str, Any]) -> PositionSummary:
    return PositionSummary(
        market_slug=slug,
        net_position=_to_float0(position.get("netPosition")),
        qty_bought=_to_float0(position.get("qtyBought")),
        qty_sold=_to_float0(position.get("qtySold")),
        qty_available=_to_float0(position.get("qtyAvailable")),
        cost=_to_float0(position.get("cost")),
        realized=_to_float0(position.get("realized")),
        cash_value=_to_float0(position.get("cashValue")),
        expired=bool(position.get("expired", False)),
        update_time=position.get("updateTime"),
    )


def _trade_summary(trade: dict[str, Any]) -> TradeSummary:
    return TradeSummary(
        id=trade.get("id", ""),
        market_slug=trade.get("marketSlug", ""),
        state=trade.get("state"),
        price=_to_float(trade.get("price")),
        qty=_to_float0(trade.get("qty")),
        cost_basis=_to_float0(trade.get("costBasis")),
        realized_pnl=_to_float0(trade.get("realizedPnl")),
        is_aggressor=trade.get("isAggressor"),
        create_time=trade.get("createTime"),
    )


def _trade_metadata(trade: dict[str, Any]) -> dict[str, Any] | None:
    """Dig the ``marketMetadata`` out of a trade.

    Unlike orders and positions, a trade has no top-level ``marketMetadata``.
    The same blob (title / outcome / eventSlug for the contract) is instead
    nested under each execution and counterparty leg. We probe them in order
    and return the first present — they describe the same contract, so any is
    equivalent. Without this, markets known *only* through trades (positions
    fully closed by selling) have no event slug and fall into "Ungrouped".
    """
    for leg_key in ("aggressorExecution", "passiveExecution"):
        leg = trade.get(leg_key) or {}
        order = leg.get("order") or {}
        metadata = order.get("marketMetadata")
        if metadata:
            return metadata
    for leg_key in ("aggressor", "passive"):
        leg = trade.get(leg_key) or {}
        metadata = leg.get("marketMetadata")
        if metadata:
            return metadata
    return None


def _resolution_summary(resolution: dict[str, Any]) -> ResolutionSummary:
    """Summarize a settled position from a ``positionResolution`` activity.

    The realized PnL of a resolution is the *change* in the position's own
    realized counter across settlement, so any realized gain from partial
    sells that happened before resolution (already captured by the sell
    trades) is excluded here and not double-counted.
    """
    before = resolution.get("beforePosition") or {}
    after = resolution.get("afterPosition") or {}
    realized_before = _to_float0(before.get("realized"))
    realized_after = _to_float0(after.get("realized"))
    return ResolutionSummary(
        market_slug=resolution.get("marketSlug", ""),
        side=resolution.get("side"),
        side_label=_humanize_enum(resolution.get("side"), "POSITION_RESOLUTION_SIDE_"),
        net_position=_to_float0(before.get("netPosition")),
        cost=_to_float0(before.get("cost")),
        payout=_to_float0(before.get("cashValue")),
        realized_pnl=realized_after - realized_before,
        resolved_time=resolution.get("updateTime"),
    )


def _contract_stats(acc: _ContractAccumulator) -> ContractStats:
    open_buy = sum(1 for o in acc.orders if o.side == "ORDER_SIDE_BUY")
    open_sell = sum(1 for o in acc.orders if o.side == "ORDER_SIDE_SELL")
    open_notional = sum(o.notional for o in acc.orders)

    # Realized PnL, de-duplicated across the SDK's three overlapping sources:
    #   * An OPEN position carries ``position.realized`` — the authoritative
    #     cumulative realized-from-selling for that market. The individual sell
    #     trades that produced it are already baked into that number, and it is
    #     not truncated by the activity fetch window, so we trust it and do NOT
    #     also add the per-trade figures (that was the double-count bug).
    #   * A CLOSED-BY-SELLING position no longer appears in the positions list,
    #     so its realized PnL is the sum of the trades that closed it.
    #   * A RESOLVED position's payout never appears as a trade at all; it lives
    #     only in the resolution delta, which is self-contained (after - before)
    #     and therefore safe to add on top of either case above.
    resolution_pnl = sum(r.realized_pnl for r in acc.resolutions)
    if acc.position is not None:
        realized = acc.position.realized + resolution_pnl
    else:
        realized = sum(t.realized_pnl for t in acc.trades) + resolution_pnl

    return ContractStats(
        open_order_count=len(acc.orders),
        open_buy_count=open_buy,
        open_sell_count=open_sell,
        open_order_notional=open_notional,
        net_position=acc.position.net_position if acc.position else 0.0,
        position_cost=acc.position.cost if acc.position else 0.0,
        position_value=acc.position.cash_value if acc.position else 0.0,
        realized_pnl=realized,
        trade_count=len(acc.trades),
        resolution_count=len(acc.resolutions),
    )


def _build_contracts(
    orders: list[dict[str, Any]],
    positions: dict[str, dict[str, Any]],
    activities: list[dict[str, Any]],
) -> dict[str, _ContractAccumulator]:
    """Bucket every raw record into a per-contract accumulator keyed by slug."""
    contracts: dict[str, _ContractAccumulator] = {}

    def get(slug: str) -> _ContractAccumulator:
        if slug not in contracts:
            contracts[slug] = _ContractAccumulator(slug)
        return contracts[slug]

    for order in orders:
        slug = order.get("marketSlug")
        if not slug:
            continue
        acc = get(slug)
        acc.absorb_metadata(order.get("marketMetadata"))
        acc.orders.append(_order_summary(order))

    for slug, position in positions.items():
        if not slug:
            continue
        acc = get(slug)
        acc.absorb_metadata(position.get("marketMetadata"))
        acc.position = _position_summary(slug, position)

    for activity in activities:
        trade = activity.get("trade")
        if trade:
            slug = trade.get("marketSlug")
            if slug:
                acc = get(slug)
                acc.absorb_metadata(_trade_metadata(trade))
                acc.trades.append(_trade_summary(trade))
            continue

        resolution = activity.get("positionResolution")
        if resolution:
            slug = resolution.get("marketSlug")
            if slug:
                acc = get(slug)
                # Resolved markets often have no open position or orders left,
                # so their display metadata (title/outcome/event) must come from
                # the pre-resolution snapshot.
                before = resolution.get("beforePosition") or {}
                acc.absorb_metadata(before.get("marketMetadata"))
                acc.resolutions.append(_resolution_summary(resolution))
            continue

        # Other activity types (deposits, withdrawals, transfers, referral
        # bonuses) are account cash flows, not trading PnL, so they are
        # intentionally excluded from the per-contract rollups.

    return contracts


def _to_contract_group(acc: _ContractAccumulator) -> ContractGroup:
    return ContractGroup(
        market_slug=acc.market_slug,
        title=acc.title,
        outcome=acc.outcome,
        icon=acc.icon,
        event_slug=acc.event_slug,
        team=acc.team,
        orders=acc.orders,
        position=acc.position,
        trades=acc.trades,
        resolutions=acc.resolutions,
        stats=_contract_stats(acc),
    )


# ---------------------------------------------------------------------------
# Event grouping
# ---------------------------------------------------------------------------
def _event_title(client: PolymarketUS, slug: str, enrich: bool) -> str:
    """Resolve a human event title.

    Best-effort enrichment via the public events endpoint. This is a
    display-only enhancement, so if the lookup fails or the event is unknown we
    deliberately fall back to a humanized slug rather than failing the request.
    """
    if enrich:
        try:
            response = client.events.retrieve_by_slug(slug)
            event = response.get("event") or {}
            title = event.get("title")
            if title:
                return title
        except PolymarketUSError:
            pass  # fall through to humanized slug (display-only fallback)
    return _humanize_slug(slug)


def _group_by_event(
    client: PolymarketUS,
    contracts: dict[str, _ContractAccumulator],
    enrich_events: bool,
) -> list[EventGroup]:
    buckets: dict[str, list[ContractGroup]] = {}
    for acc in contracts.values():
        key = acc.event_slug or _UNGROUPED_SLUG
        buckets.setdefault(key, []).append(_to_contract_group(acc))

    lookups_remaining = _MAX_EVENT_LOOKUPS
    events: list[EventGroup] = []
    for event_slug, group_contracts in buckets.items():
        group_contracts.sort(key=lambda c: c.market_slug)

        if event_slug == _UNGROUPED_SLUG:
            title = "Ungrouped markets"
        else:
            title = _event_title(client, event_slug, enrich_events and lookups_remaining > 0)
            lookups_remaining -= 1

        stats = EventStats(
            contract_count=len(group_contracts),
            open_order_count=sum(c.stats.open_order_count for c in group_contracts),
            open_order_notional=sum(c.stats.open_order_notional for c in group_contracts),
            position_value=sum(c.stats.position_value for c in group_contracts),
            position_cost=sum(c.stats.position_cost for c in group_contracts),
            realized_pnl=sum(c.stats.realized_pnl for c in group_contracts),
            trade_count=sum(c.stats.trade_count for c in group_contracts),
            resolution_count=sum(c.stats.resolution_count for c in group_contracts),
        )
        events.append(
            EventGroup(
                event_slug=event_slug,
                title=title,
                contracts=group_contracts,
                stats=stats,
            )
        )

    # Most active events first: open orders, then live position value, then
    # settled magnitude so resolved events surface by their realized PnL
    # instead of sinking to the bottom just because they have no open activity.
    events.sort(
        key=lambda e: (
            e.stats.open_order_count,
            e.stats.position_value,
            abs(e.stats.realized_pnl),
        ),
        reverse=True,
    )
    return events


def _dashboard_totals(events: list[EventGroup]) -> DashboardTotals:
    return DashboardTotals(
        event_count=len(events),
        contract_count=sum(e.stats.contract_count for e in events),
        open_order_count=sum(e.stats.open_order_count for e in events),
        open_order_notional=sum(e.stats.open_order_notional for e in events),
        position_value=sum(e.stats.position_value for e in events),
        position_cost=sum(e.stats.position_cost for e in events),
        realized_pnl=sum(e.stats.realized_pnl for e in events),
        trade_count=sum(e.stats.trade_count for e in events),
        resolution_count=sum(e.stats.resolution_count for e in events),
    )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
def build_dashboard(
    client: PolymarketUS,
    *,
    max_activities: int = 300,
    enrich_events: bool = True,
) -> DashboardResponse:
    """Fetch all account data and return it grouped by event -> contract."""
    orders = _fetch_open_orders(client)
    positions = _fetch_positions(client)
    activities = _fetch_activities(client, max_activities=max_activities)
    balances = _fetch_balances(client)

    contracts = _build_contracts(orders, positions, activities)
    events = _group_by_event(client, contracts, enrich_events=enrich_events)
    totals = _dashboard_totals(events)

    return DashboardResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        credentials_configured=True,
        balances=balances,
        events=events,
        totals=totals,
    )
