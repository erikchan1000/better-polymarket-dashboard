"use client";

import { useState } from "react";
import type { BalanceSummary, PendingCashFlow, PendingCashSummary } from "@/lib/types";
import { usd, signedUsd, timeAgo, titleCase } from "@/lib/format";

function Row({
  label,
  value,
  valueClassName,
  sub,
}: {
  label: string;
  value: string;
  valueClassName?: string;
  sub?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <span className="text-sm text-gray-400">
        {label}
        {sub ? <span className="ml-2 text-xs text-gray-600">{sub}</span> : null}
      </span>
      <span className={`text-sm font-semibold tabular-nums ${valueClassName ?? "text-gray-200"}`}>
        {value}
      </span>
    </div>
  );
}

function PendingItem({ flow }: { flow: PendingCashFlow }) {
  const sign = flow.direction === "outgoing" ? -flow.amount : flow.amount;
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-2">
      <div className="min-w-0">
        <div className="truncate text-xs text-gray-300">
          {flow.description || titleCase(flow.type_label) || "Cash movement"}
        </div>
        <div className="text-[11px] text-gray-600">
          {titleCase(flow.status_label) || "Pending"} · requested {timeAgo(flow.create_time)}
        </div>
      </div>
      <span
        className={`shrink-0 text-sm font-medium tabular-nums ${
          flow.direction === "outgoing" ? "text-sell" : "text-buy"
        }`}
      >
        {signedUsd(sign)}
      </span>
    </div>
  );
}

export function BalanceBreakdown({
  balance,
  pending,
}: {
  balance: BalanceSummary | undefined;
  pending: PendingCashSummary;
}) {
  const [open, setOpen] = useState(false);

  if (!balance) return null;

  const total = balance.current_balance ?? 0;
  const available = balance.buying_power ?? 0;
  const pendingW = pending.total_withdrawals;
  const pendingD = pending.total_deposits;
  // Anything between available and total not explained by pending withdrawals
  // (e.g. cash locked in open orders, unsettled funds, reservations).
  const otherHolds = total - available - pendingW;
  const hasOther = Math.abs(otherHolds) > 0.01;

  const gap = Math.abs(total - available) > 0.01;
  const hasPending = pending.withdrawals.length > 0 || pending.deposits.length > 0;

  // Nothing to explain: available already equals the balance and no pending flows.
  if (!gap && !hasPending) return null;

  return (
    <section className="overflow-hidden rounded-2xl border border-surface-700 bg-surface-800/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
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
          <h2 className="text-base font-semibold text-gray-50">Balance breakdown</h2>
          <div className="truncate text-[11px] text-gray-500">
            {usd(available)} available of {usd(total)} balance
            {pendingW > 0 ? ` · ${usd(pendingW)} pending withdrawal${pending.withdrawals.length === 1 ? "" : "s"}` : ""}
          </div>
        </div>
        {pendingW > 0 ? (
          <span className="shrink-0 rounded border border-sell/30 bg-sell/10 px-2 py-0.5 text-xs font-medium text-sell">
            −{usd(pendingW)}
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="border-t border-surface-700 bg-surface-900/30 px-5 py-4">
          {/* Reconciliation: available + pending withdrawals (+ other holds) = total */}
          <div className="rounded-lg border border-surface-700 bg-surface-900/40 px-4 py-2">
            <Row label="Available (buying power)" value={usd(available)} valueClassName="text-gray-100" />
            {pendingW > 0 ? (
              <Row
                label="Pending withdrawals"
                sub={`${pending.withdrawals.length} request${pending.withdrawals.length === 1 ? "" : "s"}`}
                value={signedUsd(pendingW)}
                valueClassName="text-sell"
              />
            ) : null}
            {hasOther ? (
              <Row
                label="Other holds"
                sub="open orders / unsettled / reserved"
                value={signedUsd(otherHolds)}
                valueClassName="text-gray-300"
              />
            ) : null}
            <div className="mt-1 border-t border-surface-700 pt-1">
              <Row label="Total balance" value={usd(total)} valueClassName="text-gray-100" />
            </div>
          </div>

          {pending.withdrawals.length > 0 ? (
            <div className="mt-4">
              <div className="px-1 pb-1 text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                Pending withdrawals ({pending.withdrawals.length})
              </div>
              <div className="divide-y divide-surface-800 rounded-lg border border-surface-700 bg-surface-900/40">
                {pending.withdrawals.map((f, i) => (
                  <PendingItem key={f.transaction_id ?? `w-${i}`} flow={f} />
                ))}
              </div>
            </div>
          ) : null}

          {pending.deposits.length > 0 ? (
            <div className="mt-4">
              <div className="px-1 pb-1 text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                Incoming — pending deposits ({pending.deposits.length})
              </div>
              <p className="px-1 pb-1.5 text-[11px] text-gray-600">
                Not yet in your balance; adds {usd(pendingD)} once cleared.
              </p>
              <div className="divide-y divide-surface-800 rounded-lg border border-surface-700 bg-surface-900/40">
                {pending.deposits.map((f, i) => (
                  <PendingItem key={f.transaction_id ?? `d-${i}`} flow={f} />
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
