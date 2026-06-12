"use client";

import Link from "next/link";
import * as React from "react";
import {
  ConfidenceBar,
  DataState,
  DirectionBadge,
  RiskFlags,
  SignalDisclaimer,
  SortHeader,
  useSort,
} from "@/components/common";
import { Badge, Button, Card, CardContent, Select, Table, TBody, Td, Th, THead, Tr } from "@/components/ui/primitives";
import { useHotMarkets, useRunScanner, useScannerLatest } from "@/hooks/use-api";
import { useI18n, type MessageKey } from "@/lib/i18n";
import { formatCents, formatDateTime, formatUsd } from "@/lib/format";
import type { HotMarket } from "@/types/api";

const RISK_FLAG_OPTIONS = [
  "LOW_LIQUIDITY", "WIDE_SPREAD", "NEAR_RESOLUTION", "EXTREME_PRICE",
  "LOW_SMART_SAMPLE", "NEW_ACCOUNT_HEAVY", "ONE_SIDED_BOOK", "PARTIAL_DATA",
];

export default function DashboardPage() {
  const { t } = useI18n();
  const [category, setCategory] = React.useState("");
  const [direction, setDirection] = React.useState("");
  const [minConfidence, setMinConfidence] = React.useState("");
  const [minLiquidity, setMinLiquidity] = React.useState("");
  const [excludedFlags, setExcludedFlags] = React.useState<string[]>([]);

  const query = useHotMarkets({
    category: category || undefined,
    direction: direction || undefined,
    min_confidence: minConfidence ? Number(minConfidence) : undefined,
    min_liquidity: minLiquidity ? Number(minLiquidity) : undefined,
  });
  const scanner = useScannerLatest();
  const runScanner = useRunScanner();

  const markets = React.useMemo(() => {
    const rows = query.data?.markets ?? [];
    if (!excludedFlags.length) return rows;
    return rows.filter((m) => !m.risk_flags.some((f) => excludedFlags.includes(f)));
  }, [query.data, excludedFlags]);

  const categories = React.useMemo(() => {
    const set = new Set((query.data?.markets ?? []).map((m) => m.category).filter(Boolean));
    return [...set] as string[];
  }, [query.data]);

  const { sorted, sortKey, desc, toggle } = useSort<HotMarket>(markets, "volume_24h");
  const scan = scanner.data;
  const scanning = scan?.status === "running";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight">{t("dash.title")}</h1>
          <SignalDisclaimer />
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right text-xs text-muted">
            {scanning ? (
              <>
                <span className="text-accent">{t("dash.scanning")}</span> {scan?.current_step}
                <br />
                {t("dash.scanCount", { analyzed: scan?.markets_analyzed ?? 0,
                                       found: scan?.markets_found ?? 0 })}
              </>
            ) : scan?.scan_id ? (
              <>
                {t("dash.lastScan", { status: scan.status, analyzed: scan.markets_analyzed,
                                      signals: scan.signals_generated })}
                <br />
                {formatDateTime(scan.finished_at ?? scan.started_at)}
                {scan.errors.length > 0 && (
                  <span className="text-warn"> · {t("dash.errors", { n: scan.errors.length })}</span>
                )}
              </>
            ) : (
              t("dash.notRunYet")
            )}
          </div>
          <Button onClick={() => runScanner.mutate()} disabled={scanning || runScanner.isPending}>
            {scanning ? t("dash.scanning") : t("dash.runScanner")}
          </Button>
          <Button variant="outline" onClick={() => query.refetch()}>
            {t("dash.refresh")}
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="flex flex-wrap items-center gap-2 pt-4">
          <Select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category filter">
            <option value="">{t("dash.allCategories")}</option>
            {categories.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </Select>
          <Select value={direction} onChange={(e) => setDirection(e.target.value)} aria-label="Direction filter">
            <option value="">{t("dash.anyDirection")}</option>
            <option value="YES">YES</option>
            <option value="NO">NO</option>
            <option value="NEUTRAL">{t("common.neutral")}</option>
          </Select>
          <Select value={minConfidence} onChange={(e) => setMinConfidence(e.target.value)} aria-label="Confidence filter">
            <option value="">{t("dash.anyConfidence")}</option>
            {["40", "60", "75"].map((n) => (
              <option key={n} value={n}>{t("dash.confGte", { n })}</option>
            ))}
          </Select>
          <Select value={minLiquidity} onChange={(e) => setMinLiquidity(e.target.value)} aria-label="Liquidity filter">
            <option value="">{t("dash.anyLiquidity")}</option>
            {[["10000", "10k"], ["50000", "50k"], ["250000", "250k"]].map(([value, label]) => (
              <option key={value} value={value}>{t("dash.liqGte", { n: label })}</option>
            ))}
          </Select>
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-[11px] uppercase tracking-wider text-muted">{t("dash.exclude")}</span>
            {RISK_FLAG_OPTIONS.map((flag) => {
              const active = excludedFlags.includes(flag);
              return (
                <button
                  key={flag}
                  onClick={() =>
                    setExcludedFlags((prev) =>
                      active ? prev.filter((f) => f !== flag) : [...prev, flag],
                    )
                  }
                  title={t("dash.excludeTooltip", { flag })}
                >
                  <Badge variant={active ? "warn" : "outline"}>
                    {t(`flags.${flag}` as MessageKey)}
                  </Badge>
                </button>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <Card>
        <DataState
          loading={query.isLoading}
          error={query.error as Error | null}
          empty={sorted.length === 0}
          emptyHint={t("dash.emptyHint")}
          onRetry={() => query.refetch()}
          skeletonRows={8}
        >
          <Table>
            <THead>
              <tr>
                <Th>{t("dash.thMarket")}</Th>
                <Th>{t("dash.thCategory")}</Th>
                <Th><SortHeader label={t("dash.thYes")} sortId="yes_price" activeKey={sortKey} desc={desc} onToggle={toggle} /></Th>
                <Th><SortHeader label={t("dash.thNo")} sortId="no_price" activeKey={sortKey} desc={desc} onToggle={toggle} /></Th>
                <Th><SortHeader label={t("dash.thSpread")} sortId="spread" activeKey={sortKey} desc={desc} onToggle={toggle} /></Th>
                <Th><SortHeader label={t("dash.thVol")} sortId="volume_24h" activeKey={sortKey} desc={desc} onToggle={toggle} /></Th>
                <Th><SortHeader label={t("dash.thLiquidity")} sortId="liquidity" activeKey={sortKey} desc={desc} onToggle={toggle} /></Th>
                <Th><SortHeader label={t("dash.thOi")} sortId="open_interest" activeKey={sortKey} desc={desc} onToggle={toggle} title={t("dash.oiTooltip")} /></Th>
                <Th>{t("dash.thSmart")}</Th>
                <Th><SortHeader label={t("dash.thConf")} sortId="confidence_score" activeKey={sortKey} desc={desc} onToggle={toggle} title={t("common.confidenceTooltip")} /></Th>
                <Th>{t("dash.thRiskFlags")}</Th>
              </tr>
            </THead>
            <TBody>
              {sorted.map((m) => (
                <Tr key={m.market_id}>
                  <Td className="max-w-md">
                    <Link href={`/markets/${m.market_id}`} className="block truncate text-accent hover:underline" title={m.question}>
                      {m.question}
                    </Link>
                    <span className="text-[10px] text-muted">
                      {t("dash.analyzedAt", { time: formatDateTime(m.last_analyzed_at) })}
                    </span>
                  </Td>
                  <Td><Badge variant="outline">{m.category ?? "—"}</Badge></Td>
                  <Td className="tabular-nums text-yes">{formatCents(m.yes_price)}</Td>
                  <Td className="tabular-nums text-no">{formatCents(m.no_price)}</Td>
                  <Td className="tabular-nums">{m.spread != null ? formatCents(m.spread) : "—"}</Td>
                  <Td className="tabular-nums">{formatUsd(m.volume_24h)}</Td>
                  <Td className="tabular-nums">{formatUsd(m.liquidity)}</Td>
                  <Td className="tabular-nums">{formatUsd(m.open_interest)}</Td>
                  <Td><DirectionBadge direction={m.smart_money_direction} /></Td>
                  <Td><ConfidenceBar score={m.confidence_score} /></Td>
                  <Td><RiskFlags flags={m.risk_flags} max={2} /></Td>
                </Tr>
              ))}
            </TBody>
          </Table>
        </DataState>
      </Card>
      {(query.data?.warnings?.length ?? 0) > 0 && (
        <div className="text-xs text-warn">⚠ {query.data!.warnings.join(" · ")}</div>
      )}
    </div>
  );
}
