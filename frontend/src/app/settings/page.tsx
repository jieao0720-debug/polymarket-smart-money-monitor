"use client";

import { DataState } from "@/components/common";
import { LanguageSwitcher } from "@/components/language-switcher";
import { Badge, Card, CardContent, CardHeader, CardTitle } from "@/components/ui/primitives";
import { useHealth, usePublicSettings } from "@/hooks/use-api";
import { API_BASE } from "@/lib/api-client";
import { useI18n } from "@/lib/i18n";

function Row({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border/50 py-2 text-sm">
      <span className="text-muted" title={hint}>{label}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  );
}

export default function SettingsPage() {
  const { t } = useI18n();
  const settings = usePublicSettings();
  const health = useHealth();
  const s = settings.data;

  return (
    <div className="max-w-2xl space-y-4">
      <div>
        <h1 className="text-xl font-bold tracking-tight">{t("settings.title")}</h1>
        <p className="text-[11px] text-muted">{t("settings.subtitle")}</p>
      </div>

      <Card>
        <CardHeader><CardTitle>{t("settings.prefsCard")}</CardTitle></CardHeader>
        <CardContent>
          <div className="flex items-center justify-between py-2 text-sm">
            <div>
              <div className="text-muted">{t("settings.language")}</div>
              <div className="text-[11px] text-muted/70">{t("settings.languageHint")}</div>
            </div>
            <LanguageSwitcher />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>{t("settings.backendCard")}</CardTitle></CardHeader>
        <CardContent>
          <DataState loading={health.isLoading} error={health.error as Error | null} onRetry={() => health.refetch()}>
            <Row label={t("settings.apiBase")} value={<span className="font-mono text-xs">{API_BASE}</span>} />
            <Row label={t("settings.status")} value={<Badge variant={health.data?.status === "ok" ? "yes" : "warn"}>{health.data?.status ?? "—"}</Badge>} />
            <Row label={t("settings.database")} value={health.data?.database ?? "—"} />
            <Row label={t("settings.version")} value={health.data?.version ?? "—"} />
            <Row label={t("settings.scheduler")} value={health.data?.scheduler_running ? t("settings.running") : t("settings.schedulerOff")} />
          </DataState>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>{t("settings.safetyCard")}</CardTitle></CardHeader>
        <CardContent>
          <DataState loading={settings.isLoading} error={settings.error as Error | null} onRetry={() => settings.refetch()}>
            {s && (
              <>
                <Row label="ENABLE_LIVE_TRADING" value={<Badge variant={s.enable_live_trading ? "no" : "yes"}>{String(s.enable_live_trading)}</Badge>} />
                <Row label="MAX_TRADE_NOTIONAL" value={`$${s.max_trade_notional}`} />
                <Row
                  label="MAX_SPREAD_BPS"
                  value={t("settings.spreadBpsValue", { bps: s.max_spread_bps, abs: (s.max_spread_bps / 10000).toFixed(4) })}
                  hint={t("settings.bpsHint")}
                />
                <Row label="MAX_SLIPPAGE_BPS" value={`${s.max_slippage_bps} bps`} />
                <Row label="MIN_LIQUIDITY" value={`$${s.min_liquidity}`} />
                <Row label="MIN_POSITION_VALUE" value={`$${s.min_position_value}`} />
                <Row label={t("settings.closeOnlyRegions")} value={s.close_only_countries.join(", ")} />
              </>
            )}
          </DataState>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>{t("settings.scannerCard")}</CardTitle></CardHeader>
        <CardContent>
          {s && (
            <>
              <Row label={t("settings.maxMarkets")} value={s.scanner_max_markets} />
              <Row
                label={t("settings.interval")}
                value={s.scanner_interval_minutes > 0
                  ? t("settings.intervalMin", { n: s.scanner_interval_minutes })
                  : t("settings.intervalDisabled")}
              />
              <Row label={t("settings.scoreThreshold")} value={s.smart_money_score_threshold} />
              <Row label={t("settings.nearResFlag")} value={t("settings.nearResValue", { h: s.near_resolution_hours })} />
              <Row label={t("settings.autoPaper")} value={String(s.paper_trade_auto_log)} />
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>{t("settings.disclaimersCard")}</CardTitle></CardHeader>
        <CardContent className="space-y-2 text-xs leading-relaxed text-muted">
          <p>{t("settings.d1")}</p>
          <p>{t("settings.d2")}</p>
          <p>{t("settings.d3")}</p>
          <p>{t("settings.d4")}</p>
          <p>{t("settings.d5")}</p>
          <p>{t("settings.d6")}</p>
        </CardContent>
      </Card>
    </div>
  );
}
