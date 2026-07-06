import { titleCase } from "@/lib/format";

export function SideBadge({ side }: { side: string | null }) {
  if (!side) return null;
  const isBuy = side === "ORDER_SIDE_BUY";
  const isSell = side === "ORDER_SIDE_SELL";
  const label = isBuy ? "BUY" : isSell ? "SELL" : side;
  const cls = isBuy
    ? "bg-buy/15 text-buy border-buy/30"
    : isSell
      ? "bg-sell/15 text-sell border-sell/30"
      : "bg-surface-600 text-gray-300 border-surface-600";
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-semibold tracking-wide ${cls}`}
    >
      {label}
    </span>
  );
}

export function StateBadge({ label }: { label: string | null }) {
  if (!label) return null;
  const done = /fill/.test(label) && !/partial/.test(label);
  const cancelled = /cancel|reject|expire/.test(label);
  const cls = done
    ? "bg-buy/10 text-buy border-buy/20"
    : cancelled
      ? "bg-sell/10 text-sell border-sell/20"
      : "bg-accent/10 text-accent-soft border-accent/20";
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium ${cls}`}
    >
      {titleCase(label)}
    </span>
  );
}
