from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Container, get_container, get_db
from app.core.errors import ValidationFailed
from app.models import Account, Market, MarketSnapshot
from app.schemas.api import (
    AccountCategoryStats,
    AccountCurrentMarket,
    AccountOverallStats,
    AccountProfileResponse,
)
from app.services.scoring import MarketRiskContext
from app.services.signal_service import hours_to_resolution
from app.services.smart_money_service import assess_holder

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


@router.get("/{address}/profile", response_model=AccountProfileResponse)
async def account_profile(
    address: str,
    market_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    container: Container = Depends(get_container),
) -> AccountProfileResponse:
    if not ADDRESS_RE.match(address):
        raise ValidationFailed("invalid wallet address format")
    address = address.lower()
    now = datetime.now(UTC).replace(tzinfo=None)
    warnings: list[str] = []

    stats = await container.profile_service.get_stats(address, as_of=now)
    if stats.history_truncated:
        warnings.append("history truncated at fetch limit — stats cover most recent "
                        "closed positions only (ASSUMPTION-A4)")

    account_row = (await db.execute(select(Account).where(
        Account.wallet_address == address))).scalar_one_or_none()

    same_category = None
    current_market = None
    if market_id:
        market = (await db.execute(select(Market).where(
            Market.polymarket_market_id == market_id))).scalar_one_or_none()
        if market is None:
            warnings.append(f"market {market_id} not in local DB — run analysis first; "
                            "returning overall stats only")
        else:
            cat_stats = stats.category_stats(market.category)
            same_category = AccountCategoryStats(
                category=market.category, trade_count=cat_stats.trade_count,
                win_rate=cat_stats.win_rate, average_roi=cat_stats.average_roi)

            position = await container.profile_service.get_market_position(
                address, market.condition_id)
            snap = (await db.execute(
                select(MarketSnapshot).where(MarketSnapshot.market_id == market.id)
                .order_by(MarketSnapshot.snapshot_time.desc()).limit(1))).scalar_one_or_none()
            value = position.current_value if position else None
            entry_approx = position.entry_notional_approx if position else None
            if entry_approx is None and value is not None:
                entry_approx = value  # UNCERTAINTY-U3 fallback, still approximate
            ctx = MarketRiskContext(
                spread=snap.spread if snap else None,
                liquidity=market.liquidity,
                hours_to_resolution=hours_to_resolution(market.end_date, now),
                entry_price=(position.current_price if position else None),
                max_spread_abs=container.settings.max_spread_abs,
                min_liquidity=container.settings.min_liquidity,
                near_resolution_hours=container.settings.near_resolution_hours,
                extreme_price_low=container.settings.extreme_price_low,
                extreme_price_high=container.settings.extreme_price_high)
            assessment = assess_holder(
                stats=stats, category=market.category,
                entry_notional_approx=entry_approx,
                current_position_value=value or 0.0, market_ctx=ctx,
                min_position_value=container.settings.min_position_value,
                smart_money_score_threshold=container.settings.smart_money_score_threshold)
            current_market = AccountCurrentMarket(
                market_id=market.polymarket_market_id,
                direction=position.direction if position else None,
                shares=position.shares if position else None,
                average_price=position.average_price if position else None,
                current_position_value=value,
                entry_notional_approx=entry_approx,
                anomaly_index=assessment.anomaly_index,
                label=assessment.label, label_reason=assessment.reason,
                smart_money_score=assessment.smart_money_score)

    return AccountProfileResponse(
        address=address,
        profile_name=account_row.profile_name if account_row else None,
        first_seen_at=(account_row.first_seen_at if account_row else stats.first_seen_at),
        last_seen_at=stats.last_seen_at,
        as_of=now,
        history_truncated=stats.history_truncated,
        overall=AccountOverallStats(
            resolved_trade_count=stats.resolved_trade_count, win_rate=stats.win_rate,
            realized_pnl=stats.realized_pnl, average_roi=stats.average_roi,
            median_entry_notional=stats.median_entry_notional),
        same_category=same_category,
        current_market=current_market,
        warnings=warnings)
