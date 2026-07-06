"use client";

import { useState } from "react";
import type { ContractGroup } from "@/lib/types";
import { num, usd, signedUsd, pnlColor } from "@/lib/format";
import { OrdersTable } from "./OrdersTable";
import { TradesTable } from "./TradesTable";
import { ResolutionsTable } from "./ResolutionsTable";

function Metric({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className="min-w-[84px]">
      <div className="text-[10px] uppercase tracking-wider text-gray-500">{label}</div>
      <div className={`text-sm font-semibold tabular-nums ${className ?? "text-gray-200"}`}>
        {value}
      </div>
    </div>
  );
}

export function ContractCard({ contract }: { contract: ContractGroup }) {
  const { stats } = contract;
  const hasDetail =
    contract.orders.length > 0 ||
    contract.trades.length > 0 ||
    contract.resolutions.length > 0;
  const [open, setOpen] = useState(false);

  // A market with no open orders and no live position but a settlement record
  // has resolved to its final payout.
  const isResolved =
    contract.resolutions.length > 0 &&
    contract.orders.length === 0 &&
    stats.net_position === 0;

  const label = contract.outcome || contract.title || contract.market_slug;

  return (
    <div className="rounded-lg border border-surface-700 bg-surface-900/50">
      <button
        type="button"
        disabled={!hasDetail}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-4 px-4 py-3 text-left disabled:cursor-default"
      >
        <div className="flex min-w-0 flex-1 items-center gap-3">
          {contract.icon ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={contract.icon}
              alt=""
              className="h-6 w-6 shrink-0 rounded-full object-cover"
            />
          ) : (
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-700 text-[10px] font-bold text-gray-400">
              {label.slice(0, 1).toUpperCase()}
            </div>
          )}
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="truncate text-sm font-medium text-gray-100">{label}</span>
              {isResolved ? (
                <span className="inline-flex shrink-0 items-center rounded border border-surface-600 bg-surface-700 px-1.5 py-0.5 text-[10px] font-medium text-gray-400">
                  Resolved
                </span>
              ) : null}
            </div>
            <div className="truncate font-mono text-[11px] text-gray-500">
              {contract.market_slug}
            </div>
          </div>
        </div>

        <div className="hidden items-center gap-6 sm:flex">
          <Metric label="Net pos" value={num(stats.net_position)} />
          <Metric label="Value" value={usd(stats.position_value)} />
          <Metric
            label="Open ord"
            value={String(stats.open_order_count)}
            className={stats.open_order_count > 0 ? "text-accent-soft" : "text-gray-500"}
          />
          <Metric
            label="Realized"
            value={signedUsd(stats.realized_pnl)}
            className={pnlColor(stats.realized_pnl)}
          />
        </div>

        {hasDetail ? (
          <svg
            className={`h-4 w-4 shrink-0 text-gray-500 transition-transform ${open ? "rotate-180" : ""}`}
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path
              fillRule="evenodd"
              d="M5.23 7.21a.75.75 0 011.06.02L10 11.06l3.71-3.83a.75.75 0 111.08 1.04l-4.25 4.39a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z"
              clipRule="evenodd"
            />
          </svg>
        ) : (
          <span className="w-4" />
        )}
      </button>

      {/* Mobile metrics row */}
      <div className="flex flex-wrap items-center gap-4 px-4 pb-3 sm:hidden">
        <Metric label="Net pos" value={num(stats.net_position)} />
        <Metric label="Value" value={usd(stats.position_value)} />
        <Metric label="Open ord" value={String(stats.open_order_count)} />
        <Metric
          label="Realized"
          value={signedUsd(stats.realized_pnl)}
          className={pnlColor(stats.realized_pnl)}
        />
      </div>

      {open && hasDetail ? (
        <div className="border-t border-surface-700">
          {contract.orders.length > 0 ? (
            <div>
              <div className="px-4 pt-3 text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                Open orders ({contract.orders.length})
              </div>
              <OrdersTable orders={contract.orders} />
            </div>
          ) : null}
          {contract.trades.length > 0 ? (
            <div className="border-t border-surface-800">
              <div className="px-4 pt-3 text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                Recent trades ({contract.trades.length})
              </div>
              <TradesTable trades={contract.trades} />
            </div>
          ) : null}
          {contract.resolutions.length > 0 ? (
            <div className="border-t border-surface-800">
              <div className="px-4 pt-3 text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                Resolutions ({contract.resolutions.length})
              </div>
              <ResolutionsTable resolutions={contract.resolutions} />
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
