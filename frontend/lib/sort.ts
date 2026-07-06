// Sorting for the dashboard's event/contract lists.
// Events and the contracts within each event are sorted by the same key so the
// ordering stays coherent at both levels.

import type { ContractGroup, EventGroup } from "./types";

export type SortKey = "active" | "recent" | "oldest" | "pnl" | "value" | "name";

export const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "active", label: "Most active" },
  { value: "recent", label: "Recent activity" },
  { value: "oldest", label: "Oldest activity" },
  { value: "pnl", label: "Realized P&L" },
  { value: "value", label: "Position value" },
  { value: "name", label: "Name (A–Z)" },
];

interface SortableStats {
  open_order_count: number;
  position_value: number;
  realized_pnl: number;
  last_activity: string | null;
}

/** Parse an ISO timestamp to epoch ms, or `fallback` when missing/invalid. */
function timeMs(iso: string | null, fallback: number): number {
  if (!iso) return fallback;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? fallback : t;
}

function compareStats(
  a: SortableStats,
  b: SortableStats,
  key: SortKey,
  nameA: string,
  nameB: string,
): number {
  switch (key) {
    case "active": {
      // Open orders first, then live value, then settled magnitude.
      if (b.open_order_count !== a.open_order_count)
        return b.open_order_count - a.open_order_count;
      if (b.position_value !== a.position_value) return b.position_value - a.position_value;
      return Math.abs(b.realized_pnl) - Math.abs(a.realized_pnl);
    }
    case "recent": {
      // Newest first; items with no timestamp sink to the bottom.
      const av = timeMs(a.last_activity, -Infinity);
      const bv = timeMs(b.last_activity, -Infinity);
      return av === bv ? 0 : bv - av;
    }
    case "oldest": {
      // Oldest first; items with no timestamp sink to the bottom.
      const av = timeMs(a.last_activity, Infinity);
      const bv = timeMs(b.last_activity, Infinity);
      return av === bv ? 0 : av - bv;
    }
    case "pnl":
      return b.realized_pnl - a.realized_pnl;
    case "value":
      return b.position_value - a.position_value;
    case "name":
      return nameA.localeCompare(nameB);
  }
}

const contractName = (c: ContractGroup): string =>
  (c.title || c.outcome || c.market_slug).toLowerCase();
const eventName = (e: EventGroup): string => (e.title || e.event_slug).toLowerCase();

/** Return a new, sorted copy of `events` (and each event's contracts). */
export function sortEvents(events: EventGroup[], key: SortKey): EventGroup[] {
  return events
    .map((e) => ({
      ...e,
      contracts: [...e.contracts].sort((a, b) =>
        compareStats(a.stats, b.stats, key, contractName(a), contractName(b)),
      ),
    }))
    .sort((a, b) => compareStats(a.stats, b.stats, key, eventName(a), eventName(b)));
}
