"""Hot-market scanner orchestration.

Pipeline per scan: Gamma list → normalize → filter → rank by 24h volume → for each
market: CLOB books + holders + per-account history → labels/scores → market signal →
persist (markets / snapshots / holders / stats / labels / signals) → optional paper trade.

NOTE: this module must never import order_submit_service (development-rules.md #1).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients.clob_client import ClobClient
from app.clients.gamma_client import GammaClient
from app.core.config import Settings
from app.core.errors import UpstreamError
from app.models import (
    Account,
    AccountLabel,
    AccountResolvedStats,
    Market,
    MarketHolder,
    MarketSnapshot,
    SmartMoneySignal,
)
from app.services.cohort_service import capture_cohort
from app.services.holder_analysis_service import AnalyzedHolder, HolderAnalysisService
from app.services.normalization import (
    NormalizedBook,
    NormalizedMarket,
    NotBinaryMarket,
    normalize_book,
    normalize_market,
)
from app.services.paper_trade_service import PaperTradeService, should_auto_log
from app.services.scan_registry import ScanRegistry
from app.services.scoring import MarketRiskContext
from app.services.signal_service import (
    HolderSignalInput,
    SignalDraft,
    build_signal,
    hours_to_resolution,
    notify_hook,
)
from app.services.smart_money_service import assess_holder

logger = logging.getLogger("app.scanner")


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _book_summary(book: NormalizedBook | None) -> dict | None:
    """Per-side top of book + depth; best_bid is the paper mark price (A24)."""
    if book is None:
        return None
    return {"best_bid": book.best_bid, "best_ask": book.best_ask,
            "bid_depth_usdc": book.bid_depth_usdc, "ask_depth_usdc": book.ask_depth_usdc,
            "top3_ask_usdc": book.top3_ask_usdc}


@dataclass
class FilterResult:
    passed: bool
    reason: str | None = None


def filter_market(market: NormalizedMarket, now: datetime, settings: Settings) -> FilterResult:
    """Scanner inclusion filter (product-spec §4.1). Pure function — unit tested."""
    if not market.active or market.closed:
        return FilterResult(False, "inactive_or_closed")
    if not market.accepting_orders or not market.enable_order_book:
        return FilterResult(False, "not_accepting_orders")
    if not market.condition_id or not market.yes_token_id or not market.no_token_id:
        return FilterResult(False, "missing_identifiers")
    if market.liquidity < settings.min_liquidity:
        return FilterResult(False, "low_liquidity")
    if market.volume_24h < settings.scanner_min_volume_24h:
        return FilterResult(False, "low_volume_24h")
    hrs = hours_to_resolution(market.end_date, now)
    if hrs is None:
        return FilterResult(False, "missing_end_date")
    if hrs < settings.scanner_min_hours_to_resolution:
        return FilterResult(False, "too_close_to_resolution")
    return FilterResult(True)


class MarketScannerService:
    def __init__(self, *, gamma: GammaClient, clob: ClobClient,
                 holder_analysis: HolderAnalysisService, paper_trades: PaperTradeService,
                 registry: ScanRegistry, session_factory: async_sessionmaker[AsyncSession],
                 settings: Settings) -> None:
        self.gamma = gamma
        self.clob = clob
        self.holder_analysis = holder_analysis
        self.paper_trades = paper_trades
        self.registry = registry
        self.session_factory = session_factory
        self.settings = settings

    # ------------------------------------------------------------------ scan loop

    async def run_scan(self, scan_id: str, *, max_markets: int | None = None) -> None:
        state = self.registry.get(scan_id)
        assert state is not None
        limit = max_markets or self.settings.scanner_max_markets
        try:
            state.current_step = "fetching markets from gamma"
            raw_markets = await self.gamma.list_markets(
                limit=self.settings.scanner_market_fetch_limit)
            now = _utcnow()
            candidates: list[NormalizedMarket] = []
            for raw in raw_markets:
                try:
                    market = normalize_market(raw)
                except NotBinaryMarket:
                    continue
                if filter_market(market, now, self.settings).passed:
                    candidates.append(market)
            candidates.sort(key=lambda m: m.volume_24h, reverse=True)
            state.markets_found = len(candidates)
            targets = candidates[:limit]

            for idx, market in enumerate(targets, start=1):
                state.current_step = f"analyzing {market.question[:60]!r} ({idx}/{len(targets)})"
                try:
                    signal = await self.analyze_and_persist(market)
                    state.markets_analyzed += 1
                    if signal is not None and signal.direction != "NEUTRAL":
                        state.signals_generated += 1
                except UpstreamError as exc:
                    state.errors.append(f"{market.gamma_id}: upstream failure ({exc.message})")
                except Exception as exc:  # keep scanning other markets
                    logger.exception("market %s analysis failed", market.gamma_id)
                    state.errors.append(f"{market.gamma_id}: {type(exc).__name__}")
            self.registry.finish(scan_id)
        except Exception as exc:
            logger.exception("scan %s failed", scan_id)
            state.errors.append(f"scan failed: {type(exc).__name__}")
            self.registry.finish(scan_id, failed=True)

    # ------------------------------------------------------------------ one market

    async def _get_book(self, token_id: str) -> NormalizedBook | None:
        try:
            raw = await self.clob.get_book(token_id)
            return normalize_book(raw, token_id)
        except UpstreamError:
            return None

    async def analyze_and_persist(self, market: NormalizedMarket,
                                  *, as_of: datetime | None = None) -> SignalDraft | None:
        now = as_of or _utcnow()
        yes_book, no_book = await asyncio.gather(
            self._get_book(market.yes_token_id), self._get_book(market.no_token_id))
        holders, partial = await self.holder_analysis.analyze(market, yes_book, no_book, now)

        hrs = hours_to_resolution(market.end_date, now)
        assessments = []
        for holder in holders:
            ctx = MarketRiskContext(
                spread=yes_book.spread if yes_book else None,
                liquidity=market.liquidity,
                hours_to_resolution=hrs,
                entry_price=holder.current_price,
                max_spread_abs=self.settings.max_spread_abs,
                min_liquidity=self.settings.min_liquidity,
                near_resolution_hours=self.settings.near_resolution_hours,
                extreme_price_low=self.settings.extreme_price_low,
                extreme_price_high=self.settings.extreme_price_high,
            )
            assessments.append(assess_holder(
                stats=holder.stats, category=market.category,
                entry_notional_approx=holder.entry_notional_approx,
                current_position_value=holder.current_position_value,
                market_ctx=ctx, min_position_value=self.settings.min_position_value,
                smart_money_score_threshold=self.settings.smart_money_score_threshold))

        signal = build_signal(
            market=market,
            holders=[HolderSignalInput(
                direction=h.direction, current_position_value=h.current_position_value,
                smart_money_score=a.smart_money_score, is_smart_money=a.is_smart_money,
                label=a.label) for h, a in zip(holders, assessments, strict=True)],
            yes_book=yes_book, no_book=no_book, now=now, settings=self.settings,
            partial_data=partial)

        async with self.session_factory() as session:
            market_row = await self._upsert_market(session, market)
            await self._persist_snapshot(session, market_row, market, yes_book, no_book, now)
            signal_row = await self._persist_holders_and_signal(
                session, market_row, market, holders, assessments, signal, now)
            await session.commit()

            if self.settings.paper_trade_auto_log:
                side_book = (yes_book if signal.direction == "YES"
                             else no_book if signal.direction == "NO" else None)
                entry_price = side_book.best_ask if side_book else None  # ASSUMPTION-A9
                decision = should_auto_log(
                    direction=signal.direction,
                    confidence_score=signal.confidence_score,
                    min_confidence=self.settings.paper_trade_min_confidence,
                    risk_flags=signal.risk_flags,
                    entry_price=entry_price,
                    spread=side_book.spread if side_book else None,
                    max_relative_spread=self.settings.paper_trade_max_relative_spread)
                if decision.should_log:
                    assert entry_price is not None
                    trade = await self.paper_trades.auto_log(
                        session, market_row=market_row, signal_uid=signal_row.signal_uid,
                        direction=signal.direction, entry_price=entry_price,
                        entry_time=now,
                        notional=min(self.settings.paper_trade_default_notional,
                                     signal.suggested_max_notional
                                     or self.settings.paper_trade_default_notional))
                    if trade is not None:
                        await capture_cohort(
                            session, trade, smart_money_score_threshold=(
                                self.settings.smart_money_score_threshold))
                    await session.commit()
                else:
                    logger.debug("paper auto-log skipped for market %s: %s",
                                 market.gamma_id, decision.reason)
        notify_hook(signal, market)
        return signal

    # ------------------------------------------------------------------ persistence

    async def _upsert_market(self, session: AsyncSession, market: NormalizedMarket) -> Market:
        row = (await session.execute(select(Market).where(
            Market.polymarket_market_id == market.gamma_id))).scalar_one_or_none()
        if row is None:
            row = Market(polymarket_market_id=market.gamma_id, condition_id=market.condition_id,
                         question=market.question, yes_token_id=market.yes_token_id,
                         no_token_id=market.no_token_id)
            session.add(row)
        row.event_id = market.event_id
        row.question = market.question
        row.slug = market.slug
        row.category = market.category
        row.tags = market.tags
        row.yes_token_id = market.yes_token_id
        row.no_token_id = market.no_token_id
        row.active = market.active
        row.closed = market.closed
        row.accepting_orders = market.accepting_orders
        row.neg_risk = market.neg_risk
        row.tick_size = market.tick_size
        row.end_date = market.end_date
        row.volume = market.volume_total
        row.volume_24h = market.volume_24h
        row.liquidity = market.liquidity
        row.open_interest = market.open_interest_event
        await session.flush()
        return row

    async def _persist_snapshot(self, session: AsyncSession, market_row: Market,
                                market: NormalizedMarket, yes_book: NormalizedBook | None,
                                no_book: NormalizedBook | None, now: datetime) -> None:
        yes_price = (yes_book.midpoint if yes_book else None) or market.yes_price_hint
        no_price = (no_book.midpoint if no_book else None) or market.no_price_hint
        session.add(MarketSnapshot(
            market_id=market_row.id, snapshot_time=now,
            yes_price=yes_price, no_price=no_price,
            spread=yes_book.spread if yes_book else market.spread_hint,
            midpoint=yes_book.midpoint if yes_book else None,
            best_bid=yes_book.best_bid if yes_book else market.best_bid_hint,
            best_ask=yes_book.best_ask if yes_book else market.best_ask_hint,
            orderbook_depth={"yes": _book_summary(yes_book), "no": _book_summary(no_book)},
            volume_24h=market.volume_24h, liquidity=market.liquidity,
            open_interest=market.open_interest_event))

    async def _persist_holders_and_signal(self, session: AsyncSession, market_row: Market,
                                          market: NormalizedMarket,
                                          holders: list[AnalyzedHolder], assessments: list,
                                          signal: SignalDraft, now: datetime) -> SmartMoneySignal:
        for holder, assessment in zip(holders, assessments, strict=True):
            account = (await session.execute(select(Account).where(
                Account.wallet_address == holder.wallet_address))).scalar_one_or_none()
            if account is None:
                account = Account(wallet_address=holder.wallet_address,
                                  profile_name=holder.profile_name,
                                  first_seen_at=holder.stats.first_seen_at or now)
                session.add(account)
                await session.flush()
            else:
                if holder.profile_name:
                    account.profile_name = holder.profile_name
                if holder.stats.first_seen_at and (
                        account.first_seen_at is None
                        or holder.stats.first_seen_at < account.first_seen_at):
                    account.first_seen_at = holder.stats.first_seen_at

            session.add(MarketHolder(
                market_id=market_row.id, account_id=account.id, snapshot_time=now,
                direction=holder.direction, shares=holder.shares,
                current_position_value=holder.current_position_value,
                average_price=holder.average_price, current_price=holder.current_price,
                entry_notional_approx=holder.entry_notional_approx,
                rank=holder.rank, value_is_approx=holder.value_is_approx,
                opposite_shares=holder.opposite_shares))

            cat = market.category
            cat_stats = holder.stats.category_stats(cat)
            session.add(AccountResolvedStats(
                account_id=account.id, category=None, snapshot_time=now,
                resolved_trade_count=holder.stats.resolved_trade_count,
                win_rate=holder.stats.win_rate, realized_pnl=holder.stats.realized_pnl,
                average_roi=holder.stats.average_roi,
                median_entry_notional=holder.stats.median_entry_notional,
                same_category_trade_count=cat_stats.trade_count,
                same_category_win_rate=cat_stats.win_rate,
                same_category_roi=cat_stats.average_roi,
                history_truncated=holder.stats.history_truncated))

            session.add(AccountLabel(
                account_id=account.id, market_id=market_row.id, snapshot_time=now,
                direction=holder.direction, label=assessment.label,
                anomaly_index=assessment.anomaly_index,
                smart_money_score=assessment.smart_money_score,
                score_breakdown=assessment.score_breakdown, reason=assessment.reason))

        signal_row = SmartMoneySignal(
            market_id=market_row.id, snapshot_time=now, direction=signal.direction,
            confidence_score=signal.confidence_score,
            yes_smart_money_count=signal.yes_smart_money_count,
            no_smart_money_count=signal.no_smart_money_count,
            yes_smart_money_notional=signal.yes_smart_money_notional,
            no_smart_money_notional=signal.no_smart_money_notional,
            risk_flags=signal.risk_flags,
            suggested_limit_price=signal.suggested_limit_price,
            suggested_max_notional=signal.suggested_max_notional,
            score_inputs=signal.score_inputs)
        session.add(signal_row)
        await session.flush()
        return signal_row

    # ------------------------------------------------------------------ on-demand

    async def analyze_single_market(self, gamma_market_id: str) -> SignalDraft | None:
        raw = await self.gamma.get_market(gamma_market_id)
        if raw is None:
            return None
        market = normalize_market(raw)  # raises NotBinaryMarket for unsupported markets
        return await self.analyze_and_persist(market)
