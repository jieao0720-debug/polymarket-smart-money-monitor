from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Container, get_container, get_db
from app.core.errors import NotFoundError
from app.models import Market, MarketSnapshot, PaperTrade
from app.schemas.api import (
    PaperTradeCloseRequest,
    PaperTradeCreateRequest,
    PaperTradeEntry,
    PaperTradesResponse,
    PaperTradeSummary,
)

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


def _to_entry(trade: PaperTrade, market: Market,
              snap: MarketSnapshot | None) -> PaperTradeEntry:
    current_price = None
    unrealized = None
    if trade.status == "OPEN" and snap is not None:
        current_price = snap.yes_price if trade.direction == "YES" else snap.no_price
        if current_price is not None:
            unrealized = round(trade.shares * (current_price - trade.entry_price), 4)
    return PaperTradeEntry(
        paper_trade_id=trade.trade_uid, signal_id=trade.signal_id,
        market_id=market.polymarket_market_id, question=market.question,
        direction=trade.direction, entry_price=trade.entry_price,
        entry_time=trade.entry_time, notional=trade.notional, shares=trade.shares,
        exit_price=trade.exit_price, exit_time=trade.exit_time, pnl=trade.pnl,
        unrealized_pnl=unrealized, current_price=current_price,
        status=trade.status, source=trade.source)


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
    snaps = await _latest_prices(db, [m.id for _, m in rows])
    entries = [_to_entry(t, m, snaps.get(m.id)) for t, m in rows]

    # Summary across ALL paper trades (not just the page).
    all_rows = (await db.execute(select(PaperTrade, Market).join(
        Market, PaperTrade.market_id == Market.id))).all()
    all_snaps = await _latest_prices(db, [m.id for _, m in all_rows])
    summary = PaperTradeSummary()
    for trade, market in all_rows:
        if trade.status == "OPEN":
            summary.open_count += 1
            snap = all_snaps.get(market.id)
            price = ((snap.yes_price if trade.direction == "YES" else snap.no_price)
                     if snap else None)
            if price is not None:
                summary.total_unrealized_pnl += trade.shares * (price - trade.entry_price)
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


@router.post("/{paper_trade_id}/close", response_model=PaperTradeEntry)
async def close_paper_trade(paper_trade_id: str, body: PaperTradeCloseRequest,
                            db: AsyncSession = Depends(get_db),
                            container: Container = Depends(get_container)
                            ) -> PaperTradeEntry:
    trade = await container.paper_trades.close(db, paper_trade_id, body.exit_price)
    await db.commit()
    market = (await db.execute(select(Market).where(
        Market.id == trade.market_id))).scalar_one()
    return _to_entry(trade, market, None)
