#!/usr/bin/env python3
"""Seed the local database with deterministic demo data (no network needed) so the
frontend can be developed/демoed offline.

Usage:
    cd backend && .venv/bin/python ../scripts/seed.py
"""
from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db.init_db import init_db  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.models import (  # noqa: E402
    Account,
    AccountLabel,
    AccountResolvedStats,
    Market,
    MarketHolder,
    MarketSnapshot,
    PaperTrade,
    SmartMoneySignal,
)

NOW = datetime.now(UTC).replace(tzinfo=None)

DEMO_MARKETS = [
    dict(polymarket_market_id="900001", condition_id="0xdemo1",
         question="Will the Fed cut rates at the next FOMC meeting?",
         slug="fed-cut-next-fomc", category="economy", tags=["Economy", "Fed"],
         yes_price=0.62, no_price=0.38, volume_24h=250_000, liquidity=80_000,
         direction="YES", confidence=71.5, yes_n=42_000, no_n=9_000,
         risk_flags=[]),
    dict(polymarket_market_id="900002", condition_id="0xdemo2",
         question="Will Bitcoin close above $150k this month?",
         slug="btc-150k-month", category="crypto", tags=["Crypto", "Bitcoin"],
         yes_price=0.18, no_price=0.82, volume_24h=410_000, liquidity=120_000,
         direction="NO", confidence=58.0, yes_n=4_000, no_n=21_000,
         risk_flags=["NEAR_RESOLUTION"]),
    dict(polymarket_market_id="900003", condition_id="0xdemo3",
         question="Will Team Alpha win the championship final?",
         slug="team-alpha-final", category="sports", tags=["Sports"],
         yes_price=0.45, no_price=0.55, volume_24h=95_000, liquidity=30_000,
         direction="NEUTRAL", confidence=0.0, yes_n=5_000, no_n=5_200,
         risk_flags=["LOW_SMART_SAMPLE"]),
]

DEMO_HOLDERS = [
    # (address suffix, direction, shares, value, avg_price, label, score, n, wr, pnl)
    ("a1", "YES", 50_000, 31_000, 0.55, "HIGH_WIN_RATE", 78.2, 64, 0.71, 18_400),
    ("a2", "YES", 18_000, 11_160, 0.58, "OTHER", 41.0, 12, 0.5, 220),
    ("a3", "YES", 9_000, 5_580, 0.61, "NEW_ACCOUNT", 0.0, 0, 0.0, 0.0),
    ("b1", "NO", 22_000, 8_360, 0.40, "ABNORMAL_POSITION", 52.4, 15, 0.53, 950),
    ("b2", "NO", 4_000, 1_520, 0.36, "OTHER", 22.0, 3, 0.33, -120),
]


async def seed() -> None:
    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        for spec in DEMO_MARKETS:
            market = Market(
                polymarket_market_id=spec["polymarket_market_id"],
                condition_id=spec["condition_id"], event_id="evt-demo",
                question=spec["question"], slug=spec["slug"], category=spec["category"],
                tags=spec["tags"], yes_token_id=f"{spec['condition_id']}-yes",
                no_token_id=f"{spec['condition_id']}-no", active=True, closed=False,
                accepting_orders=True, neg_risk=False, tick_size=0.01,
                end_date=NOW + timedelta(days=21), volume=2_000_000,
                volume_24h=spec["volume_24h"], liquidity=spec["liquidity"],
                open_interest=spec["liquidity"] * 3)
            session.add(market)
            await session.flush()

            session.add(MarketSnapshot(
                market_id=market.id, snapshot_time=NOW, yes_price=spec["yes_price"],
                no_price=spec["no_price"], spread=0.01,
                midpoint=spec["yes_price"], best_bid=spec["yes_price"] - 0.005,
                best_ask=spec["yes_price"] + 0.005,
                orderbook_depth={"yes": {"bid_depth_usdc": 12_000, "ask_depth_usdc": 9_000,
                                         "top3_ask_usdc": 4_000},
                                 "no": {"bid_depth_usdc": 8_000, "ask_depth_usdc": 7_000,
                                        "top3_ask_usdc": 3_000}},
                volume_24h=spec["volume_24h"], liquidity=spec["liquidity"],
                open_interest=spec["liquidity"] * 3))

            signal = SmartMoneySignal(
                market_id=market.id, snapshot_time=NOW, direction=spec["direction"],
                confidence_score=spec["confidence"],
                yes_smart_money_count=2 if spec["direction"] == "YES" else 0,
                no_smart_money_count=2 if spec["direction"] == "NO" else 0,
                yes_smart_money_notional=spec["yes_n"],
                no_smart_money_notional=spec["no_n"],
                risk_flags=spec["risk_flags"],
                suggested_limit_price=(spec["yes_price"] + 0.01
                                       if spec["direction"] == "YES"
                                       else spec["no_price"] + 0.01
                                       if spec["direction"] == "NO" else None),
                suggested_max_notional=100.0 if spec["direction"] != "NEUTRAL" else None,
                score_inputs={"seeded": True})
            session.add(signal)
            await session.flush()

            if spec["direction"] != "NEUTRAL":
                entry = (spec["yes_price"] if spec["direction"] == "YES"
                         else spec["no_price"]) + 0.005
                session.add(PaperTrade(
                    signal_id=signal.signal_uid, market_id=market.id,
                    direction=spec["direction"], entry_price=round(entry, 3),
                    entry_time=NOW, notional=100.0,
                    shares=round(100.0 / entry, 4), status="OPEN", source="AUTO_SIGNAL"))

            if spec["polymarket_market_id"] == "900001":
                for i, (suffix, direction, shares, value, avg_price, label, score,
                        n, wr, pnl) in enumerate(DEMO_HOLDERS):
                    account = Account(wallet_address="0x" + suffix * 20,
                                      profile_name=f"demo-{suffix}",
                                      first_seen_at=NOW - timedelta(days=300))
                    session.add(account)
                    await session.flush()
                    session.add(MarketHolder(
                        market_id=market.id, account_id=account.id, snapshot_time=NOW,
                        direction=direction, shares=shares,
                        current_position_value=value, average_price=avg_price,
                        current_price=spec["yes_price"] if direction == "YES"
                        else spec["no_price"],
                        entry_notional_approx=avg_price * shares,
                        rank=i + 1, value_is_approx=False))
                    session.add(AccountResolvedStats(
                        account_id=account.id, category=None, snapshot_time=NOW,
                        resolved_trade_count=n, win_rate=wr, realized_pnl=pnl,
                        average_roi=0.18 if pnl > 0 else -0.1,
                        median_entry_notional=max(50.0, value / 50),
                        same_category_trade_count=max(0, n // 2),
                        same_category_win_rate=wr, same_category_roi=0.15,
                        history_truncated=False))
                    session.add(AccountLabel(
                        account_id=account.id, market_id=market.id, snapshot_time=NOW,
                        label=label, anomaly_index=6.2 if label == "ABNORMAL_POSITION"
                        else 1.1, smart_money_score=score,
                        score_breakdown={"seeded": True},
                        reason=f"Seeded demo holder ({label})."))
        await session.commit()
    print(f"Seeded {len(DEMO_MARKETS)} markets, holders, signals and paper trades.")


if __name__ == "__main__":
    asyncio.run(seed())
