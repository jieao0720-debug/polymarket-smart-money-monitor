"""Live order submission — the ONLY module allowed to call clob.post_order.

Gate order (risk-control.md):
  1. ticket state machine (CONFIRMED by an explicit manual confirmation, not expired)
  2. ENABLE_LIVE_TRADING hard gate (default false → 403, ticket REJECTED)
  3. full risk re-check against fresh market/book/geoblock data
  4. balance + allowance verification (fail-closed on RPC failure)
  5. signed payload sanity validation (shape only — the signature itself was produced
     by the user's wallet in the frontend; the backend never sees a private key)
  6. single non-retried POST to CLOB; result persisted on the ticket.

Credentials passed through are used in-memory for header construction only — never
persisted, never logged (logging_utils redaction also covers accidental leaks).
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.clob_auth import ClobCredentials, build_l2_headers
from app.clients.clob_client import ClobClient
from app.clients.polygon_rpc_client import (
    CTF_EXCHANGE_ADDRESS,
    NEG_RISK_EXCHANGE_ADDRESS,
    PolygonRpcClient,
)
from app.core.config import Settings
from app.core.errors import (
    LiveTradingDisabledError,
    RiskCheckFailedError,
    ValidationFailed,
)
from app.models import TradeTicket
from app.services.normalization import NormalizedBook, NormalizedMarket
from app.services.trading_risk_service import TradingRiskService

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_REQUIRED_ORDER_FIELDS = {"salt", "maker", "signer", "taker", "tokenId", "makerAmount",
                          "takerAmount", "expiration", "nonce", "feeRateBps", "side",
                          "signatureType", "signature"}


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def validate_signed_payload(payload: dict[str, Any], *, wallet_address: str,
                            expected_token_id: str) -> dict[str, Any]:
    """Shape validation only. Raises ValidationFailed with a safe message
    (never echoes the signature back)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("order"), dict):
        raise ValidationFailed("signed_order_payload.order is required")
    order = payload["order"]
    missing = _REQUIRED_ORDER_FIELDS - set(order)
    if missing:
        raise ValidationFailed("signed order is missing required fields",
                               details={"missing": sorted(missing)})
    if str(order.get("maker", "")).lower() != wallet_address.lower():
        raise ValidationFailed("order.maker does not match the submitting wallet")
    if str(order.get("tokenId")) != str(expected_token_id):
        raise ValidationFailed("order.tokenId does not match the ticket's market direction")
    if order.get("side") not in ("BUY", 0, "0"):
        raise ValidationFailed("v1 only supports BUY orders (ASSUMPTION-A12)")
    if order.get("signatureType") not in (0, 1, 2):
        raise ValidationFailed("invalid signatureType")
    sig = str(order.get("signature", ""))
    if not sig.startswith("0x") or len(sig) < 65:
        raise ValidationFailed("order.signature looks invalid")
    order_type = payload.get("orderType", "GTC")
    if order_type not in ("GTC", "FOK", "GTD", "FAK"):
        raise ValidationFailed("invalid orderType")
    body = {"order": order, "owner": str(payload.get("owner", "")), "orderType": order_type}
    return body


class OrderSubmitService:
    def __init__(self, *, clob: ClobClient, rpc: PolygonRpcClient,
                 risk: TradingRiskService, settings: Settings) -> None:
        self.clob = clob
        self.rpc = rpc
        self.risk = risk
        self.settings = settings

    async def submit(self, session: AsyncSession, *, ticket: TradeTicket,
                     market: NormalizedMarket, book: NormalizedBook | None,
                     wallet_address: str, signed_order_payload: dict[str, Any],
                     credentials: ClobCredentials | None) -> dict[str, Any]:
        if not ADDRESS_RE.match(wallet_address):
            raise ValidationFailed("invalid wallet address")
        now = _utcnow()

        # 1. ticket state machine
        if ticket.status != "CONFIRMED":
            raise ValidationFailed(
                f"ticket must be CONFIRMED before submission (current: {ticket.status})")
        if ticket.expires_at is not None and ticket.expires_at < now:
            ticket.status = "EXPIRED"
            await session.commit()
            raise ValidationFailed("ticket has expired — create a new one (stale prices)")
        if ticket.wallet_address and ticket.wallet_address.lower() != wallet_address.lower():
            raise ValidationFailed("wallet does not match the confirming wallet")

        # 2. hard live-trading gate (the default-deny safety property)
        if not self.settings.enable_live_trading:
            ticket.status = "REJECTED"
            ticket.error_message = "live trading is disabled (ENABLE_LIVE_TRADING=false)"
            await session.commit()
            raise LiveTradingDisabledError(
                "Live trading is disabled. Set ENABLE_LIVE_TRADING=true only after "
                "reviewing /docs/risk-control.md.")

        # 3. full risk re-check on fresh data
        checks = await self.risk.run_ticket_checks(
            market=market, book=book, limit_price=ticket.limit_price,
            max_notional=ticket.max_notional)
        ticket.risk_checks_at_submit = checks
        if not checks["all_passed"]:
            ticket.status = "REJECTED"
            ticket.error_message = "; ".join(checks["reasons"])[:1000]
            await session.commit()
            raise RiskCheckFailedError("risk re-check failed at submit time",
                                       details={"risk_checks": checks})

        # 4. balance + allowance (fail-closed)
        balance = await self.rpc.get_usdc_balance(wallet_address)
        if balance is None or balance < ticket.max_notional:
            ticket.status = "REJECTED"
            ticket.error_message = "insufficient or unverifiable USDC balance"
            await session.commit()
            raise RiskCheckFailedError(
                "USDC balance below required notional (or RPC unavailable — failing closed)",
                details={"balance": balance, "required": ticket.max_notional})
        spender = NEG_RISK_EXCHANGE_ADDRESS if market.neg_risk else CTF_EXCHANGE_ADDRESS
        allowance = await self.rpc.get_usdc_allowance(wallet_address, spender)
        if allowance is None or allowance < ticket.max_notional:
            ticket.status = "REJECTED"
            ticket.error_message = "insufficient or unverifiable USDC allowance"
            await session.commit()
            raise RiskCheckFailedError(
                "USDC allowance for the exchange contract is insufficient — approve first "
                "from your own wallet (this system never sends approvals for you)",
                details={"allowance": allowance, "required": ticket.max_notional,
                         "spender": spender})

        # 5. payload sanity
        expected_token = market.yes_token_id if ticket.direction == "YES" else market.no_token_id
        body = validate_signed_payload(signed_order_payload, wallet_address=wallet_address,
                                       expected_token_id=expected_token)
        if credentials is None:
            raise ValidationFailed("clob_credentials are required for live submission")

        # 6. single, non-retried POST
        headers = build_l2_headers(credentials=credentials, wallet_address=wallet_address,
                                   method="POST", request_path="/order", body=body)
        status_code, resp = await self.clob.post_order(body, headers)
        submitted_at = _utcnow()
        if status_code < 400 and isinstance(resp, dict) and resp.get("success"):
            ticket.status = "SUBMITTED"
            ticket.submitted_at = submitted_at
            ticket.order_id = str(resp.get("orderID") or "") or None
            tx_hashes = resp.get("transactionsHashes") or []
            ticket.tx_hash = str(tx_hashes[0]) if tx_hashes else None
            await session.commit()
            return {"status": "SUBMITTED", "order_id": ticket.order_id,
                    "submitted_at": submitted_at,
                    "clob_status": str(resp.get("status") or "unknown")}
        error_msg = "order rejected by CLOB"
        if isinstance(resp, dict) and resp.get("errorMsg"):
            error_msg = str(resp["errorMsg"])[:500]
        ticket.status = "FAILED"
        ticket.error_message = error_msg
        await session.commit()
        raise RiskCheckFailedError(f"CLOB rejected the order: {error_msg}",
                                   details={"http_status": status_code})
