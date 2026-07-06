"use client";

import type { EventGroup } from "@/lib/types";
import { usd, signedUsd, pnlColor } from "@/lib/format";
import { ContractCard } from "./ContractCard";

function HeaderStat({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className="text-right">
      <div className="text-[10px] uppercase tracking-wider text-gray-500">{label}</div>
      <div className={`text-sm font-semibold tabular-nums ${className ?? "text-gray-200"}`}>
        {value}
      </div>
    </div>
  );
}

export function EventCard({
  event,
  open,
  onToggleOpen,
}: {
  event: EventGroup;
  open: boolean;
  onToggleOpen: () => void;
}) {
  const { stats } = event;

  return (
    <section className="overflow-hidden rounded-2xl border border-surface-700 bg-surface-800/40">
      <button
        type="button"
        onClick={onToggleOpen}
        className="flex w-full items-center gap-4 px-5 py-4 text-left hover:bg-surface-800/60"
      >
        <svg
          className={`h-4 w-4 shrink-0 text-gray-500 transition-transform ${open ? "" : "-rotate-90"}`}
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 11.06l3.71-3.83a.75.75 0 111.08 1.04l-4.25 4.39a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-base font-semibold text-gray-50">{event.title}</h2>
          <div className="truncate font-mono text-[11px] text-gray-500">{event.event_slug}</div>
        </div>

        <div className="flex items-center gap-5">
          <HeaderStat label="Contracts" value={String(stats.contract_count)} />
          <HeaderStat
            label="Open ord"
            value={String(stats.open_order_count)}
            className={stats.open_order_count > 0 ? "text-accent-soft" : "text-gray-400"}
          />
          <HeaderStat label="Open notional" value={usd(stats.open_order_notional)} />
          <HeaderStat label="Value" value={usd(stats.position_value)} />
          <HeaderStat
            label="Realized"
            value={signedUsd(stats.realized_pnl)}
            className={pnlColor(stats.realized_pnl)}
          />
        </div>
      </button>

      {open ? (
        <div className="space-y-2 border-t border-surface-700 bg-surface-900/30 p-3">
          {event.contracts.map((c) => (
            <ContractCard key={c.market_slug} contract={c} />
          ))}
        </div>
      ) : null}
    </section>
  );
}
