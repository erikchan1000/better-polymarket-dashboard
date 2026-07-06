import type { ResolutionSummary } from "@/lib/types";
import { num, signedUsd, usd, pnlColor, timeAgo, titleCase } from "@/lib/format";

export function ResolutionsTable({ resolutions }: { resolutions: ResolutionSummary[] }) {
  if (resolutions.length === 0) {
    return <div className="px-4 py-3 text-xs text-gray-500">No resolutions.</div>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead className="text-[10px] uppercase tracking-wider text-gray-500">
          <tr className="border-b border-surface-700">
            <th className="px-4 py-2 font-medium">Side</th>
            <th className="px-4 py-2 text-right font-medium">Qty</th>
            <th className="px-4 py-2 text-right font-medium">Cost</th>
            <th className="px-4 py-2 text-right font-medium">Payout</th>
            <th className="px-4 py-2 text-right font-medium">Realized P&L</th>
            <th className="px-4 py-2 text-right font-medium">When</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {resolutions.map((r, i) => (
            <tr key={`${r.market_slug}-${i}`} className="border-b border-surface-800 last:border-0">
              <td className="px-4 py-2 text-gray-300">{titleCase(r.side_label) || "—"}</td>
              <td className="px-4 py-2 text-right text-gray-300">{num(r.net_position)}</td>
              <td className="px-4 py-2 text-right text-gray-300">{usd(r.cost)}</td>
              <td className="px-4 py-2 text-right text-gray-300">{usd(r.payout)}</td>
              <td className={`px-4 py-2 text-right font-medium ${pnlColor(r.realized_pnl)}`}>
                {signedUsd(r.realized_pnl)}
              </td>
              <td className="px-4 py-2 text-right text-gray-500">{timeAgo(r.resolved_time)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
