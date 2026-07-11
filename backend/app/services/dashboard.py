"""Build the grouped dashboard payload from raw Polymarket US SDK data.

The SDK returns flat lists of orders / positions / trades, each carrying a
``marketSlug`` and (usually) an ``eventSlug`` inside ``marketMetadata``. This
service reshapes that flat data into a two-level hierarchy:

    Event  ->  Contract (market)  ->  {orders, position, trades} + stats

and rolls per-contract metrics up to the event and dashboard level.
"""

from __future__ import annotations

import logging
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
    PendingCashFlow,
    PendingCashSummary,
    PositionSummary,
    ResolutionSummary,
    TradeSummary,
)

logger = logging.getLogger(__name__)

# Pagination guardrails so a large account can't loop unbounded.
_PAGE_SIZE = 100
_MAX_POSITION_PAGES = 25
# Loop guard for the activity feed. Complete-history fetches terminate on the
# API's own ``eof`` signal; this ceiling (100k records) only bounds a
# misbehaving cursor that never reports eof — it is NOT a functional cap on how
# much history we return.
_MAX_ACTIVITY_PAGES = 1000
_MAX_EVENT_LOOKUPS = 60

# The activities feed interleaves trading events with cash movements. We fetch
# the two groups with separate ``types`` filters so each pages to completion
# independently: trade/resolution history feeds the per-contract rollups, while
# cash movements feed the pending-cash panel. Together these cover all seven
# ActivityType values the SDK defines.
_TRADE_ACTIVITY_TYPES = [
    "ACTIVITY_TYPE_TRADE",
    "ACTIVITY_TYPE_POSITION_RESOLUTION",
]
_CASH_ACTIVITY_TYPES = [
    "ACTIVITY_TYPE_ACCOUNT_DEPOSIT",
    "ACTIVITY_TYPE_ACCOUNT_ADVANCED_DEPOSIT",
    "ACTIVITY_TYPE_ACCOUNT_WITHDRAWAL",
    "ACTIVITY_TYPE_TRANSFER",
    "ACTIVITY_TYPE_REFERRAL_BONUS",
]

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


def _max_time(*times: str | None) -> str | None:
    """Return the latest of a set of RFC3339/ISO-8601 UTC timestamps.

    The SDK emits all timestamps as UTC (``...Z``) with fixed precision, so a
    plain lexicographic max is chronologically correct and avoids parsing.
    ``None`` / empty values are ignored.
    """
    present = [t for t in times if t]
    return max(present) if present else None


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


def _fetch_activities(
    client: PolymarketUS,
    types: list[str],
    *,
    max_records: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch activities of the given ``types``, newest first, following the
    cursor to the end of the feed.

    The activities endpoint exposes no date-range filter (only limit / cursor /
    marketSlug / types / sortOrder), so *complete* history can only be obtained
    by paging on ``nextCursor`` until the API reports ``eof``. ``max_records``
    optionally caps the result; ``None`` (the default) pulls the complete
    history. Termination is driven by the API's ``eof`` signal —
    ``_MAX_ACTIVITY_PAGES`` is only a runaway-loop guard, not a history cap.
    """
    activities: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(_MAX_ACTIVITY_PAGES):
        params: dict[str, Any] = {
            "limit": _PAGE_SIZE,
            "sortOrder": "SORT_ORDER_DESCENDING",
            "types": types,
        }
        if cursor:
            params["cursor"] = cursor
        response = client.portfolio.activities(params)
        activities.extend(response.get("activities") or [])
        if max_records is not None and len(activities) >= max_records:
            return activities[:max_records]
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


_PENDING_STATUS = "ACCOUNT_BALANCE_CHANGE_STATUS_PENDING"


def _pending_cash(activities: list[dict[str, Any]]) -> PendingCashSummary:
    """Pull pending (in-flight) withdrawals and deposits from the activity feed.

    Pending withdrawals are the usual reason ``current_balance`` exceeds
    ``buying_power``: the funds are on their way out (already removed from
    buying power) but still sit in the reported balance. Surfacing them lets
    the UI reconcile the two figures. Only ``PENDING`` items are included —
    completed/rejected movements are historical and don't affect the balance.
    """
    withdrawals: list[PendingCashFlow] = []
    deposits: list[PendingCashFlow] = []
    for activity in activities:
        change = activity.get("accountBalanceChange")
        if not change or change.get("status") != _PENDING_STATUS:
            continue
        atype = activity.get("type")
        outgoing = "WITHDRAWAL" in (atype or "")
        flow = PendingCashFlow(
            type=atype,
            type_label=_humanize_enum(atype, "ACTIVITY_TYPE_ACCOUNT_", "ACTIVITY_TYPE_"),
            direction="outgoing" if outgoing else "incoming",
            status=change.get("status"),
            status_label=_humanize_enum(change.get("status"), "ACCOUNT_BALANCE_CHANGE_STATUS_"),
            amount=_to_float0(change.get("amount")),
            description=change.get("description"),
            transaction_id=change.get("transactionId"),
            create_time=change.get("createTime"),
            update_time=change.get("updateTime"),
        )
        (withdrawals if outgoing else deposits).append(flow)

    return PendingCashSummary(
        withdrawals=withdrawals,
        deposits=deposits,
        total_withdrawals=sum(f.amount for f in withdrawals),
        total_deposits=sum(f.amount for f in deposits),
    )


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
        # Raw trade dicts (not summaries): per-trade realized PnL can only be
        # computed once *all* of a market's fills are known (see
        # ``_finalize_trades``), so we hold the raw records and summarize later.
        self.raw_trades: list[dict[str, Any]] = []
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


def _trade_summary(trade: dict[str, Any], realized_pnl: float) -> TradeSummary:
    """Summarize one trade. ``realized_pnl`` is supplied by the caller because
    it can only be determined with knowledge of the whole market's fills — see
    :func:`_finalize_trades`."""
    return TradeSummary(
        id=trade.get("id", ""),
        market_slug=trade.get("marketSlug", ""),
        state=trade.get("state"),
        price=_to_float(trade.get("price")),
        qty=_to_float0(trade.get("qty")),
        cost_basis=_to_float0(trade.get("costBasis")),
        realized_pnl=realized_pnl,
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


def _account_execution(trade: dict[str, Any]) -> dict[str, Any]:
    """The account's own execution leg of a trade.

    Every trade has two legs — the aggressor and the passive party — one of
    which is this account. The trade-level ``isAggressor`` flag says which, so
    we read *our* order (side) and commission rather than the counterparty's.
    """
    leg_key = "aggressorExecution" if trade.get("isAggressor") else "passiveExecution"
    return trade.get(leg_key) or {}


def _account_order_side(trade: dict[str, Any]) -> str | None:
    """This account's order side (``ORDER_SIDE_BUY`` / ``ORDER_SIDE_SELL``)."""
    return (_account_execution(trade).get("order") or {}).get("side")


def _trade_realized_understated(trade: dict[str, Any]) -> bool:
    """True when a trade booked realized P&L via the basis-naive ``realizedPnl``
    but omitted the authoritative ``effectiveRealizedPnl``.

    Normally ``effectiveRealizedPnl`` is present on every closing fill and is the
    correct, side-aware figure. On some *passive* fills, though, the API returns
    neither ``effectiveRealizedPnl`` nor ``costBasis`` and sets ``realizedPnl``
    equal to the trade's gross proceeds (cost basis treated as zero). Summing
    ``effectiveRealizedPnl`` then scores those fills as $0 and silently
    undercounts the market — the France-vs-Morocco half-time market is the live
    example (~$7k booked as $0). Detecting this lets us fall back to a robust
    cash-flow calculation for the affected market only.
    """
    return (
        trade.get("effectiveRealizedPnl") is None
        and _to_float0(trade.get("realizedPnl")) != 0.0
    )


def _trade_qty(trade: dict[str, Any]) -> float:
    """Exact trade quantity, preferring ``qtyDecimal`` over the rounded ``qty``.

    Uses an explicit presence check rather than ``qtyDecimal or qty`` so a
    legitimate zero ``qtyDecimal`` is not silently replaced by ``qty`` (which
    may be a different rounding).
    """
    raw = trade.get("qtyDecimal")
    if raw is None or raw == "":
        raw = trade.get("qty")
    return _to_float0(raw)


# A recovered book must net approximately flat; allow 1% slack for the
# share-level rounding the API applies to individual fills.
_RECOVERY_FLAT_TOLERANCE = 0.01


def _finalize_trades(raw_trades: list[dict[str, Any]]) -> tuple[list[TradeSummary], float]:
    """Build per-trade summaries and the market's total realized P&L from trades.

    Normal path: trust the SDK's ``effectiveRealizedPnl`` per trade. It is
    side-aware (correct for both longs and short-covers, where the plain
    ``realizedPnl`` gets the sign wrong) and 0 for opening fills, so a missing
    value is exact.

    Recovery path (a closing fill trips :func:`_trade_realized_understated`):
    the per-trade SDK figure is unusable for that market, so the *total* is
    rebuilt from the cash-flow identity on the now-flat book —

        realized = Σ(sell proceeds) − Σ(buy cost) − Σ(fees)

    which is side-agnostic (it cannot mis-sign a short) and exact for a book
    that starts and ends flat, i.e. the closed-by-selling case that reaches this
    code (an open position takes the ``position.realized`` path instead). We do
    NOT reconstruct realized market-by-market with average-cost accounting:
    validated against live data it diverges from the SDK on ~26 markets and even
    flips sign on shorts, so it must never replace the SDK figure where present.

    The cash-flow identity only equals realized P&L when we can see the whole
    round trip close out flat. If the visible buys and sells do NOT net flat
    (truncated history, or shares acquired outside trading), there is no cost
    basis to work from and deriving realized would silently OVERSTATE it (cost
    treated as zero) — so in that case we fall back to the SDK's per-trade
    figure rather than fabricate a number.

    For display, each closing sell is allocated its gain over the market's
    average buy cost so the trades table reconciles with the header; buys show
    no realized gain. For a long book this allocation sums exactly to the
    cash-flow total.
    """
    if not any(_trade_realized_understated(t) for t in raw_trades):
        return _sdk_trade_summaries(raw_trades)

    # --- Recovery: aggregate our own buy and sell fills --------------------
    buy_notional = buy_qty = buy_fee = 0.0
    sell_notional = sell_qty = sell_fee = 0.0
    for t in raw_trades:
        side = _account_order_side(t)
        notional = _to_float0(t.get("cost"))
        # commissionNotionalCollected: positive = fee paid, negative = rebate.
        fee = _to_float0(_account_execution(t).get("commissionNotionalCollected"))
        qty = _trade_qty(t)
        if side == "ORDER_SIDE_SELL":
            sell_notional += notional
            sell_qty += qty
            sell_fee += fee
        elif side == "ORDER_SIDE_BUY":
            buy_notional += notional
            buy_qty += qty
            buy_fee += fee

    book_flat = (
        buy_qty > 0
        and sell_qty > 0
        and abs(buy_qty - sell_qty) <= _RECOVERY_FLAT_TOLERANCE * max(buy_qty, sell_qty)
    )
    if not book_flat:
        slug = next((t.get("marketSlug") for t in raw_trades if t.get("marketSlug")), "?")
        logger.warning(
            "Realized-PnL recovery skipped for %s: trade book is not flat "
            "(buy_qty=%.2f, sell_qty=%.2f); using SDK effectiveRealizedPnl.",
            slug,
            buy_qty,
            sell_qty,
        )
        return _sdk_trade_summaries(raw_trades)

    total = (sell_notional - sell_fee) - (buy_notional + buy_fee)

    # --- Recovery: per-trade allocation for the trades table ---------------
    # Average buy cost per share (fees folded in) so the per-sell allocation
    # sums to the cash-flow total above for a long book. ``buy_qty > 0`` holds
    # because the book is flat.
    avg_buy_cost = (buy_notional + buy_fee) / buy_qty
    summaries: list[TradeSummary] = []
    for t in raw_trades:
        if _account_order_side(t) == "ORDER_SIDE_SELL":
            fee = _to_float0(_account_execution(t).get("commissionNotionalCollected"))
            realized = (_to_float0(t.get("cost")) - fee) - avg_buy_cost * _trade_qty(t)
        else:
            realized = 0.0
        summaries.append(_trade_summary(t, realized))
    return summaries, total


def _sdk_trade_summaries(
    raw_trades: list[dict[str, Any]],
) -> tuple[list[TradeSummary], float]:
    """Per-trade summaries and total using the SDK's ``effectiveRealizedPnl``
    (0 when absent). The default, side-correct path."""
    summaries = [
        _trade_summary(t, _to_float0(t.get("effectiveRealizedPnl"))) for t in raw_trades
    ]
    return summaries, sum(s.realized_pnl for s in summaries)


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


def _contract_stats(
    acc: _ContractAccumulator,
    trades: list[TradeSummary],
    trades_realized: float,
) -> ContractStats:
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
    #     so its realized PnL comes from the trades that closed it
    #     (``trades_realized``, computed by ``_finalize_trades``).
    #   * A RESOLVED position's payout never appears as a trade at all; it lives
    #     only in the resolution delta, which is self-contained (after - before)
    #     and therefore safe to add on top of either case above.
    resolution_pnl = sum(r.realized_pnl for r in acc.resolutions)
    if acc.position is not None:
        realized = acc.position.realized + resolution_pnl
    else:
        realized = trades_realized + resolution_pnl

    # Latest timestamp across every kind of activity on this contract.
    last_activity = _max_time(
        *(o.create_time for o in acc.orders),
        *(t.create_time for t in trades),
        *(r.resolved_time for r in acc.resolutions),
        acc.position.update_time if acc.position else None,
    )

    return ContractStats(
        open_order_count=len(acc.orders),
        open_buy_count=open_buy,
        open_sell_count=open_sell,
        open_order_notional=open_notional,
        net_position=acc.position.net_position if acc.position else 0.0,
        position_cost=acc.position.cost if acc.position else 0.0,
        position_value=acc.position.cash_value if acc.position else 0.0,
        realized_pnl=realized,
        trade_count=len(trades),
        resolution_count=len(acc.resolutions),
        last_activity=last_activity,
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
                acc.raw_trades.append(trade)
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
    trades, trades_realized = _finalize_trades(acc.raw_trades)
    return ContractGroup(
        market_slug=acc.market_slug,
        title=acc.title,
        outcome=acc.outcome,
        icon=acc.icon,
        event_slug=acc.event_slug,
        team=acc.team,
        orders=acc.orders,
        position=acc.position,
        trades=trades,
        resolutions=acc.resolutions,
        stats=_contract_stats(acc, trades, trades_realized),
    )


# ---------------------------------------------------------------------------
# Event grouping
# ---------------------------------------------------------------------------
# Event titles are immutable, so resolved ``slug -> title`` mappings are cached
# across requests. Without this, every dashboard refresh re-hit the events
# endpoint once per event (up to ``_MAX_EVENT_LOOKUPS`` calls each time), which
# was the single largest contributor to upstream rate-limiting. Only successful
# API titles are cached; a failed/absent lookup falls back to a humanized slug
# and is NOT cached, so a genuinely-known event can still resolve on a later
# request once the endpoint responds.
_EVENT_TITLE_CACHE: dict[str, str] = {}


def _event_title(client: PolymarketUS, slug: str, enrich: bool) -> str:
    """Resolve a human event title.

    Best-effort enrichment via the public events endpoint. This is a
    display-only enhancement, so if the lookup fails or the event is unknown we
    deliberately fall back to a humanized slug rather than failing the request.
    Successful lookups are memoized in :data:`_EVENT_TITLE_CACHE`.
    """
    cached = _EVENT_TITLE_CACHE.get(slug)
    if cached is not None:
        return cached
    if enrich:
        try:
            response = client.events.retrieve_by_slug(slug)
            event = response.get("event") or {}
            title = event.get("title")
            if title:
                _EVENT_TITLE_CACHE[slug] = title
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
        elif event_slug in _EVENT_TITLE_CACHE:
            # Cache hit: no upstream call, so it does not spend the lookup budget.
            title = _EVENT_TITLE_CACHE[event_slug]
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
            last_activity=_max_time(*(c.stats.last_activity for c in group_contracts)),
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
    max_activities: int = 0,
    enrich_events: bool = True,
) -> DashboardResponse:
    """Fetch all account data and return it grouped by event -> contract.

    ``max_activities`` caps the trade/resolution records pulled for grouping;
    ``0`` (the default) pulls the complete history by paging to the end of the
    feed. Cash-movement activity (deposits / withdrawals / transfers), used only
    for the pending-cash panel, is always fetched in full — its volume is low
    and completeness is required to catch every in-flight (pending) item.
    """
    max_records = max_activities if max_activities > 0 else None

    orders = _fetch_open_orders(client)
    positions = _fetch_positions(client)
    trade_activities = _fetch_activities(
        client, _TRADE_ACTIVITY_TYPES, max_records=max_records
    )
    cash_activities = _fetch_activities(client, _CASH_ACTIVITY_TYPES)
    balances = _fetch_balances(client)

    contracts = _build_contracts(orders, positions, trade_activities)
    events = _group_by_event(client, contracts, enrich_events=enrich_events)
    totals = _dashboard_totals(events)

    return DashboardResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        credentials_configured=True,
        balances=balances,
        pending_cash=_pending_cash(cash_activities),
        events=events,
        totals=totals,
    )
