from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Container, get_container, get_db
from app.core.errors import NotFoundError, UpstreamError, ValidationFailed
from app.models import (
    Account,
    AccountLabel,
    AccountResolvedStats,
    Market,
    MarketHolder,
    MarketSnapshot,
    SmartMoneySignal,
)
from app.schemas.api import (
    HolderEntry,
    HotMarket,
    HotMarketsResponse,
    MarketAnalysisResponse,
    MarketInfo,
    MarketSummary,
)
from app.services.normalization import NotBinaryMarket

router = APIRouter(prefix="/api/markets", tags=["markets"])


async def latest_snapshot(db: AsyncSession, market_id: int) -> MarketSnapshot | None:
    return (await db.execute(
        select(MarketSnapshot).where(MarketSnapshot.market_id == market_id)
        .order_by(MarketSnapshot.snapshot_time.desc()).limit(1))).scalar_one_or_none()


async def latest_signal(db: AsyncSession, market_id: int) -> SmartMoneySignal | None:
    return (await db.execute(
        select(SmartMoneySignal).where(SmartMoneySignal.market_id == market_id)
        .order_by(SmartMoneySignal.snapshot_time.desc()).limit(1))).scalar_one_or_none()


@router.get("/hot", response_model=HotMarketsResponse)
async def hot_markets(
    limit: int = Query(default=50, ge=1, le=200),
    category: str | None = None,
    min_liquidity: float | None = Query(default=None, ge=0),
    min_confidence: float | None = Query(default=None, ge=0, le=100),
    direction: str | None = Query(default=None, pattern="^(YES|NO|NEUTRAL)$"),
    db: AsyncSession = Depends(get_db),
) -> HotMarketsResponse:
    query = select(Market).where(Market.active.is_(True), Market.closed.is_(False))
    if category:
        query = query.where(Market.category == category)
    if min_liquidity is not None:
        query = query.where(Market.liquidity >= min_liquidity)
    markets = (await db.execute(
        query.order_by(Market.volume_24h.desc()).limit(limit * 2))).scalars().all()

    out: list[HotMarket] = []
    for market in markets:
        signal = await latest_signal(db, market.id)
        if signal is None:
            continue  # /hot lists analyzed markets only
        if min_confidence is not None and signal.confidence_score < min_confidence:
            continue
        if direction is not None and signal.direction != direction:
            continue
        snap = await latest_snapshot(db, market.id)
        out.append(HotMarket(
            market_id=market.polymarket_market_id, condition_id=market.condition_id,
            question=market.question, category=market.category, slug=market.slug,
            end_date=market.end_date, volume_24h=market.volume_24h,
            liquidity=market.liquidity, open_interest=market.open_interest,
            yes_price=snap.yes_price if snap else None,
            no_price=snap.no_price if snap else None,
            spread=snap.spread if snap else None,
            midpoint=snap.midpoint if snap else None,
            smart_money_direction=signal.direction,
            confidence_score=signal.confidence_score,
            risk_flags=signal.risk_flags or [],
            last_analyzed_at=signal.snapshot_time))
        if len(out) >= limit:
            break
    return HotMarketsResponse(markets=out)


@router.get("/{market_id}/analysis", response_model=MarketAnalysisResponse)
async def market_analysis(
    market_id: str,
    refresh: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    container: Container = Depends(get_container),
) -> MarketAnalysisResponse:
    warnings: list[str] = []
    market = (await db.execute(select(Market).where(
        Market.polymarket_market_id == market_id))).scalar_one_or_none()

    if refresh or market is None:
        try:
            await container.scanner.analyze_single_market(market_id)
        except NotBinaryMarket as exc:
            raise ValidationFailed("only binary Yes/No markets are supported in v1",
                                   details={"market_id": market_id}) from exc
        except UpstreamError as exc:
            if market is None:
                raise
            warnings.append(f"refresh failed, serving cached analysis ({exc.message})")
        market = (await db.execute(select(Market).where(
            Market.polymarket_market_id == market_id))).scalar_one_or_none()

    if market is None:
        raise NotFoundError(f"market {market_id} not found")

    snap = await latest_snapshot(db, market.id)
    signal = await latest_signal(db, market.id)

    summary = MarketSummary(snapshot_time=None)
    if signal is not None:
        summary = MarketSummary(
            snapshot_time=signal.snapshot_time,
            yes_smart_money_count=signal.yes_smart_money_count,
            no_smart_money_count=signal.no_smart_money_count,
            yes_smart_money_notional=signal.yes_smart_money_notional,
            no_smart_money_notional=signal.no_smart_money_notional,
            net_direction=signal.direction, confidence_score=signal.confidence_score,
            risk_flags=signal.risk_flags or [],
            suggested_limit_price=signal.suggested_limit_price,
            suggested_max_notional=signal.suggested_max_notional,
            signal_id=signal.signal_uid)
    else:
        warnings.append("market has not been analyzed yet — run the scanner or use refresh=true")

    holders: list[HolderEntry] = []
    holder_time = (await db.execute(
        select(MarketHolder.snapshot_time).where(MarketHolder.market_id == market.id)
        .order_by(MarketHolder.snapshot_time.desc()).limit(1))).scalar_one_or_none()
    if holder_time is not None:
        rows = (await db.execute(
            select(MarketHolder, Account).join(Account, MarketHolder.account_id == Account.id)
            .where(MarketHolder.market_id == market.id,
                   MarketHolder.snapshot_time == holder_time)
            .order_by(MarketHolder.current_position_value.desc()))).all()
        account_ids = [acc.id for _, acc in rows]
        labels = {row.account_id: row for row in (await db.execute(
            select(AccountLabel).where(AccountLabel.market_id == market.id,
                                       AccountLabel.snapshot_time == holder_time,
                                       AccountLabel.account_id.in_(account_ids or [0])))
            ).scalars().all()}
        stats = {s.account_id: s for s in (await db.execute(
            select(AccountResolvedStats).where(
                AccountResolvedStats.snapshot_time == holder_time,
                AccountResolvedStats.category.is_(None),
                AccountResolvedStats.account_id.in_(account_ids or [0])))).scalars().all()}
        for holder, account in rows:
            label = labels.get(account.id)
            stat = stats.get(account.id)
            holders.append(HolderEntry(
                address=account.wallet_address, profile_name=account.profile_name,
                direction=holder.direction, rank=holder.rank,
                current_position_value=holder.current_position_value,
                shares=holder.shares, average_price=holder.average_price,
                current_price=holder.current_price, value_is_approx=holder.value_is_approx,
                label=(label.label if label else "OTHER"),
                label_reason=(label.reason if label else ""),
                win_rate=(stat.win_rate if stat else 0.0),
                resolved_trade_count=(stat.resolved_trade_count if stat else 0),
                realized_pnl=(stat.realized_pnl if stat else 0.0),
                same_category_win_rate=(stat.same_category_win_rate if stat else 0.0),
                same_category_trade_count=(stat.same_category_trade_count if stat else 0),
                anomaly_index=(label.anomaly_index if label else None),
                smart_money_score=(label.smart_money_score if label else 0.0),
                history_truncated=(stat.history_truncated if stat else False)))

    info = MarketInfo(
        market_id=market.polymarket_market_id, condition_id=market.condition_id,
        question=market.question, category=market.category, slug=market.slug,
        active=market.active, closed=market.closed, accepting_orders=market.accepting_orders,
        neg_risk=market.neg_risk, end_date=market.end_date,
        yes_token_id=market.yes_token_id, no_token_id=market.no_token_id,
        yes_price=snap.yes_price if snap else None, no_price=snap.no_price if snap else None,
        spread=snap.spread if snap else None, midpoint=snap.midpoint if snap else None,
        volume_24h=market.volume_24h, liquidity=market.liquidity,
        open_interest=market.open_interest, tick_size=market.tick_size)
    return MarketAnalysisResponse(market=info, summary=summary, holders=holders,
                                  warnings=warnings)
