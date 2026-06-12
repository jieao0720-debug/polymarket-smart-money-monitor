/**
 * The ONLY HTTP layer of the frontend (development-rules.md #16): every API call
 * goes through here. Components never call fetch directly. Errors are normalized
 * to ApiError carrying the backend error envelope. No payloads are logged.
 */
import type {
  AccountProfileResponse,
  AllowanceResponse,
  BalancesResponse,
  ClobCredentials,
  Direction,
  GeoblockStatus,
  HealthResponse,
  HotMarketsResponse,
  MarketAnalysisResponse,
  OrderSubmitResponse,
  PaperTrade,
  PaperTradesResponse,
  PublicSettings,
  ScanStatus,
  SignalsResponse,
  TradeTicket,
  TradeTicketCreateRequest,
} from "@/types/api";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ?? "http://localhost:8000";

export class ApiError extends Error {
  code: string;
  status: number;
  details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "Backend unreachable — is it running on " + API_BASE + "?", {});
  }
  if (response.status === 204) return undefined as T;
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    /* non-JSON body */
  }
  if (!response.ok) {
    const envelope = body as { error?: { code?: string; message?: string; details?: Record<string, unknown> } } | null;
    throw new ApiError(
      response.status,
      envelope?.error?.code ?? "HTTP_ERROR",
      envelope?.error?.message ?? `HTTP ${response.status}`,
      envelope?.error?.details ?? {},
    );
  }
  return body as T;
}

function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  if (!entries.length) return "";
  return "?" + entries.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join("&");
}

export const api = {
  // scanner
  runScanner: (maxMarkets?: number) =>
    request<ScanStatus>("/api/scanner/run", {
      method: "POST",
      body: JSON.stringify(maxMarkets ? { max_markets: maxMarkets } : {}),
    }),
  scannerStatus: (scanId: string) => request<ScanStatus>(`/api/scanner/status/${scanId}`),
  scannerLatest: () => request<ScanStatus>("/api/scanner/latest"),

  // markets
  hotMarkets: (params: { category?: string; min_confidence?: number; min_liquidity?: number; direction?: string } = {}) =>
    request<HotMarketsResponse>(`/api/markets/hot${qs({ limit: 100, ...params })}`),
  marketAnalysis: (marketId: string, refresh = false) =>
    request<MarketAnalysisResponse>(`/api/markets/${marketId}/analysis${qs({ refresh: refresh || undefined })}`),

  // accounts
  accountProfile: (address: string, marketId?: string) =>
    request<AccountProfileResponse>(`/api/accounts/${address}/profile${qs({ market_id: marketId })}`),

  // signals
  signals: (params: { direction?: string; min_confidence?: number; market_id?: string; limit?: number; offset?: number } = {}) =>
    request<SignalsResponse>(`/api/signals${qs({ limit: 200, ...params })}`),

  // trade tickets
  createTradeTicket: (body: TradeTicketCreateRequest) =>
    request<TradeTicket>("/api/trade-tickets", { method: "POST", body: JSON.stringify(body) }),
  getTradeTicket: (ticketId: string) => request<TradeTicket>(`/api/trade-tickets/${ticketId}`),
  confirmTradeTicket: (ticketId: string, walletAddress: string) =>
    request<TradeTicket>(`/api/trade-tickets/${ticketId}/confirm`, {
      method: "POST",
      body: JSON.stringify({ wallet_address: walletAddress, manual_confirmation: true }),
    }),
  cancelTradeTicket: (ticketId: string) =>
    request<TradeTicket>(`/api/trade-tickets/${ticketId}/cancel`, { method: "POST" }),

  // paper trades
  paperTrades: (params: { status?: string } = {}) =>
    request<PaperTradesResponse>(`/api/paper-trades${qs(params)}`),
  createPaperTrade: (body: { market_id: string; direction: Direction; notional: number; entry_price?: number | null; signal_id?: string | null }) =>
    request<PaperTrade>("/api/paper-trades", { method: "POST", body: JSON.stringify(body) }),
  closePaperTrade: (id: string, exitPrice?: number | null) =>
    request<PaperTrade>(`/api/paper-trades/${id}/close`, {
      method: "POST",
      body: JSON.stringify({ exit_price: exitPrice ?? null }),
    }),

  // trading
  geoblock: (walletAddress?: string) =>
    request<GeoblockStatus>(`/api/trading/geoblock${qs({ wallet_address: walletAddress })}`),
  balances: (walletAddress: string) =>
    request<BalancesResponse>(`/api/trading/balances${qs({ wallet_address: walletAddress })}`),
  allowance: (walletAddress: string) =>
    request<AllowanceResponse>(`/api/trading/allowance${qs({ wallet_address: walletAddress })}`),
  deriveClobCredentials: (body: { wallet_address: string; signature: string; timestamp: number; nonce: number }) =>
    request<ClobCredentials>("/api/trading/clob-credentials/derive", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  submitOrder: (body: {
    ticket_id: string;
    wallet_address: string;
    signed_order_payload: Record<string, unknown>;
    clob_credentials?: ClobCredentials | null;
  }) => request<OrderSubmitResponse>("/api/trading/orders/submit", { method: "POST", body: JSON.stringify(body) }),

  // misc
  health: () => request<HealthResponse>("/api/health"),
  publicSettings: () => request<PublicSettings>("/api/settings/public"),
};
