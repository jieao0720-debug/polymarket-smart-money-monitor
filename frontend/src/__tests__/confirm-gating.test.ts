import { describe, expect, it } from "vitest";
import { getConfirmBlockers, type ConfirmGateInput } from "@/lib/confirm-gating";
import type { GeoblockStatus, RiskChecks } from "@/types/api";

function geo(mode: GeoblockStatus["mode"]): GeoblockStatus {
  return {
    blocked: mode !== "OK",
    country: "DE",
    region: null,
    mode,
    can_open_position: mode === "OK",
    can_close_position: mode !== "BLOCKED",
    checked_at: new Date().toISOString(),
    fail_closed: false,
  };
}

function checks(allPassed = true): RiskChecks {
  return {
    geoblock_ok: allPassed,
    geoblock_mode: "OK",
    market_active: allPassed,
    spread_ok: allPassed,
    liquidity_ok: allPassed,
    price_ok: allPassed,
    notional_ok: allPassed,
    live_trading_enabled: true,
    all_passed: allPassed,
    reasons: allPassed ? [] : ["spread too wide"],
  };
}

function baseInput(over: Partial<ConfirmGateInput> = {}): ConfirmGateInput {
  return {
    walletConnected: true,
    correctChain: true,
    geoblock: geo("OK"),
    riskChecks: checks(true),
    liveTradingEnabled: true,
    manualConfirmationChecked: true,
    ticketExpired: false,
    isOpeningNewPosition: true,
    ...over,
  };
}

describe("getConfirmBlockers", () => {
  it("allows confirm when every condition is satisfied", () => {
    const result = getConfirmBlockers(baseInput());
    expect(result.canConfirm).toBe(true);
    expect(result.blockers).toEqual([]);
  });

  it("blocks when wallet is not connected", () => {
    const result = getConfirmBlockers(baseInput({ walletConnected: false }));
    expect(result.canConfirm).toBe(false);
    expect(result.blockers.join(" ")).toMatch(/wallet is not connected/i);
  });

  it("blocks on wrong chain", () => {
    const result = getConfirmBlockers(baseInput({ correctChain: false }));
    expect(result.canConfirm).toBe(false);
    expect(result.blockers.join(" ")).toMatch(/polygon/i);
  });

  it("blocks when region is fully geoblocked", () => {
    const result = getConfirmBlockers(baseInput({ geoblock: geo("BLOCKED") }));
    expect(result.canConfirm).toBe(false);
    expect(result.blockers.join(" ")).toMatch(/blocked for this region/i);
  });

  it("blocks opening a new position in a close-only region", () => {
    const result = getConfirmBlockers(
      baseInput({ geoblock: geo("CLOSE_ONLY"), isOpeningNewPosition: true }),
    );
    expect(result.canConfirm).toBe(false);
    expect(result.blockers.join(" ")).toMatch(/close-only/i);
  });

  it("blocks when geoblock status is unknown (fail closed)", () => {
    const result = getConfirmBlockers(baseInput({ geoblock: null }));
    expect(result.canConfirm).toBe(false);
  });

  it("blocks when backend risk checks failed", () => {
    const result = getConfirmBlockers(baseInput({ riskChecks: checks(false) }));
    expect(result.canConfirm).toBe(false);
    expect(result.blockers.join(" ")).toMatch(/risk check failed/i);
  });

  it("blocks when live trading is disabled (default state)", () => {
    const result = getConfirmBlockers(baseInput({ liveTradingEnabled: false }));
    expect(result.canConfirm).toBe(false);
    expect(result.blockers.join(" ")).toMatch(/live trading is disabled/i);
  });

  it("blocks when the manual confirmation checkbox is unchecked", () => {
    const result = getConfirmBlockers(baseInput({ manualConfirmationChecked: false }));
    expect(result.canConfirm).toBe(false);
    expect(result.blockers.join(" ")).toMatch(/manual confirmation/i);
  });

  it("blocks when the ticket has expired", () => {
    const result = getConfirmBlockers(baseInput({ ticketExpired: true }));
    expect(result.canConfirm).toBe(false);
    expect(result.blockers.join(" ")).toMatch(/expired/i);
  });

  it("reports every blocker at once", () => {
    const result = getConfirmBlockers(
      baseInput({
        walletConnected: false,
        liveTradingEnabled: false,
        manualConfirmationChecked: false,
      }),
    );
    expect(result.blockers.length).toBe(3);
  });
});
