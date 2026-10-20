from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Container, get_container, get_db
from app.core.errors import NotFoundError, UpstreamError
from app.models import (
    Market,
    MarketSnapshot,
    PaperTrade,
    PaperTradeCohortMember,
    PaperTradeExit,
    PositionObservation,
)
from app.schemas.api import (
    CohortMemberEntry,
    MonitorRunResponse,
    PaperTradeCloseRequest,
    PaperTradeCreateRequest,
    PaperTradeEntry,
    PaperTradeExitEntry,
    PaperTradesResponse,
    PaperTradeSummary,
    PositionObservationEntry,
    PositionObservationsResponse,
    ShadowExitSummary,
)
from app.services.normalization import normalize_book
from app.services.paper_trade_service import pick_mark

router = APIRouter(prefix="/api/paper-trades", tags=["paper-trades"])


async def _latest_prices(db: AsyncSession, market_ids: list[int]) -> dict[int, MarketSnapshot]:
    out: dict[int, MarketSnapshot] = {}
    for market_id in set(market_ids):
        snap = (await db.execute(
            select(MarketSnapshot).where(MarketSnapshot.market_id == market_id)
            .order_by(MarketSnapshot.snapshot_time.desc()).limit(1))).scalar_one_or_none()
        if snap is not None:
            out[market_id] = snap
    return out


async def _latest_observations(db: AsyncSession,
                               trade_ids: list[int]) -> dict[int, PositionObservation]:
    out: dict[int, PositionObservation] = {}
    for trade_id in set(trade_ids):
        obs = (await db.execute(
            select(PositionObservation).where(PositionObservation.paper_trade_id == trade_id)
            .order_by(PositionObservation.observed_at.desc()).limit(1))).scalar_one_or_none()
        if obs is not None:
            out[trade_id] = obs
    return out


def _to_entry(trade: PaperTrade, market: Market, snap: MarketSnapshot | None,
              obs: PositionObservation | None = None) -> PaperTradeEntry:
    current_price = None
    unrealized = None
    basis = None
    as_of = None
    if trade.status == "OPEN":
        mark = pick_mark(direction=trade.direction, snapshot=snap, observation=obs)
        if mark is not None:
            current_price, basis, as_of = mark.price, mark.basis, mark.as_of
            unrealized = round(trade.open_shares * (current_price - trade.entry_price), 4)
    shadow = None
    if obs is not None:
        shadow = ShadowExitSummary(
            observed_at=obs.observed_at, market_status=obs.market_status,
            retention=obs.retention, coverage=obs.coverage,
            liquidation_return=obs.liquidation_return,
            target_fraction=obs.shadow_target_fraction,
            triggers=sorted((obs.shadow_state or {}).get("fired_at", {}).keys()))
    return PaperTradeEntry(
        paper_trade_id=trade.trade_uid, signal_id=trade.signal_id,
        market_id=market.polymarket_market_id, question=market.question,
        direction=trade.direction, entry_price=trade.entry_price,
        entry_time=trade.entry_time, notional=trade.notional, shares=trade.shares,
        remaining_shares=trade.open_shares, exit_price=trade.exit_price,
        exit_time=trade.exit_time, pnl=trade.pnl,
        unrealized_pnl=unrealized, current_price=current_price, price_basis=basis,
        price_as_of=as_of, status=trade.status, source=trade.source,
        exit_reason=trade.exit_reason, shadow=shadow)


@router.post("", response_model=PaperTradeEntry, status_code=201)
async def create_paper_trade(body: PaperTradeCreateRequest,
                             db: AsyncSession = Depends(get_db),
                             container: Container = Depends(get_container)
                             ) -> PaperTradeEntry:
    market = (await db.execute(select(Market).where(
        Market.polymarket_market_id == body.market_id))).scalar_one_or_none()
    if market is None:
        raise NotFoundError(
            f"market {body.market_id} not found locally — analyze it first "
            "(GET /api/markets/{id}/analysis?refresh=true)")
    trade = await container.paper_trades.create_manual(
        db, market_row=market, direction=body.direction, notional=body.notional,
        entry_price=body.entry_price, signal_id=body.signal_id)
    await db.commit()
    snap = (await _latest_prices(db, [market.id])).get(market.id)
    return _to_entry(trade, market, snap)


@router.get("", response_model=PaperTradesResponse)
async def list_paper_trades(status: str | None = Query(default=None,
                                                       pattern="^(OPEN|CLOSED|CANCELLED)$"),
                            market_id: str | None = None,
                            limit: int = Query(default=100, ge=1, le=500),
                            offset: int = Query(default=0, ge=0),
                            db: AsyncSession = Depends(get_db)) -> PaperTradesResponse:
    query = select(PaperTrade, Market).join(Market, PaperTrade.market_id == Market.id)
    count_q = select(func.count(PaperTrade.id)).join(Market,
                                                     PaperTrade.market_id == Market.id)
    if status:
        query = query.where(PaperTrade.status == status)
        count_q = count_q.where(PaperTrade.status == status)
    if market_id:
        query = query.where(Market.polymarket_market_id == market_id)
        count_q = count_q.where(Market.polymarket_market_id == market_id)
    total = (await db.execute(count_q)).scalar_one()
    rows = (await db.execute(query.order_by(PaperTrade.entry_time.desc())
                             .offset(offset).limit(limit))).all()

    # Summary across ALL paper trades (not just the page).
    all_rows = (await db.execute(select(PaperTrade, Market).join(
        Market, PaperTrade.market_id == Market.id))).all()
    snaps = await _latest_prices(db, [m.id for _, m in all_rows])
    observations = await _latest_observations(db, [t.id for t, _ in all_rows])
    entries = [_to_entry(t, m, snaps.get(m.id), observations.get(t.id)) for t, m in rows]
    summary = PaperTradeSummary()
    for trade, market in all_rows:
        if trade.status == "OPEN":
            summary.open_count += 1
            mark = pick_mark(direction=trade.direction, snapshot=snaps.get(market.id),
                             observation=observations.get(trade.id))
            if mark is not None:
                summary.total_unrealized_pnl += (trade.open_shares
                                                 * (mark.price - trade.entry_price))
            if trade.pnl is not None:  # realized part of a partially exited position
                summary.total_realized_pnl += trade.pnl
        elif trade.status == "CLOSED":
            summary.closed_count += 1
            if trade.pnl is not None:
                summary.total_realized_pnl += trade.pnl
                if trade.pnl > 0:
                    summary.win_count += 1
                elif trade.pnl < 0:
                    summary.loss_count += 1
    summary.total_realized_pnl = round(summary.total_realized_pnl, 2)
    summary.total_unrealized_pnl = round(summary.total_unrealized_pnl, 2)
    return PaperTradesResponse(paper_trades=entries, total=total, summary=summary)


@router.post("/monitor/run", response_model=MonitorRunResponse)
async def run_position_monitor(container: Container = Depends(get_container)
                               ) -> MonitorRunResponse:
    """One position-monitor pass: settles resolved markets and records shadow exit
    observations. Never closes or reduces a position for any other reason."""
    result = await container.position_monitor.run_once()
    return MonitorRunResponse(
        started_at=result.started_at, finished_at=result.finished_at,
        open_trades=result.open_trades, observations=result.observations,
        settled=result.settled, cohorts_backfilled=result.cohorts_backfilled,
        errors=result.errors)


@router.get("/{paper_trade_id}/observations", response_model=PositionObservationsResponse)
async def list_observations(paper_trade_id: str,
                            limit: int = Query(default=200, ge=1, le=2000),
                            db: AsyncSession = Depends(get_db)
                            ) -> PositionObservationsResponse:
    trade = (await db.execute(select(PaperTrade).where(
        PaperTrade.trade_uid == paper_trade_id))).scalar_one_or_none()
    if trade is None:
        raise NotFoundError(f"paper trade {paper_trade_id} not found")
    cohort = (await db.execute(select(PaperTradeCohortMember).where(
        PaperTradeCohortMember.paper_trade_id == trade.id)
        .order_by(PaperTradeCohortMember.weight.desc()))).scalars().all()
    exits = (await db.execute(select(PaperTradeExit).where(
        PaperTradeExit.paper_trade_id == trade.id)
        .order_by(PaperTradeExit.exit_time))).scalars().all()
    observations = (await db.execute(select(PositionObservation).where(
        PositionObservation.paper_trade_id == trade.id)
        .order_by(PositionObservation.observed_at.desc()).limit(limit))).scalars().all()
    return PositionObservationsResponse(
        paper_trade_id=trade.trade_uid,
        cohort=[CohortMemberEntry(
            wallet_address=m.wallet_address, entry_shares=m.entry_shares,
            entry_opposite_shares=m.entry_opposite_shares,
            entry_net_exposure=m.entry_net_exposure, entry_value=m.entry_value,
            weight=m.weight, smart_money_score=m.smart_money_score, label=m.label,
            source=m.source, baseline_verified=m.entry_baseline_verified is True)
            for m in cohort],
        exits=[PaperTradeExitEntry(
            exit_time=x.exit_time, shares=x.shares, price=x.price, proceeds=x.proceeds,
            fee=x.fee, reason=x.reason, pnl=x.pnl) for x in exits],
        observations=[PositionObservationEntry(
            observed_at=o.observed_at, market_status=o.market_status, best_bid=o.best_bid,
            best_ask=o.best_ask, liquidation_price=o.liquidation_price,
            liquidation_value=o.liquidation_value,
            liquidation_fill_ratio=o.liquidation_fill_ratio,
            liquidation_return=o.liquidation_return, retention=o.retention,
            coverage=o.coverage, cohort_detail=o.cohort_detail,
            latest_signal_direction=o.latest_signal_direction,
            latest_signal_time=o.latest_signal_time, shadow_state=o.shadow_state,
            shadow_triggers=o.shadow_triggers,
            shadow_target_fraction=o.shadow_target_fraction,
            data_issues=o.data_issues) for o in observations])


@router.post("/{paper_trade_id}/close", response_model=PaperTradeEntry)
async def close_paper_trade(paper_trade_id: str, body: PaperTradeCloseRequest,
                            db: AsyncSession = Depends(get_db),
                            container: Container = Depends(get_container)
                            ) -> PaperTradeEntry:
    """No exit_price → sell into the live bid ladder (net of PAPER_EXIT_FEE_BPS); only the
    depth the book can absorb is filled, the rest stays OPEN (A24)."""
    bids = None
    if body.exit_price is None:
        row = (await db.execute(select(PaperTrade, Market).join(
            Market, PaperTrade.market_id == Market.id).where(
            PaperTrade.trade_uid == paper_trade_id))).first()
        if row is not None:
            open_trade, market_row = row
            token = (market_row.yes_token_id if open_trade.direction == "YES"
                     else market_row.no_token_id)
            try:
                bids = normalize_book(await container.clob.get_book(token), token).bids
            except UpstreamError:
                bids = None
    trade = await container.paper_trades.close(
        db, paper_trade_id, body.exit_price, bids=bids,
        fee_bps=container.settings.paper_exit_fee_bps)
    await db.commit()
    market = (await db.execute(select(Market).where(
        Market.id == trade.market_id))).scalar_one()
    snap = (await _latest_prices(db, [market.id])).get(market.id)
    return _to_entry(trade, market, snap)
