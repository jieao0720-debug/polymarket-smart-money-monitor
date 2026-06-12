"use client";

/** Shared domain components: states, address chip, badges, sortable tables. */
import * as React from "react";
import { Badge, Button, Skeleton } from "@/components/ui/primitives";
import { useI18n, type MessageKey } from "@/lib/i18n";
import { riskFlagLabel, shortAddress } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AccountLabel, SignalDirection } from "@/types/api";

// ------------------------------------------------------------- loading/empty/error
export function DataState({
  loading,
  error,
  empty,
  emptyHint,
  onRetry,
  children,
  skeletonRows = 4,
}: {
  loading: boolean;
  error: Error | null;
  empty?: boolean;
  emptyHint?: React.ReactNode;
  onRetry?: () => void;
  children?: React.ReactNode;
  skeletonRows?: number;
}) {
  const { t } = useI18n();
  if (loading) {
    return (
      <div className="space-y-2 p-4" data-testid="loading-state">
        {Array.from({ length: skeletonRows }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex flex-col items-center gap-3 p-8 text-center" data-testid="error-state">
        <div className="text-sm font-medium text-no">{t("common.failedToLoad")}</div>
        <div className="max-w-md text-xs text-muted">{error.message}</div>
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            {t("common.retry")}
          </Button>
        )}
      </div>
    );
  }
  if (empty) {
    return (
      <div className="flex flex-col items-center gap-2 p-8 text-center" data-testid="empty-state">
        <div className="text-sm text-muted">{t("common.noData")}</div>
        {emptyHint && <div className="max-w-md text-xs text-muted">{emptyHint}</div>}
      </div>
    );
  }
  return <>{children}</>;
}

// ------------------------------------------------------------- address chip
export function AddressChip({
  address,
  name,
  onClick,
}: {
  address: string;
  name?: string | null;
  onClick?: () => void;
}) {
  const { t } = useI18n();
  const [copied, setCopied] = React.useState(false);
  const copy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(address);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      /* clipboard unavailable */
    }
  };
  return (
    <span className="inline-flex items-center gap-1.5">
      <button
        onClick={onClick}
        className={cn(
          "font-mono text-xs",
          onClick ? "text-accent hover:underline cursor-pointer" : "text-foreground",
        )}
        title={address}
      >
        {name ? `${name} (${shortAddress(address)})` : shortAddress(address)}
      </button>
      <button
        onClick={copy}
        className="text-[10px] text-muted hover:text-foreground"
        title={t("common.copyAddress")}
        aria-label={t("common.copyAddress")}
      >
        {copied ? "✓" : "⧉"}
      </button>
    </span>
  );
}

// ------------------------------------------------------------- direction / label badges
export function DirectionBadge({ direction }: { direction: SignalDirection | null }) {
  const { t } = useI18n();
  if (!direction || direction === "NEUTRAL") {
    return <Badge variant="neutral">{t("common.neutral")}</Badge>;
  }
  return <Badge variant={direction === "YES" ? "yes" : "no"}>{direction}</Badge>;
}

const LABEL_VARIANTS: Record<AccountLabel, "yes" | "warn" | "neutral" | "accent"> = {
  HIGH_WIN_RATE: "yes",
  ABNORMAL_POSITION: "warn",
  NEW_ACCOUNT: "accent",
  OTHER: "neutral",
};

export function AccountLabelBadge({ label }: { label: AccountLabel }) {
  const { t } = useI18n();
  const variant = LABEL_VARIANTS[label] ?? "neutral";
  const key = (`labels.${label in LABEL_VARIANTS ? label : "OTHER"}`) as MessageKey;
  return <Badge variant={variant}>{t(key)}</Badge>;
}

// ------------------------------------------------------------- risk flags
export function RiskFlags({ flags, max }: { flags: string[]; max?: number }) {
  const { locale, t } = useI18n();
  if (!flags?.length) return <span className="text-xs text-muted">—</span>;
  const shown = max ? flags.slice(0, max) : flags;
  const label = (flag: string) => {
    const key = `flags.${flag}` as MessageKey;
    const translated = t(key);
    // Unknown flags fall back to a humanized English label.
    return translated === key ? riskFlagLabel(flag) : translated;
  };
  void locale;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {shown.map((flag) => (
        <Badge key={flag} variant="warn" title={flag}>
          {label(flag)}
        </Badge>
      ))}
      {max && flags.length > max && <Badge variant="outline">+{flags.length - max}</Badge>}
    </span>
  );
}

// ------------------------------------------------------------- confidence
export function ConfidenceBar({ score }: { score: number | null }) {
  const { t } = useI18n();
  if (score === null || score === undefined) return <span className="text-xs text-muted">—</span>;
  const color = score >= 70 ? "bg-yes" : score >= 40 ? "bg-warn" : "bg-neutral";
  return (
    <span className="inline-flex items-center gap-2" title={t("common.confidenceTooltip")}>
      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-2">
        <span className={cn("block h-full rounded-full", color)} style={{ width: `${Math.min(100, score)}%` }} />
      </span>
      <span className="text-xs tabular-nums text-foreground">{score.toFixed(0)}</span>
    </span>
  );
}

// ------------------------------------------------------------- stat card
export function Stat({ label, value, sub, tone }: { label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: "yes" | "no" }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-3">
      <div className="text-[11px] uppercase tracking-wider text-muted">{label}</div>
      <div className={cn("mt-1 text-lg font-semibold tabular-nums", tone === "yes" && "text-yes", tone === "no" && "text-no")}>
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
    </div>
  );
}

// ------------------------------------------------------------- sortable header
export function useSort<T>(rows: T[], initialKey: string, initialDesc = true) {
  const [sortKey, setSortKey] = React.useState(initialKey);
  const [desc, setDesc] = React.useState(initialDesc);

  const sorted = React.useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = (a as Record<string, unknown>)[sortKey];
      const bv = (b as Record<string, unknown>)[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") return desc ? bv - av : av - bv;
      return desc ? String(bv).localeCompare(String(av)) : String(av).localeCompare(String(bv));
    });
    return copy;
  }, [rows, sortKey, desc]);

  const toggle = (key: string) => {
    if (key === sortKey) setDesc((d) => !d);
    else {
      setSortKey(key);
      setDesc(true);
    }
  };
  return { sorted, sortKey, desc, toggle };
}

export function SortHeader({
  label,
  sortId,
  activeKey,
  desc,
  onToggle,
  title,
}: {
  label: string;
  sortId: string;
  activeKey: string;
  desc: boolean;
  onToggle: (key: string) => void;
  title?: string;
}) {
  const active = activeKey === sortId;
  return (
    <button
      className={cn("inline-flex items-center gap-1 uppercase tracking-wider", active ? "text-foreground" : "text-muted hover:text-foreground")}
      onClick={() => onToggle(sortId)}
      title={title}
    >
      {label}
      <span className="text-[9px]">{active ? (desc ? "▼" : "▲") : "↕"}</span>
    </button>
  );
}

export function SignalDisclaimer() {
  const { t } = useI18n();
  return (
    <p className="text-[11px] leading-relaxed text-muted">{t("common.signalDisclaimer")}</p>
  );
}
