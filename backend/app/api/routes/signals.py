from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models import Market, SmartMoneySignal
from app.schemas.api import SignalEntry, SignalsResponse

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("", response_model=SignalsResponse)
async def list_signals(
    market_id: str | None = None,
    direction: str | None = Query(default=None, pattern="^(YES|NO|NEUTRAL)$"),
    min_confidence: float | None = Query(default=None, ge=0, le=100),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> SignalsResponse:
    query = select(SmartMoneySignal, Market).join(Market,
                                                  SmartMoneySignal.market_id == Market.id)
    count_query = select(func.count(SmartMoneySignal.id)).join(
        Market, SmartMoneySignal.market_id == Market.id)
    if market_id:
        query = query.where(Market.polymarket_market_id == market_id)
        count_query = count_query.where(Market.polymarket_market_id == market_id)
    if direction:
        query = query.where(SmartMoneySignal.direction == direction)
        count_query = count_query.where(SmartMoneySignal.direction == direction)
    if min_confidence is not None:
        query = query.where(SmartMoneySignal.confidence_score >= min_confidence)
        count_query = count_query.where(SmartMoneySignal.confidence_score >= min_confidence)

    total = (await db.execute(count_query)).scalar_one()
    rows = (await db.execute(query.order_by(SmartMoneySignal.snapshot_time.desc())
                             .offset(offset).limit(limit))).all()
    signals = [SignalEntry(
        signal_id=s.signal_uid, market_id=m.polymarket_market_id, question=m.question,
        category=m.category, snapshot_time=s.snapshot_time, direction=s.direction,
        confidence_score=s.confidence_score,
        yes_smart_money_count=s.yes_smart_money_count,
        no_smart_money_count=s.no_smart_money_count,
        yes_smart_money_notional=s.yes_smart_money_notional,
        no_smart_money_notional=s.no_smart_money_notional,
        risk_flags=s.risk_flags or [],
        suggested_limit_price=s.suggested_limit_price,
        suggested_max_notional=s.suggested_max_notional) for s, m in rows]
    return SignalsResponse(signals=signals, total=total)
