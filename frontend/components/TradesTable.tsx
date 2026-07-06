import type { TradeSummary } from "@/lib/types";
import { num, price, signedUsd, usd, pnlColor, timeAgo } from "@/lib/format";

export function TradesTable({ trades }: { trades: TradeSummary[] }) {
  if (trades.length === 0) {
    return <div className="px-4 py-3 text-xs text-gray-500">No recent trades.</div>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead className="text-[10px] uppercase tracking-wider text-gray-500">
          <tr className="border-b border-surface-700">
            <th className="px-4 py-2 font-medium">Price</th>
            <th className="px-4 py-2 text-right font-medium">Qty</th>
            <th className="px-4 py-2 text-right font-medium">Cost basis</th>
            <th className="px-4 py-2 text-right font-medium">Realized P&L</th>
            <th className="px-4 py-2 text-right font-medium">When</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {trades.map((t) => (
            <tr key={t.id} className="border-b border-surface-800 last:border-0">
              <td className="px-4 py-2 font-mono text-gray-200">{price(t.price)}</td>
              <td className="px-4 py-2 text-right text-gray-300">{num(t.qty)}</td>
              <td className="px-4 py-2 text-right text-gray-300">{usd(t.cost_basis)}</td>
              <td className={`px-4 py-2 text-right font-medium ${pnlColor(t.realized_pnl)}`}>
                {signedUsd(t.realized_pnl)}
              </td>
              <td className="px-4 py-2 text-right text-gray-500">{timeAgo(t.create_time)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
