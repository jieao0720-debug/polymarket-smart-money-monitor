"""Minimal Polygon JSON-RPC client for USDC.e balance / allowance reads.

Hand-encoded eth_call (no web3 dependency). Contract addresses: architecture.md §6
(UNCERTAINTY-U12 — re-verify on polygonscan before enabling live trading).
"""
from __future__ import annotations

from app.clients.base import BaseHTTPClient

USDC_E_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
CTF_EXCHANGE_ADDRESS = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
NEG_RISK_EXCHANGE_ADDRESS = "0xC5d563A36AE78145C45a50134d48A1215220f80a"
USDC_DECIMALS = 6

_SELECTOR_BALANCE_OF = "0x70a08231"
_SELECTOR_ALLOWANCE = "0xdd62ed3e"


def _pad_address(address: str) -> str:
    return address.lower().replace("0x", "").rjust(64, "0")


class PolygonRpcClient(BaseHTTPClient):
    source = "rpc"

    _rpc_id = 0

    async def _eth_call(self, to: str, data: str) -> int | None:
        PolygonRpcClient._rpc_id += 1
        body = {"jsonrpc": "2.0", "id": PolygonRpcClient._rpc_id, "method": "eth_call",
                "params": [{"to": to, "data": data}, "latest"]}
        status, resp = await self.post_json(self.base_url or "/", json_body=body)
        if status >= 400 or not isinstance(resp, dict) or "result" not in resp:
            return None
        try:
            return int(resp["result"], 16)
        except (TypeError, ValueError):
            return None

    async def get_usdc_balance(self, wallet: str) -> float | None:
        raw = await self._eth_call(USDC_E_ADDRESS, _SELECTOR_BALANCE_OF + _pad_address(wallet))
        return None if raw is None else raw / 10**USDC_DECIMALS

    async def get_usdc_allowance(self, owner: str, spender: str) -> float | None:
        data = _SELECTOR_ALLOWANCE + _pad_address(owner) + _pad_address(spender)
        raw = await self._eth_call(USDC_E_ADDRESS, data)
        return None if raw is None else raw / 10**USDC_DECIMALS

    async def get_native_balance(self, wallet: str) -> float | None:
        PolygonRpcClient._rpc_id += 1
        body = {"jsonrpc": "2.0", "id": PolygonRpcClient._rpc_id,
                "method": "eth_getBalance", "params": [wallet, "latest"]}
        status, resp = await self.post_json(self.base_url or "/", json_body=body)
        if status >= 400 or not isinstance(resp, dict) or "result" not in resp:
            return None
        try:
            return int(resp["result"], 16) / 10**18
        except (TypeError, ValueError):
            return None
