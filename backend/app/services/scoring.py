"""Transparent rule-based scoring. No ML.

smart_money_score =
    0.25*win_rate_score + 0.25*realized_pnl_score + 0.15*sample_size_score
  + 0.15*same_category_score + 0.10*anomaly_score + 0.10*position_size_score
  - risk_penalty
clamped to [0, 100]. Every component is a standalone, unit-tested function.

confidence_score (market level) is a heuristic ranking aid — it is NOT a win
probability and must never be presented as one (development-rules.md #17).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

WEIGHTS = {
    "win_rate": 0.25,
    "realized_pnl": 0.25,
    "sample_size": 0.15,
    "same_category": 0.15,
    "anomaly": 0.10,
    "position_size": 0.10,
}


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


# ----------------------------------------------------------------- component scores

def win_rate_score(win_rate: float) -> float:
    """0–1 win rate → 0–100."""
    return clamp(win_rate * 100.0)


def realized_pnl_score(realized_pnl: float) -> float:
    """Log-scaled: $0→0, ~$100→40, ~$1k→60, ~$10k→80, ≥$100k→100. Negative PnL → 0."""
    if realized_pnl <= 0:
        return 0.0
    return clamp(20.0 * math.log10(1.0 + realized_pnl))


def sample_size_score(resolved_trade_count: int) -> float:
    """2 points per resolved position, saturating at 50 positions."""
    return clamp(2.0 * max(0, resolved_trade_count))


def same_category_score(same_category_win_rate: float, same_category_trade_count: int) -> float:
    """Blend toward a neutral 50 when category history is thin.

    w = min(1, count/10); score = w*win_rate*100 + (1-w)*50.
    """
    w = min(1.0, max(0, same_category_trade_count) / 10.0)
    return clamp(w * same_category_win_rate * 100.0 + (1.0 - w) * 50.0)


def anomaly_score(anomaly_index: float | None) -> float:
    """Conviction sizing: anomaly_index 1x→10, 5x→50, ≥10x→100. Unknown → 0."""
    if anomaly_index is None or anomaly_index <= 0:
        return 0.0
    return clamp(10.0 * anomaly_index)


def position_size_score(current_position_value: float) -> float:
    """$100→1, $1k→10, ≥$10k→100 (linear in value/100)."""
    return clamp(current_position_value / 100.0)


# ----------------------------------------------------------------- risk penalties

def low_sample_penalty(resolved_trade_count: int) -> float:
    if resolved_trade_count >= 20:
        return 0.0
    if resolved_trade_count >= 10:
        return 10.0
    if resolved_trade_count >= 5:
        return 20.0
    if resolved_trade_count >= 1:
        return 25.0
    return 0.0  # the n==0 case is covered by new_account_penalty


def new_account_penalty(resolved_trade_count: int) -> float:
    return 30.0 if resolved_trade_count == 0 else 0.0


def high_spread_penalty(spread: float | None, max_spread_abs: float) -> float:
    if spread is None:
        return 10.0  # unknown spread is treated as risky
    return 10.0 if spread > max_spread_abs else 0.0


def low_liquidity_penalty(liquidity: float, min_liquidity: float) -> float:
    return 10.0 if liquidity < min_liquidity else 0.0


def near_resolution_penalty(hours_to_resolution: float | None,
                            near_resolution_hours: float = 48.0) -> float:
    if hours_to_resolution is None:
        return 0.0
    return 10.0 if hours_to_resolution < near_resolution_hours else 0.0


def extreme_price_penalty(price: float | None, low: float = 0.05, high: float = 0.95) -> float:
    if price is None:
        return 0.0
    return 10.0 if (price < low or price > high) else 0.0


@dataclass(frozen=True)
class MarketRiskContext:
    spread: float | None
    liquidity: float
    hours_to_resolution: float | None
    entry_price: float | None  # current price of the side the account holds
    max_spread_abs: float = 0.03
    min_liquidity: float = 1000.0
    near_resolution_hours: float = 48.0
    extreme_price_low: float = 0.05
    extreme_price_high: float = 0.95


def risk_penalty(resolved_trade_count: int,
                 ctx: MarketRiskContext) -> tuple[float, dict[str, float]]:
    parts = {
        "low_sample_penalty": low_sample_penalty(resolved_trade_count),
        "new_account_penalty": new_account_penalty(resolved_trade_count),
        "high_spread_penalty": high_spread_penalty(ctx.spread, ctx.max_spread_abs),
        "low_liquidity_penalty": low_liquidity_penalty(ctx.liquidity, ctx.min_liquidity),
        "near_resolution_penalty": near_resolution_penalty(ctx.hours_to_resolution,
                                                           ctx.near_resolution_hours),
        "extreme_price_penalty": extreme_price_penalty(ctx.entry_price, ctx.extreme_price_low,
                                                       ctx.extreme_price_high),
    }
    return sum(parts.values()), parts


# ----------------------------------------------------------------- total score

def smart_money_score(*, win_rate: float, realized_pnl: float, resolved_trade_count: int,
                      same_category_win_rate: float, same_category_trade_count: int,
                      anomaly_index: float | None, current_position_value: float,
                      market_ctx: MarketRiskContext) -> tuple[float, dict[str, Any]]:
    components = {
        "win_rate_score": win_rate_score(win_rate),
        "realized_pnl_score": realized_pnl_score(realized_pnl),
        "sample_size_score": sample_size_score(resolved_trade_count),
        "same_category_score": same_category_score(same_category_win_rate,
                                                   same_category_trade_count),
        "anomaly_score": anomaly_score(anomaly_index),
        "position_size_score": position_size_score(current_position_value),
    }
    weighted = (
        WEIGHTS["win_rate"] * components["win_rate_score"]
        + WEIGHTS["realized_pnl"] * components["realized_pnl_score"]
        + WEIGHTS["sample_size"] * components["sample_size_score"]
        + WEIGHTS["same_category"] * components["same_category_score"]
        + WEIGHTS["anomaly"] * components["anomaly_score"]
        + WEIGHTS["position_size"] * components["position_size_score"]
    )
    penalty_total, penalty_parts = risk_penalty(resolved_trade_count, market_ctx)
    score = clamp(weighted - penalty_total)
    breakdown: dict[str, Any] = {
        "components": components, "weights": WEIGHTS, "weighted_sum": round(weighted, 2),
        "penalties": penalty_parts, "penalty_total": penalty_total, "final": round(score, 2),
    }
    return score, breakdown


# ----------------------------------------------------------------- market confidence

def market_confidence(*, dominant_notional: float, other_notional: float,
                      dominant_count: int, dominant_avg_score: float,
                      market_penalty: float) -> float:
    """ASSUMPTION-A20. 0.40*notional imbalance + 0.25*count + 0.35*avg score − penalty."""
    total = dominant_notional + other_notional
    if total <= 0 or dominant_count <= 0:
        return 0.0
    imbalance = dominant_notional / total  # 0.5–1.0
    imbalance_score = clamp((imbalance - 0.5) * 2.0 * 100.0)
    count_score = clamp(dominant_count * 20.0)
    raw = 0.40 * imbalance_score + 0.25 * count_score + 0.35 * clamp(dominant_avg_score)
    return clamp(raw - market_penalty)
