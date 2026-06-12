"""Market-level signal aggregation.

Aggregates per-holder assessments into a YES/NO/NEUTRAL signal with a transparent
confidence score (NOT a win probability), risk flags, and trade suggestions.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.config import Settings
from app.services.normalization import NormalizedBook, NormalizedMarket
from app.services.scoring import market_confidence

FLAG_LOW_LIQUIDITY = "LOW_LIQUIDITY"
FLAG_WIDE_SPREAD = "WIDE_SPREAD"
FLAG_NEAR_RESOLUTION = "NEAR_RESOLUTION"
FLAG_EXTREME_PRICE = "EXTREME_PRICE"
FLAG_LOW_SMART_SAMPLE = "LOW_SMART_SAMPLE"
FLAG_NEW_ACCOUNT_HEAVY = "NEW_ACCOUNT_HEAVY"
FLAG_ONE_SIDED_BOOK = "ONE_SIDED_BOOK"
FLAG_PARTIAL_DATA = "PARTIAL_DATA"

_FLAG_PENALTIES = {
    FLAG_WIDE_SPREAD: 10.0, FLAG_LOW_LIQUIDITY: 10.0, FLAG_NEAR_RESOLUTION: 10.0,
    FLAG_EXTREME_PRICE: 15.0, FLAG_ONE_SIDED_BOOK: 15.0, FLAG_LOW_SMART_SAMPLE: 20.0,
    FLAG_NEW_ACCOUNT_HEAVY: 5.0, FLAG_PARTIAL_DATA: 5.0,
}


@dataclass
class HolderSignalInput:
    """The slice of an analyzed holder that signal aggregation needs."""
    direction: str  # YES / NO
    current_position_value: float
    smart_money_score: float
    is_smart_money: bool
    label: str


@dataclass
class SignalDraft:
    snapshot_time: datetime
    direction: str  # YES / NO / NEUTRAL
    confidence_score: float
    yes_smart_money_count: int
    no_smart_money_count: int
    yes_smart_money_notional: float
    no_smart_money_notional: float
    risk_flags: list[str]
    suggested_limit_price: float | None
    suggested_max_notional: float | None
    score_inputs: dict[str, Any] = field(default_factory=dict)


def hours_to_resolution(end_date: datetime | None, now: datetime) -> float | None:
    if end_date is None:
        return None
    return (end_date - now).total_seconds() / 3600.0


def market_risk_flags(market: NormalizedMarket, yes_book: NormalizedBook | None,
                      no_book: NormalizedBook | None, now: datetime,
                      settings: Settings, *, partial_data: bool = False) -> list[str]:
    flags: list[str] = []
    if market.liquidity < settings.min_liquidity:
        flags.append(FLAG_LOW_LIQUIDITY)
    spread = yes_book.spread if yes_book else None
    if spread is None or spread > settings.max_spread_abs:
        flags.append(FLAG_WIDE_SPREAD)
    hrs = hours_to_resolution(market.end_date, now)
    if hrs is not None and hrs < settings.near_resolution_hours:
        flags.append(FLAG_NEAR_RESOLUTION)
    mid = yes_book.midpoint if yes_book else market.yes_price_hint
    if mid is not None and (mid < settings.extreme_price_low or mid > settings.extreme_price_high):
        flags.append(FLAG_EXTREME_PRICE)
    if (yes_book is None or no_book is None or yes_book.one_sided or no_book.one_sided
            or (yes_book.midpoint is None)):
        flags.append(FLAG_ONE_SIDED_BOOK)
    if partial_data:
        flags.append(FLAG_PARTIAL_DATA)
    return flags


def round_down_to_tick(price: float, tick: float) -> float:
    if tick <= 0:
        tick = 0.01
    steps = math.floor(price / tick + 1e-9)
    return round(steps * tick, 6)


def suggest_limit_price(book: NormalizedBook | None, tick: float,
                        max_slippage_abs: float) -> float | None:
    """BUY suggestion: marketable limit capped at best ask and mid+slippage (risk-control §4)."""
    if book is None or book.best_ask is None or book.midpoint is None:
        return None
    raw = min(book.best_ask, book.midpoint + max_slippage_abs)
    price = round_down_to_tick(raw, tick)
    price = max(tick, min(1.0 - tick, price))
    return round(price, 6)


def suggest_max_notional(market: NormalizedMarket, book: NormalizedBook | None,
                         settings: Settings) -> float | None:
    """min(MAX_TRADE_NOTIONAL, 1% liquidity, 25% of top-3 ask depth) — risk-control §5."""
    candidates = [settings.max_trade_notional]
    if market.liquidity > 0:
        candidates.append(0.01 * market.liquidity)
    if book is not None and book.top3_ask_usdc > 0:
        candidates.append(0.25 * book.top3_ask_usdc)
    value = max(0.0, min(candidates))
    return round(value, 2) if value >= 1 else None


def build_signal(*, market: NormalizedMarket, holders: list[HolderSignalInput],
                 yes_book: NormalizedBook | None, no_book: NormalizedBook | None,
                 now: datetime, settings: Settings, partial_data: bool = False) -> SignalDraft:
    smart = [h for h in holders if h.is_smart_money]
    yes_smart = [h for h in smart if h.direction == "YES"]
    no_smart = [h for h in smart if h.direction == "NO"]
    yes_notional = round(sum(h.current_position_value for h in yes_smart), 2)
    no_notional = round(sum(h.current_position_value for h in no_smart), 2)

    flags = market_risk_flags(market, yes_book, no_book, now, settings,
                              partial_data=partial_data)
    new_accounts = sum(1 for h in holders if h.label == "NEW_ACCOUNT")
    if holders and new_accounts / len(holders) > 0.5:
        flags.append(FLAG_NEW_ACCOUNT_HEAVY)

    # Direction: requires minimum smart notional and a 55%+ notional imbalance (A20).
    direction = "NEUTRAL"
    total = yes_notional + no_notional
    if total >= settings.min_smart_notional and total > 0:
        share_yes = yes_notional / total
        if share_yes >= 0.55 and yes_smart:
            direction = "YES"
        elif share_yes <= 0.45 and no_smart:
            direction = "NO"

    dominant = yes_smart if direction == "YES" else no_smart if direction == "NO" else []
    if direction != "NEUTRAL" and len(dominant) < 2:
        flags.append(FLAG_LOW_SMART_SAMPLE)

    confidence = 0.0
    if direction != "NEUTRAL":
        dom_notional, other_notional = ((yes_notional, no_notional) if direction == "YES"
                                        else (no_notional, yes_notional))
        avg_score = (sum(h.smart_money_score for h in dominant) / len(dominant)
                     if dominant else 0.0)
        penalty = sum(_FLAG_PENALTIES.get(f, 0.0) for f in set(flags))
        confidence = market_confidence(
            dominant_notional=dom_notional, other_notional=other_notional,
            dominant_count=len(dominant), dominant_avg_score=avg_score,
            market_penalty=penalty)

    side_book = yes_book if direction == "YES" else no_book if direction == "NO" else None
    suggested_price = (suggest_limit_price(side_book, market.tick_size,
                                           settings.max_slippage_abs)
                       if direction != "NEUTRAL" else None)
    suggested_notional = (suggest_max_notional(market, side_book, settings)
                          if direction != "NEUTRAL" else None)

    return SignalDraft(
        snapshot_time=now,
        direction=direction,
        confidence_score=round(confidence, 2),
        yes_smart_money_count=len(yes_smart),
        no_smart_money_count=len(no_smart),
        yes_smart_money_notional=yes_notional,
        no_smart_money_notional=no_notional,
        risk_flags=sorted(set(flags)),
        suggested_limit_price=suggested_price,
        suggested_max_notional=suggested_notional,
        score_inputs={
            "smart_holder_count": len(smart), "holder_count": len(holders),
            "yes_avg_score": (round(sum(h.smart_money_score for h in yes_smart)
                                    / len(yes_smart), 2) if yes_smart else None),
            "no_avg_score": (round(sum(h.smart_money_score for h in no_smart)
                                   / len(no_smart), 2) if no_smart else None),
            "min_smart_notional": settings.min_smart_notional,
        },
    )


def notify_hook(signal: SignalDraft, market: NormalizedMarket) -> None:
    """Reserved integration point (e.g. Telegram) — intentionally a no-op in v1 (A21)."""
    return None
