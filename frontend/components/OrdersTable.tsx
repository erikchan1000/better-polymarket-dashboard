import type { OrderSummary } from "@/lib/types";
import { num, price, usd, timeAgo } from "@/lib/format";
import { SideBadge, StateBadge } from "./Badge";

export function OrdersTable({ orders }: { orders: OrderSummary[] }) {
  if (orders.length === 0) {
    return <div className="px-4 py-3 text-xs text-gray-500">No open orders.</div>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead className="text-[10px] uppercase tracking-wider text-gray-500">
          <tr className="border-b border-surface-700">
            <th className="px-4 py-2 font-medium">Side</th>
            <th className="px-4 py-2 font-medium">Price</th>
            <th className="px-4 py-2 text-right font-medium">Filled / Qty</th>
            <th className="px-4 py-2 text-right font-medium">Open notional</th>
            <th className="px-4 py-2 font-medium">State</th>
            <th className="px-4 py-2 text-right font-medium">Age</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {orders.map((o) => (
            <tr key={o.id} className="border-b border-surface-800 last:border-0">
              <td className="px-4 py-2">
                <SideBadge side={o.side} />
              </td>
              <td className="px-4 py-2 font-mono text-gray-200">{price(o.price)}</td>
              <td className="px-4 py-2 text-right text-gray-300">
                {num(o.cum_quantity)} / {num(o.quantity)}
              </td>
              <td className="px-4 py-2 text-right text-gray-200">{usd(o.notional)}</td>
              <td className="px-4 py-2">
                <StateBadge label={o.state_label} />
              </td>
              <td className="px-4 py-2 text-right text-gray-500">{timeAgo(o.create_time)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
