from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.deps import Container
from app.core.config import Settings
from app.db import session as session_module
from app.main import create_app
from app.tests import fakes


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def make_test_settings(**overrides: Any) -> Settings:
    base = dict(
        DATABASE_URL="sqlite+aiosqlite://",
        ENABLE_LIVE_TRADING=False,
        GEOBLOCK_FORCE_MODE="",  # tests use the fake geoblock client by default
        SCANNER_MIN_VOLUME_24H=1000.0,
        MIN_LIQUIDITY=1000.0,
        PAPER_TRADE_MIN_CONFIDENCE=0.0,
        SCANNER_INTERVAL_MINUTES=0,
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


def build_test_app(settings: Settings, dataset: dict[str, Any] | None = None,
                   *, geoblock_fail: bool = False,
                   rpc: fakes.FakeRpcClient | None = None,
                   database_url: str | None = None):
    """App + container wired with fake clients over an in-memory sqlite DB (one shared
    connection), or over `database_url` with a real pool — needed by concurrency tests,
    where every session must own its connection and transaction like in production."""
    dataset = dataset or fakes.default_dataset()
    if database_url is None:
        engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool,
                                     connect_args={"check_same_thread": False})
    else:
        engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session_module.reset_engine_for_tests(engine, factory)

    container = Container(
        settings, factory,
        gamma=fakes.FakeGammaClient(dataset),
        data=fakes.FakeDataClient(dataset),
        clob=fakes.FakeClobClient(dataset),
        geoblock=fakes.FakeGeoblockClient(dataset, fail=geoblock_fail),
        rpc=rpc or fakes.FakeRpcClient(),
        log_fetches=False)
    app = create_app(settings=settings, container=container)
    return app, container, dataset


@pytest.fixture
def app_bundle():
    settings = make_test_settings()
    app, container, dataset = build_test_app(settings)
    with TestClient(app) as client:
        yield client, container, dataset


@pytest.fixture
def client(app_bundle):
    return app_bundle[0]


def run_scan_and_wait(client: TestClient, timeout: float = 10.0) -> dict[str, Any]:
    resp = client.post("/api/scanner/run", json={})
    assert resp.status_code == 200, resp.text
    scan_id = resp.json()["scan_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = client.get(f"/api/scanner/status/{scan_id}").json()
        if status["status"] in ("completed", "failed"):
            return status
        time.sleep(0.05)
    raise AssertionError("scan did not finish in time")
