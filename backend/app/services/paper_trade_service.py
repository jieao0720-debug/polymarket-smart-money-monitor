"""Paper trading: auto-log qualifying signals, manual entries, close with PnL.

Accounting (api-contract §9): shares = notional / entry_price (frozen at entry).
Exits are recorded as paper_trade_exits fills; pnl = Σ fill proceeds − exited shares ×
entry_price (realized so far), remaining_shares = shares still held, and the trade is
CLOSED once nothing remains (exit_price = average net exit price). Every exit — manual
close or settlement — goes through record_exit, which books the fill and decrements the
held shares in one transaction guarded by a compare-and-swap on those shares, so two
concurrent exits can never sell the same shares twice (the loser gets ConflictError).
Auto entries use the
side's best ask at signal time (ASSUMPTION-A9) so paper fills are honest taker prices;
open positions are marked at the side's best BID, and a default close sells into the
live bid ladder net of fees — only what the book can absorb is filled (A24). Settled
markets close at the official payout (A25).

Auto-log guards (ASSUMPTION-A9b): extreme-price signals and signals whose relative
spread (spread / entry price) exceeds PAPER_TRADE_MAX_RELATIVE_SPREAD are NOT
auto-logged — on long-shot markets the half-spread mark-down dominates the notional
and the paper PnL would measure transaction cost, not signal quality. One OPEN auto
position per market+direction (re-scans must not stack duplicates).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.models import Market, MarketSnapshot, PaperTrade, PaperTradeExit, PositionObservation
from app.services.exit_rules import liquidation_quote, mark_price_from_snapshot

EXTREME_PRICE_FLAG = "EXTREME_PRICE"

EXIT_REASON_MANUAL = "MANUAL"
EXIT_REASON_RESOLVED = "RESOLVED"

MARK_BASIS_BID = "BID"
MARK_BASIS_MIDPOINT = "MIDPOINT"  # fallback only when no bid was ever recorded


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True)
class MarkQuote:
    price: float
    basis: str  # BID / MIDPOINT
    as_of: datetime


def snapshot_side_price(snap: MarketSnapshot, direction: str, side: str) -> float | None:
    """Per-side best bid/ask from a snapshot (older snapshots only carry YES columns)."""
    if side == "bid":
        return mark_price_from_snapshot(snap.orderbook_depth, snap.best_bid, direction)
    book = (snap.orderbook_depth or {}).get("yes" if direction == "YES" else "no") or {}
    ask = book.get("best_ask")
    if ask is None and direction == "YES":
        ask = snap.best_ask
    return float(ask) if ask is not None else None


def pick_mark(*, direction: str, snapshot: MarketSnapshot | None,
              observation: PositionObservation | None) -> MarkQuote | None:
    """Newest best bid among the latest market snapshot and the latest position-monitor
    observation; midpoint only if neither has a bid (flagged as such)."""
    candidates: list[MarkQuote] = []
    if observation is not None and observation.best_bid is not None:
        candidates.append(MarkQuote(observation.best_bid, MARK_BASIS_BID,
                                    observation.observed_at))
    if snapshot is not None:
        bid = snapshot_side_price(snapshot, direction, "bid")
        if bid is not None:
            candidates.append(MarkQuote(bid, MARK_BASIS_BID, snapshot.snapshot_time))
    if candidates:
        return max(candidates, key=lambda q: q.as_of)
    if snapshot is not None:
        mid = snapshot.yes_price if direction == "YES" else snapshot.no_price
        if mid is not None:
            return MarkQuote(mid, MARK_BASIS_MIDPOINT, snapshot.snapshot_time)
    return None


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
        trade.remaining_shares = trade.shares
        session.add(trade)
        await session.flush()
        return trade

    async def latest_snapshot(self, session: AsyncSession,
                              market_id: int) -> MarketSnapshot | None:
        return (await session.execute(
            select(MarketSnapshot).where(MarketSnapshot.market_id == market_id)
            .order_by(MarketSnapshot.snapshot_time.desc()).limit(1))).scalar_one_or_none()

    async def latest_observation(self, session: AsyncSession,
                                 trade_id: int) -> PositionObservation | None:
        return (await session.execute(
            select(PositionObservation).where(PositionObservation.paper_trade_id == trade_id)
            .order_by(PositionObservation.observed_at.desc()).limit(1))).scalar_one_or_none()

    async def latest_entry_price(self, session: AsyncSession, market_id: int,
                                 direction: str) -> float | None:
        """Default manual entry = the side's best ask (a buy pays the ask, A9)."""
        snap = await self.latest_snapshot(session, market_id)
        if snap is None:
            return None
        ask = snapshot_side_price(snap, direction, "ask")
        if ask is not None:
            return ask
        return snap.yes_price if direction == "YES" else snap.no_price

    async def latest_mark(self, session: AsyncSession, trade: PaperTrade) -> MarkQuote | None:
        return pick_mark(direction=trade.direction,
                         snapshot=await self.latest_snapshot(session, trade.market_id),
                         observation=await self.latest_observation(session, trade.id))

    async def create_manual(self, session: AsyncSession, *, market_row: Market,
                            direction: str, notional: float, entry_price: float | None,
                            signal_id: str | None) -> PaperTrade:
        if entry_price is None:
            entry_price = await self.latest_entry_price(session, market_row.id, direction)
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
        trade.remaining_shares = trade.shares
        session.add(trade)
        await session.flush()
        return trade

    async def close(self, session: AsyncSession, trade_uid: str, exit_price: float | None,
                    *, bids: list[tuple[float, float]] | None = None,
                    fee_bps: float = 0.0) -> PaperTrade:
        """exit_price given → the user asserts a fill: everything remaining exits at it.
        Otherwise sell the remaining shares into `bids` (the live ladder, best first) net of
        fees; only what the book absorbs is filled and the rest stays OPEN. No book or no
        bids → refused: a fill that cannot be verified is never recorded."""
        # Fresh read (the identity map may hold a copy loaded before an await); FOR UPDATE
        # locks the row on server databases, SQLite relies on record_exit's CAS.
        trade = (await session.execute(
            select(PaperTrade).where(PaperTrade.trade_uid == trade_uid).with_for_update()
            .execution_options(populate_existing=True))).scalar_one_or_none()
        if trade is None:
            raise NotFoundError(f"paper trade {trade_uid} not found")
        if trade.status != "OPEN":
            raise ValidationFailed(f"paper trade is {trade.status}, only OPEN can be closed")
        remaining = trade.open_shares
        now = _utcnow()
        if exit_price is not None:
            if not (0 <= exit_price <= 1):
                raise ValidationFailed("exit_price must be within [0, 1]")
            await self.record_exit(session, trade, shares=remaining, price=exit_price,
                                    at=now, reason=EXIT_REASON_MANUAL)
            return trade
        if bids is None:
            raise ValidationFailed(
                "order book unavailable — cannot verify a fill; pass exit_price to force")
        quote = liquidation_quote(bids, remaining, fee_bps)
        if quote.price is None or quote.filled_shares <= 0:
            raise ValidationFailed("no bids in the order book — nothing can be sold now")
        await self.record_exit(session, trade, shares=quote.filled_shares, price=quote.price,
                               at=now, reason=EXIT_REASON_MANUAL, fee=quote.fee)
        return trade

    async def settle(self, session: AsyncSession, trade: PaperTrade, payout: float,
                     settled_at: datetime) -> PaperTrade:
        """Close what remains of an OPEN trade at the official payout (A25). Idempotent."""
        # The monitor loaded `trade` before its network calls; re-read what is held now.
        await session.refresh(trade, with_for_update=True)
        if trade.status != "OPEN":
            return trade
        if not (0 <= payout <= 1):
            raise ValidationFailed("settlement payout must be within [0, 1]")
        await self.record_exit(session, trade, shares=trade.open_shares, price=payout,
                               at=settled_at, reason=EXIT_REASON_RESOLVED)
        return trade

    async def record_exit(self, session: AsyncSession, trade: PaperTrade, *, shares: float,
                          price: float, at: datetime, reason: str,
                          fee: float = 0.0) -> PaperTradeExit:
        """Book one exit fill. The trade row is updated only if it is still OPEN and still
        holds exactly the shares this session read (compare-and-swap), in the same
        transaction as the fill insert. A concurrent exit that got there first makes this
        one fail with ConflictError — nothing is booked — instead of selling the same
        shares twice. The caller must roll back on any error."""
        if trade.status != "OPEN":
            raise ConflictError(f"paper trade is {trade.status}, nothing left to exit")
        held = trade.open_shares
        shares = min(shares, held)
        if shares <= 0:
            raise ValidationFailed("no open shares left to exit")
        proceeds = shares * price
        fill_pnl = proceeds - shares * trade.entry_price
        left = held - shares
        remaining = 0.0 if left <= 1e-9 else round(left, 6)
        pnl = round((trade.pnl or 0.0) + fill_pnl, 4)
        changes: dict[str, object] = {"remaining_shares": remaining, "pnl": pnl}
        if remaining == 0.0:
            exited = trade.shares
            total_proceeds = pnl + exited * trade.entry_price
            changes.update(
                exit_price=round(total_proceeds / exited, 6) if exited > 0 else price,
                exit_time=at, exit_reason=reason, status="CLOSED")
        try:
            result = await session.execute(
                update(PaperTrade)
                .where(PaperTrade.id == trade.id, PaperTrade.status == "OPEN",
                       func.coalesce(PaperTrade.remaining_shares, PaperTrade.shares) == held)
                .values(**changes)
                .execution_options(synchronize_session=False))
        except OperationalError as exc:
            # SQLite answers a write-write race with "database is locked" (SQLITE_BUSY).
            if "locked" not in str(exc).lower():
                raise
            raise ConflictError("paper trade is being exited concurrently — retry") from exc
        if result.rowcount != 1:
            raise ConflictError(
                "paper trade changed concurrently (another exit was booked) — reload and "
                "retry")
        for key, value in changes.items():
            set_committed_value(trade, key, value)
        fill = PaperTradeExit(
            paper_trade_id=trade.id, exit_time=at, shares=round(shares, 6),
            price=round(price, 6), proceeds=round(proceeds, 6), fee=round(fee, 6),
            reason=reason, pnl=round(fill_pnl, 6))
        session.add(fill)
        await session.flush()
        return fill
