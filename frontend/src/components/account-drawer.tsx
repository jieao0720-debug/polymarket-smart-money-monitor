"use client";

import * as React from "react";
import { AccountLabelBadge, AddressChip, DataState, DirectionBadge } from "@/components/common";
import { Badge, Drawer } from "@/components/ui/primitives";
import { useAccountProfile } from "@/hooks/use-api";
import { useI18n } from "@/lib/i18n";
import { formatDate, formatPercent, formatPrice, formatSignedUsd, formatUsd, formatNumber } from "@/lib/format";

function Row({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border/50 py-2 text-sm" title={hint}>
      <span className="text-muted">{label}{hint ? " ⓘ" : ""}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  );
}

export function AccountDrawer({
  address,
  marketId,
  onClose,
}: {
  address: string | null;
  marketId?: string;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const query = useAccountProfile(address, marketId);
  const profile = query.data;

  return (
    <Drawer
      open={!!address}
      onClose={onClose}
      title={address ? <AddressChip address={address} name={profile?.profile_name} /> : null}
    >
      <DataState
        loading={query.isLoading}
        error={query.error as Error | null}
        empty={!profile}
        onRetry={() => query.refetch()}
        skeletonRows={8}
      >
        {profile && (
          <div className="space-y-5">
            <section>
              <h4 className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">
                {t("drawer.overallTitle")}
              </h4>
              {profile.history_truncated && (
                <p className="mb-2 text-[11px] text-warn">{t("drawer.truncated")}</p>
              )}
              <Row label={t("drawer.resolvedPositions")} value={profile.overall.resolved_trade_count} />
              <Row label={t("drawer.winRate")} value={formatPercent(profile.overall.win_rate)} />
              <Row
                label={t("drawer.realizedPnl")}
                value={
                  <span className={profile.overall.realized_pnl >= 0 ? "text-yes" : "text-no"}>
                    {formatSignedUsd(profile.overall.realized_pnl)}
                  </span>
                }
              />
              <Row label={t("drawer.avgRoi")} value={formatPercent(profile.overall.average_roi, 1)} />
              <Row label={t("drawer.medianEntry")} value={formatUsd(profile.overall.median_entry_notional, 2)} />
              <Row label={t("drawer.firstSeen")} value={formatDate(profile.first_seen_at)} />
              <Row label={t("drawer.lastSeen")} value={formatDate(profile.last_seen_at)} />
            </section>

            {profile.same_category && (
              <section>
                <h4 className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">
                  {t("drawer.sameCatTitle")}
                  {profile.same_category.category ? ` · ${profile.same_category.category}` : ""}
                  <span className="ml-1 normal-case text-muted">{t("drawer.keywordApprox")}</span>
                </h4>
                <Row label={t("drawer.trades")} value={profile.same_category.trade_count} />
                <Row label={t("drawer.winRate")} value={formatPercent(profile.same_category.win_rate)} />
                <Row label={t("drawer.avgRoi")} value={formatPercent(profile.same_category.average_roi, 1)} />
              </section>
            )}

            {profile.current_market && (
              <section>
                <h4 className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">
                  {t("drawer.currentMarketTitle")}
                </h4>
                <Row label={t("drawer.direction")} value={<DirectionBadge direction={profile.current_market.direction} />} />
                <Row label={t("drawer.shares")} value={formatNumber(profile.current_market.shares)} />
                <Row label={t("drawer.avgPrice")} value={formatPrice(profile.current_market.average_price)} />
                <Row label={t("drawer.posValue")} value={formatUsd(profile.current_market.current_position_value, 2)} />
                <Row
                  label={t("drawer.entryApprox")}
                  hint={t("drawer.entryApproxHint")}
                  value={formatUsd(profile.current_market.entry_notional_approx, 2)}
                />
                <Row
                  label={t("drawer.anomalyIndex")}
                  hint={t("drawer.anomalyHint")}
                  value={profile.current_market.anomaly_index?.toFixed(1) ?? "—"}
                />
                <Row label={t("drawer.smartScore")} value={profile.current_market.smart_money_score.toFixed(1)} />
                <Row label={t("drawer.label")} value={<AccountLabelBadge label={profile.current_market.label} />} />
                <p className="mt-2 text-xs leading-relaxed text-muted">{profile.current_market.label_reason}</p>
              </section>
            )}

            {profile.warnings.length > 0 && (
              <div className="space-y-1">
                {profile.warnings.map((w) => (
                  <Badge key={w} variant="warn" className="block whitespace-normal normal-case">
                    {w}
                  </Badge>
                ))}
              </div>
            )}
            <p className="text-[10px] text-muted">
              {t("drawer.asOfNote", { date: formatDate(profile.as_of) })}
            </p>
          </div>
        )}
      </DataState>
    </Drawer>
  );
}
