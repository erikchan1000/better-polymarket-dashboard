"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DashboardResponse, EventGroup } from "@/lib/types";
import { fetchDashboard, DashboardApiError, API_BASE_URL } from "@/lib/api";
import { formatTime, timeAgo } from "@/lib/format";
import { SummaryBar } from "./SummaryBar";
import { EventCard } from "./EventCard";

const REFRESH_INTERVAL_MS = 15_000;

export function Dashboard() {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<DashboardApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const [autoRefresh, setAutoRefresh] = useState(true);
  const [query, setQuery] = useState("");
  const [onlyOpenOrders, setOnlyOpenOrders] = useState(false);
  // Events are open by default; we track the slugs the user has explicitly
  // collapsed. A slug is open iff it is NOT in this set.
  const [collapsedEvents, setCollapsedEvents] = useState<Set<string>>(new Set());

  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setRefreshing(true);
    try {
      const result = await fetchDashboard({ signal: controller.signal });
      setData(result);
      setError(null);
      setLastUpdated(new Date());
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      if (e instanceof DashboardApiError) {
        setError(e);
      } else {
        setError(new DashboardApiError({ kind: "unknown", message: String(e) }));
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
    return () => abortRef.current?.abort();
  }, [load]);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(() => void load(), REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [autoRefresh, load]);

  const filteredEvents = useMemo<EventGroup[]>(() => {
    if (!data) return [];
    const q = query.trim().toLowerCase();
    return data.events
      .map((event) => {
        const contracts = event.contracts.filter((c) => {
          if (onlyOpenOrders && c.stats.open_order_count === 0) return false;
          if (!q) return true;
          const haystack = [event.title, event.event_slug, c.title, c.outcome, c.market_slug]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();
          return haystack.includes(q);
        });
        return { ...event, contracts };
      })
      .filter((event) => {
        if (event.contracts.length === 0) return false;
        if (onlyOpenOrders && event.stats.open_order_count === 0) return false;
        return true;
      });
  }, [data, query, onlyOpenOrders]);

  const toggleEvent = useCallback((slug: string) => {
    setCollapsedEvents((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      return next;
    });
  }, []);

  const expandAll = useCallback(() => setCollapsedEvents(new Set()), []);
  const collapseAll = useCallback(
    () => setCollapsedEvents(new Set(filteredEvents.map((e) => e.event_slug))),
    [filteredEvents],
  );

  // Are any / all of the currently visible events collapsed? Drives which
  // control is disabled so the buttons reflect the actual state.
  const anyOpen = filteredEvents.some((e) => !collapsedEvents.has(e.event_slug));
  const anyCollapsed = filteredEvents.some((e) => collapsedEvents.has(e.event_slug));

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-50">
            Polymarket US Dashboard
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Orders, positions &amp; trades grouped by event and contract.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated ? (
            <span className="text-xs text-gray-500" title={formatTime(lastUpdated.toISOString())}>
              Updated {timeAgo(lastUpdated.toISOString())}
            </span>
          ) : null}
          <label className="flex cursor-pointer items-center gap-1.5 text-xs text-gray-400">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="h-3.5 w-3.5 accent-accent"
            />
            Auto
          </label>
          <button
            type="button"
            onClick={() => void load()}
            disabled={refreshing}
            className="inline-flex items-center gap-2 rounded-lg border border-surface-600 bg-surface-800 px-3 py-1.5 text-sm font-medium text-gray-200 hover:bg-surface-700 disabled:opacity-50"
          >
            <svg
              className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`}
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M15.312 5.312a6.5 6.5 0 10.7 8.688h-2.2a4.5 4.5 0 11-.9-5.4L11 11h6V5l-1.688.312z"
                clipRule="evenodd"
              />
            </svg>
            Refresh
          </button>
        </div>
      </header>

      {error ? <ErrorPanel error={error} onRetry={() => void load()} /> : null}

      {loading && !data ? <LoadingState /> : null}

      {data ? (
        <div className="space-y-6">
          <SummaryBar totals={data.totals} balances={data.balances} />

          <div className="flex flex-wrap items-center gap-3">
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter by event, contract, outcome or slug…"
              className="w-full max-w-sm rounded-lg border border-surface-600 bg-surface-800 px-3 py-2 text-sm text-gray-200 placeholder:text-gray-600 focus:border-accent focus:outline-none"
            />
            <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-400">
              <input
                type="checkbox"
                checked={onlyOpenOrders}
                onChange={(e) => setOnlyOpenOrders(e.target.checked)}
                className="h-4 w-4 accent-accent"
              />
              Only with open orders
            </label>
            <div className="ml-auto flex items-center gap-3">
              {filteredEvents.length > 0 ? (
                <div className="flex items-center overflow-hidden rounded-lg border border-surface-600">
                  <button
                    type="button"
                    onClick={expandAll}
                    disabled={!anyCollapsed}
                    className="px-2.5 py-1.5 text-xs font-medium text-gray-300 hover:bg-surface-700 disabled:cursor-default disabled:text-gray-600 disabled:hover:bg-transparent"
                  >
                    Expand all
                  </button>
                  <span className="h-4 w-px bg-surface-600" />
                  <button
                    type="button"
                    onClick={collapseAll}
                    disabled={!anyOpen}
                    className="px-2.5 py-1.5 text-xs font-medium text-gray-300 hover:bg-surface-700 disabled:cursor-default disabled:text-gray-600 disabled:hover:bg-transparent"
                  >
                    Collapse all
                  </button>
                </div>
              ) : null}
              <span className="text-xs text-gray-500">
                {filteredEvents.length} event{filteredEvents.length === 1 ? "" : "s"} shown
              </span>
            </div>
          </div>

          {filteredEvents.length === 0 ? (
            <EmptyState hasData={data.events.length > 0} />
          ) : (
            <div className="space-y-4">
              {filteredEvents.map((event) => (
                <EventCard
                  key={event.event_slug}
                  event={event}
                  open={!collapsedEvents.has(event.event_slug)}
                  onToggleOpen={() => toggleEvent(event.event_slug)}
                />
              ))}
            </div>
          )}
        </div>
      ) : null}
    </main>
  );
}

function ErrorPanel({
  error,
  onRetry,
}: {
  error: DashboardApiError;
  onRetry: () => void;
}) {
  if (error.kind === "missing_credentials") {
    return (
      <div className="mb-6 rounded-xl border border-amber-500/30 bg-amber-500/10 p-5">
        <h2 className="text-base font-semibold text-amber-300">Credentials not configured</h2>
        <p className="mt-1 text-sm text-amber-100/80">{error.message}</p>
        <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm text-amber-100/70">
          <li>
            Copy <code className="rounded bg-black/30 px-1">.env.example</code> to{" "}
            <code className="rounded bg-black/30 px-1">.env</code> in the project root.
          </li>
          <li>
            Set <code className="rounded bg-black/30 px-1">POLYMARKET_KEY_ID</code> and{" "}
            <code className="rounded bg-black/30 px-1">POLYMARKET_SECRET_KEY</code>.
          </li>
          <li>Restart the backend, then refresh.</li>
        </ol>
      </div>
    );
  }

  const title =
    error.kind === "network"
      ? "Cannot reach the backend"
      : error.status
        ? `Backend error (${error.status})`
        : "Something went wrong";

  return (
    <div className="mb-6 rounded-xl border border-sell/30 bg-sell/10 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold text-red-300">{title}</h2>
          <p className="mt-1 text-sm text-red-100/80">{error.message}</p>
          {error.kind === "network" ? (
            <p className="mt-1 text-xs text-red-100/60">
              Expected backend at <code>{API_BASE_URL}</code>.
            </p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="shrink-0 rounded-lg border border-red-400/40 px-3 py-1.5 text-sm text-red-200 hover:bg-red-500/10"
        >
          Retry
        </button>
      </div>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-[76px] animate-pulse rounded-xl bg-surface-800" />
        ))}
      </div>
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="h-24 animate-pulse rounded-2xl bg-surface-800/60" />
      ))}
    </div>
  );
}

function EmptyState({ hasData }: { hasData: boolean }) {
  return (
    <div className="rounded-2xl border border-dashed border-surface-700 bg-surface-800/30 px-6 py-16 text-center">
      <p className="text-sm text-gray-400">
        {hasData ? "No events match your filters." : "No orders, positions or trades found."}
      </p>
      {!hasData ? (
        <p className="mt-1 text-xs text-gray-600">
          Once you place orders on Polymarket US they&apos;ll appear here grouped by event.
        </p>
      ) : null}
    </div>
  );
}
