/**
 * TypeScript mirror of /docs/api-contract.md — keep field-for-field in sync with
 * backend/app/schemas/api.py (development-rules.md #5).
 */

export type Direction = "YES" | "NO";
export type SignalDirection = "YES" | "NO" | "NEUTRAL";
export type AccountLabel = "NEW_ACCOUNT" | "HIGH_WIN_RATE" | "ABNORMAL_POSITION" | "OTHER";
export type TicketStatus =
  | "PENDING_USER_CONFIRMATION"
  | "CONFIRMED"
  | "SUBMITTED"
  | "REJECTED"
  | "FAILED"
  | "CANCELLED"
  | "EXPIRED";
export type PaperTradeStatus = "OPEN" | "CLOSED" | "CANCELLED";
export type GeoMode = "OK" | "CLOSE_ONLY" | "BLOCKED";

export interface ApiErrorBody {
  error: { code: string; message: string; details: Record<string, unknown> };
}

export interface ScanStatus {
  scan_id: string | null;
  status: "idle" | "running" | "completed" | "failed";
  started_at: string | null;
  finished_at: string | null;
  markets_found: number;
  markets_analyzed: number;
  signals_generated: number;
  errors: string[];
  current_step: string | null;
}

export interface HotMarket {
  market_id: string;
  condition_id: string;
  question: string;
  category: string | null;
  slug: string;
  end_date: string | null;
  volume_24h: number;
  liquidity: number;
  open_interest: number | null;
  yes_price: number | null;
  no_price: number | null;
  spread: number | null;
  midpoint: number | null;
  smart_money_direction: SignalDirection | null;
  confidence_score: number | null;
  risk_flags: string[];
  last_analyzed_at: string | null;
}

export interface HotMarketsResponse {
  markets: HotMarket[];
  warnings: string[];
}

export interface MarketInfo {
  market_id: string;
  condition_id: string;
  question: string;
  category: string | null;
  slug: string;
  active: boolean;
  closed: boolean;
  accepting_orders: boolean;
  neg_risk: boolean;
  end_date: string | null;
  yes_token_id: string;
  no_token_id: string;
  yes_price: number | null;
  no_price: number | null;
  spread: number | null;
  midpoint: number | null;
  volume_24h: number;
  liquidity: number;
  open_interest: number | null;
  tick_size: number;
}

export interface MarketSummary {
  snapshot_time: string | null;
  yes_smart_money_count: number;
  no_smart_money_count: number;
  yes_smart_money_notional: number;
  no_smart_money_notional: number;
  net_direction: SignalDirection;
  confidence_score: number;
  risk_flags: string[];
  suggested_limit_price: number | null;
  suggested_max_notional: number | null;
  signal_id: string | null;
}

export interface HolderEntry {
  address: string;
  profile_name: string | null;
  direction: Direction;
  rank: number;
  current_position_value: number;
  shares: number;
  average_price: number | null;
  current_price: number | null;
  value_is_approx: boolean;
  label: AccountLabel;
  label_reason: string;
  win_rate: number;
  resolved_trade_count: number;
  realized_pnl: number;
  same_category_win_rate: number;
  same_category_trade_count: number;
  anomaly_index: number | null;
  smart_money_score: number;
  history_truncated: boolean;
}

export interface MarketAnalysisResponse {
  market: MarketInfo;
  summary: MarketSummary;
  holders: HolderEntry[];
  warnings: string[];
}

export interface AccountProfileResponse {
  address: string;
  profile_name: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  as_of: string;
  history_truncated: boolean;
  overall: {
    resolved_trade_count: number;
    win_rate: number;
    realized_pnl: number;
    average_roi: number;
    median_entry_notional: number;
  };
  same_category: {
    category: string | null;
    trade_count: number;
    win_rate: number;
    average_roi: number;
  } | null;
  current_market: {
    market_id: string;
    direction: Direction | null;
    shares: number | null;
    average_price: number | null;
    current_position_value: number | null;
    entry_notional_approx: number | null;
    anomaly_index: number | null;
    label: AccountLabel;
    label_reason: string;
    smart_money_score: number;
  } | null;
  warnings: string[];
}

export interface SignalEntry {
  signal_id: string;
  market_id: string;
  question: string;
  category: string | null;
  snapshot_time: string;
  direction: SignalDirection;
  confidence_score: number;
  yes_smart_money_count: number;
  no_smart_money_count: number;
  yes_smart_money_notional: number;
  no_smart_money_notional: number;
  risk_flags: string[];
  suggested_limit_price: number | null;
  suggested_max_notional: number | null;
}

export interface SignalsResponse {
  signals: SignalEntry[];
  total: number;
}

export interface RiskChecks {
  geoblock_ok: boolean;
  geoblock_mode: GeoMode;
  market_active: boolean;
  spread_ok: boolean;
  liquidity_ok: boolean;
  price_ok: boolean;
  notional_ok: boolean;
  live_trading_enabled: boolean;
  all_passed: boolean;
  reasons: string[];
}

export interface TradeTicket {
  ticket_id: string;
  status: TicketStatus;
  signal_id: string | null;
  market_id: string;
  question: string;
  direction: Direction;
  side: string;
  limit_price: number;
  max_notional: number;
  wallet_address: string | null;
  risk_checks: RiskChecks | null;
  risk_checks_at_submit: Record<string, unknown> | null;
  created_at: string;
  confirmed_at: string | null;
  submitted_at: string | null;
  expires_at: string | null;
  order_id: string | null;
  tx_hash: string | null;
  error_message: string | null;
}

export interface TradeTicketCreateRequest {
  signal_id?: string | null;
  market_id: string;
  direction: Direction;
  limit_price: number;
  max_notional: number;
  wallet_address?: string | null;
  side?: "BUY";
}

export interface PaperTrade {
  paper_trade_id: string;
  signal_id: string | null;
  market_id: string;
  question: string;
  direction: Direction;
  entry_price: number;
  entry_time: string;
  notional: number;
  shares: number;
  remaining_shares?: number | null; // still held after partial exits
  exit_price: number | null; // average net exit price once fully closed
  exit_time: string | null;
  pnl: number | null; // realized so far, partial exits included
  unrealized_pnl: number | null;
  current_price: number | null; // side best bid
  price_basis?: "BID" | "MIDPOINT" | null;
  price_as_of?: string | null;
  status: PaperTradeStatus;
  source: string;
  exit_reason?: "MANUAL" | "RESOLVED" | null;
  shadow?: ShadowExitSummary | null;
}

/** Latest position-monitor view — shadow mode: recorded, never executed. */
export interface ShadowExitSummary {
  observed_at: string;
  market_status: string;
  retention: number | null;
  coverage: number | null;
  liquidation_return: number | null;
  target_fraction: number | null;
  triggers: string[];
}

export interface PaperTradesResponse {
  paper_trades: PaperTrade[];
  total: number;
  summary: {
    open_count: number;
    closed_count: number;
    total_realized_pnl: number;
    total_unrealized_pnl: number;
    win_count: number;
    loss_count: number;
  };
}

export interface GeoblockStatus {
  blocked: boolean;
  country: string | null;
  region: string | null;
  mode: GeoMode;
  can_open_position: boolean;
  can_close_position: boolean;
  checked_at: string;
  fail_closed: boolean;
}

export interface BalancesResponse {
  wallet_address: string;
  chain_id: number;
  usdc_balance: number | null;
  native_balance: number | null;
  checked_at: string;
  warnings: string[];
}

export interface AllowanceResponse {
  wallet_address: string;
  ctf_exchange_allowance: number | null;
  neg_risk_exchange_allowance: number | null;
  ctf_exchange_ok: boolean;
  neg_risk_exchange_ok: boolean;
  checked_at: string;
}

export interface OrderSubmitResponse {
  status: string;
  order_id: string | null;
  submitted_at: string;
  clob_status: string | null;
}

export interface ClobCredentials {
  api_key: string;
  secret: string;
  passphrase: string;
}

export interface HealthResponse {
  status: string;
  version: string;
  database: string;
  time: string;
  live_trading_enabled: boolean;
  scheduler_running: boolean;
}

export interface PublicSettings {
  enable_live_trading: boolean;
  max_trade_notional: number;
  max_slippage_bps: number;
  max_spread_bps: number;
  min_liquidity: number;
  min_position_value: number;
  smart_money_score_threshold: number;
  scanner_max_markets: number;
  scanner_interval_minutes: number;
  close_only_countries: string[];
  near_resolution_hours: number;
  paper_trade_auto_log: boolean;
}
