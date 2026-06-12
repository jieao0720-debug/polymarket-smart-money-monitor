"""Data-API client — holders / positions / closed positions.

Verified 2026-06-11: /holders limit hard-capped at 20 (V2); /closed-positions paginated
50/page with sortBy=TIMESTAMP (V4); /positions supports market filter (V3).
"""
from __future__ import annotations

from typing import Any

from app.clients.base import BaseHTTPClient


class DataClient(BaseHTTPClient):
    source = "data"

    async def get_holders(self, condition_id: str, *, limit: int = 20,
                          min_balance: int = 1) -> list[dict[str, Any]]:
        """Returns [{token, holders: [{proxyWallet, amount(shares), outcomeIndex, ...}]}, ...]"""
        params = {"market": condition_id, "limit": min(limit, 20), "minBalance": min_balance}
        data = await self.get_json("/holders", params)
        return data if isinstance(data, list) else []

    async def get_positions(self, user: str, *, condition_id: str | None = None,
                            limit: int = 50, sort_by: str = "CURRENT") -> list[dict[str, Any]]:
        params: dict[str, Any] = {"user": user, "limit": limit, "sortBy": sort_by}
        if condition_id:
            params["market"] = condition_id
        data = await self.get_json("/positions", params)
        return data if isinstance(data, list) else []

    async def get_closed_positions_page(self, user: str, *, limit: int = 50, offset: int = 0,
                                        sort_by: str = "TIMESTAMP",
                                        sort_direction: str = "DESC") -> list[dict[str, Any]]:
        params = {"user": user, "limit": min(limit, 50), "offset": offset,
                  "sortBy": sort_by, "sortDirection": sort_direction}
        data = await self.get_json("/closed-positions", params)
        return data if isinstance(data, list) else []

    async def get_closed_positions(self, user: str, *, max_pages: int = 4
                                   ) -> tuple[list[dict[str, Any]], bool]:
        """Fetch up to max_pages*50 most-recent closed positions.

        Returns (rows, truncated). truncated=True means history may be incomplete
        (ASSUMPTION-A4) and stats must be flagged as such.
        """
        rows: list[dict[str, Any]] = []
        page_size = 50
        for page in range(max_pages):
            batch = await self.get_closed_positions_page(user, limit=page_size,
                                                         offset=page * page_size)
            rows.extend(batch)
            if len(batch) < page_size:
                return rows, False
        return rows, True
