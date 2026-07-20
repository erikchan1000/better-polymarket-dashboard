"""Unit test for the grouping service using a stub SDK client.

Runnable two ways:
    pytest backend/tests
    python backend/tests/test_dashboard_grouping.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.dashboard import build_dashboard  # noqa: E402


def _amount(value: str) -> dict:
    return {"value": value, "currency": "USD"}


class _StubResource:
    def __init__(self, **methods):
        self._methods = methods

    def __getattr__(self, name):
        return self._methods[name]


class StubClient:
    """Mimics the parts of PolymarketUS that build_dashboard touches."""

    def __init__(self):
        self.orders = _StubResource(list=self._orders_list)
        self.portfolio = _StubResource(
            positions=self._positions, activities=self._activities
        )
        self.account = _StubResource(balances=self._balances)
        self.events = _StubResource(retrieve_by_slug=self._event)

    def _orders_list(self, params=None):
        return {
            "orders": [
                {
                    "id": "o1",
                    "marketSlug": "yankees-win",
                    "side": "ORDER_SIDE_BUY",
                    "type": "ORDER_TYPE_LIMIT",
                    "state": "ORDER_STATE_NEW",
                    "price": _amount("0.55"),
                    "quantity": 100,
                    "leavesQuantity": 100,
                    "createTime": "2025-07-04T12:00:00Z",
                    "marketMetadata": {
                        "title": "Yankees vs Red Sox",
                        "outcome": "Yankees",
                        "eventSlug": "mlb-nyy-bos-2025-07-04",
                    },
                },
                {
                    "id": "o2",
                    "marketSlug": "redsox-win",
                    "side": "ORDER_SIDE_SELL",
                    "type": "ORDER_TYPE_LIMIT",
                    "state": "ORDER_STATE_PARTIALLY_FILLED",
                    "price": _amount("0.48"),
                    "quantity": 50,
                    "leavesQuantity": 30,
                    "marketMetadata": {
                        "title": "Yankees vs Red Sox",
                        "outcome": "Red Sox",
                        "eventSlug": "mlb-nyy-bos-2025-07-04",
                    },
                },
                {
                    "id": "o3",
                    "marketSlug": "lonely-market",
                    "side": "ORDER_SIDE_BUY",
                    "price": _amount("0.10"),
                    "quantity": 10,
                    "leavesQuantity": 10,
                    "marketMetadata": {"title": "Lonely", "outcome": "Yes"},
                },
            ]
        }

    def _positions(self, params=None):
        return {
            "positions": {
                # Open position that has already realized 5.00 from a partial
                # sell. The sell trade below carries the *same* 5.00 — the stats
                # must not double-count it.
                "yankees-win": {
                    "netPosition": "40",
                    "qtyBought": "40",
                    "qtySold": "0",
                    "qtyAvailable": "40",
                    "cost": _amount("22.00"),
                    "realized": _amount("5.00"),
                    "cashValue": _amount("24.00"),
                    "marketMetadata": {
                        "title": "Yankees vs Red Sox",
                        "outcome": "Yankees",
                        "eventSlug": "mlb-nyy-bos-2025-07-04",
                    },
                }
            },
            "eof": True,
        }

    def _activities(self, params=None):
        return {
            "activities": [
                {
                    "type": "ACTIVITY_TYPE_TRADE",
                    "trade": {
                        "id": "t1",
                        "marketSlug": "yankees-win",
                        "price": _amount("0.55"),
                        "qty": "40",
                        "costBasis": _amount("22.00"),
                        # Already reflected in the position's `realized` above.
                        # A plain long: effective == nominal.
                        "realizedPnl": _amount("5.00"),
                        "effectiveRealizedPnl": _amount("5.00"),
                        "createTime": "2025-07-04T12:05:00Z",
                    },
                },
                # A held-to-expiry winner: the payout lands here, NOT as a trade.
                {
                    "type": "ACTIVITY_TYPE_POSITION_RESOLUTION",
                    "positionResolution": {
                        "marketSlug": "brazil-advance",
                        "side": "POSITION_RESOLUTION_SIDE_LONG",
                        "updateTime": "2025-07-05T20:00:00Z",
                        "beforePosition": {
                            "netPosition": "1000",
                            "cost": _amount("327.95"),
                            "realized": _amount("0"),
                            "cashValue": _amount("995.00"),
                            "marketMetadata": {
                                "title": "Brazil vs Norway",
                                "outcome": "Norway",
                                "eventSlug": "fwc-bra-nor-2025-07-05",
                            },
                        },
                        "afterPosition": {
                            "netPosition": "0",
                            "cost": _amount("0"),
                            "realized": _amount("685.00"),
                        },
                    },
                },
                # A position fully closed by selling: known ONLY through a
                # trade, with no order/position/resolution. Its metadata lives
                # nested under the execution legs (no top-level marketMetadata),
                # so it must still be grouped into its event, not "Ungrouped".
                {
                    "type": "ACTIVITY_TYPE_TRADE",
                    "trade": {
                        "id": "t2",
                        "marketSlug": "usa-win",
                        "price": _amount("0.60"),
                        "qty": "10",
                        "costBasis": _amount("6.00"),
                        # Plain long closed by selling: effective == nominal.
                        "realizedPnl": _amount("12.00"),
                        "effectiveRealizedPnl": _amount("12.00"),
                        "createTime": "2025-07-05T18:00:00Z",
                        "aggressorExecution": {
                            "order": {
                                "marketMetadata": {
                                    "title": "USA vs Australia",
                                    "outcome": "USA",
                                    "eventSlug": "fwc-usa-aus-2025-06-19",
                                }
                            }
                        },
                    },
                },
                # A SHORT covered by buying back cheap: shorted at 0.60, bought
                # back to cover at 0.005 -> a real GAIN. The side-naive
                # `realizedPnl` reports it as a loss (-600); `effectiveRealizedPnl`
                # has the correct sign (+400). The grouper must use the effective
                # field, so this contract's realized P&L is +400, not -600.
                {
                    "type": "ACTIVITY_TYPE_TRADE",
                    "trade": {
                        "id": "t3",
                        "marketSlug": "short-cover-win",
                        "price": _amount("0.005"),
                        "originalPrice": _amount("0.60"),
                        "qty": "1000",
                        "costBasis": _amount("600.00"),
                        "realizedPnl": _amount("-600.00"),
                        "effectiveRealizedPnl": _amount("400.00"),
                        "createTime": "2025-07-06T09:00:00Z",
                        "aggressorExecution": {
                            "order": {
                                "side": "ORDER_SIDE_BUY",
                                "marketMetadata": {
                                    "title": "Longshot Market",
                                    "outcome": "No",
                                    "eventSlug": "misc-longshot-2025-07-06",
                                },
                            }
                        },
                    },
                },
                # A pending (in-flight) withdrawal: excluded from PnL, but must
                # surface in pending_cash so the balance gap is explained.
                {
                    "type": "ACTIVITY_TYPE_ACCOUNT_WITHDRAWAL",
                    "accountBalanceChange": {
                        "amount": _amount("1950.59"),
                        "status": "ACCOUNT_BALANCE_CHANGE_STATUS_PENDING",
                        "transactionId": "W1",
                        "description": "Polymarket Withdrawal",
                        "createTime": "2025-07-05T22:58:27Z",
                    },
                },
                # A pending deposit (incoming).
                {
                    "type": "ACTIVITY_TYPE_ACCOUNT_DEPOSIT",
                    "accountBalanceChange": {
                        "amount": _amount("2000.00"),
                        "status": "ACCOUNT_BALANCE_CHANGE_STATUS_PENDING",
                        "transactionId": "D1",
                        "description": "Apple Pay Deposit",
                        "createTime": "2025-07-05T23:00:00Z",
                    },
                },
                # A COMPLETED withdrawal must NOT show up as pending.
                {
                    "type": "ACTIVITY_TYPE_ACCOUNT_WITHDRAWAL",
                    "accountBalanceChange": {
                        "amount": _amount("500.00"),
                        "status": "ACCOUNT_BALANCE_CHANGE_STATUS_COMPLETED",
                        "transactionId": "W2",
                    },
                },
            ],
            "eof": True,
        }

    def _balances(self):
        return {
            "balances": [
                {"currency": "USD", "currentBalance": 1000.0, "buyingPower": 950.0}
            ]
        }

    def _event(self, slug):
        titles = {"mlb-nyy-bos-2025-07-04": "MLB: Yankees @ Red Sox"}
        if slug in titles:
            return {"event": {"slug": slug, "title": titles[slug]}}
        return {"event": {}}


def test_grouping():
    dash = build_dashboard(StubClient(), max_activities=100, enrich_events=True)

    # Five event groups: the MLB game, the resolved World Cup market, the
    # trade-only USA match, the short-cover market, plus "Ungrouped markets"
    # for lonely-market.
    assert dash.totals.event_count == 5
    assert dash.totals.contract_count == 6
    assert dash.totals.open_order_count == 3

    events_by_slug = {e.event_slug: e for e in dash.events}

    mlb = events_by_slug["mlb-nyy-bos-2025-07-04"]
    assert mlb.title == "MLB: Yankees @ Red Sox"  # enriched via events API
    assert mlb.stats.contract_count == 2
    assert mlb.stats.open_order_count == 2
    # open notional: 0.55*100 + 0.48*30 = 55 + 14.4 = 69.4
    assert abs(mlb.stats.open_order_notional - 69.4) < 1e-6
    # position value from yankees-win cashValue
    assert abs(mlb.stats.position_value - 24.0) < 1e-6

    yankees = next(c for c in mlb.contracts if c.market_slug == "yankees-win")
    assert yankees.outcome == "Yankees"
    assert yankees.position is not None
    assert abs(yankees.position.net_position - 40.0) < 1e-6
    assert len(yankees.trades) == 1
    assert yankees.stats.open_order_count == 1
    # Double-count guard: position.realized (5.00) and the sell trade (5.00)
    # describe the SAME realized gain, so the contract total is 5.00, not 10.00.
    assert abs(yankees.stats.realized_pnl - 5.0) < 1e-6

    # Resolution: held-to-expiry winner books its payout via the resolution
    # delta (685 - 0), even though there is no position or trade for it.
    wc = events_by_slug["fwc-bra-nor-2025-07-05"]
    assert wc.stats.contract_count == 1
    assert wc.stats.resolution_count == 1
    assert abs(wc.stats.realized_pnl - 685.0) < 1e-6
    brazil = next(c for c in wc.contracts if c.market_slug == "brazil-advance")
    assert brazil.title == "Brazil vs Norway"  # metadata absorbed from resolution
    assert brazil.position is None
    assert len(brazil.resolutions) == 1
    assert abs(brazil.resolutions[0].realized_pnl - 685.0) < 1e-6
    assert abs(brazil.resolutions[0].payout - 995.0) < 1e-6

    # Trade-only market: metadata pulled from the nested execution leg, so it
    # groups into its event instead of falling into "Ungrouped".
    usa = events_by_slug["fwc-usa-aus-2025-06-19"]
    assert usa.stats.contract_count == 1
    usa_win = next(c for c in usa.contracts if c.market_slug == "usa-win")
    assert usa_win.title == "USA vs Australia"
    assert usa_win.outcome == "USA"
    assert usa_win.event_slug == "fwc-usa-aus-2025-06-19"
    assert abs(usa_win.stats.realized_pnl - 12.0) < 1e-6

    # Short-cover market: the grouper must read `effectiveRealizedPnl` (+400,
    # side-aware) rather than the side-naive `realizedPnl` (-600). This asserts
    # the sign is correct for a buy that closes a short. On the old code (which
    # summed `realizedPnl`) this contract would read -600.
    sc = events_by_slug["misc-longshot-2025-07-06"]
    short_cover = next(c for c in sc.contracts if c.market_slug == "short-cover-win")
    assert abs(short_cover.stats.realized_pnl - 400.0) < 1e-6
    assert abs(sc.stats.realized_pnl - 400.0) < 1e-6

    # last_activity is the latest timestamp across each contract's activity, and
    # the event rolls up to the max of its contracts.
    assert usa_win.stats.last_activity == "2025-07-05T18:00:00Z"  # its trade
    assert usa.stats.last_activity == "2025-07-05T18:00:00Z"
    assert wc.stats.last_activity == "2025-07-05T20:00:00Z"  # resolution time
    assert brazil.stats.last_activity == "2025-07-05T20:00:00Z"
    # MLB: max of yankees-win order (12:00) and its trade (12:05); the red-sox
    # order has no timestamp and is ignored.
    assert mlb.stats.last_activity == "2025-07-04T12:05:00Z"

    # Only lonely-market (which genuinely has no event slug) stays ungrouped.
    ungrouped = events_by_slug["__ungrouped__"]
    assert ungrouped.title == "Ungrouped markets"
    assert ungrouped.stats.contract_count == 1
    assert ungrouped.contracts[0].market_slug == "lonely-market"

    # Dashboard totals: yankees 5.00 + brazil 685.00 + usa 12.00 + short-cover
    # 400.00 = 1102.00. The 1950.59 withdrawal is a cash flow and must not leak
    # into realized PnL.
    assert abs(dash.totals.realized_pnl - 1102.0) < 1e-6
    assert dash.totals.resolution_count == 1
    assert dash.totals.trade_count == 3

    # Balances flow through.
    assert dash.balances[0].current_balance == 1000.0
    assert dash.credentials_configured is True

    # Pending cash: only PENDING items, split by direction. The completed
    # withdrawal (W2) is excluded; PnL totals above are unaffected by any of it.
    pc = dash.pending_cash
    assert len(pc.withdrawals) == 1
    assert pc.withdrawals[0].direction == "outgoing"
    assert pc.withdrawals[0].transaction_id == "W1"
    assert abs(pc.total_withdrawals - 1950.59) < 1e-6
    assert len(pc.deposits) == 1
    assert pc.deposits[0].direction == "incoming"
    assert abs(pc.total_deposits - 2000.0) < 1e-6

    print("test_grouping: PASS")
    print(f"  events={dash.totals.event_count} contracts={dash.totals.contract_count} "
          f"open_orders={dash.totals.open_order_count} "
          f"open_notional={dash.totals.open_order_notional:.2f} "
          f"realized={dash.totals.realized_pnl:.2f} "
          f"resolutions={dash.totals.resolution_count}")


class _PaginatingClient:
    """Stub whose trade feed spans several cursor pages.

    Exercises complete-history pagination: the feed is far larger than the old
    300-record default cap, so the service must follow ``nextCursor`` to ``eof``
    to surface every trade. Also records the ``types`` filter of each activities
    call so we can assert trade and cash feeds are fetched separately.
    """

    def __init__(self, trade_pages: list[list[dict]]):
        self._trade_pages = trade_pages
        # cursor "cN" -> page index N; the first (cursor-less) call is page 0.
        self.activity_calls: list[dict] = []
        self.orders = _StubResource(list=lambda params=None: {"orders": []})
        self.portfolio = _StubResource(positions=self._positions, activities=self._activities)
        self.account = _StubResource(balances=lambda: {"balances": []})
        self.events = _StubResource(retrieve_by_slug=lambda slug: {"event": {}})

    def _positions(self, params=None):
        return {"positions": {}, "eof": True}

    def _activities(self, params=None):
        params = params or {}
        self.activity_calls.append(params)
        types = params.get("types") or []
        # Cash feed is empty in this scenario; only the trade feed paginates.
        if "ACTIVITY_TYPE_TRADE" not in types:
            return {"activities": [], "eof": True}
        cursor = params.get("cursor")
        idx = 0 if cursor is None else int(cursor[1:])
        page = self._trade_pages[idx]
        resp: dict = {"activities": page}
        if idx + 1 < len(self._trade_pages):
            resp["nextCursor"] = f"c{idx + 1}"
        else:
            resp["eof"] = True
        return resp


def _make_trade(i: int) -> dict:
    return {
        "type": "ACTIVITY_TYPE_TRADE",
        "trade": {
            "id": f"t{i}",
            "marketSlug": "m",
            "price": _amount("0.50"),
            "qty": "1",
            "costBasis": _amount("0.50"),
            "realizedPnl": _amount("0.00"),
            "createTime": "2025-01-01T00:00:00Z",
            "aggressorExecution": {
                "order": {
                    "marketMetadata": {"title": "M", "outcome": "Yes", "eventSlug": "evt"}
                }
            },
        },
    }


def test_activities_paginate_to_completion():
    # 450 trades across 5 pages (100*4 + 50). The old default capped at 300, so
    # this asserts the service now pages all the way to eof for complete history.
    trades = [_make_trade(i) for i in range(450)]
    pages = [trades[0:100], trades[100:200], trades[200:300], trades[300:400], trades[400:450]]
    client = _PaginatingClient(pages)

    # No max_activities -> complete history (default).
    dash = build_dashboard(client, enrich_events=False)

    # Every trade is surfaced, not truncated at the old 300 cap.
    assert dash.totals.trade_count == 450

    # We issued exactly 5 trade-feed calls (one per page) plus >=1 cash-feed
    # call, following the cursor to eof rather than stopping early.
    trade_calls = [c for c in client.activity_calls if "ACTIVITY_TYPE_TRADE" in (c.get("types") or [])]
    cash_calls = [c for c in client.activity_calls if "ACTIVITY_TYPE_TRADE" not in (c.get("types") or [])]
    assert len(trade_calls) == 5
    assert len(cash_calls) >= 1

    # Trade and cash feeds are requested with explicit, disjoint type filters.
    assert "ACTIVITY_TYPE_POSITION_RESOLUTION" in trade_calls[0]["types"]
    assert "ACTIVITY_TYPE_ACCOUNT_WITHDRAWAL" in cash_calls[0]["types"]
    assert "ACTIVITY_TYPE_TRADE" not in cash_calls[0]["types"]

    print("test_activities_paginate_to_completion: PASS")
    print(f"  trade_count={dash.totals.trade_count} trade_calls={len(trade_calls)}")


def test_max_activities_cap_still_truncates():
    # An explicit cap must still bound the fetch (and stop paging early).
    trades = [_make_trade(i) for i in range(450)]
    pages = [trades[0:100], trades[100:200], trades[200:300], trades[300:400], trades[400:450]]
    client = _PaginatingClient(pages)

    dash = build_dashboard(client, max_activities=150, enrich_events=False)

    assert dash.totals.trade_count == 150
    trade_calls = [c for c in client.activity_calls if "ACTIVITY_TYPE_TRADE" in (c.get("types") or [])]
    # 150 records is reached after the 2nd page, so paging stops there.
    assert len(trade_calls) == 2

    print("test_max_activities_cap_still_truncates: PASS")


class _PassiveFillClient:
    """Stub reproducing the passive-fill realized-PnL gap.

    ``halftime-fra`` mirrors the live France-vs-Morocco half-time market: a long
    opened by buying, then fully closed by *passive* sell fills for which the API
    returns NO ``effectiveRealizedPnl`` and NO ``costBasis``, only a basis-naive
    ``realizedPnl`` equal to the gross proceeds. Summing ``effectiveRealizedPnl``
    scores it as $0; the cash-flow recovery must instead book the true gain.

    ``normal-sell`` is a control: a closed-by-selling market whose closing trade
    DOES carry ``effectiveRealizedPnl``. Recovery must NOT fire there — the
    side-correct SDK figure must be used verbatim (not the cash-flow number).
    """

    def __init__(self):
        self.orders = _StubResource(list=lambda params=None: {"orders": []})
        self.portfolio = _StubResource(positions=self._positions, activities=self._activities)
        self.account = _StubResource(balances=lambda: {"balances": []})
        self.events = _StubResource(retrieve_by_slug=lambda slug: {"event": {}})

    def _positions(self, params=None):
        # Both markets are fully closed -> no open positions.
        return {"positions": {}, "eof": True}

    def _activities(self, params=None):
        params = params or {}
        if "ACTIVITY_TYPE_TRADE" not in (params.get("types") or []):
            return {"activities": [], "eof": True}
        meta = {
            "title": "France vs. Morocco",
            "outcome": "Yes",
            "eventSlug": "fwc-fra-mar-halftime",
        }
        return {
            "activities": [
                # Closing PASSIVE sell: effectiveRealizedPnl ABSENT, realizedPnl
                # equals gross proceeds (800). isAggressor False -> our leg is the
                # passive one (side SELL).
                {
                    "type": "ACTIVITY_TYPE_TRADE",
                    "trade": {
                        "id": "h-sell",
                        "marketSlug": "halftime-fra",
                        "price": _amount("0.80"),
                        "qty": "1000",
                        "qtyDecimal": "1000",
                        "cost": _amount("800.00"),
                        "realizedPnl": _amount("800.00"),
                        "isAggressor": False,
                        "createTime": "2026-07-09T20:27:00Z",
                        "passiveExecution": {
                            "order": {"side": "ORDER_SIDE_SELL", "marketMetadata": meta},
                            "commissionNotionalCollected": _amount("0"),
                        },
                    },
                },
                # Opening buy: no realized P&L. isAggressor True -> our leg is the
                # aggressor one (side BUY).
                {
                    "type": "ACTIVITY_TYPE_TRADE",
                    "trade": {
                        "id": "h-buy",
                        "marketSlug": "halftime-fra",
                        "price": _amount("0.40"),
                        "qty": "1000",
                        "qtyDecimal": "1000",
                        "cost": _amount("400.00"),
                        "isAggressor": True,
                        "createTime": "2026-07-09T18:00:00Z",
                        "aggressorExecution": {
                            "order": {"side": "ORDER_SIDE_BUY", "marketMetadata": meta},
                            "commissionNotionalCollected": _amount("0"),
                        },
                    },
                },
                # Control market: closing sell WITH effectiveRealizedPnl (50),
                # whose basis-naive realizedPnl (70) differs. Recovery must not
                # fire; realized must read 50, not the cash-flow 70.
                {
                    "type": "ACTIVITY_TYPE_TRADE",
                    "trade": {
                        "id": "n-sell",
                        "marketSlug": "normal-sell",
                        "price": _amount("0.70"),
                        "qty": "100",
                        "qtyDecimal": "100",
                        "cost": _amount("70.00"),
                        "realizedPnl": _amount("70.00"),
                        "effectiveRealizedPnl": _amount("50.00"),
                        "isAggressor": True,
                        "createTime": "2026-07-08T12:00:00Z",
                        "aggressorExecution": {
                            "order": {
                                "side": "ORDER_SIDE_SELL",
                                "marketMetadata": {
                                    "title": "Normal",
                                    "outcome": "Yes",
                                    "eventSlug": "evt-normal",
                                },
                            }
                        },
                    },
                },
            ],
            "eof": True,
        }


def test_passive_fill_realized_recovery():
    dash = build_dashboard(_PassiveFillClient(), enrich_events=False)
    events_by_slug = {e.event_slug: e for e in dash.events}

    # Recovery market: without the fix (summing effectiveRealizedPnl) this reads
    # $0; the cash-flow recovery books the true gain 800 - 400 = 400.
    fra = events_by_slug["fwc-fra-mar-halftime"]
    halftime = next(c for c in fra.contracts if c.market_slug == "halftime-fra")
    assert abs(halftime.stats.realized_pnl - 400.0) < 1e-6
    assert abs(fra.stats.realized_pnl - 400.0) < 1e-6

    # Per-trade rows reconcile with the header: the closing sell carries the
    # gain, the opening buy carries none.
    sell = next(t for t in halftime.trades if t.id == "h-sell")
    buy = next(t for t in halftime.trades if t.id == "h-buy")
    assert abs(sell.realized_pnl - 400.0) < 1e-6
    assert abs(buy.realized_pnl - 0.0) < 1e-6
    assert abs(sum(t.realized_pnl for t in halftime.trades) - 400.0) < 1e-6

    # Control market: effectiveRealizedPnl present -> recovery must NOT fire, so
    # realized is the side-correct 50 (NOT the basis-naive / cash-flow 70).
    normal = events_by_slug["evt-normal"]
    normal_sell = next(c for c in normal.contracts if c.market_slug == "normal-sell")
    assert abs(normal_sell.stats.realized_pnl - 50.0) < 1e-6

    # Totals: 400 (recovered) + 50 (control) = 450.
    assert abs(dash.totals.realized_pnl - 450.0) < 1e-6

    print("test_passive_fill_realized_recovery: PASS")
    print(f"  halftime_realized={halftime.stats.realized_pnl:.2f} (was $0 before fix) "
          f"control_realized={normal_sell.stats.realized_pnl:.2f} "
          f"total={dash.totals.realized_pnl:.2f}")


class _EventCountingClient:
    """Stub that counts ``events.retrieve_by_slug`` calls, to prove event-title
    lookups are cached across dashboard builds rather than re-fetched."""

    def __init__(self):
        self.event_calls = 0
        self.orders = _StubResource(list=lambda params=None: {"orders": []})
        self.portfolio = _StubResource(positions=self._positions, activities=self._activities)
        self.account = _StubResource(balances=lambda: {"balances": []})
        self.events = _StubResource(retrieve_by_slug=self._event)

    def _positions(self, params=None):
        return {"positions": {}, "eof": True}

    def _activities(self, params=None):
        params = params or {}
        if "ACTIVITY_TYPE_TRADE" not in (params.get("types") or []):
            return {"activities": [], "eof": True}
        return {
            "activities": [
                {
                    "type": "ACTIVITY_TYPE_TRADE",
                    "trade": {
                        "id": "e1",
                        "marketSlug": "m-eventcache",
                        "price": _amount("0.50"),
                        "qty": "1",
                        "effectiveRealizedPnl": _amount("0"),
                        "createTime": "2026-01-01T00:00:00Z",
                        "aggressorExecution": {
                            "order": {
                                "marketMetadata": {
                                    "title": "T",
                                    "outcome": "Yes",
                                    "eventSlug": "evt-cache-xyz",
                                }
                            }
                        },
                    },
                }
            ],
            "eof": True,
        }

    def _event(self, slug):
        self.event_calls += 1
        return {"event": {"slug": slug, "title": "Cached Event Title"}}


def test_event_title_cache():
    from app.services.dashboard import _EVENT_TITLE_CACHE

    _EVENT_TITLE_CACHE.pop("evt-cache-xyz", None)
    client = _EventCountingClient()

    d1 = build_dashboard(client, enrich_events=True)
    assert client.event_calls == 1
    ev1 = {e.event_slug: e for e in d1.events}["evt-cache-xyz"]
    assert ev1.title == "Cached Event Title"

    # Second build reuses the cached title -> no additional upstream lookup.
    d2 = build_dashboard(client, enrich_events=True)
    assert client.event_calls == 1
    ev2 = {e.event_slug: e for e in d2.events}["evt-cache-xyz"]
    assert ev2.title == "Cached Event Title"

    print("test_event_title_cache: PASS")
    print(f"  event_calls after two builds = {client.event_calls} (cached)")


def test_upstream_retry_backoff():
    import httpx
    from polymarket_us import PolymarketUS
    from polymarket_us.errors import RateLimitError

    from app import client as client_mod

    def _rl(headers=None):
        req = httpx.Request("GET", "https://x/p")
        return RateLimitError(
            "rate limited",
            response=httpx.Response(429, request=req, headers=headers or {}),
        )

    orig_parent = PolymarketUS._request
    orig_sleep = client_mod.time.sleep
    sleeps: list[float] = []
    client_mod.time.sleep = lambda s: sleeps.append(s)
    try:
        # Case 1: two 429s then success -> exponential backoff, then returns.
        attempts = {"n": 0}

        def two_then_ok(self, method, path, **kwargs):
            attempts["n"] += 1
            if attempts["n"] <= 2:
                raise _rl()
            return {"ok": True}

        PolymarketUS._request = two_then_ok
        c = client_mod._RetryingPolymarketUS(max_retries=3, backoff_base=1.0, backoff_max=8.0)
        assert c._request("GET", "/p") == {"ok": True}
        assert attempts["n"] == 3
        assert sleeps == [1.0, 2.0]

        # Case 2: Retry-After header is honored over the computed backoff.
        sleeps.clear()
        attempts["n"] = 0

        def retry_after_then_ok(self, method, path, **kwargs):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise _rl(headers={"Retry-After": "5"})
            return {"ok": True}

        PolymarketUS._request = retry_after_then_ok
        c = client_mod._RetryingPolymarketUS(max_retries=3, backoff_base=1.0, backoff_max=8.0)
        assert c._request("GET", "/p") == {"ok": True}
        assert sleeps == [5.0]

        # Case 3: persistent 429 -> raises after max_retries (bounded).
        sleeps.clear()
        attempts["n"] = 0

        def always_rl(self, method, path, **kwargs):
            attempts["n"] += 1
            raise _rl()

        PolymarketUS._request = always_rl
        c = client_mod._RetryingPolymarketUS(max_retries=2, backoff_base=1.0, backoff_max=8.0)
        raised = False
        try:
            c._request("GET", "/p")
        except RateLimitError:
            raised = True
        assert raised
        assert attempts["n"] == 3  # initial attempt + 2 retries
        assert sleeps == [1.0, 2.0]
    finally:
        PolymarketUS._request = orig_parent
        client_mod.time.sleep = orig_sleep

    print("test_upstream_retry_backoff: PASS")


def test_dashboard_cache_and_stale():
    import httpx
    from polymarket_us.errors import RateLimitError

    from app.routers import dashboard as d
    from app.schemas import DashboardResponse

    d._cache.clear()
    calls = {"n": 0}
    good = DashboardResponse(generated_at="t1", credentials_configured=True)

    def fake_fetch(max_activities, enrich_events):
        calls["n"] += 1
        if calls["n"] == 1:
            return good
        req = httpx.Request("GET", "https://x")
        raise RateLimitError("rate limited", response=httpx.Response(429, request=req))

    orig = d._fetch
    d._fetch = fake_fetch
    try:
        # First call fetches upstream.
        assert d.get_dashboard(max_activities=0, enrich_events=True) is good
        assert calls["n"] == 1

        # Second call within TTL is served from cache (no upstream fetch).
        assert d.get_dashboard(max_activities=0, enrich_events=True) is good
        assert calls["n"] == 1

        # Expire the entry; the refetch now fails, so the stale-but-good
        # response is served instead of surfacing the rate-limit error.
        ts, val = d._cache[(0, True)]
        d._cache[(0, True)] = (ts - 10_000.0, val)
        assert d.get_dashboard(max_activities=0, enrich_events=True) is good
        assert calls["n"] == 2  # a refetch was attempted
    finally:
        d._fetch = orig
        d._cache.clear()

    print("test_dashboard_cache_and_stale: PASS")


class _OrphanSellClient:
    """A market with an understated closing sell but NO buys in the fetched
    window (e.g. truncated history, or shares acquired outside trading).

    Recovery detects the understated sell, but with no buys there is no cost
    basis: deriving realized would treat cost as zero and overstate the gain as
    the full sale proceeds. The guard must skip recovery and fall back to the
    SDK figure instead of fabricating that number.
    """

    def __init__(self):
        self.orders = _StubResource(list=lambda params=None: {"orders": []})
        self.portfolio = _StubResource(positions=self._positions, activities=self._activities)
        self.account = _StubResource(balances=lambda: {"balances": []})
        self.events = _StubResource(retrieve_by_slug=lambda slug: {"event": {}})

    def _positions(self, params=None):
        return {"positions": {}, "eof": True}

    def _activities(self, params=None):
        params = params or {}
        if "ACTIVITY_TYPE_TRADE" not in (params.get("types") or []):
            return {"activities": [], "eof": True}
        meta = {"title": "Orphan", "outcome": "Yes", "eventSlug": "evt-orphan"}
        return {
            "activities": [
                {
                    "type": "ACTIVITY_TYPE_TRADE",
                    "trade": {
                        "id": "o-sell",
                        "marketSlug": "orphan-sell",
                        "price": _amount("0.80"),
                        "qty": "1000",
                        "qtyDecimal": "1000",
                        "cost": _amount("800.00"),
                        "realizedPnl": _amount("800.00"),
                        "isAggressor": False,
                        "createTime": "2026-07-09T20:00:00Z",
                        "passiveExecution": {
                            "order": {"side": "ORDER_SIDE_SELL", "marketMetadata": meta},
                            "commissionNotionalCollected": _amount("0"),
                        },
                    },
                }
            ],
            "eof": True,
        }


def test_recovery_skipped_when_book_not_flat():
    dash = build_dashboard(_OrphanSellClient(), enrich_events=False)
    ev = {e.event_slug: e for e in dash.events}["evt-orphan"]
    m = next(c for c in ev.contracts if c.market_slug == "orphan-sell")
    # No buys -> no cost basis -> recovery skipped. Realized falls back to the
    # SDK figure (0 here) rather than the overstated 800 of raw proceeds.
    assert abs(m.stats.realized_pnl - 0.0) < 1e-6

    print("test_recovery_skipped_when_book_not_flat: PASS")


class _FlatBookCorruptClient:
    """Reproduces the Tomic-vs-Johnson bug: a flat (closed-by-selling) book whose
    per-fill ``costBasis`` is corrupted upstream, so the SDK's
    ``effectiveRealizedPnl`` is PRESENT but wrong and sums to a loss on a book
    that actually made money.

    Bought 10,000 @ 0.45 (cost 4,500) then sold 10,000 @ 0.55 (cash 5,500): a
    clean +1,000 gain. But the API assigns 4,000 of cost basis to each 5,000-lot
    sell (8,000 total vs the real 4,500), so each sell's ``effectiveRealizedPnl``
    reads 2,750 − 4,000 = −1,250 and the naive sum is −2,500. The grouper must
    book the cash-flow truth (+1,000), not the corrupted SDK sum.

    Unlike the passive-fill case, ``effectiveRealizedPnl`` is present here, so the
    fix cannot key off its absence — it keys off the book being flat.
    """

    def __init__(self):
        self.orders = _StubResource(list=lambda params=None: {"orders": []})
        self.portfolio = _StubResource(positions=self._positions, activities=self._activities)
        self.account = _StubResource(balances=lambda: {"balances": []})
        self.events = _StubResource(retrieve_by_slug=lambda slug: {"event": {}})

    def _positions(self, params=None):
        # Fully closed by selling -> no open position.
        return {"positions": {}, "eof": True}

    def _activities(self, params=None):
        params = params or {}
        if "ACTIVITY_TYPE_TRADE" not in (params.get("types") or []):
            return {"activities": [], "eof": True}
        meta = {"title": "Tomic vs Johnson", "outcome": "Tomic", "eventSlug": "evt-flatcorrupt"}

        def _sell(i: int) -> dict:
            return {
                "type": "ACTIVITY_TYPE_TRADE",
                "trade": {
                    "id": f"c-sell{i}",
                    "marketSlug": "flat-corrupt",
                    "price": _amount("0.55"),
                    "qty": "5000",
                    "qtyDecimal": "5000",
                    "cost": _amount("2750.00"),
                    # Corrupted upstream basis (4000 vs the real 2250) -> a
                    # spurious per-fill loss the naive sum would trust.
                    "costBasis": _amount("4000.00"),
                    "realizedPnl": _amount("-1250.00"),
                    "effectiveRealizedPnl": _amount("-1250.00"),
                    "isAggressor": False,
                    "createTime": f"2026-07-19T01:0{i}:00Z",
                    "passiveExecution": {
                        "order": {"side": "ORDER_SIDE_SELL", "marketMetadata": meta},
                        "commissionNotionalCollected": _amount("0"),
                    },
                },
            }

        return {
            "activities": [
                _sell(1),
                _sell(2),
                # Opening buy: 10,000 @ 0.45.
                {
                    "type": "ACTIVITY_TYPE_TRADE",
                    "trade": {
                        "id": "c-buy",
                        "marketSlug": "flat-corrupt",
                        "price": _amount("0.45"),
                        "qty": "10000",
                        "qtyDecimal": "10000",
                        "cost": _amount("4500.00"),
                        "isAggressor": True,
                        "createTime": "2026-07-19T00:00:00Z",
                        "aggressorExecution": {
                            "order": {"side": "ORDER_SIDE_BUY", "marketMetadata": meta},
                            "commissionNotionalCollected": _amount("0"),
                        },
                    },
                },
            ],
            "eof": True,
        }


def test_flat_book_costbasis_corruption():
    dash = build_dashboard(_FlatBookCorruptClient(), enrich_events=False)
    ev = {e.event_slug: e for e in dash.events}["evt-flatcorrupt"]
    m = next(c for c in ev.contracts if c.market_slug == "flat-corrupt")

    # Cash-flow truth: 5,500 in − 4,500 out = +1,000, NOT the SDK sum of −2,500.
    assert abs(m.stats.realized_pnl - 1000.0) < 1e-6
    assert abs(ev.stats.realized_pnl - 1000.0) < 1e-6

    # Per-trade rows reconcile with the header: each 5,000 sell books its gain
    # over the 0.45 average cost (2,750 − 2,250 = 500); the buy books nothing.
    sells = [t for t in m.trades if t.id.startswith("c-sell")]
    buy = next(t for t in m.trades if t.id == "c-buy")
    assert len(sells) == 2
    assert all(abs(s.realized_pnl - 500.0) < 1e-6 for s in sells)
    assert abs(buy.realized_pnl - 0.0) < 1e-6
    assert abs(sum(t.realized_pnl for t in m.trades) - 1000.0) < 1e-6

    print("test_flat_book_costbasis_corruption: PASS")
    print(f"  realized={m.stats.realized_pnl:.2f} (naive SDK sum was -2500.00)")


class _ShortRoundTripClient:
    """Lakers-vs-Warriors shape: a position ENTERED by selling (chronologically
    first) and EXITED by buying it back cheaper — a real profit that a naive
    ``sell_cash − buy_cash`` sign-flips into a loss.

    The account sold NO at $0.67 to open (long-YES-equivalent at $0.33) then
    bought NO back at $0.30 to close. Booked by entry-vs-exit *order*, realized is
    +$222; keyed off BUY/SELL side it would wrongly read −$222. Fills are returned
    newest-first (as the real feed does) so the test also exercises the
    timestamp sort.
    """

    def __init__(self):
        self.orders = _StubResource(list=lambda params=None: {"orders": []})
        self.portfolio = _StubResource(positions=self._positions, activities=self._activities)
        self.account = _StubResource(balances=lambda: {"balances": []})
        self.events = _StubResource(retrieve_by_slug=lambda slug: {"event": {}})

    def _positions(self, params=None):
        return {"positions": {}, "eof": True}  # closed by trading -> no open position

    def _activities(self, params=None):
        params = params or {}
        if "ACTIVITY_TYPE_TRADE" not in (params.get("types") or []):
            return {"activities": [], "eof": True}
        meta = {"title": "LAL vs GSW", "outcome": "Warriors", "eventSlug": "evt-lakers"}
        return {
            "activities": [
                # EXIT (later): buy NO back at 0.30 -> YES-equiv proceeds 600*0.70.
                {
                    "type": "ACTIVITY_TYPE_TRADE",
                    "trade": {
                        "id": "exit",
                        "marketSlug": "lakers",
                        "price": _amount("0.30"),
                        "qty": "600",
                        "qtyDecimal": "600",
                        "cost": _amount("420.00"),
                        "effectiveRealizedPnl": _amount("222.00"),
                        "isAggressor": True,
                        "createTime": "2026-07-19T02:03:40Z",
                        "aggressorExecution": {
                            "order": {
                                "side": "ORDER_SIDE_BUY",
                                "outcomeSide": "OUTCOME_SIDE_NO",
                                "marketMetadata": meta,
                            }
                        },
                    },
                },
                # ENTRY (earlier): sell NO at 0.67 -> YES-equiv basis 600*0.33.
                {
                    "type": "ACTIVITY_TYPE_TRADE",
                    "trade": {
                        "id": "entry",
                        "marketSlug": "lakers",
                        "price": _amount("0.67"),
                        "qty": "600",
                        "qtyDecimal": "600",
                        "cost": _amount("198.00"),
                        "isAggressor": True,
                        "createTime": "2026-07-19T01:53:09Z",
                        "aggressorExecution": {
                            "order": {
                                "side": "ORDER_SIDE_SELL",
                                "outcomeSide": "OUTCOME_SIDE_NO",
                                "marketMetadata": meta,
                            }
                        },
                    },
                },
            ],
            "eof": True,
        }


def test_short_round_trip_realized_by_timestamp():
    dash = build_dashboard(_ShortRoundTripClient(), enrich_events=False)
    ev = {e.event_slug: e for e in dash.events}["evt-lakers"]
    m = next(c for c in ev.contracts if c.market_slug == "lakers")

    # Profit, not loss: proceeds 420 (exit) − basis 198 (entry) = +222.
    assert abs(m.stats.realized_pnl - 222.0) < 1e-6, m.stats.realized_pnl

    # P&L is booked on the exit (the later fill); the entry shows none.
    entry = next(t for t in m.trades if t.id == "entry")
    exit_ = next(t for t in m.trades if t.id == "exit")
    assert abs(entry.realized_pnl - 0.0) < 1e-6
    assert abs(exit_.realized_pnl - 222.0) < 1e-6
    assert abs(sum(t.realized_pnl for t in m.trades) - 222.0) < 1e-6

    print("test_short_round_trip_realized_by_timestamp: PASS")
    print(f"  realized={m.stats.realized_pnl:.2f} (side-based sell-minus-buy would be -222.00)")


def test_account_realized_pnl_from_balance_identity():
    """Headline realized P&L comes from cash, not the activity sum.

    Mirrors a real live account: the reported balance is inflated by an
    advanced-credited *pending* deposit that has not settled, and the user has
    withdrawn more than deposited. Realized must be settled equity (balance minus
    the pending-deposit credit) minus net external capital moved in, so withdrawn
    profits are counted and promotional/transfer credits are excluded.
    """
    from app.schemas import BalanceSummary
    from app.services.dashboard import _account_realized_pnl

    balances = [BalanceSummary(currency="USD", current_balance=18026.20575)]

    def _cash(atype: str, status: str, amount: str) -> dict:
        return {
            "type": atype,
            "accountBalanceChange": {
                "status": f"ACCOUNT_BALANCE_CHANGE_STATUS_{status}",
                "amount": _amount(amount),
            },
        }

    cash = [
        _cash("ACTIVITY_TYPE_ACCOUNT_DEPOSIT", "COMPLETED", "11850.00"),
        _cash("ACTIVITY_TYPE_ACCOUNT_DEPOSIT", "PENDING", "11500.00"),  # advanced credit
        _cash("ACTIVITY_TYPE_ACCOUNT_DEPOSIT", "REJECTED", "10000.00"),  # ignored
        _cash("ACTIVITY_TYPE_ACCOUNT_WITHDRAWAL", "COMPLETED", "17919.81"),
        _cash("ACTIVITY_TYPE_ACCOUNT_WITHDRAWAL", "PENDING", "6526.20"),  # still in balance
        _cash("ACTIVITY_TYPE_REFERRAL_BONUS", "COMPLETED", "20.00"),  # non-trading
        _cash("ACTIVITY_TYPE_TRANSFER", "COMPLETED", "114.23"),  # non-trading
    ]

    pnl = _account_realized_pnl(balances, cash)
    # settled_equity = 18026.21 - 11500 (pending) = 6526.21
    # net_external    = 11850 + (20 + 114.23) - 17919.81 = -5935.58
    # realized        = 6526.21 - (-5935.58) = 12461.79
    assert abs(pnl - 12461.79) < 0.01, pnl

    # Without discounting the advanced pending-deposit credit, the balance reads
    # inflated by exactly that credit ($11,500) — the bug this guards against.
    without_pending_deposit = [
        c for c in cash if c["type"] != "ACTIVITY_TYPE_ACCOUNT_DEPOSIT"
        or c["accountBalanceChange"]["status"] != "ACCOUNT_BALANCE_CHANGE_STATUS_PENDING"
    ]
    assert abs(_account_realized_pnl(balances, without_pending_deposit) - 23961.79) < 0.01

    print("test_account_realized_pnl_from_balance_identity: PASS")
    print(f"  account_realized_pnl={pnl:.2f}")


if __name__ == "__main__":
    test_grouping()
    test_activities_paginate_to_completion()
    test_max_activities_cap_still_truncates()
    test_passive_fill_realized_recovery()
    test_recovery_skipped_when_book_not_flat()
    test_flat_book_costbasis_corruption()
    test_short_round_trip_realized_by_timestamp()
    test_account_realized_pnl_from_balance_identity()
    test_event_title_cache()
    test_upstream_retry_backoff()
    test_dashboard_cache_and_stale()
