"use client";

import Link from "next/link";
import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { DataState, DirectionBadge, SortHeader, Stat, useSort } from "@/components/common";
import { Badge, Button, Card, Table, TBody, Td, Th, THead, Tr } from "@/components/ui/primitives";
import { usePaperTrades } from "@/hooks/use-api";
import { api, ApiError } from "@/lib/api-client";
import { useI18n } from "@/lib/i18n";
import { formatCents, formatDateTime, formatNumber, formatSignedUsd, formatUsd } from "@/lib/format";
import type { PaperTrade } from "@/types/api";

export default function PaperTradesPage() {
  const { t } = useI18n();
  const query = usePaperTrades();
  const queryClient = useQueryClient();
  const [closing, setClosing] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const trades = query.data?.paper_trades ?? [];
  const summary = query.data?.summary;
  const { sorted, sortKey, desc, toggle } = useSort<PaperTrade>(trades, "entry_time");

  const closeTrade = async (id: string) => {
    setClosing(id);
    setError(null);
    try {
      await api.closePaperTrade(id); // exit at latest snapshot price
      await queryClient.invalidateQueries({ queryKey: ["paper-trades"] });
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : t("paper.closeFailed"));
    } finally {
      setClosing(null);
    }
  };

  const winRate =
    summary && summary.win_count + summary.loss_count > 0
      ? summary.win_count / (summary.win_count + summary.loss_count)
      : null;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold tracking-tight">{t("paper.title")}</h1>
        <p className="max-w-3xl text-[11px] leading-relaxed text-muted">{t("paper.subtitle")}</p>
      </div>

      {summary && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <Stat label={t("paper.open")} value={summary.open_count} />
          <Stat label={t("paper.closed")} value={summary.closed_count} />
          <Stat
            label={t("paper.realizedPnl")}
            value={formatSignedUsd(summary.total_realized_pnl)}
            tone={summary.total_realized_pnl >= 0 ? "yes" : "no"}
          />
          <Stat
            label={t("paper.unrealizedPnl")}
            value={formatSignedUsd(summary.total_unrealized_pnl)}
            tone={summary.total_unrealized_pnl >= 0 ? "yes" : "no"}
            sub={t("paper.markedNote")}
          />
          <Stat label={t("paper.winRateClosed")} value={winRate != null ? `${(winRate * 100).toFixed(0)}%` : "—"} sub={`${summary.win_count}W / ${summary.loss_count}L`} />
        </div>
      )}

      {error && <div className="text-xs text-no">{error}</div>}

      <Card>
        <DataState
          loading={query.isLoading}
          error={query.error as Error | null}
          empty={sorted.length === 0}
          emptyHint={t("paper.emptyHint")}
          onRetry={() => query.refetch()}
          skeletonRows={6}
        >
          <Table>
            <THead>
              <tr>
                <Th><SortHeader label={t("paper.thEntryTime")} sortId="entry_time" activeKey={sortKey} desc={desc} onToggle={toggle} /></Th>
                <Th>{t("paper.thMarket")}</Th>
                <Th>{t("paper.thSide")}</Th>
                <Th>{t("paper.thSource")}</Th>
                <Th><SortHeader label={t("paper.thEntry")} sortId="entry_price" activeKey={sortKey} desc={desc} onToggle={toggle} /></Th>
                <Th><SortHeader label={t("paper.thNotional")} sortId="notional" activeKey={sortKey} desc={desc} onToggle={toggle} /></Th>
                <Th>{t("paper.thShares")}</Th>
                <Th>{t("paper.thNowExit")}</Th>
                <Th><SortHeader label={t("paper.thPnl")} sortId="pnl" activeKey={sortKey} desc={desc} onToggle={toggle} /></Th>
                <Th>{t("paper.thStatus")}</Th>
                <Th></Th>
              </tr>
            </THead>
            <TBody>
              {sorted.map((trade) => {
                const pnl = trade.status === "CLOSED" ? trade.pnl : trade.unrealized_pnl;
                return (
                  <Tr key={trade.paper_trade_id}>
                    <Td className="text-xs text-muted">{formatDateTime(trade.entry_time)}</Td>
                    <Td className="max-w-xs">
                      <Link href={`/markets/${trade.market_id}`} className="block truncate text-accent hover:underline" title={trade.question}>
                        {trade.question}
                      </Link>
                    </Td>
                    <Td><DirectionBadge direction={trade.direction} /></Td>
                    <Td>
                      <Badge variant={trade.source === "AUTO_SIGNAL" ? "accent" : "outline"}>
                        {trade.source === "AUTO_SIGNAL" ? t("paper.auto") : t("paper.manual")}
                      </Badge>
                    </Td>
                    <Td className="tabular-nums">{formatCents(trade.entry_price)}</Td>
                    <Td className="tabular-nums">{formatUsd(trade.notional, 2)}</Td>
                    <Td className="tabular-nums">{formatNumber(trade.shares)}</Td>
                    <Td className="tabular-nums">
                      {trade.status === "CLOSED" ? formatCents(trade.exit_price) : formatCents(trade.current_price)}
                    </Td>
                    <Td className={`tabular-nums ${pnl != null && pnl < 0 ? "text-no" : pnl != null ? "text-yes" : ""}`}>
                      {formatSignedUsd(pnl)}
                      {trade.status === "OPEN" && pnl != null && (
                        <span className="ml-1 text-[10px] text-muted">{t("paper.unrealizedTag")}</span>
                      )}
                    </Td>
                    <Td><Badge variant={trade.status === "OPEN" ? "accent" : "neutral"}>{trade.status}</Badge></Td>
                    <Td>
                      {trade.status === "OPEN" && (
                        <Button size="sm" variant="outline" onClick={() => closeTrade(trade.paper_trade_id)} disabled={closing === trade.paper_trade_id}>
                          {closing === trade.paper_trade_id ? t("paper.closing") : t("paper.closeAtMkt")}
                        </Button>
                      )}
                    </Td>
                  </Tr>
                );
              })}
            </TBody>
          </Table>
        </DataState>
      </Card>
    </div>
  );
}
