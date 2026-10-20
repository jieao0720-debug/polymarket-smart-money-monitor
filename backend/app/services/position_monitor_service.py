"""Position monitor — runs over every OPEN paper trade, independent of the hot-market
scanner (a held market that stops being "hot" or nears its end is still watched).

Per pass and per OPEN trade:
  1. Gamma market → settle at the official payout if resolved (A25). This is the ONLY
     state change the monitor makes.
  2. Otherwise: side order book → best bid + bid-ladder liquidation quote (A24);
     each frozen cohort account's current position → net exposure → retention (A26);
     latest post-entry scanner signal → flip check.
  3. Shadow exit rules (A27) → recorded on a PositionObservation, never executed.

NOTE: like the scanner, this module must never import order_submit_service
(development-rules.md #1) — it has no path to real orders.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients.clob_client import ClobClient
from app.clients.data_client import DataClient
from app.clients.gamma_client import GammaClient
from app.core.config import Settings
from app.core.errors import UpstreamError
from app.models import (
    Market,
    PaperTrade,
    PaperTradeCohortMember,
    PositionObservation,
    SmartMoneySignal,
)
from app.services.cohort_service import COHORT_SOURCE_BACKFILL, capture_cohort
from app.services.exit_rules import (
    MARKET_RESOLVED,
    MARKET_UNKNOWN,
    MarketResolution,
    MemberExposure,
    ShadowThresholds,
    compute_retention,
    evaluate_shadow,
    liquidation_quote,
    member_status,
    net_exposure,
    resolve_market,
)
from app.services.normalization import (
    NormalizedBook,
    NormalizedMarket,
    NotBinaryMarket,
    normalize_book,
    normalize_market,
    normalize_position,
)
from app.services.paper_trade_service import PaperTradeService

logger = logging.getLogger("app.position_monitor")


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass
class MonitorRunResult:
    started_at: datetime
    finished_at: datetime | None = None
    open_trades: int = 0
    observations: int = 0
    settled: int = 0
    cohorts_backfilled: int = 0
    errors: list[str] = field(default_factory=list)


class PositionMonitorService:
    def __init__(self, *, gamma: GammaClient, clob: ClobClient, data: DataClient,
                 paper_trades: PaperTradeService,
                 session_factory: async_sessionmaker[AsyncSession],
                 settings: Settings) -> None:
        self.gamma = gamma
        self.clob = clob
        self.data = data
        self.paper_trades = paper_trades
        self.session_factory = session_factory
        self.settings = settings
        self._lock = asyncio.Lock()

    @property
    def thresholds(self) -> ShadowThresholds:
        s = self.settings
        return ShadowThresholds(
            retention_reduce=s.shadow_exit_retention_reduce,
            retention_exit=s.shadow_exit_retention_exit,
            min_coverage=s.shadow_exit_min_coverage,
            confirmations=s.shadow_exit_confirmations,
            stop_loss_return=s.shadow_exit_stop_loss_return,
            min_confirm_interval_minutes=s.shadow_exit_min_confirm_interval_minutes)

    @property
    def running(self) -> bool:
        return self._lock.locked()

    async def run_once(self, *, now: datetime | None = None) -> MonitorRunResult:
        """One monitor pass. Concurrent calls are serialized (never two passes at once,
        which would double-count confirmation streaks)."""
        async with self._lock:
            return await self._run(now or _utcnow())

    # ------------------------------------------------------------------ pass

    async def _run(self, now: datetime) -> MonitorRunResult:
        result = MonitorRunResult(started_at=now)
        async with self.session_factory() as session:
            rows = (await session.execute(
                select(PaperTrade.id, Market.id, Market.polymarket_market_id)
                .join(Market, PaperTrade.market_id == Market.id)
                .where(PaperTrade.status == "OPEN").order_by(PaperTrade.id))).all()
        result.open_trades = len(rows)
        # Keep scalar identifiers across transactions. Rollback expires ORM objects;
        # accessing those while logging/processing the next market can trigger async IO.
        by_market: dict[tuple[int, str], list[int]] = {}
        for trade_id, market_id, public_id in rows:
            by_market.setdefault((market_id, public_id), []).append(trade_id)

        for (market_id, public_id), trade_ids in by_market.items():
            # A failure must neither poison the next market's session nor report counts
            # for fills/observations that were rolled back.
            market_result = MonitorRunResult(started_at=now)
            async with self.session_factory() as session:
                try:
                    market_row = await session.get(Market, market_id)
                    if market_row is None:
                        continue
                    trades = (await session.execute(select(PaperTrade).where(
                        PaperTrade.id.in_(trade_ids), PaperTrade.status == "OPEN")
                        .order_by(PaperTrade.id))).scalars().all()
                    await self._process_market(session, market_row, list(trades), now,
                                               market_result)
                    await session.commit()
                except Exception as exc:  # keep monitoring the other markets
                    await session.rollback()
                    logger.exception("position monitor failed for market %s", public_id)
                    result.errors.append(f"{public_id}: {type(exc).__name__}")
                else:
                    result.settled += market_result.settled
                    result.observations += market_result.observations
                    result.cohorts_backfilled += market_result.cohorts_backfilled
        result.finished_at = _utcnow()
        return result

    async def _process_market(self, session: AsyncSession, market_row: Market,
                              trades: list[PaperTrade], now: datetime,
                              result: MonitorRunResult) -> None:
        market_issues: list[str] = []
        market = await self._get_market(market_row, market_issues)
        resolution = (resolve_market(market, now) if market is not None
                      else MarketResolution(MARKET_UNKNOWN))

        if resolution.status == MARKET_RESOLVED:
            settled_at = (market.closed_time if market is not None and market.closed_time
                          else now)
            for trade in trades:
                payout = resolution.payout(trade.direction)
                assert payout is not None
                fill = await self.paper_trades.settle(session, trade, payout, settled_at)
                if fill is None:  # manually closed while we fetched the market
                    continue
                result.settled += 1
                session.add(PositionObservation(
                    paper_trade_id=trade.id, observed_at=now, market_status=MARKET_RESOLVED,
                    best_bid=None, best_ask=None, liquidation_price=fill.price,
                    liquidation_value=round(fill.proceeds, 4),
                    liquidation_fill_ratio=1.0,
                    liquidation_return=_ret(_realized_proceeds(trade), trade.notional),
                    data_issues=market_issues or None))
                result.observations += 1
            market_row.closed = True
            market_row.active = False
            return

        books = {}
        for direction in {t.direction for t in trades}:
            token = market_row.yes_token_id if direction == "YES" else market_row.no_token_id
            books[direction] = await self._get_book(token)
        latest_signal = (await session.execute(
            select(SmartMoneySignal).where(SmartMoneySignal.market_id == market_row.id)
            .order_by(SmartMoneySignal.snapshot_time.desc()).limit(1))).scalar_one_or_none()
        positions_cache: dict[str, list | None] = {}

        for trade in trades:
            if await capture_cohort(
                    session, trade, source=COHORT_SOURCE_BACKFILL,
                    smart_money_score_threshold=self.settings.smart_money_score_threshold):
                result.cohorts_backfilled += 1
            issues = list(market_issues)
            obs = await self._observe(session, market_row, trade, resolution.status,
                                      books.get(trade.direction), latest_signal,
                                      positions_cache, now, issues)
            session.add(obs)
            result.observations += 1

    async def _observe(self, session: AsyncSession, market_row: Market, trade: PaperTrade,
                       market_status: str, book: NormalizedBook | None,
                       latest_signal: SmartMoneySignal | None,
                       positions_cache: dict[str, list | None], now: datetime,
                       issues: list[str]) -> PositionObservation:
        # --- sell-side valuation of what is still held (A24); return includes exits so far
        if book is None:
            issues.append("order book unavailable")
            quote = None
        else:
            quote = liquidation_quote(book.bids, trade.open_shares,
                                      self.settings.paper_exit_fee_bps)
            if quote.fill_ratio == 0:
                issues.append("no bids — position cannot be sold now")
        liq_return = (_ret(_realized_proceeds(trade) + quote.value, trade.notional)
                      if quote is not None and quote.fill_ratio > 0 else None)

        # --- cohort retention (A26)
        members = (await session.execute(select(PaperTradeCohortMember).where(
            PaperTradeCohortMember.paper_trade_id == trade.id))).scalars().all()
        if not members:
            issues.append("no entry cohort (manual trade without signal, or no smart "
                          "holder at entry)")
        our_token = market_row.yes_token_id if trade.direction == "YES" \
            else market_row.no_token_id
        opp_token = market_row.no_token_id if trade.direction == "YES" \
            else market_row.yes_token_id
        await asyncio.gather(*(
            self._fetch_positions(m.wallet_address, market_row.condition_id,
                                  positions_cache)
            for m in members if m.wallet_address not in positions_cache))
        exposures: list[MemberExposure] = []
        detail: list[dict[str, Any]] = []
        for m in members:
            positions = positions_cache.get(m.wallet_address)
            current = (None if positions is None
                       else net_exposure(positions, our_token, opp_token))
            verified = m.entry_baseline_verified is True
            exposures.append(MemberExposure(m.weight, m.entry_net_exposure, current, verified))
            detail.append({
                "wallet": m.wallet_address, "weight": round(m.weight, 6),
                "entry_net_exposure": m.entry_net_exposure,
                "current_net_exposure": None if current is None else round(current, 4),
                "baseline_verified": verified,
                "status": member_status(m.entry_net_exposure, current, verified)})
        retention, coverage = compute_retention(exposures)
        if members and any(e.current_net_exposure is None for e in exposures):
            issues.append("some cohort positions unavailable — treated as unknown, not 0")
        if any(not e.baseline_verified for e in exposures):
            issues.append("some entry baselines unverified — excluded from retention")

        # --- latest scanner signal after entry: evidence only when it is NEW since the
        # previous observation and FRESH, so one old signal is never re-confirmed (A27)
        previous = await self.paper_trades.latest_observation(session, trade.id)
        flipped: bool | None = None
        sig_dir = sig_time = None
        if latest_signal is not None and latest_signal.snapshot_time > trade.entry_time:
            sig_dir, sig_time = latest_signal.direction, latest_signal.snapshot_time
            seen = previous.latest_signal_time if previous else None
            is_new = seen is None or sig_time > seen
            max_age = self.settings.shadow_exit_signal_max_age_hours * 3600.0
            is_fresh = (now - sig_time).total_seconds() <= max_age
            if is_new and is_fresh:
                flipped = sig_dir in ("YES", "NO") and sig_dir != trade.direction
            elif is_new:
                issues.append("latest scanner signal is stale — not used as evidence")

        # --- shadow exit rules (A27): recorded only
        shadow = evaluate_shadow(
            retention=retention, coverage=coverage, liquidation_return=liq_return,
            signal_flipped=flipped,
            previous_state=previous.shadow_state if previous else None,
            previous_target=previous.shadow_target_fraction if previous else None,
            observed_at=now, thresholds=self.thresholds)

        return PositionObservation(
            paper_trade_id=trade.id, observed_at=now, market_status=market_status,
            best_bid=book.best_bid if book else None,
            best_ask=book.best_ask if book else None,
            liquidation_price=quote.price if quote else None,
            liquidation_value=quote.value if quote else None,
            liquidation_fill_ratio=quote.fill_ratio if quote else None,
            liquidation_return=liq_return, retention=retention,
            coverage=coverage if members else None, cohort_detail=detail or None,
            latest_signal_direction=sig_dir, latest_signal_time=sig_time,
            shadow_state=shadow.state, shadow_triggers=shadow.fired or None,
            shadow_target_fraction=shadow.target_fraction, data_issues=issues or None)

    # ------------------------------------------------------------------ fetchers

    async def _get_market(self, market_row: Market,
                          issues: list[str]) -> NormalizedMarket | None:
        try:
            raw = await self.gamma.get_market(market_row.polymarket_market_id)
        except UpstreamError:
            issues.append("gamma market unavailable — settlement not checked")
            return None
        if raw is None:
            issues.append("gamma market not found — settlement not checked")
            return None
        try:
            return normalize_market(raw)
        except NotBinaryMarket:
            issues.append("market no longer normalizes as binary Yes/No")
            return None

    async def _get_book(self, token_id: str) -> NormalizedBook | None:
        try:
            return normalize_book(await self.clob.get_book(token_id), token_id)
        except UpstreamError:
            return None

    async def _fetch_positions(self, wallet: str, condition_id: str,
                               cache: dict[str, list | None]) -> None:
        """None = unknown (fetch failed); [] = known flat (the account holds nothing)."""
        try:
            raw = await self.data.get_positions(wallet, condition_id=condition_id, limit=10)
        except UpstreamError:
            cache[wallet] = None
            return
        positions = [normalize_position(r) for r in raw]
        cache[wallet] = [p for p in positions if p.condition_id == condition_id]


def _realized_proceeds(trade: PaperTrade) -> float:
    """Net proceeds of exits already recorded = realized pnl + exited shares × entry."""
    exited = trade.shares - trade.open_shares
    return (trade.pnl or 0.0) + exited * trade.entry_price if exited > 0 else 0.0


def _ret(value: float, notional: float) -> float | None:
    return round(value / notional - 1.0, 6) if notional > 0 else None
