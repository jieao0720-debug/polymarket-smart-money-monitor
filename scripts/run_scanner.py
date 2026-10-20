#!/usr/bin/env python3
"""Run one scanner pass from the CLI (read-only against Polymarket APIs).

Usage:
    cd backend && .venv/bin/python ../scripts/run_scanner.py [--max-markets N]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.api.deps import Container  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.logging_utils import configure_logging  # noqa: E402
from app.db.init_db import init_db  # noqa: E402
from app.db.session import get_engine, get_session_factory  # noqa: E402


async def main(max_markets: int | None) -> int:
    settings = get_settings()
    configure_logging(settings.debug)
    await init_db()
    container = Container(settings, get_session_factory())
    try:
        state = await container.registry.start()
        print(f"scan {state.scan_id} started (max_markets="
              f"{max_markets or settings.scanner_max_markets})")
        await container.scanner.run_scan(state.scan_id, max_markets=max_markets)
        print(f"status      : {state.status}")
        print(f"found       : {state.markets_found}")
        print(f"analyzed    : {state.markets_analyzed}")
        print(f"signals     : {state.signals_generated}")
        for err in state.errors:
            print(f"error       : {err}")
        return 0 if state.status == "completed" else 1
    finally:
        await container.aclose()
        await get_engine().dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-markets", type=int, default=None)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.max_markets)))
