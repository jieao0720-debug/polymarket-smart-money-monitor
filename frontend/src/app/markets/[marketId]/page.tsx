"use client";

import { useParams } from "next/navigation";
import * as React from "react";
import { useAccount, useChainId, useSignTypedData } from "wagmi";
import { AccountDrawer } from "@/components/account-drawer";
import {
  AccountLabelBadge,
  AddressChip,
  ConfidenceBar,
  DataState,
  DirectionBadge,
  RiskFlags,
  SignalDisclaimer,
  SortHeader,
  Stat,
  useSort,
} from "@/components/common";
import { SmartMoneyNotionalChart } from "@/components/smart-money-chart";
import { TradeTicketModal } from "@/components/trade-ticket-modal";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Table, TBody, Td, Th, THead, Tr } from "@/components/ui/primitives";
import { useGeoblock, useMarketAnalysis, usePublicSettings } from "@/hooks/use-api";
import { useI18n } from "@/lib/i18n";
import { POLYGON_CHAIN_ID } from "@/lib/wagmi";
import { formatCents, formatDateTime, formatNumber, formatPercent, formatUsd } from "@/lib/format";
import type { HolderEntry } from "@/types/api";

export default function MarketDetailPage() {
  const { t } = useI18n();
  const params = useParams<{ marketId: string }>();
  const marketId = params.marketId;
  const [refreshing, setRefreshing] = React.useState(false);
  const query = useMarketAnalysis(marketId);
  const settings = usePublicSettings();
  const geoblock = useGeoblock();
  const account = useAccount();
  const chainId = useChainId();
  const { signTypedDataAsync } = useSignTypedData();

  const [drawerAddress, setDrawerAddress] = React.useState<string | null>(null);
  const [ticketDirection, setTicketDirection] = React.useState<"YES" | "NO" | null>(null);

  const data = query.data;
  const holders = data?.holders ?? [];
  const { sorted, sortKey, desc, toggle } = useSort<HolderEntry>(holders, "current_position_value");

  const refresh = async () => {
    setRefreshing(true);
    try {
      const { api } = await import("@/lib/api-client");
      await api.marketAnalysis(marketId, true);
      await query.refetch();
    } catch {
      /* surfaced via query state on refetch */
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="space-y-4">
      <DataState
        loading={query.isLoading}
        error={query.error as Error | null}
        empty={!data}
        onRetry={() => query.refetch()}
        skeletonRows={10}
      >
        {data && (
          <>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <h1 className="text-lg font-bold leading-snug">{data.market.question}</h1>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                  <Badge variant="outline">{data.market.category ?? "—"}</Badge>
                  <span>{t("market.ends", { time: formatDateTime(data.market.end_date) })}</span>
                  <span>·</span>
                  <span>
                    {data.market.active && !data.market.closed
                      ? t("market.active") : t("market.inactiveClosed")}
                    {data.market.accepting_orders ? "" : ` · ${t("market.notAccepting")}`}
                  </span>
                  {data.market.neg_risk && <Badge variant="outline">neg-risk</Badge>}
                  <span>· {t("market.analyzedAt", { time: formatDateTime(data.summary.snapshot_time) })}</span>
                </div>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" onClick={refresh} disabled={refreshing}>
                  {refreshing ? t("market.reanalyzing") : t("market.reanalyze")}
                </Button>
                <Button
                  onClick={() =>
                    setTicketDirection(data.summary.net_direction === "NO" ? "NO" : "YES")
                  }
                >
                  {t("market.generateTicket")}
                </Button>
              </div>
            </div>

            {data.warnings.length > 0 && (
              <div className="text-xs text-warn">⚠ {data.warnings.join(" · ")}</div>
            )}

            <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
              <Stat label={t("market.statYes")} value={formatCents(data.market.yes_price)} tone="yes" />
              <Stat label={t("market.statNo")} value={formatCents(data.market.no_price)} tone="no" />
              <Stat label={t("market.statSpread")} value={formatCents(data.market.spread)} />
              <Stat label={t("market.statLiquidity")} value={formatUsd(data.market.liquidity)} />
              <Stat label={t("market.statVol")} value={formatUsd(data.market.volume_24h)} />
              <Stat label={t("market.statOi")} value={formatUsd(data.market.open_interest)} sub={t("market.eventLevel")} />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader className="flex-row items-center justify-between">
                  <CardTitle>{t("market.summaryTitle")}</CardTitle>
                  <DirectionBadge direction={data.summary.net_direction} />
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <Stat
                      label={t("market.yesSmart")}
                      value={formatUsd(data.summary.yes_smart_money_notional, 2)}
                      sub={t("market.holdersCount", { n: data.summary.yes_smart_money_count })}
                      tone="yes"
                    />
                    <Stat
                      label={t("market.noSmart")}
                      value={formatUsd(data.summary.no_smart_money_notional, 2)}
                      sub={t("market.holdersCount", { n: data.summary.no_smart_money_count })}
                      tone="no"
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted">{t("market.confLine")}</span>
                    <ConfidenceBar score={data.summary.confidence_score} />
                  </div>
                  <div>
                    <span className="mr-2 text-[11px] uppercase tracking-wider text-muted">{t("market.riskFlags")}</span>
                    <RiskFlags flags={data.summary.risk_flags} />
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <div className="flex justify-between"><span className="text-muted">{t("market.suggPrice")}</span><span className="tabular-nums">{formatCents(data.summary.suggested_limit_price)}</span></div>
                    <div className="flex justify-between"><span className="text-muted">{t("market.suggMax")}</span><span className="tabular-nums">{formatUsd(data.summary.suggested_max_notional, 2)}</span></div>
                  </div>
                  <SignalDisclaimer />
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>{t("market.chartTitle")}</CardTitle>
                </CardHeader>
                <CardContent>
                  <SmartMoneyNotionalChart
                    yesNotional={data.summary.yes_smart_money_notional}
                    noNotional={data.summary.no_smart_money_notional}
                  />
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <CardTitle>{t("market.holdersTitle")}</CardTitle>
              </CardHeader>
              <DataState
                loading={false}
                error={null}
                empty={holders.length === 0}
                emptyHint={t("market.holdersEmpty")}
              >
                <Table>
                  <THead>
                    <tr>
                      <Th>{t("market.thRank")}</Th>
                      <Th>{t("market.thAddress")}</Th>
                      <Th>{t("market.thSide")}</Th>
                      <Th><SortHeader label={t("market.thPosValue")} sortId="current_position_value" activeKey={sortKey} desc={desc} onToggle={toggle} /></Th>
                      <Th><SortHeader label={t("market.thShares")} sortId="shares" activeKey={sortKey} desc={desc} onToggle={toggle} /></Th>
                      <Th><SortHeader label={t("market.thAvgPx")} sortId="average_price" activeKey={sortKey} desc={desc} onToggle={toggle} /></Th>
                      <Th>{t("market.thLabel")}</Th>
                      <Th><SortHeader label={t("market.thWinRate")} sortId="win_rate" activeKey={sortKey} desc={desc} onToggle={toggle} /></Th>
                      <Th><SortHeader label={t("market.thResolved")} sortId="resolved_trade_count" activeKey={sortKey} desc={desc} onToggle={toggle} /></Th>
                      <Th><SortHeader label={t("market.thCatWr")} sortId="same_category_win_rate" activeKey={sortKey} desc={desc} onToggle={toggle} title={t("market.catWrTooltip")} /></Th>
                      <Th><SortHeader label={t("market.thAnomaly")} sortId="anomaly_index" activeKey={sortKey} desc={desc} onToggle={toggle} title={t("market.anomalyTooltip")} /></Th>
                      <Th><SortHeader label={t("market.thScore")} sortId="smart_money_score" activeKey={sortKey} desc={desc} onToggle={toggle} /></Th>
                    </tr>
                  </THead>
                  <TBody>
                    {sorted.map((h) => (
                      <Tr key={`${h.address}-${h.direction}`} className="cursor-pointer" onClick={() => setDrawerAddress(h.address)}>
                        <Td className="text-muted">#{h.rank}</Td>
                        <Td><AddressChip address={h.address} name={h.profile_name} onClick={() => setDrawerAddress(h.address)} /></Td>
                        <Td><DirectionBadge direction={h.direction} /></Td>
                        <Td className="tabular-nums">
                          {formatUsd(h.current_position_value, 2)}
                          {h.value_is_approx && <span className="ml-1 text-[10px] text-warn" title={t("market.approxTooltip")}>≈</span>}
                        </Td>
                        <Td className="tabular-nums">{formatNumber(h.shares)}</Td>
                        <Td className="tabular-nums">{formatCents(h.average_price)}</Td>
                        <Td><AccountLabelBadge label={h.label} /></Td>
                        <Td className="tabular-nums">{h.resolved_trade_count > 0 ? formatPercent(h.win_rate) : "—"}</Td>
                        <Td className="tabular-nums">{h.resolved_trade_count}{h.history_truncated ? "+" : ""}</Td>
                        <Td className="tabular-nums">{h.same_category_trade_count > 0 ? formatPercent(h.same_category_win_rate) : "—"}</Td>
                        <Td className="tabular-nums">{h.anomaly_index != null ? `${h.anomaly_index.toFixed(1)}×` : "—"}</Td>
                        <Td className="tabular-nums font-medium">{h.smart_money_score.toFixed(0)}</Td>
                      </Tr>
                    ))}
                  </TBody>
                </Table>
              </DataState>
            </Card>

            <AccountDrawer
              address={drawerAddress}
              marketId={marketId}
              onClose={() => setDrawerAddress(null)}
            />

            {ticketDirection && (
              <TradeTicketModal
                open={!!ticketDirection}
                onClose={() => setTicketDirection(null)}
                market={data.market}
                summary={data.summary}
                direction={ticketDirection}
                wallet={{
                  address: account.address,
                  connected: account.isConnected,
                  correctChain: chainId === POLYGON_CHAIN_ID,
                }}
                geoblock={geoblock.data ?? null}
                liveTradingEnabled={settings.data?.enable_live_trading ?? false}
                signTypedData={async (args) =>
                  signTypedDataAsync(args as unknown as Parameters<typeof signTypedDataAsync>[0])
                }
              />
            )}
          </>
        )}
      </DataState>
    </div>
  );
}
