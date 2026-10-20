#!/usr/bin/env python3
"""Run one position-monitor pass from the CLI (read-only against Polymarket APIs).

Settles OPEN paper trades whose market has officially resolved and records a shadow
exit observation for every other OPEN paper trade. Never touches real orders.

Usage:
    cd backend && .venv/bin/python ../scripts/run_monitor.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.api.deps import Container  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.logging_utils import configure_logging  # noqa: E402
from app.db.init_db import init_db  # noqa: E402
from app.db.session import get_engine, get_session_factory  # noqa: E402


async def main() -> int:
    settings = get_settings()
    configure_logging(settings.debug)
    await init_db()
    container = Container(settings, get_session_factory())
    try:
        result = await container.position_monitor.run_once()
        print(f"open trades : {result.open_trades}")
        print(f"observations: {result.observations}")
        print(f"settled     : {result.settled}")
        print(f"backfilled  : {result.cohorts_backfilled}")
        for err in result.errors:
            print(f"error       : {err}")
        return 0 if not result.errors else 1
    finally:
        await container.aclose()
        await get_engine().dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
