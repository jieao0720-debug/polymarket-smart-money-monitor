/**
 * Trade ticket confirm-button gating — pure logic, unit-tested.
 * UX layer only: the backend re-enforces every one of these (risk-control.md §10).
 */
import type { GeoblockStatus, RiskChecks } from "@/types/api";

export interface ConfirmGateInput {
  walletConnected: boolean;
  correctChain: boolean;
  geoblock: GeoblockStatus | null;
  riskChecks: RiskChecks | null;
  liveTradingEnabled: boolean;
  manualConfirmationChecked: boolean;
  ticketExpired: boolean;
  isOpeningNewPosition: boolean; // v1 tickets are always opening BUYs (A12)
}

export interface ConfirmGateResult {
  canConfirm: boolean;
  blockers: string[];
}

export function getConfirmBlockers(input: ConfirmGateInput): ConfirmGateResult {
  const blockers: string[] = [];

  if (!input.walletConnected) blockers.push("Wallet is not connected.");
  else if (!input.correctChain) blockers.push("Wallet is not on Polygon (chain 137).");

  if (!input.geoblock) {
    blockers.push("Geoblock status not verified yet.");
  } else if (input.geoblock.mode === "BLOCKED") {
    blockers.push("Trading is blocked for this region.");
  } else if (input.geoblock.mode === "CLOSE_ONLY" && input.isOpeningNewPosition) {
    blockers.push("This region is close-only. Opening new positions is disabled.");
  }

  if (!input.riskChecks) {
    blockers.push("Backend risk checks not available.");
  } else if (!input.riskChecks.all_passed) {
    blockers.push(
      input.riskChecks.reasons.length
        ? `Backend risk check failed: ${input.riskChecks.reasons[0]}`
        : "Backend risk check failed.",
    );
  }

  if (!input.liveTradingEnabled) {
    blockers.push("Live trading is disabled (ENABLE_LIVE_TRADING=false).");
  }

  if (input.ticketExpired) blockers.push("Ticket expired — prices are stale. Create a new one.");

  if (!input.manualConfirmationChecked) {
    blockers.push("Manual confirmation checkbox is not checked.");
  }

  return { canConfirm: blockers.length === 0, blockers };
}
