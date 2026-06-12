"""CLOB API client — order book / prices / order submission (V5).

POST /order is only reachable through order_submit_service, which enforces the
ENABLE_LIVE_TRADING gate and full risk re-checks. Never auto-retried.
"""
from __future__ import annotations

from typing import Any

from app.clients.base import BaseHTTPClient


class ClobClient(BaseHTTPClient):
    source = "clob"

    async def get_book(self, token_id: str) -> dict[str, Any]:
        return await self.get_json("/book", {"token_id": token_id})

    async def get_midpoint(self, token_id: str) -> float | None:
        data = await self.get_json("/midpoint", {"token_id": token_id})
        try:
            return float(data["mid"])
        except (KeyError, TypeError, ValueError):
            return None

    async def get_spread(self, token_id: str) -> float | None:
        data = await self.get_json("/spread", {"token_id": token_id})
        try:
            return float(data["spread"])
        except (KeyError, TypeError, ValueError):
            return None

    async def get_price(self, token_id: str, side: str) -> float | None:
        data = await self.get_json("/price", {"token_id": token_id, "side": side})
        try:
            return float(data["price"])
        except (KeyError, TypeError, ValueError):
            return None

    async def get_clob_market(self, condition_id: str) -> dict[str, Any] | None:
        """CLOB market metadata (tick size, neg_risk, fees) — used pre-order."""
        data = await self.get_json(f"/markets/{condition_id}")
        return data if isinstance(data, dict) else None

    async def post_order(self, body: dict[str, Any],
                         headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
        """Submit a signed order. Caller (order_submit_service) owns all safety gates."""
        return await self.post_json("/order", json_body=body, headers=headers)

    async def derive_api_key(self, l1_headers: dict[str, str]) -> dict[str, Any] | None:
        """GET /auth/derive-api-key with L1 (wallet-signature) headers.

        Returns {apiKey, secret, passphrase} or None. The caller must never persist
        or log the result (development-rules.md #2). UNCERTAINTY-U10: untested live.
        """
        try:
            async with self.semaphore:
                resp = await self._client.get(f"{self.base_url}/auth/derive-api-key",
                                              headers=l1_headers)
            if resp.status_code < 400:
                data = resp.json()
                if isinstance(data, dict) and data.get("apiKey"):
                    return data
            return None
        except Exception:
            return None

    async def create_api_key(self, l1_headers: dict[str, str]) -> dict[str, Any] | None:
        """POST /auth/api-key (first-time credential creation). Same secrecy rules."""
        try:
            async with self.semaphore:
                resp = await self._client.post(f"{self.base_url}/auth/api-key",
                                               headers=l1_headers)
            if resp.status_code < 400:
                data = resp.json()
                if isinstance(data, dict) and data.get("apiKey"):
                    return data
            return None
        except Exception:
            return None
