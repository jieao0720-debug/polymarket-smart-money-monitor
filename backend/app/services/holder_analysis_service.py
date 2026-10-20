"""Per-market holder analysis: top-20 holders on each side, enriched with the
account's current position in this market and resolved-history stats."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from app.clients.data_client import DataClient
from app.core.errors import UpstreamError
from app.services.account_profile_service import AccountProfileService, ResolvedStats
from app.services.normalization import (
    NormalizedBook,
    NormalizedMarket,
    normalize_holders,
)


@dataclass
class AnalyzedHolder:
    wallet_address: str
    profile_name: str | None
    direction: str
    shares: float
    current_position_value: float
    average_price: float | None
    current_price: float | None
    entry_notional_approx: float | None
    value_is_approx: bool
    rank: int
    stats: ResolvedStats
    # Full other-side holding from /positions; None = lookup failed (A26).
    opposite_shares: float | None = None


class HolderAnalysisService:
    def __init__(self, data_client: DataClient, profile_service: AccountProfileService,
                 *, holders_per_side: int = 20) -> None:
        self.data_client = data_client
        self.profile_service = profile_service
        self.holders_per_side = min(holders_per_side, 20)  # data-api hard cap (V2)

    async def analyze(self, market: NormalizedMarket, yes_book: NormalizedBook | None,
                      no_book: NormalizedBook | None, as_of: datetime
                      ) -> tuple[list[AnalyzedHolder], bool]:
        """Returns (holders sorted+ranked per side, partial_data)."""
        partial = False
        raw_holders = await self.data_client.get_holders(market.condition_id,
                                                         limit=self.holders_per_side)
        holder_rows = normalize_holders(raw_holders, market.token_directions)

        side_price = {
            "YES": (yes_book.midpoint if yes_book else None) or market.yes_price_hint,
            "NO": (no_book.midpoint if no_book else None) or market.no_price_hint,
        }

        async def enrich(row) -> AnalyzedHolder | None:
            nonlocal partial
            try:
                stats = await self.profile_service.get_stats(row.wallet_address, as_of)
            except UpstreamError:
                partial = True
                return None  # without history we cannot label honestly — drop with warning
            positions = await self.profile_service.get_market_positions(
                row.wallet_address, market.condition_id)
            # Match this row's token explicitly — a two-sided account has two positions.
            position = next((p for p in positions or [] if p.token_id == row.token_id), None)
            opposite_shares = (None if positions is None else
                               sum(p.shares for p in positions if p.token_id != row.token_id))
            price = side_price.get(row.direction)
            if position is not None:
                value = position.current_value
                avg_price = position.average_price
                cur_price = position.current_price if position.current_price is not None else price
                entry_approx = position.entry_notional_approx
                value_is_approx = value is None
                if value is None:  # UNCERTAINTY-U4 fallback
                    value = row.shares * (cur_price or 0.0)
            else:
                partial = partial or positions is None
                avg_price = None
                cur_price = price
                entry_approx = None
                value = row.shares * (price or 0.0)
                value_is_approx = True
            if entry_approx is None and value:
                entry_approx = value  # spec-sanctioned fallback, still *_approx (U3)
            return AnalyzedHolder(
                wallet_address=row.wallet_address,
                profile_name=row.profile_name,
                direction=row.direction,
                shares=row.shares,
                current_position_value=round(value or 0.0, 2),
                average_price=avg_price,
                current_price=cur_price,
                entry_notional_approx=entry_approx,
                value_is_approx=value_is_approx,
                rank=0,
                stats=stats,
                opposite_shares=opposite_shares,
            )

        enriched = await asyncio.gather(*(enrich(r) for r in holder_rows))
        holders = [h for h in enriched if h is not None]
        if len(holders) < len(holder_rows):
            partial = True

        ranked: list[AnalyzedHolder] = []
        for direction in ("YES", "NO"):
            side = sorted((h for h in holders if h.direction == direction),
                          key=lambda h: h.current_position_value, reverse=True)
            for i, holder in enumerate(side[: self.holders_per_side], start=1):
                holder.rank = i
                ranked.append(holder)
        return ranked, partial
