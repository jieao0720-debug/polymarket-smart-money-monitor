"""Account classification (NEW_ACCOUNT / HIGH_WIN_RATE / ABNORMAL_POSITION / OTHER)
and smart-money scoring orchestration.

Classification rules (spec, verbatim):
  NEW_ACCOUNT:        resolved_trade_count_before_signal_time == 0
  HIGH_WIN_RATE:      resolved_trade_count >= 20 AND win_rate >= 0.60 AND realized_pnl > 0
  ABNORMAL_POSITION:  resolved_trade_count >= 10 AND anomaly_index >= 5
                      AND current_position_value >= MIN_POSITION_VALUE
  OTHER:              everything else
Precedence: NEW_ACCOUNT > HIGH_WIN_RATE > ABNORMAL_POSITION > OTHER (ASSUMPTION-A7);
secondary qualification is appended to `reason`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.account_profile_service import ResolvedStats, compute_anomaly_index
from app.services.scoring import MarketRiskContext, smart_money_score

LABEL_NEW_ACCOUNT = "NEW_ACCOUNT"
LABEL_HIGH_WIN_RATE = "HIGH_WIN_RATE"
LABEL_ABNORMAL_POSITION = "ABNORMAL_POSITION"
LABEL_OTHER = "OTHER"

HIGH_WIN_RATE_MIN_TRADES = 20
HIGH_WIN_RATE_MIN_WIN_RATE = 0.60
ABNORMAL_MIN_TRADES = 10
ABNORMAL_MIN_ANOMALY_INDEX = 5.0


@dataclass
class ClassificationResult:
    label: str
    reason: str
    anomaly_index: float | None


def classify_account(*, resolved_trade_count: int, win_rate: float, realized_pnl: float,
                     anomaly_index: float | None, current_position_value: float,
                     min_position_value: float) -> ClassificationResult:
    if resolved_trade_count == 0:
        return ClassificationResult(
            LABEL_NEW_ACCOUNT,
            "No resolved positions before signal time (ASSUMPTION-A19).",
            anomaly_index)

    is_high_win_rate = (resolved_trade_count >= HIGH_WIN_RATE_MIN_TRADES
                        and win_rate >= HIGH_WIN_RATE_MIN_WIN_RATE
                        and realized_pnl > 0)
    is_abnormal = (resolved_trade_count >= ABNORMAL_MIN_TRADES
                   and anomaly_index is not None
                   and anomaly_index >= ABNORMAL_MIN_ANOMALY_INDEX
                   and current_position_value >= min_position_value)

    if is_high_win_rate:
        reason = (f"{resolved_trade_count} resolved positions, win rate "
                  f"{win_rate:.0%}, realized PnL ${realized_pnl:,.0f}.")
        if is_abnormal:
            reason += f" Also abnormal sizing ({anomaly_index:.1f}x historical median)."
        return ClassificationResult(LABEL_HIGH_WIN_RATE, reason, anomaly_index)

    if is_abnormal:
        assert anomaly_index is not None
        return ClassificationResult(
            LABEL_ABNORMAL_POSITION,
            (f"Entry ≈{anomaly_index:.1f}x the account's median historical entry "
             f"(${current_position_value:,.0f} position, {resolved_trade_count} resolved)."),
            anomaly_index)

    return ClassificationResult(
        LABEL_OTHER,
        f"{resolved_trade_count} resolved positions, win rate {win_rate:.0%}.",
        anomaly_index)


@dataclass
class HolderAssessment:
    label: str
    reason: str
    anomaly_index: float | None
    smart_money_score: float
    score_breakdown: dict[str, Any]
    is_smart_money: bool


def assess_holder(*, stats: ResolvedStats, category: str | None,
                  entry_notional_approx: float | None, current_position_value: float,
                  market_ctx: MarketRiskContext, min_position_value: float,
                  smart_money_score_threshold: float) -> HolderAssessment:
    """Classify + score one holder of one market at one snapshot time."""
    anomaly_index = compute_anomaly_index(entry_notional_approx, stats.median_entry_notional)
    classification = classify_account(
        resolved_trade_count=stats.resolved_trade_count,
        win_rate=stats.win_rate,
        realized_pnl=stats.realized_pnl,
        anomaly_index=anomaly_index,
        current_position_value=current_position_value,
        min_position_value=min_position_value,
    )
    cat_stats = stats.category_stats(category)
    score, breakdown = smart_money_score(
        win_rate=stats.win_rate,
        realized_pnl=stats.realized_pnl,
        resolved_trade_count=stats.resolved_trade_count,
        same_category_win_rate=cat_stats.win_rate,
        same_category_trade_count=cat_stats.trade_count,
        anomaly_index=anomaly_index,
        current_position_value=current_position_value,
        market_ctx=market_ctx,
    )
    # ASSUMPTION-A8: smart money = not-new account with score over threshold.
    is_smart = (classification.label != LABEL_NEW_ACCOUNT
                and score >= smart_money_score_threshold)
    return HolderAssessment(
        label=classification.label,
        reason=classification.reason,
        anomaly_index=anomaly_index,
        smart_money_score=round(score, 2),
        score_breakdown=breakdown,
        is_smart_money=is_smart,
    )
