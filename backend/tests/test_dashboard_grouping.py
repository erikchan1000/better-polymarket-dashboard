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
                        "realizedPnl": _amount("5.00"),
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
                        "realizedPnl": _amount("12.00"),
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
                # A cash flow that must be ignored by PnL rollups entirely.
                {
                    "type": "ACTIVITY_TYPE_ACCOUNT_WITHDRAWAL",
                    "accountBalanceChange": {"amount": _amount("1950.59")},
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

    # Four event groups: the MLB game, the resolved World Cup market, the
    # trade-only USA match, plus "Ungrouped markets" for lonely-market.
    assert dash.totals.event_count == 4
    assert dash.totals.contract_count == 5
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

    # Dashboard totals: yankees 5.00 + brazil 685.00 + usa 12.00 = 702.00. The
    # 1950.59 withdrawal is a cash flow and must not leak into realized PnL.
    assert abs(dash.totals.realized_pnl - 702.0) < 1e-6
    assert dash.totals.resolution_count == 1
    assert dash.totals.trade_count == 2

    # Balances flow through.
    assert dash.balances[0].current_balance == 1000.0
    assert dash.credentials_configured is True

    print("test_grouping: PASS")
    print(f"  events={dash.totals.event_count} contracts={dash.totals.contract_count} "
          f"open_orders={dash.totals.open_order_count} "
          f"open_notional={dash.totals.open_order_notional:.2f} "
          f"realized={dash.totals.realized_pnl:.2f} "
          f"resolutions={dash.totals.resolution_count}")


if __name__ == "__main__":
    test_grouping()
