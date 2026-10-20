"""Dependency container: clients + services wired once per app, overridable in tests."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clients.base import LogSink
from app.clients.clob_client import ClobClient
from app.clients.data_client import DataClient
from app.clients.gamma_client import GammaClient
from app.clients.geoblock_client import GeoblockClient
from app.clients.polygon_rpc_client import PolygonRpcClient
from app.core.config import Settings
from app.models import ApiFetchLog
from app.services.account_profile_service import AccountProfileService
from app.services.holder_analysis_service import HolderAnalysisService
from app.services.market_scanner_service import MarketScannerService
from app.services.order_submit_service import OrderSubmitService
from app.services.paper_trade_service import PaperTradeService
from app.services.position_monitor_service import PositionMonitorService
from app.services.scan_registry import ScanRegistry
from app.services.trading_risk_service import TradingRiskService


def make_log_sink(session_factory: async_sessionmaker[AsyncSession]) -> LogSink:
    async def sink(entry: dict[str, Any]) -> None:
        async with session_factory() as session:
            session.add(ApiFetchLog(**entry))
            await session.commit()
    return sink


class Container:
    def __init__(self, settings: Settings,
                 session_factory: async_sessionmaker[AsyncSession], *,
                 gamma: GammaClient | None = None, data: DataClient | None = None,
                 clob: ClobClient | None = None, geoblock: GeoblockClient | None = None,
                 rpc: PolygonRpcClient | None = None, log_fetches: bool = True) -> None:
        self.settings = settings
        self.session_factory = session_factory
        semaphore = asyncio.Semaphore(settings.external_concurrency)
        sink = make_log_sink(session_factory) if log_fetches else None
        common = dict(timeout=settings.http_timeout_seconds, retries=settings.http_retries,
                      semaphore=semaphore, log_sink=sink)

        self.gamma = gamma or GammaClient(settings.polymarket_gamma_base, **common)
        self.data = data or DataClient(settings.polymarket_data_base, **common)
        self.clob = clob or ClobClient(settings.polymarket_clob_base, **common)
        self.geoblock = geoblock or GeoblockClient(settings.geoblock_url, **common)
        self.rpc = rpc or PolygonRpcClient(settings.polygon_rpc_url, **common)

        self.registry = ScanRegistry()
        self.profile_service = AccountProfileService(
            self.data, max_pages=settings.account_history_max_pages,
            cache_ttl_seconds=settings.account_stats_cache_hours * 3600)
        self.holder_analysis = HolderAnalysisService(
            self.data, self.profile_service, holders_per_side=settings.holders_per_side)
        self.paper_trades = PaperTradeService()
        self.risk = TradingRiskService(self.geoblock, settings)
        self.order_submit = OrderSubmitService(clob=self.clob, rpc=self.rpc, risk=self.risk,
                                               settings=settings)
        self.scanner = MarketScannerService(
            gamma=self.gamma, clob=self.clob, holder_analysis=self.holder_analysis,
            paper_trades=self.paper_trades, registry=self.registry,
            session_factory=session_factory, settings=settings)
        self.position_monitor = PositionMonitorService(
            gamma=self.gamma, clob=self.clob, data=self.data,
            paper_trades=self.paper_trades, session_factory=session_factory,
            settings=settings)
        self.background_tasks: set[asyncio.Task] = set()

    def spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)
        return task

    async def aclose(self) -> None:
        for task in list(self.background_tasks):
            task.cancel()
        for client in (self.gamma, self.data, self.clob, self.geoblock, self.rpc):
            try:
                await client.aclose()
            except Exception:
                pass


def get_container(request: Request) -> Container:
    return request.app.state.container


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    container: Container = request.app.state.container
    async with container.session_factory() as session:
        yield session
