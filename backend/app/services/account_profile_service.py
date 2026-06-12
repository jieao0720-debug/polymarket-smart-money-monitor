"""Account resolved-history profiling with a hard look-ahead guard.

Every statistic accepts `as_of`: only closed positions with closed_at <= as_of AND
end_date <= as_of are counted (ASSUMPTION-A3). Stats computed at a signal timestamp
therefore never see resolutions that happened after that timestamp.
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime

from app.clients.data_client import DataClient
from app.core.errors import UpstreamError
from app.services.normalization import (
    NormalizedClosedPosition,
    NormalizedPosition,
    normalize_closed_position,
    normalize_position,
)


@dataclass
class CategoryStats:
    category: str | None
    trade_count: int = 0
    win_rate: float = 0.0
    average_roi: float = 0.0
    realized_pnl: float = 0.0


@dataclass
class ResolvedStats:
    as_of: datetime
    resolved_trade_count: int = 0
    win_rate: float = 0.0
    realized_pnl: float = 0.0
    average_roi: float = 0.0
    median_entry_notional: float = 0.0
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    history_truncated: bool = False
    by_category: dict[str, CategoryStats] = field(default_factory=dict)

    def category_stats(self, category: str | None) -> CategoryStats:
        if category and category in self.by_category:
            return self.by_category[category]
        return CategoryStats(category=category)


def compute_resolved_stats(closed_positions: list[NormalizedClosedPosition],
                           as_of: datetime, *, history_truncated: bool = False) -> ResolvedStats:
    """Pure function — unit-tested for the look-ahead guard (tests/test_lookahead.py)."""
    eligible = [p for p in closed_positions if p.resolved_before(as_of)]
    stats = ResolvedStats(as_of=as_of, history_truncated=history_truncated)
    if not eligible:
        return stats

    wins = [p for p in eligible if p.won]
    rois = [p.roi for p in eligible if p.roi is not None]
    notionals = [p.entry_notional for p in eligible if p.entry_notional]
    closed_times = [p.closed_at for p in eligible if p.closed_at]

    stats.resolved_trade_count = len(eligible)
    stats.win_rate = len(wins) / len(eligible)
    stats.realized_pnl = sum(p.realized_pnl for p in eligible)
    stats.average_roi = statistics.fmean(rois) if rois else 0.0
    stats.median_entry_notional = statistics.median(notionals) if notionals else 0.0
    stats.first_seen_at = min(closed_times) if closed_times else None
    stats.last_seen_at = max(closed_times) if closed_times else None

    for pos in eligible:
        cat = pos.category()
        if not cat:
            continue
        bucket = stats.by_category.setdefault(cat, CategoryStats(category=cat))
        bucket.trade_count += 1
        bucket.realized_pnl += pos.realized_pnl
    for cat, bucket in stats.by_category.items():
        cat_positions = [p for p in eligible if p.category() == cat]
        cat_wins = sum(1 for p in cat_positions if p.won)
        cat_rois = [p.roi for p in cat_positions if p.roi is not None]
        bucket.win_rate = cat_wins / bucket.trade_count if bucket.trade_count else 0.0
        bucket.average_roi = statistics.fmean(cat_rois) if cat_rois else 0.0
    return stats


def compute_anomaly_index(entry_notional_approx: float | None,
                          median_entry_notional: float) -> float | None:
    """anomaly_index = current entry notional (approx, U3) / median historical entry notional."""
    if entry_notional_approx is None or entry_notional_approx <= 0:
        return None
    if median_entry_notional <= 0:
        return None
    return entry_notional_approx / median_entry_notional


class AccountProfileService:
    """Fetches account history with an in-memory TTL cache (UNCERTAINTY-U9)."""

    def __init__(self, data_client: DataClient, *, max_pages: int = 4,
                 cache_ttl_seconds: float = 6 * 3600) -> None:
        self.data_client = data_client
        self.max_pages = max_pages
        self.cache_ttl = cache_ttl_seconds
        self._cache: dict[str, tuple[float, list[NormalizedClosedPosition], bool]] = {}

    async def get_closed_positions(self, address: str
                                   ) -> tuple[list[NormalizedClosedPosition], bool]:
        address = address.lower()
        cached = self._cache.get(address)
        if cached and (time.monotonic() - cached[0]) < self.cache_ttl:
            return cached[1], cached[2]
        raw, truncated = await self.data_client.get_closed_positions(address,
                                                                     max_pages=self.max_pages)
        positions = [normalize_closed_position(r) for r in raw]
        self._cache[address] = (time.monotonic(), positions, truncated)
        return positions, truncated

    async def get_stats(self, address: str, as_of: datetime) -> ResolvedStats:
        positions, truncated = await self.get_closed_positions(address)
        return compute_resolved_stats(positions, as_of, history_truncated=truncated)

    async def get_market_position(self, address: str, condition_id: str
                                  ) -> NormalizedPosition | None:
        """Current position of `address` in one market (for avg price / value / approx entry)."""
        try:
            raw = await self.data_client.get_positions(address, condition_id=condition_id,
                                                       limit=10)
        except UpstreamError:
            return None
        positions = [normalize_position(r) for r in raw]
        positions = [p for p in positions if p.condition_id == condition_id and p.shares > 0]
        if not positions:
            return None
        # An account can hold both sides; keep the larger value side for holder context.
        positions.sort(key=lambda p: p.current_value or 0.0, reverse=True)
        return positions[0]

    def clear_cache(self) -> None:
        self._cache.clear()
