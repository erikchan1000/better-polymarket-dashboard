import type { BalanceSummary, DashboardTotals } from "@/lib/types";
import { StatCard } from "./StatCard";
import { usd, signedUsd, pnlColor } from "@/lib/format";

export function SummaryBar({
  totals,
  balances,
}: {
  totals: DashboardTotals;
  balances: BalanceSummary[];
}) {
  const primary = balances[0];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <StatCard
        label="Buying power"
        value={usd(primary?.buying_power ?? null)}
        hint={primary ? `of ${usd(primary.current_balance ?? null)} balance` : "No balance data"}
      />
      <StatCard
        label="Position value"
        value={usd(totals.position_value)}
        hint={`Cost ${usd(totals.position_cost)}`}
      />
      <StatCard
        label="Realized P&L"
        value={signedUsd(totals.account_realized_pnl)}
        valueClassName={pnlColor(totals.account_realized_pnl)}
        hint="from settled balance"
      />
      <StatCard
        label="Open orders"
        value={String(totals.open_order_count)}
        hint={`${usd(totals.open_order_notional)} notional`}
      />
      <StatCard
        label="Events"
        value={String(totals.event_count)}
        hint={`${totals.contract_count} contracts`}
      />
      <StatCard label="Trades" value={String(totals.trade_count)} hint="recent window" />
    </div>
  );
}
