from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Container, get_container, get_db
from app.schemas.api import HealthResponse, PublicSettingsResponse

router = APIRouter(prefix="/api", tags=["misc"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request, db: AsyncSession = Depends(get_db),
                 container: Container = Depends(get_container)) -> HealthResponse:
    try:
        await db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "error"
    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        version=container.settings.version, database=database,
        time=datetime.now(UTC).replace(tzinfo=None),
        live_trading_enabled=container.settings.enable_live_trading,
        scheduler_running=bool(getattr(request.app.state, "scheduler_running", False)))


@router.get("/settings/public", response_model=PublicSettingsResponse)
async def public_settings(container: Container = Depends(get_container)
                          ) -> PublicSettingsResponse:
    s = container.settings
    return PublicSettingsResponse(
        enable_live_trading=s.enable_live_trading, max_trade_notional=s.max_trade_notional,
        max_slippage_bps=s.max_slippage_bps, max_spread_bps=s.max_spread_bps,
        min_liquidity=s.min_liquidity, min_position_value=s.min_position_value,
        smart_money_score_threshold=s.smart_money_score_threshold,
        scanner_max_markets=s.scanner_max_markets,
        scanner_interval_minutes=s.scanner_interval_minutes,
        close_only_countries=s.close_only_country_list,
        near_resolution_hours=s.near_resolution_hours,
        paper_trade_auto_log=s.paper_trade_auto_log)
