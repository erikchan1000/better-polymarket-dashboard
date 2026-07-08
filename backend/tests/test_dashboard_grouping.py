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


if __name__ == "__main__":
    test_grouping()
    test_activities_paginate_to_completion()
    test_max_activities_cap_still_truncates()
