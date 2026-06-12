"""FastAPI application factory.

Safety notes:
- The scheduler (if enabled) only triggers the scanner. There is NO scheduled path to
  order submission (development-rules.md #1).
- CORS is restricted to CORS_ORIGINS (default: localhost:3000).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import Container
from app.api.routes import (
    accounts,
    markets,
    misc,
    paper_trades,
    scanner,
    signals,
    trade_tickets,
    trading,
)
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging_utils import configure_logging
from app.db.init_db import init_db
from app.db.session import get_session_factory

logger = logging.getLogger("app.main")


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.debug)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db()
        app.state.container = container or Container(settings, get_session_factory())
        app.state.scheduler_running = False
        scheduler = None
        if settings.scanner_interval_minutes > 0:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler

            scheduler = AsyncIOScheduler()

            async def scheduled_scan() -> None:
                try:
                    state = await app.state.container.registry.start()
                except Exception:
                    return  # a scan is already running — skip this tick
                await app.state.container.scanner.run_scan(state.scan_id)

            scheduler.add_job(scheduled_scan, "interval",
                              minutes=settings.scanner_interval_minutes)
            scheduler.start()
            app.state.scheduler_running = True
            logger.info("scanner scheduled every %s minutes", settings.scanner_interval_minutes)
        if settings.enable_live_trading:
            logger.warning("ENABLE_LIVE_TRADING=true — live order submission is ACTIVE. "
                           "Review /docs/risk-control.md.")
        yield
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        await app.state.container.aclose()

    app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    register_error_handlers(app)
    for module in (misc, scanner, markets, accounts, signals, trade_tickets,
                   paper_trades, trading):
        app.include_router(module.router)
    return app


app = create_app()
