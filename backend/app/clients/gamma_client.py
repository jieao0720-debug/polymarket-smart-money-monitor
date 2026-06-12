"""Gamma API client — markets/events metadata. Verified 2026-06-11 (UNCERTAINTY-V1)."""
from __future__ import annotations

from typing import Any

from app.clients.base import BaseHTTPClient


class GammaClient(BaseHTTPClient):
    source = "gamma"

    async def list_markets(self, *, limit: int = 100, offset: int = 0, active: bool = True,
                           closed: bool = False, order: str = "volume24hr",
                           ascending: bool = False) -> list[dict[str, Any]]:
        params = {"limit": limit, "offset": offset, "active": str(active).lower(),
                  "closed": str(closed).lower(), "order": order,
                  "ascending": str(ascending).lower()}
        data = await self.get_json("/markets", params)
        return data if isinstance(data, list) else []

    async def get_market(self, gamma_market_id: str) -> dict[str, Any] | None:
        data = await self.get_json(f"/markets/{gamma_market_id}")
        return data if isinstance(data, dict) else None

    async def get_event(self, event_id: str) -> dict[str, Any] | None:
        data = await self.get_json("/events", {"id": event_id})
        if isinstance(data, list) and data:
            return data[0]
        return data if isinstance(data, dict) else None
