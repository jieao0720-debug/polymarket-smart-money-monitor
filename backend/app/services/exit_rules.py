"""Pure building blocks for settlement, sell-side valuation and SHADOW exit rules.

Nothing in this module performs I/O or changes positions. Exit rules run in shadow mode
(A27): they only record what they would do, so thresholds can be replayed offline
against the same observations before any rule is allowed to act.

Retention (A26):  R_t = Σ_i w_i · min(1, max(0, e_i,t) / e_i,0)
  e_i,0  account i's net exposure to OUR side at entry, in shares (our − opposite)
  e_i,t  the same quantity now; unknown (fetch failed) accounts are excluded and the
         known weight is reported as `coverage` — unknown is never treated as zero.
  w_i    frozen at entry ∝ our-side position value, Σ w_i = 1.
Shares are used, never market value: a price move must not look like an exit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.services.normalization import (
    DIRECTION_NO,
    DIRECTION_YES,
    NormalizedMarket,
    NormalizedPosition,
)

# ----------------------------------------------------------------- settlement

MARKET_OPEN = "OPEN"
MARKET_AWAITING_RESOLUTION = "AWAITING_RESOLUTION"
MARKET_RESOLVED = "RESOLVED"
MARKET_UNKNOWN = "UNKNOWN"

_VALID_PAYOUTS = (0.0, 0.5, 1.0)


@dataclass(frozen=True)
class MarketResolution:
    status: str
    yes_payout: float | None = None
    no_payout: float | None = None

    def payout(self, direction: str) -> float | None:
        return self.yes_payout if direction == DIRECTION_YES else self.no_payout


def _snap_payout(value: float | None) -> float | None:
    if value is None:
        return None
    for p in _VALID_PAYOUTS:
        if abs(value - p) < 1e-6:
            return p
    return None


def resolve_market(market: NormalizedMarket, now: datetime | None = None) -> MarketResolution:
    """A25: settled only when Gamma says closed AND outcome prices are a valid payout
    vector (1/0, 0/1 or 0.5/0.5). When umaResolutionStatus is present it must read
    "resolved"; when absent only an exact 1/0 vector is accepted. Reaching end_date is
    NOT settlement — such markets are AWAITING_RESOLUTION."""
    if not market.closed:
        if now is not None and market.end_date is not None and market.end_date <= now:
            return MarketResolution(MARKET_AWAITING_RESOLUTION)
        return MarketResolution(MARKET_OPEN)
    yes = _snap_payout(market.yes_price_hint)
    no = _snap_payout(market.no_price_hint)
    if yes is None or no is None or abs(yes + no - 1.0) > 1e-6:
        return MarketResolution(MARKET_AWAITING_RESOLUTION)
    if market.uma_resolution_status is not None:
        if market.uma_resolution_status != "resolved":
            return MarketResolution(MARKET_AWAITING_RESOLUTION)
    elif yes == 0.5:
        return MarketResolution(MARKET_AWAITING_RESOLUTION)
    return MarketResolution(MARKET_RESOLVED, yes_payout=yes, no_payout=no)


# ----------------------------------------------------------------- valuation

@dataclass(frozen=True)
class LiquidationQuote:
    """Selling `shares` into the bid ladder now. Unfillable shares contribute nothing
    to `value` (conservative); `fill_ratio` says how much of the position the book
    could absorb."""
    price: float | None  # average net proceeds per filled share
    value: float  # net USDC proceeds for the fillable part
    fill_ratio: float


def liquidation_quote(bids: list[tuple[float, float]], shares: float,
                      fee_bps: float = 0.0) -> LiquidationQuote:
    if shares <= 0:
        return LiquidationQuote(None, 0.0, 0.0)
    remaining = shares
    gross = 0.0
    for price, size in sorted(bids, key=lambda x: x[0], reverse=True):
        if remaining <= 0:
            break
        take = min(size, remaining)
        gross += take * price
        remaining -= take
    filled = shares - remaining
    if filled <= 0:
        return LiquidationQuote(None, 0.0, 0.0)
    net = gross * (1.0 - fee_bps / 10000.0)
    return LiquidationQuote(round(net / filled, 6), round(net, 4), round(filled / shares, 6))


def mark_price_from_snapshot(orderbook_depth: dict[str, Any] | None,
                             yes_best_bid: float | None, direction: str) -> float | None:
    """Best bid of `direction` from a MarketSnapshot (A24). YES falls back to the
    snapshot's YES best_bid column (older snapshots have no per-side bid)."""
    side = (orderbook_depth or {}).get("yes" if direction == DIRECTION_YES else "no") or {}
    bid = side.get("best_bid")
    if bid is None and direction == DIRECTION_YES:
        bid = yes_best_bid
    return float(bid) if bid is not None else None


# ----------------------------------------------------------------- cohort

@dataclass(frozen=True)
class HolderRecord:
    """One holder row of the entry snapshot (either side)."""
    wallet_address: str
    direction: str
    shares: float
    position_value: float
    smart_money_score: float
    label: str
    is_smart_money: bool


@dataclass(frozen=True)
class CohortSeed:
    wallet_address: str
    entry_shares: float
    entry_opposite_shares: float
    entry_net_exposure: float
    entry_value: float
    weight: float
    smart_money_score: float
    label: str


def build_cohort(holders: list[HolderRecord], direction: str) -> list[CohortSeed]:
    """Smart-money holders on our side with positive net exposure, weighted by our-side
    position value (same basis as the signal's direction rule). Opposite shares come
    from the same snapshot's other-side top-20; absent there they are taken as 0."""
    opposite = DIRECTION_NO if direction == DIRECTION_YES else DIRECTION_YES
    opp_shares = {h.wallet_address: h.shares for h in holders if h.direction == opposite}
    picked = []
    for h in holders:
        if h.direction != direction or not h.is_smart_money:
            continue
        opp = opp_shares.get(h.wallet_address, 0.0)
        net = h.shares - opp
        if net <= 0 or h.position_value <= 0:
            continue
        picked.append((h, opp, net))
    total = sum(h.position_value for h, _, _ in picked)
    if total <= 0:
        return []
    return [CohortSeed(wallet_address=h.wallet_address, entry_shares=h.shares,
                       entry_opposite_shares=opp, entry_net_exposure=net,
                       entry_value=h.position_value, weight=h.position_value / total,
                       smart_money_score=h.smart_money_score, label=h.label)
            for h, opp, net in picked]


def net_exposure(positions: list[NormalizedPosition], our_token_id: str,
                 opposite_token_id: str) -> float:
    """Our-side shares minus opposite-side shares (a YES and a NO share pay $1 jointly,
    so equal holdings cancel)."""
    ours = sum(p.shares for p in positions if p.token_id == our_token_id)
    theirs = sum(p.shares for p in positions if p.token_id == opposite_token_id)
    return ours - theirs


@dataclass(frozen=True)
class MemberExposure:
    weight: float
    entry_net_exposure: float
    current_net_exposure: float | None  # None = unknown this pass


def compute_retention(members: list[MemberExposure]) -> tuple[float | None, float]:
    """Returns (R over known members renormalized to their weight, known weight)."""
    known = [m for m in members if m.current_net_exposure is not None
             and m.entry_net_exposure > 0]
    coverage = sum(m.weight for m in known)
    if coverage <= 0:
        return None, 0.0
    kept = sum(m.weight * min(1.0, max(0.0, m.current_net_exposure or 0.0)
                              / m.entry_net_exposure) for m in known)
    return round(kept / coverage, 6), round(coverage, 6)


# ----------------------------------------------------------------- shadow rules

TRIGGER_COHORT_REDUCE = "COHORT_REDUCE"
TRIGGER_COHORT_EXIT = "COHORT_EXIT"
TRIGGER_SIGNAL_FLIP = "SIGNAL_FLIP"
TRIGGER_STOP_LOSS = "STOP_LOSS"

TRIGGER_TARGETS = {
    TRIGGER_COHORT_REDUCE: 0.5,
    TRIGGER_COHORT_EXIT: 0.0,
    TRIGGER_SIGNAL_FLIP: 0.0,
    TRIGGER_STOP_LOSS: 0.0,
}


@dataclass(frozen=True)
class ShadowThresholds:
    retention_reduce: float = 0.70
    retention_exit: float = 0.40
    min_coverage: float = 0.70
    confirmations: int = 2
    stop_loss_return: float = -0.25


@dataclass
class ShadowResult:
    state: dict[str, Any]  # {"streaks": {trigger: n}, "fired_at": {trigger: iso}}
    fired: list[str] = field(default_factory=list)  # triggers confirmed this pass
    target_fraction: float = 1.0  # sticky min across passes; 1.0 = hold everything


def evaluate_shadow(*, retention: float | None, coverage: float,
                    liquidation_return: float | None, signal_flipped: bool,
                    previous_state: dict[str, Any] | None,
                    previous_target: float | None, observed_at_iso: str,
                    thresholds: ShadowThresholds) -> ShadowResult:
    """Consecutive-confirmation shadow evaluation.

    Each candidate condition is True / False / None (None = its data is unavailable this
    pass: the streak is kept, neither advanced nor reset). A trigger fires once its
    streak reaches `confirmations`; the target position fraction is the minimum over
    fired triggers and never rises again (a reduction is a one-off action — it is not
    undone if the cohort later re-buys)."""
    cohort_known = retention is not None and coverage >= thresholds.min_coverage
    conditions: dict[str, bool | None] = {
        TRIGGER_COHORT_REDUCE: (retention < thresholds.retention_reduce
                                if cohort_known and retention is not None else None),
        TRIGGER_COHORT_EXIT: (retention < thresholds.retention_exit
                              if cohort_known and retention is not None else None),
        TRIGGER_SIGNAL_FLIP: signal_flipped,
        TRIGGER_STOP_LOSS: (liquidation_return <= thresholds.stop_loss_return
                            if liquidation_return is not None else None),
    }
    prev = previous_state or {}
    streaks: dict[str, int] = dict(prev.get("streaks") or {})
    fired_at: dict[str, str] = dict(prev.get("fired_at") or {})
    fired_now: list[str] = []
    for name, cond in conditions.items():
        if cond is None:
            continue
        streaks[name] = streaks.get(name, 0) + 1 if cond else 0
        if streaks[name] >= thresholds.confirmations:
            fired_now.append(name)
            fired_at.setdefault(name, observed_at_iso)
    target = previous_target if previous_target is not None else 1.0
    for name in fired_now:
        target = min(target, TRIGGER_TARGETS[name])
    return ShadowResult(state={"streaks": streaks, "fired_at": fired_at},
                        fired=fired_now, target_fraction=target)
