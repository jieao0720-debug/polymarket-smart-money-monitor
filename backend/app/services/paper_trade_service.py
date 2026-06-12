"""Paper trading: auto-log qualifying signals, manual entries, close with PnL.

Accounting (api-contract §9): shares = notional / entry_price (frozen at entry);
pnl = shares * (exit_price - entry_price). Auto entries use the side's best ask at
signal time (ASSUMPTION-A9) so paper fills are honest taker prices.

Auto-log guards (ASSUMPTION-A9b): extreme-price signals and signals whose relative
spread (spread / entry price) exceeds PAPER_TRADE_MAX_RELATIVE_SPREAD are NOT
auto-logged — on long-shot markets the half-spread mark-down dominates the notional
and the paper PnL would measure transaction cost, not signal quality. One OPEN auto
position per market+direction (re-scans must not stack duplicates).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationFailed
from app.models import Market, MarketSnapshot, PaperTrade

EXTREME_PRICE_FLAG = "EXTREME_PRICE"


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True)
class AutoLogDecision:
    should_log: bool
    reason: str | None = None


def should_auto_log(*, direction: str, confidence_score: float, min_confidence: float,
                    risk_flags: list[str] | None, entry_price: float | None,
                    spread: float | None, max_relative_spread: float) -> AutoLogDecision:
    """Pure gate for signal → paper trade auto-logging (unit-tested)."""
    if direction not in ("YES", "NO"):
        return AutoLogDecision(False, "neutral signal")
    if confidence_score < min_confidence:
        return AutoLogDecision(
            False, f"confidence {confidence_score:.0f} below threshold {min_confidence:.0f}")
    if entry_price is None or not (0 < entry_price < 1):
        return AutoLogDecision(False, "no executable entry price (missing/one-sided book)")
    if risk_flags and EXTREME_PRICE_FLAG in risk_flags:
        return AutoLogDecision(False, "extreme price — spread cost dominates the notional")
    if spread is not None and spread / entry_price > max_relative_spread:
        return AutoLogDecision(
            False, f"relative spread {spread / entry_price:.1%} exceeds "
                   f"{max_relative_spread:.0%} cap")
    return AutoLogDecision(True)


class PaperTradeService:
    async def auto_log(self, session: AsyncSession, *, market_row: Market, signal_uid: str,
                       direction: str, entry_price: float, entry_time: datetime,
                       notional: float) -> PaperTrade | None:
        if not (0 < entry_price < 1) or notional <= 0:
            return None
        # Idempotence: one auto paper trade per signal.
        existing = (await session.execute(select(PaperTrade).where(
            PaperTrade.signal_id == signal_uid,
            PaperTrade.source == "AUTO_SIGNAL"))).scalar_one_or_none()
        if existing is not None:
            return existing
        # Dedupe (A9b): never stack a second OPEN auto position on the same
        # market+direction just because a later scan emitted a fresh signal.
        open_duplicate = (await session.execute(select(PaperTrade).where(
            PaperTrade.market_id == market_row.id,
            PaperTrade.direction == direction,
            PaperTrade.source == "AUTO_SIGNAL",
            PaperTrade.status == "OPEN"))).scalars().first()
        if open_duplicate is not None:
            return None
        trade = PaperTrade(
            signal_id=signal_uid, market_id=market_row.id, direction=direction,
            entry_price=entry_price, entry_time=entry_time, notional=round(notional, 2),
            shares=round(notional / entry_price, 6), status="OPEN", source="AUTO_SIGNAL")
        session.add(trade)
        await session.flush()
        return trade

    async def latest_price(self, session: AsyncSession, market_id: int,
                           direction: str) -> float | None:
        snap = (await session.execute(
            select(MarketSnapshot).where(MarketSnapshot.market_id == market_id)
            .order_by(MarketSnapshot.snapshot_time.desc()).limit(1))).scalar_one_or_none()
        if snap is None:
            return None
        return snap.yes_price if direction == "YES" else snap.no_price

    async def create_manual(self, session: AsyncSession, *, market_row: Market,
                            direction: str, notional: float, entry_price: float | None,
                            signal_id: str | None) -> PaperTrade:
        if entry_price is None:
            entry_price = await self.latest_price(session, market_row.id, direction)
        if entry_price is None:
            raise ValidationFailed(
                "entry_price not provided and no snapshot price available for this market")
        if not (0 < entry_price < 1):
            raise ValidationFailed("entry_price must be between 0 and 1 (exclusive)")
        if notional <= 0:
            raise ValidationFailed("notional must be positive")
        trade = PaperTrade(
            signal_id=signal_id, market_id=market_row.id, direction=direction,
            entry_price=entry_price, entry_time=_utcnow(), notional=round(notional, 2),
            shares=round(notional / entry_price, 6), status="OPEN", source="MANUAL")
        session.add(trade)
        await session.flush()
        return trade

    async def close(self, session: AsyncSession, trade_uid: str,
                    exit_price: float | None) -> PaperTrade:
        trade = (await session.execute(select(PaperTrade).where(
            PaperTrade.trade_uid == trade_uid))).scalar_one_or_none()
        if trade is None:
            raise NotFoundError(f"paper trade {trade_uid} not found")
        if trade.status != "OPEN":
            raise ValidationFailed(f"paper trade is {trade.status}, only OPEN can be closed")
        if exit_price is None:
            exit_price = await self.latest_price(session, trade.market_id, trade.direction)
        if exit_price is None:
            raise ValidationFailed(
                "exit_price not provided and no snapshot price available for this market")
        if not (0 <= exit_price <= 1):
            raise ValidationFailed("exit_price must be within [0, 1]")
        trade.exit_price = exit_price
        trade.exit_time = _utcnow()
        trade.pnl = round(trade.shares * (exit_price - trade.entry_price), 4)
        trade.status = "CLOSED"
        await session.flush()
        return trade
