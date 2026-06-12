"""Look-ahead bias guard (spec test area 16, ASSUMPTION-A3).

At a signal timestamp T, only positions resolved at or before T may be counted.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.services.account_profile_service import compute_resolved_stats
from app.services.normalization import NormalizedClosedPosition

T0 = datetime(2026, 1, 1, 12, 0, 0)


def make_pos(*, closed_at: datetime | None, end_date: datetime | None,
             won: bool = True, pnl: float = 50.0, entry: float = 50.0
             ) -> NormalizedClosedPosition:
    return NormalizedClosedPosition(
        wallet_address="0x" + "aa" * 20, condition_id="0x1", direction="YES",
        average_price=0.5, total_bought=entry / 0.5, realized_pnl=pnl,
        final_price=1.0 if won else 0.0, closed_at=closed_at, end_date=end_date,
        title="US election market", event_slug="presidential-election", slug="s")


class TestLookAheadGuard:
    def test_future_resolution_excluded(self):
        """A position that resolves AFTER the signal time must not影响 stats at T."""
        past = make_pos(closed_at=T0 - timedelta(days=10), end_date=T0 - timedelta(days=11))
        future = make_pos(closed_at=T0 + timedelta(days=1), end_date=T0 + timedelta(hours=1),
                          won=True, pnl=1000.0)
        stats = compute_resolved_stats([past, future], as_of=T0)
        assert stats.resolved_trade_count == 1
        assert stats.realized_pnl == pytest.approx(50.0)

    def test_end_date_after_as_of_excluded_even_if_timestamp_before(self):
        """Conservative double condition: ambiguous rows never leak future info."""
        weird = make_pos(closed_at=T0 - timedelta(hours=1), end_date=T0 + timedelta(days=1))
        stats = compute_resolved_stats([weird], as_of=T0)
        assert stats.resolved_trade_count == 0

    def test_missing_closed_at_excluded(self):
        no_ts = make_pos(closed_at=None, end_date=T0 - timedelta(days=1))
        stats = compute_resolved_stats([no_ts], as_of=T0)
        assert stats.resolved_trade_count == 0

    def test_boundary_exactly_at_as_of_included(self):
        at_t = make_pos(closed_at=T0, end_date=T0)
        stats = compute_resolved_stats([at_t], as_of=T0)
        assert stats.resolved_trade_count == 1

    def test_stats_change_with_as_of(self):
        """The same history viewed at two timestamps gives different (correct) stats."""
        p1 = make_pos(closed_at=T0 - timedelta(days=30), end_date=T0 - timedelta(days=31),
                      won=True, pnl=50.0)
        p2 = make_pos(closed_at=T0 + timedelta(days=30), end_date=T0 + timedelta(days=29),
                      won=False, pnl=-50.0)
        early = compute_resolved_stats([p1, p2], as_of=T0)
        late = compute_resolved_stats([p1, p2], as_of=T0 + timedelta(days=60))
        assert early.resolved_trade_count == 1 and early.win_rate == 1.0
        assert late.resolved_trade_count == 2 and late.win_rate == 0.5


class TestStatsArithmetic:
    def test_core_metrics(self):
        positions = [
            make_pos(closed_at=T0 - timedelta(days=3), end_date=T0 - timedelta(days=4),
                     won=True, pnl=100.0, entry=100.0),
            make_pos(closed_at=T0 - timedelta(days=2), end_date=T0 - timedelta(days=3),
                     won=False, pnl=-50.0, entry=50.0),
            make_pos(closed_at=T0 - timedelta(days=1), end_date=T0 - timedelta(days=2),
                     won=True, pnl=30.0, entry=60.0),
        ]
        stats = compute_resolved_stats(positions, as_of=T0)
        assert stats.resolved_trade_count == 3
        assert stats.win_rate == pytest.approx(2 / 3)
        assert stats.realized_pnl == pytest.approx(80.0)
        # ROIs: 1.0, -1.0, 0.5 → mean 1/6
        assert stats.average_roi == pytest.approx((1.0 - 1.0 + 0.5) / 3)
        assert stats.median_entry_notional == pytest.approx(60.0)
        assert stats.first_seen_at == T0 - timedelta(days=3)
        assert stats.last_seen_at == T0 - timedelta(days=1)

    def test_same_category_slice(self):
        politics = make_pos(closed_at=T0 - timedelta(days=2), end_date=T0 - timedelta(days=3))
        crypto = NormalizedClosedPosition(
            wallet_address="0x" + "aa" * 20, condition_id="0x2", direction="NO",
            average_price=0.4, total_bought=100, realized_pnl=-40.0, final_price=0.0,
            closed_at=T0 - timedelta(days=2), end_date=T0 - timedelta(days=3),
            title="Will Bitcoin hit $150k?", event_slug="bitcoin-150k", slug="btc")
        stats = compute_resolved_stats([politics, crypto], as_of=T0)
        pol = stats.category_stats("politics")
        cry = stats.category_stats("crypto")
        assert pol.trade_count == 1 and pol.win_rate == 1.0
        assert cry.trade_count == 1 and cry.win_rate == 0.0
        none_cat = stats.category_stats("sports")
        assert none_cat.trade_count == 0

    def test_empty_history(self):
        stats = compute_resolved_stats([], as_of=T0)
        assert stats.resolved_trade_count == 0
        assert stats.win_rate == 0.0
        assert stats.median_entry_notional == 0.0
