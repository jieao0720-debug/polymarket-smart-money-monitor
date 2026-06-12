from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Container, get_container, get_db
from app.api.routes.trade_tickets import fetch_fresh_market, fetch_side_book, load_ticket
from app.clients.clob_auth import ClobCredentials
from app.clients.polygon_rpc_client import (
    CTF_EXCHANGE_ADDRESS,
    NEG_RISK_EXCHANGE_ADDRESS,
)
from app.core.errors import ValidationFailed
from app.models import WalletConnection
from app.schemas.api import (
    AllowanceResponse,
    BalancesResponse,
    DeriveClobCredentialsRequest,
    DeriveClobCredentialsResponse,
    GeoblockResponse,
    OrderSubmitRequest,
    OrderSubmitResponse,
)

router = APIRouter(prefix="/api/trading", tags=["trading"])

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _validate_address(wallet_address: str) -> str:
    if not ADDRESS_RE.match(wallet_address):
        raise ValidationFailed("invalid wallet address format")
    return wallet_address.lower()


@router.get("/geoblock", response_model=GeoblockResponse)
async def geoblock(wallet_address: str | None = Query(default=None),
                   db: AsyncSession = Depends(get_db),
                   container: Container = Depends(get_container)) -> GeoblockResponse:
    geo = await container.risk.get_geoblock()
    response = GeoblockResponse(
        blocked=geo.blocked, country=geo.country, region=geo.region, mode=geo.mode,
        can_open_position=geo.can_open_position, can_close_position=geo.can_close_position,
        checked_at=geo.checked_at, fail_closed=geo.fail_closed)
    if wallet_address and ADDRESS_RE.match(wallet_address):
        address = wallet_address.lower()
        row = (await db.execute(select(WalletConnection).where(
            WalletConnection.wallet_address == address))).scalar_one_or_none()
        if row is None:
            row = WalletConnection(wallet_address=address, chain_id=137)
            db.add(row)
        row.last_connected_at = _utcnow()
        row.geoblock_status = response.model_dump(mode="json")
        await db.commit()
    return response


@router.get("/balances", response_model=BalancesResponse)
async def balances(wallet_address: str,
                   container: Container = Depends(get_container)) -> BalancesResponse:
    address = _validate_address(wallet_address)
    warnings: list[str] = []
    usdc = await container.rpc.get_usdc_balance(address)
    native = await container.rpc.get_native_balance(address)
    if usdc is None:
        warnings.append("USDC balance unavailable (RPC error)")
    if native is None:
        warnings.append("native balance unavailable (RPC error)")
    return BalancesResponse(wallet_address=address, usdc_balance=usdc,
                            native_balance=native, checked_at=_utcnow(), warnings=warnings)


@router.get("/allowance", response_model=AllowanceResponse)
async def allowance(wallet_address: str,
                    container: Container = Depends(get_container)) -> AllowanceResponse:
    address = _validate_address(wallet_address)
    ctf = await container.rpc.get_usdc_allowance(address, CTF_EXCHANGE_ADDRESS)
    neg = await container.rpc.get_usdc_allowance(address, NEG_RISK_EXCHANGE_ADDRESS)
    threshold = container.settings.max_trade_notional
    return AllowanceResponse(
        wallet_address=address, ctf_exchange_allowance=ctf, neg_risk_exchange_allowance=neg,
        ctf_exchange_ok=(ctf is not None and ctf >= threshold),
        neg_risk_exchange_ok=(neg is not None and neg >= threshold),
        checked_at=_utcnow())


@router.post("/clob-credentials/derive", response_model=DeriveClobCredentialsResponse)
async def derive_clob_credentials(body: DeriveClobCredentialsRequest,
                                  container: Container = Depends(get_container)
                                  ) -> DeriveClobCredentialsResponse:
    """Proxy the CLOB L1→L2 credential derivation (the user's wallet signed `ClobAuth`
    in the frontend). Credentials are returned to the caller and NEVER persisted or
    logged here. Only available when live trading is explicitly enabled."""
    from app.clients.clob_auth import build_l1_headers
    from app.core.errors import LiveTradingDisabledError, UpstreamError

    if not container.settings.enable_live_trading:
        raise LiveTradingDisabledError(
            "Live trading is disabled — CLOB credentials are not needed in paper mode.")
    wallet = _validate_address(body.wallet_address)
    headers = build_l1_headers(wallet_address=wallet, signature=body.signature,
                               timestamp=body.timestamp, nonce=body.nonce)
    creds = await container.clob.derive_api_key(headers)
    if creds is None:
        creds = await container.clob.create_api_key(headers)
    if creds is None:
        raise UpstreamError("could not derive CLOB API credentials "
                            "(signature rejected or CLOB unavailable)")
    return DeriveClobCredentialsResponse(
        api_key=str(creds.get("apiKey", "")), secret=str(creds.get("secret", "")),
        passphrase=str(creds.get("passphrase", "")), derived_at=_utcnow())


@router.post("/orders/submit", response_model=OrderSubmitResponse)
async def submit_order(body: OrderSubmitRequest,
                       db: AsyncSession = Depends(get_db),
                       container: Container = Depends(get_container)) -> OrderSubmitResponse:
    """Live order submission. Hard-gated by ENABLE_LIVE_TRADING (default false) inside
    OrderSubmitService — that gate must stay in the service, not here."""
    wallet = _validate_address(body.wallet_address)
    ticket, market_row = await load_ticket(db, body.ticket_id)
    norm, _ = await fetch_fresh_market(container, market_row.polymarket_market_id)
    book = await fetch_side_book(container, norm, ticket.direction)
    credentials = None
    if body.clob_credentials is not None:
        credentials = ClobCredentials(api_key=body.clob_credentials.api_key,
                                      secret=body.clob_credentials.secret,
                                      passphrase=body.clob_credentials.passphrase)
    result = await container.order_submit.submit(
        db, ticket=ticket, market=norm, book=book, wallet_address=wallet,
        signed_order_payload=body.signed_order_payload, credentials=credentials)
    await db.commit()
    return OrderSubmitResponse(**result)
