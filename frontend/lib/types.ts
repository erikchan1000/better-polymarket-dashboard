// Mirrors the Pydantic response models in `backend/app/schemas.py`.
// Keep these in sync with the backend contract.

export interface OrderSummary {
  id: string;
  market_slug: string;
  side: string | null;
  side_label: string | null;
  type: string | null;
  state: string | null;
  state_label: string | null;
  intent: string | null;
  tif: string | null;
  price: number | null;
  avg_px: number | null;
  quantity: number;
  cum_quantity: number;
  leaves_quantity: number;
  notional: number;
  create_time: string | null;
}

export interface PositionSummary {
  market_slug: string;
  net_position: number;
  qty_bought: number;
  qty_sold: number;
  qty_available: number;
  cost: number;
  realized: number;
  cash_value: number;
  expired: boolean;
  update_time: string | null;
}

export interface TradeSummary {
  id: string;
  market_slug: string;
  state: string | null;
  price: number | null;
  qty: number;
  cost_basis: number;
  realized_pnl: number;
  is_aggressor: boolean | null;
  create_time: string | null;
}

export interface ResolutionSummary {
  market_slug: string;
  side: string | null;
  side_label: string | null;
  net_position: number;
  cost: number;
  payout: number;
  realized_pnl: number;
  resolved_time: string | null;
}

export interface ContractStats {
  open_order_count: number;
  open_buy_count: number;
  open_sell_count: number;
  open_order_notional: number;
  net_position: number;
  position_cost: number;
  position_value: number;
  realized_pnl: number;
  trade_count: number;
  resolution_count: number;
  last_activity: string | null;
}

export interface ContractGroup {
  market_slug: string;
  title: string | null;
  outcome: string | null;
  icon: string | null;
  event_slug: string | null;
  team: Record<string, unknown> | null;
  orders: OrderSummary[];
  position: PositionSummary | null;
  trades: TradeSummary[];
  resolutions: ResolutionSummary[];
  stats: ContractStats;
}

export interface EventStats {
  contract_count: number;
  open_order_count: number;
  open_order_notional: number;
  position_value: number;
  position_cost: number;
  realized_pnl: number;
  trade_count: number;
  resolution_count: number;
  last_activity: string | null;
}

export interface EventGroup {
  event_slug: string;
  title: string;
  contracts: ContractGroup[];
  stats: EventStats;
}

export interface BalanceSummary {
  currency: string | null;
  current_balance: number | null;
  buying_power: number | null;
  asset_notional: number | null;
  asset_available: number | null;
  open_orders: number | null;
  unsettled_funds: number | null;
  pending_credit: number | null;
  last_updated: string | null;
}

export interface DashboardTotals {
  event_count: number;
  contract_count: number;
  open_order_count: number;
  open_order_notional: number;
  position_value: number;
  position_cost: number;
  realized_pnl: number;
  trade_count: number;
  resolution_count: number;
}

export interface DashboardResponse {
  generated_at: string;
  credentials_configured: boolean;
  balances: BalanceSummary[];
  events: EventGroup[];
  totals: DashboardTotals;
}

export interface HealthResponse {
  status: string;
  credentials_configured: boolean;
  gateway_base_url: string;
  api_base_url: string;
}

// Discriminated result type so the UI can render setup / error states cleanly.
export type ApiErrorKind = "missing_credentials" | "upstream_error" | "network" | "unknown";

export interface ApiError {
  kind: ApiErrorKind;
  message: string;
  status?: number;
}
