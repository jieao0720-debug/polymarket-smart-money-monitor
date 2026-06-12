"use client";

/**
 * Trade Ticket Modal — the manual confirmation surface for real trading.
 *
 * Safety properties (mirrors risk-control.md; backend re-enforces everything):
 *  - Confirm stays disabled until: wallet connected on Polygon, geoblock OK,
 *    backend risk checks passed, live trading enabled server-side, ticket not
 *    expired, and the manual-confirmation checkbox is explicitly ticked.
 *  - Signing happens in the user's wallet (EIP-712). No keys touch this app.
 *  - Nothing sensitive is ever logged.
 *  - Blocker texts originate from confirm-gating.ts (canonical English, unit-tested)
 *    and are translated for display only.
 */
import * as React from "react";
import { DirectionBadge, RiskFlags } from "@/components/common";
import { Alert, Badge, Button, Checkbox, Dialog, Input } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api-client";
import { getConfirmBlockers } from "@/lib/confirm-gating";
import { translateBlocker, useI18n } from "@/lib/i18n";
import {
  buildBuyOrder,
  clobAuthTypedData,
  orderDomain,
  ORDER_TYPES,
  orderTypedMessage,
} from "@/lib/polymarket-order";
import { formatCents, formatUsd } from "@/lib/format";
import type { GeoblockStatus, MarketInfo, MarketSummary, TradeTicket } from "@/types/api";
import type { TypedDataDomain } from "viem";

export type SignTypedDataFn = (args: {
  domain: TypedDataDomain;
  types: Record<string, readonly { name: string; type: string }[]>;
  primaryType: string;
  message: Record<string, unknown>;
}) => Promise<string>;

export interface TradeTicketModalProps {
  open: boolean;
  onClose: () => void;
  market: MarketInfo;
  summary: MarketSummary;
  direction: "YES" | "NO";
  wallet: { address?: string; connected: boolean; correctChain: boolean };
  geoblock: GeoblockStatus | null;
  liveTradingEnabled: boolean;
  signTypedData?: SignTypedDataFn;
  onPaperTradeLogged?: () => void;
}

type Step = "form" | "review" | "submitting" | "done";

function CheckRow({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className={ok ? "text-yes" : "text-no"}>{ok ? "✓" : "✗"}</span>
      <span className={ok ? "text-foreground" : "text-no"}>{label}</span>
    </div>
  );
}

export function TradeTicketModal(props: TradeTicketModalProps) {
  const { open, onClose, market, summary, direction, wallet, geoblock, liveTradingEnabled } = props;
  const { locale, t } = useI18n();
  const price = direction === "YES" ? market.yes_price : market.no_price;

  const [limitPrice, setLimitPrice] = React.useState<string>("");
  const [maxNotional, setMaxNotional] = React.useState<string>("");
  const [ticket, setTicket] = React.useState<TradeTicket | null>(null);
  const [manualChecked, setManualChecked] = React.useState(false);
  const [step, setStep] = React.useState<Step>("form");
  const [error, setError] = React.useState<string | null>(null);
  const [statusText, setStatusText] = React.useState<string>("");
  const [paperLogged, setPaperLogged] = React.useState(false);

  React.useEffect(() => {
    if (open) {
      setLimitPrice(summary.suggested_limit_price?.toString() ?? price?.toString() ?? "");
      setMaxNotional(summary.suggested_max_notional?.toString() ?? "50");
      setTicket(null);
      setManualChecked(false);
      setStep("form");
      setError(null);
      setPaperLogged(false);
      setStatusText("");
    }
  }, [open, summary, price]);

  const ticketExpired =
    !!ticket?.expires_at && new Date(ticket.expires_at + "Z").getTime() < Date.now();

  const gate = getConfirmBlockers({
    walletConnected: wallet.connected,
    correctChain: wallet.correctChain,
    geoblock,
    riskChecks: ticket?.risk_checks ?? null,
    liveTradingEnabled,
    manualConfirmationChecked: manualChecked,
    ticketExpired,
    isOpeningNewPosition: true, // v1 only opens BUY positions (A12)
  });

  const createTicket = async () => {
    setError(null);
    try {
      const created = await api.createTradeTicket({
        signal_id: summary.signal_id,
        market_id: market.market_id,
        direction,
        limit_price: Number(limitPrice),
        max_notional: Number(maxNotional),
        wallet_address: wallet.address ?? null,
      });
      setTicket(created);
      setStep("review");
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : t("modal.createFailed"));
    }
  };

  const logPaperTrade = async () => {
    setError(null);
    try {
      await api.createPaperTrade({
        market_id: market.market_id,
        direction,
        notional: Number(maxNotional),
        entry_price: Number(limitPrice),
        signal_id: summary.signal_id,
      });
      setPaperLogged(true);
      props.onPaperTradeLogged?.();
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : t("modal.paperFailed"));
    }
  };

  const confirmAndSubmit = async () => {
    if (!ticket || !wallet.address || !props.signTypedData) return;
    setError(null);
    setStep("submitting");
    try {
      setStatusText(t("modal.statusConfirming"));
      const confirmed = await api.confirmTradeTicket(ticket.ticket_id, wallet.address);
      setTicket(confirmed);

      setStatusText(t("modal.statusSigning"));
      const tokenId = direction === "YES" ? market.yes_token_id : market.no_token_id;
      const order = buildBuyOrder({
        maker: wallet.address as `0x${string}`,
        tokenId,
        limitPrice: Number(limitPrice),
        notional: Number(maxNotional),
      });
      const orderSignature = await props.signTypedData({
        domain: orderDomain(market.neg_risk),
        types: ORDER_TYPES as unknown as Record<string, readonly { name: string; type: string }[]>,
        primaryType: "Order",
        message: orderTypedMessage(order) as unknown as Record<string, unknown>,
      });

      setStatusText(t("modal.statusDeriving"));
      const ts = Math.floor(Date.now() / 1000);
      const auth = clobAuthTypedData(wallet.address as `0x${string}`, ts);
      const authSignature = await props.signTypedData({
        domain: auth.domain,
        types: auth.types as unknown as Record<string, readonly { name: string; type: string }[]>,
        primaryType: auth.primaryType,
        message: auth.message as unknown as Record<string, unknown>,
      });
      const creds = await api.deriveClobCredentials({
        wallet_address: wallet.address,
        signature: authSignature,
        timestamp: ts,
        nonce: 0,
      });

      setStatusText(t("modal.statusSubmitting"));
      const result = await api.submitOrder({
        ticket_id: ticket.ticket_id,
        wallet_address: wallet.address,
        signed_order_payload: {
          order: { ...order, side: "BUY", signature: orderSignature },
          owner: creds.api_key,
          orderType: "GTC",
        },
        clob_credentials: creds,
      });
      setStatusText(t("modal.statusDone", { status: result.status, id: result.order_id ?? "n/a" }));
      setStep("done");
    } catch (e) {
      setError(e instanceof ApiError
        ? `${e.code}: ${e.message}`
        : t("modal.submitFailed", { message: (e as Error).message ?? "unknown" }));
      setStep("review");
      try {
        const fresh = await api.getTradeTicket(ticket.ticket_id);
        setTicket(fresh);
      } catch {
        /* keep stale ticket view */
      }
    }
  };

  const checks = ticket?.risk_checks;

  return (
    <Dialog open={open} onClose={onClose} wide>
      <div className="border-b border-border px-5 py-3">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">{t("modal.title")}</h3>
          <DirectionBadge direction={direction} />
        </div>
        <p className="mt-1 line-clamp-2 text-xs text-muted">{market.question}</p>
      </div>

      <div className="space-y-4 px-5 py-4">
        <Alert variant="info">{t("modal.manualStatement")}</Alert>

        {geoblock?.mode === "CLOSE_ONLY" && (
          <Alert variant="danger">{t("modal.closeOnlyStatement")}</Alert>
        )}
        {geoblock?.mode === "BLOCKED" && (
          <Alert variant="danger">
            {t("modal.blockedStatement",
               { suffix: geoblock.fail_closed ? t("modal.failClosedSuffix") : "" })}
          </Alert>
        )}
        {!liveTradingEnabled && <Alert variant="warn">{t("modal.liveDisabledAlert")}</Alert>}

        <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs md:grid-cols-3">
          <div className="flex justify-between gap-2"><span className="text-muted">{t("modal.curPrice")}</span><span className="tabular-nums">{formatCents(price)}</span></div>
          <div className="flex justify-between gap-2"><span className="text-muted">{t("modal.spread")}</span><span className="tabular-nums">{formatCents(market.spread)}</span></div>
          <div className="flex justify-between gap-2"><span className="text-muted">{t("modal.liquidity")}</span><span className="tabular-nums">{formatUsd(market.liquidity)}</span></div>
          <div className="flex justify-between gap-2"><span className="text-muted">{t("modal.confidence")}</span><span className="tabular-nums">{t("modal.confValue", { score: summary.confidence_score.toFixed(0) })}</span></div>
          <div className="flex justify-between gap-2"><span className="text-muted">{t("modal.suggPrice")}</span><span className="tabular-nums">{formatCents(summary.suggested_limit_price)}</span></div>
          <div className="flex justify-between gap-2"><span className="text-muted">{t("modal.suggMax")}</span><span className="tabular-nums">{formatUsd(summary.suggested_max_notional, 2)}</span></div>
        </div>
        <div>
          <span className="mr-2 text-[11px] uppercase tracking-wider text-muted">{t("modal.riskFlags")}</span>
          <RiskFlags flags={summary.risk_flags} />
        </div>

        {step === "form" && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <label className="space-y-1 text-xs">
                <span className="text-muted">{t("modal.limitLabel", { tick: market.tick_size })}</span>
                <Input
                  type="number"
                  step={market.tick_size}
                  min={market.tick_size}
                  max={1 - market.tick_size}
                  value={limitPrice}
                  onChange={(e) => setLimitPrice(e.target.value)}
                  aria-label="Limit price"
                />
              </label>
              <label className="space-y-1 text-xs">
                <span className="text-muted">{t("modal.notionalLabel")}</span>
                <Input
                  type="number"
                  step="1"
                  min="1"
                  value={maxNotional}
                  onChange={(e) => setMaxNotional(e.target.value)}
                  aria-label="Max notional"
                />
              </label>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={onClose}>{t("modal.cancel")}</Button>
              <Button variant="outline" onClick={logPaperTrade} disabled={paperLogged}>
                {paperLogged ? t("modal.paperLogged") : t("modal.logPaper")}
              </Button>
              <Button onClick={createTicket} disabled={!limitPrice || !maxNotional}>
                {t("modal.runChecks")}
              </Button>
            </div>
          </div>
        )}

        {(step === "review" || step === "submitting" || step === "done") && ticket && (
          <div className="space-y-3">
            <div className="rounded-md border border-border bg-surface-2/50 p-3">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[11px] uppercase tracking-wider text-muted">{t("modal.checksTitle")}</span>
                <Badge variant={checks?.all_passed ? "yes" : "no"}>
                  {checks?.all_passed ? t("modal.allPassed") : t("modal.checksFailed")}
                </Badge>
              </div>
              {checks && (
                <div className="grid grid-cols-2 gap-1">
                  <CheckRow ok={checks.geoblock_ok} label={t("modal.checkGeoblock", { mode: checks.geoblock_mode })} />
                  <CheckRow ok={checks.market_active} label={t("modal.checkMarket")} />
                  <CheckRow ok={checks.spread_ok} label={t("modal.checkSpread")} />
                  <CheckRow ok={checks.liquidity_ok} label={t("modal.checkLiquidity")} />
                  <CheckRow ok={checks.price_ok} label={t("modal.checkPrice")} />
                  <CheckRow ok={checks.notional_ok} label={t("modal.checkNotional")} />
                  <CheckRow ok={checks.live_trading_enabled} label={t("modal.checkLive")} />
                </div>
              )}
              {checks?.reasons?.length ? (
                <ul className="mt-2 list-inside list-disc text-[11px] text-no">
                  {checks.reasons.map((r) => <li key={r}>{r}</li>)}
                </ul>
              ) : null}
              <div className="mt-2 text-[10px] text-muted">
                {t("modal.ticketLine", { id: ticket.ticket_id.slice(0, 8), status: ticket.status })}
                {ticket.expires_at
                  ? t("modal.expires", { time: new Date(ticket.expires_at + "Z").toLocaleTimeString() })
                  : ""}
              </div>
            </div>

            <label className="flex items-start gap-2 text-xs">
              <Checkbox
                checked={manualChecked}
                onChange={(e) => setManualChecked(e.target.checked)}
                aria-label="Manual confirmation"
                disabled={step !== "review"}
              />
              <span>
                {t("modal.confirmCheckbox", {
                  direction,
                  price: formatCents(Number(limitPrice)),
                  notional: formatUsd(Number(maxNotional), 2),
                })}
              </span>
            </label>

            {step === "review" && !gate.canConfirm && (
              <ul className="space-y-0.5 text-[11px] text-warn">
                {gate.blockers.map((b) => <li key={b}>· {translateBlocker(locale, b)}</li>)}
              </ul>
            )}
            {step === "submitting" && <Alert variant="info">{statusText}</Alert>}
            {step === "done" && <Alert variant="info">{statusText} {t("modal.doneSuffix")}</Alert>}

            <div className="flex justify-end gap-2">
              <Button
                variant="ghost"
                onClick={async () => {
                  if (ticket && step === "review") {
                    try { await api.cancelTradeTicket(ticket.ticket_id); } catch { /* already final */ }
                  }
                  onClose();
                }}
              >
                {step === "done" ? t("modal.closeBtn") : t("modal.cancel")}
              </Button>
              <Button variant="outline" onClick={logPaperTrade} disabled={paperLogged}>
                {paperLogged ? t("modal.paperLogged") : t("modal.logPaper")}
              </Button>
              {step !== "done" && (
                <Button
                  onClick={confirmAndSubmit}
                  disabled={!gate.canConfirm || step === "submitting"}
                  title={gate.blockers[0] ? translateBlocker(locale, gate.blockers[0]) : undefined}
                >
                  {step === "submitting" ? t("modal.submitting") : t("modal.confirmSign")}
                </Button>
              )}
            </div>
          </div>
        )}

        {error && <Alert variant="danger">{error}</Alert>}
      </div>
    </Dialog>
  );
}
