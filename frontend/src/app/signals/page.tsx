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
import { Badge, Card, Select, Table, TBody, Td, Th, THead, Tr } from "@/components/ui/primitives";
import { useSignals } from "@/hooks/use-api";
import { useI18n } from "@/lib/i18n";
import { formatCents, formatDateTime, formatUsd } from "@/lib/format";
import type { SignalEntry } from "@/types/api";

export default function SignalsPage() {
  const { t } = useI18n();
  const [direction, setDirection] = React.useState("");
  const [minConfidence, setMinConfidence] = React.useState("");
  const query = useSignals({
    direction: direction || undefined,
    min_confidence: minConfidence ? Number(minConfidence) : undefined,
  });
  const signals = query.data?.signals ?? [];
  const { sorted, sortKey, desc, toggle } = useSort<SignalEntry>(signals, "snapshot_time");

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold tracking-tight">{t("signals.title")}</h1>
        <SignalDisclaimer />
      </div>

      <div className="flex gap-2">
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
      </div>

      <Card>
        <DataState
          loading={query.isLoading}
          error={query.error as Error | null}
          empty={sorted.length === 0}
          emptyHint={t("signals.emptyHint")}
          onRetry={() => query.refetch()}
          skeletonRows={8}
        >
          <Table>
            <THead>
              <tr>
                <Th><SortHeader label={t("signals.thTime")} sortId="snapshot_time" activeKey={sortKey} desc={desc} onToggle={toggle} /></Th>
                <Th>{t("dash.thMarket")}</Th>
                <Th>{t("dash.thCategory")}</Th>
                <Th>{t("signals.thDirection")}</Th>
                <Th><SortHeader label={t("dash.thConf")} sortId="confidence_score" activeKey={sortKey} desc={desc} onToggle={toggle} title={t("common.confidenceTooltip")} /></Th>
                <Th><SortHeader label={t("signals.thYesSmart")} sortId="yes_smart_money_notional" activeKey={sortKey} desc={desc} onToggle={toggle} /></Th>
                <Th><SortHeader label={t("signals.thNoSmart")} sortId="no_smart_money_notional" activeKey={sortKey} desc={desc} onToggle={toggle} /></Th>
                <Th>{t("signals.thCounts")}</Th>
                <Th>{t("signals.thSuggPrice")}</Th>
                <Th>{t("signals.thSuggMax")}</Th>
                <Th>{t("dash.thRiskFlags")}</Th>
              </tr>
            </THead>
            <TBody>
              {sorted.map((s) => (
                <Tr key={s.signal_id}>
                  <Td className="text-xs text-muted">{formatDateTime(s.snapshot_time)}</Td>
                  <Td className="max-w-xs">
                    <Link href={`/markets/${s.market_id}`} className="block truncate text-accent hover:underline" title={s.question}>
                      {s.question}
                    </Link>
                  </Td>
                  <Td><Badge variant="outline">{s.category ?? "—"}</Badge></Td>
                  <Td><DirectionBadge direction={s.direction} /></Td>
                  <Td><ConfidenceBar score={s.confidence_score} /></Td>
                  <Td className="tabular-nums text-yes">{formatUsd(s.yes_smart_money_notional, 2)}</Td>
                  <Td className="tabular-nums text-no">{formatUsd(s.no_smart_money_notional, 2)}</Td>
                  <Td className="text-xs text-muted">{s.yes_smart_money_count}Y / {s.no_smart_money_count}N</Td>
                  <Td className="tabular-nums">{formatCents(s.suggested_limit_price)}</Td>
                  <Td className="tabular-nums">{formatUsd(s.suggested_max_notional, 2)}</Td>
                  <Td><RiskFlags flags={s.risk_flags} max={2} /></Td>
                </Tr>
              ))}
            </TBody>
          </Table>
        </DataState>
      </Card>
    </div>
  );
}
