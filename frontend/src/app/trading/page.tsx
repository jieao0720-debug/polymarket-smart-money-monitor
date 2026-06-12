"use client";

import * as React from "react";
import { useAccount, useChainId, useConnect, useDisconnect, useSwitchChain } from "wagmi";
import { AddressChip, Stat } from "@/components/common";
import { Alert, Badge, Button, Card, CardContent, CardHeader, CardTitle } from "@/components/ui/primitives";
import { useAllowance, useBalances, useGeoblock, usePublicSettings } from "@/hooks/use-api";
import { useI18n } from "@/lib/i18n";
import { formatUsd } from "@/lib/format";
import { POLYGON_CHAIN_ID } from "@/lib/wagmi";

export default function TradingPage() {
  const { t } = useI18n();
  const account = useAccount();
  const chainId = useChainId();
  const { connect, connectors, isPending: connecting, error: connectError } = useConnect();
  const { disconnect } = useDisconnect();
  const { switchChain } = useSwitchChain();

  const geoblock = useGeoblock(account.address);
  const balances = useBalances(account.address);
  const allowance = useAllowance(account.address);
  const settings = usePublicSettings();

  const correctChain = chainId === POLYGON_CHAIN_ID;
  const geo = geoblock.data;
  const live = settings.data?.enable_live_trading ?? false;

  return (
    <div className="max-w-3xl space-y-4">
      <div>
        <h1 className="text-xl font-bold tracking-tight">{t("trading.title")}</h1>
        <p className="text-[11px] text-muted">{t("trading.subtitle")}</p>
      </div>

      <Card>
        <CardHeader><CardTitle>{t("trading.walletCard")}</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {account.isConnected && account.address ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="space-y-1">
                <AddressChip address={account.address} />
                <div className="flex items-center gap-2 text-xs">
                  <Badge variant={correctChain ? "yes" : "warn"}>
                    {correctChain ? "Polygon (137)" : t("trading.wrongChain", { id: chainId })}
                  </Badge>
                  <Badge variant="outline">{account.connector?.name ?? "injected"}</Badge>
                </div>
              </div>
              <div className="flex gap-2">
                {!correctChain && (
                  <Button variant="outline" onClick={() => switchChain({ chainId: POLYGON_CHAIN_ID })}>
                    {t("trading.switchPolygon")}
                  </Button>
                )}
                <Button variant="ghost" onClick={() => disconnect()}>{t("trading.disconnect")}</Button>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              <p className="text-sm text-muted">{t("trading.noWallet")}</p>
              <div className="flex flex-wrap gap-2">
                {connectors.map((connector) => (
                  <Button key={connector.uid} onClick={() => connect({ connector })} disabled={connecting}>
                    {connecting ? t("trading.connecting") : t("trading.connect", { name: connector.name })}
                  </Button>
                ))}
              </div>
              {connectors.length === 0 && (
                <p className="text-xs text-warn">{t("trading.noInjected")}</p>
              )}
              {connectError && <p className="text-xs text-no">{connectError.message}</p>}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>{t("trading.geoCard")}</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {geo ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={geo.mode === "OK" ? "yes" : geo.mode === "CLOSE_ONLY" ? "warn" : "no"}>
                  {geo.mode}
                </Badge>
                <span className="text-xs text-muted">
                  {t("trading.countryLine", {
                    country: `${geo.country ?? "?"}${geo.region ? ` / ${geo.region}` : ""}`,
                  })}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>{t("trading.openPositions")} <span className={geo.can_open_position ? "text-yes" : "text-no"}>{geo.can_open_position ? t("trading.allowed") : t("trading.blocked")}</span></div>
                <div>{t("trading.closePositions")} <span className={geo.can_close_position ? "text-yes" : "text-no"}>{geo.can_close_position ? t("trading.allowed") : t("trading.blocked")}</span></div>
              </div>
              {geo.mode === "CLOSE_ONLY" && (
                <Alert variant="danger">{t("modal.closeOnlyStatement")}</Alert>
              )}
              {geo.mode === "BLOCKED" && (
                <Alert variant="danger">
                  {t("trading.blockedAlert",
                     { suffix: geo.fail_closed ? t("trading.failClosedSuffix") : "" })}
                </Alert>
              )}
            </>
          ) : (
            <p className="text-xs text-muted">
              {geoblock.isLoading ? t("trading.checkingGeo") : t("trading.geoUnavailable")}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>{t("trading.balancesCard")}</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {account.isConnected ? (
            <>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <Stat label={t("trading.usdcBalance")} value={formatUsd(balances.data?.usdc_balance ?? null, 2)} />
                <Stat label={t("trading.polBalance")} value={balances.data?.native_balance?.toFixed(4) ?? "—"} />
                <Stat label={t("trading.ctfAllowance")} value={formatUsd(allowance.data?.ctf_exchange_allowance ?? null, 2)} sub={allowance.data ? (allowance.data.ctf_exchange_ok ? t("trading.sufficient") : t("trading.insufficient")) : undefined} />
                <Stat label={t("trading.negAllowance")} value={formatUsd(allowance.data?.neg_risk_exchange_allowance ?? null, 2)} sub={allowance.data ? (allowance.data.neg_risk_exchange_ok ? t("trading.sufficient") : t("trading.insufficient")) : undefined} />
              </div>
              {(balances.data?.warnings?.length ?? 0) > 0 && (
                <p className="text-xs text-warn">⚠ {balances.data!.warnings.join(" · ")}</p>
              )}
              <p className="text-[11px] leading-relaxed text-muted">{t("trading.approvalsNote")}</p>
            </>
          ) : (
            <p className="text-xs text-muted">{t("trading.connectToView")}</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>{t("trading.modeCard")}</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <div className="flex items-center gap-2">
            <Badge variant={live ? "no" : "yes"}>
              {live ? t("trading.liveEnabled") : t("trading.paperMode")}
            </Badge>
            <span className="text-xs text-muted">{t("trading.serverFlag", { value: String(live) })}</span>
          </div>
          {live ? (
            <Alert variant="danger">{t("trading.liveAlert")}</Alert>
          ) : (
            <Alert variant="info">{t("trading.paperAlert")}</Alert>
          )}
          <p className="text-[11px] text-muted">
            {t("trading.limitsLine", {
              notional: formatUsd(settings.data?.max_trade_notional ?? null),
              spread: settings.data?.max_spread_bps ?? "—",
              slippage: settings.data?.max_slippage_bps ?? "—",
              regions: settings.data?.close_only_countries.join(", ") ?? "—",
            })}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
