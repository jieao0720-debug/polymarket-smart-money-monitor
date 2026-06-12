import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TradeTicketModal } from "@/components/trade-ticket-modal";
import type { MarketInfo, MarketSummary, TradeTicket } from "@/types/api";

vi.mock("@/lib/api-client", () => {
  class ApiError extends Error {
    code: string;
    status: number;
    details: Record<string, unknown>;
    constructor(status: number, code: string, message: string) {
      super(message);
      this.status = status;
      this.code = code;
      this.details = {};
    }
  }
  return {
    ApiError,
    API_BASE: "http://test",
    api: {
      createTradeTicket: vi.fn(),
      confirmTradeTicket: vi.fn(),
      cancelTradeTicket: vi.fn(),
      getTradeTicket: vi.fn(),
      createPaperTrade: vi.fn(),
      deriveClobCredentials: vi.fn(),
      submitOrder: vi.fn(),
    },
  };
});

import { api } from "@/lib/api-client";

const market: MarketInfo = {
  market_id: "1001",
  condition_id: "0xc1",
  question: "Will the test candidate win the election?",
  category: "politics",
  slug: "test",
  active: true,
  closed: false,
  accepting_orders: true,
  neg_risk: false,
  end_date: "2026-12-01T00:00:00",
  yes_token_id: "111",
  no_token_id: "222",
  yes_price: 0.6,
  no_price: 0.4,
  spread: 0.02,
  midpoint: 0.6,
  volume_24h: 50000,
  liquidity: 20000,
  open_interest: 100000,
  tick_size: 0.01,
};

const summary: MarketSummary = {
  snapshot_time: "2026-06-11T00:00:00",
  yes_smart_money_count: 1,
  no_smart_money_count: 0,
  yes_smart_money_notional: 6000,
  no_smart_money_notional: 0,
  net_direction: "YES",
  confidence_score: 55,
  risk_flags: ["LOW_SMART_SAMPLE"],
  suggested_limit_price: 0.61,
  suggested_max_notional: 50,
  signal_id: "sig1",
};

function ticket(allPassed = true, liveEnabled = false): TradeTicket {
  return {
    ticket_id: "t1",
    status: "PENDING_USER_CONFIRMATION",
    signal_id: "sig1",
    market_id: "1001",
    question: market.question,
    direction: "YES",
    side: "BUY",
    limit_price: 0.61,
    max_notional: 50,
    wallet_address: null,
    risk_checks: {
      geoblock_ok: allPassed,
      geoblock_mode: "OK",
      market_active: true,
      spread_ok: allPassed,
      liquidity_ok: true,
      price_ok: true,
      notional_ok: true,
      live_trading_enabled: liveEnabled,
      all_passed: allPassed,
      reasons: allPassed ? [] : ["spread too wide"],
    },
    risk_checks_at_submit: null,
    created_at: "2026-06-11T00:00:00",
    confirmed_at: null,
    submitted_at: null,
    expires_at: new Date(Date.now() + 10 * 60_000).toISOString().replace("Z", ""),
    order_id: null,
    tx_hash: null,
    error_message: null,
  };
}

const geoOk = {
  blocked: false,
  country: "DE",
  region: null,
  mode: "OK" as const,
  can_open_position: true,
  can_close_position: true,
  checked_at: "2026-06-11T00:00:00",
  fail_closed: false,
};

function renderModal(over: Partial<Parameters<typeof TradeTicketModal>[0]> = {}) {
  return render(
    <TradeTicketModal
      open
      onClose={() => {}}
      market={market}
      summary={summary}
      direction="YES"
      wallet={{ address: undefined, connected: false, correctChain: false }}
      geoblock={geoOk}
      liveTradingEnabled={false}
      {...over}
    />,
  );
}

describe("TradeTicketModal", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the mandatory manual-trading statement", () => {
    renderModal();
    expect(
      screen.getByText("This is not automated trading. You are manually confirming this order."),
    ).toBeInTheDocument();
  });

  it("shows the close-only warning when the region is close-only", () => {
    renderModal({
      geoblock: { ...geoOk, blocked: true, mode: "CLOSE_ONLY", can_open_position: false },
    });
    expect(
      screen.getByText("This region is close-only. Opening new positions is disabled."),
    ).toBeInTheDocument();
  });

  it("warns when live trading is disabled server-side", () => {
    renderModal();
    expect(screen.getByText(/live trading is disabled server-side/i)).toBeInTheDocument();
  });

  it("keeps Confirm disabled when wallet disconnected, even with all checks green", async () => {
    vi.mocked(api.createTradeTicket).mockResolvedValue(ticket(true, true));
    renderModal({ liveTradingEnabled: true });
    fireEvent.click(screen.getByRole("button", { name: /run risk checks/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /confirm & sign/i })).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText("Manual confirmation"));
    const confirm = screen.getByRole("button", { name: /confirm & sign/i });
    expect(confirm).toBeDisabled();
    expect(screen.getByText(/wallet is not connected/i)).toBeInTheDocument();
  });

  it("keeps Confirm disabled in a close-only region for an opening trade", async () => {
    vi.mocked(api.createTradeTicket).mockResolvedValue(ticket(true, true));
    renderModal({
      liveTradingEnabled: true,
      wallet: { address: "0x" + "ab".repeat(20), connected: true, correctChain: true },
      geoblock: { ...geoOk, blocked: true, mode: "CLOSE_ONLY", can_open_position: false },
    });
    fireEvent.click(screen.getByRole("button", { name: /run risk checks/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /confirm & sign/i })).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText("Manual confirmation"));
    expect(screen.getByRole("button", { name: /confirm & sign/i })).toBeDisabled();
  });

  it("keeps Confirm disabled while live trading is off and until the checkbox is ticked", async () => {
    vi.mocked(api.createTradeTicket).mockResolvedValue(ticket(true, false));
    renderModal({
      wallet: { address: "0x" + "ab".repeat(20), connected: true, correctChain: true },
    });
    fireEvent.click(screen.getByRole("button", { name: /run risk checks/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /confirm & sign/i })).toBeInTheDocument());

    const confirm = screen.getByRole("button", { name: /confirm & sign/i });
    expect(confirm).toBeDisabled(); // checkbox unchecked + live disabled
    fireEvent.click(screen.getByLabelText("Manual confirmation"));
    expect(confirm).toBeDisabled(); // live trading still disabled → stays blocked
    expect(screen.getByText(/live trading is disabled \(enable_live_trading=false\)/i)).toBeInTheDocument();
  });

  it("enables Confirm only when every gate passes", async () => {
    vi.mocked(api.createTradeTicket).mockResolvedValue(ticket(true, true));
    renderModal({
      liveTradingEnabled: true,
      wallet: { address: "0x" + "ab".repeat(20), connected: true, correctChain: true },
    });
    fireEvent.click(screen.getByRole("button", { name: /run risk checks/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /confirm & sign/i })).toBeInTheDocument());

    const confirm = screen.getByRole("button", { name: /confirm & sign/i });
    expect(confirm).toBeDisabled();
    fireEvent.click(screen.getByLabelText("Manual confirmation"));
    expect(confirm).toBeEnabled();
  });

  it("can log a paper trade regardless of live-trading state", async () => {
    vi.mocked(api.createPaperTrade).mockResolvedValue({} as never);
    renderModal();
    fireEvent.click(screen.getByRole("button", { name: /log as paper trade/i }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /paper trade logged/i })).toBeInTheDocument(),
    );
    expect(api.createPaperTrade).toHaveBeenCalledWith({
      market_id: "1001",
      direction: "YES",
      notional: 50,
      entry_price: 0.61,
      signal_id: "sig1",
    });
  });
});
