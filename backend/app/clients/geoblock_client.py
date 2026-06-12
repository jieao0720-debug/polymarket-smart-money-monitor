"""Geoblock client (V6): GET https://polymarket.com/api/geoblock → {blocked, ip, country, region}.

The caller (trading_risk_service) maps this to OK / CLOSE_ONLY / BLOCKED and treats
fetch failures as BLOCKED (fail-closed). This client never interprets policy.
"""
from __future__ import annotations

from typing import Any

from app.clients.base import BaseHTTPClient


class GeoblockClient(BaseHTTPClient):
    source = "geoblock"

    def __init__(self, geoblock_url: str, **kwargs: Any) -> None:
        super().__init__(base_url="", **kwargs)
        self.geoblock_url = geoblock_url

    async def check(self) -> dict[str, Any]:
        """Raw geoblock response. Raises UpstreamError on failure (caller fails closed)."""
        data = await self.get_json(self.geoblock_url)
        if not isinstance(data, dict) or "blocked" not in data:
            from app.core.errors import UpstreamError
            raise UpstreamError("geoblock response malformed", details={"got": str(data)[:100]})
        return data
