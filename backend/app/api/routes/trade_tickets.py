from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Container, get_container, get_db
from app.core.errors import (
    CloseOnlyRegionError,
    GeoblockedError,
    MarketNotTradableError,
    NotFoundError,
    RiskCheckFailedError,
    UpstreamError,
    ValidationFailed,
)
from app.models import Market, TradeTicket
from app.schemas.api import (
    RiskChecks,
    TradeTicketConfirmRequest,
    TradeTicketCreateRequest,
    TradeTicketListResponse,
    TradeTicketResponse,
)
from app.services.normalization import (
    NormalizedBook,
    NormalizedMarket,
    NotBinaryMarket,
    normalize_book,
    normalize_market,
)

router = APIRouter(prefix="/api/trade-tickets", tags=["trade-tickets"])


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def fetch_fresh_market(container: Container, gamma_market_id: str
                             ) -> tuple[NormalizedMarket, int]:
    """Fresh gamma fetch + upsert (risk checks must not run on stale rows)."""
    raw = await container.gamma.get_market(gamma_market_id)
    if raw is None:
        raise NotFoundError(f"market {gamma_market_id} not found on Polymarket")
    try:
        norm = normalize_market(raw)
    except NotBinaryMarket as exc:
        raise ValidationFailed("only binary Yes/No markets are supported in v1") from exc
    async with container.session_factory() as session:
        row = await container.scanner._upsert_market(session, norm)
        await session.commit()
        market_pk = row.id
    return norm, market_pk


async def fetch_side_book(container: Container, norm: NormalizedMarket,
                          direction: str) -> NormalizedBook | None:
    token = norm.yes_token_id if direction == "YES" else norm.no_token_id
    try:
        raw = await container.clob.get_book(token)
        return normalize_book(raw, token)
    except UpstreamError:
        return None


def ticket_to_response(ticket: TradeTicket, question: str) -> TradeTicketResponse:
    return TradeTicketResponse(
        ticket_id=ticket.ticket_uid, status=ticket.status, signal_id=ticket.signal_id,
        market_id=question_market_id(ticket), question=question, direction=ticket.direction,
        side=ticket.side, limit_price=ticket.limit_price, max_notional=ticket.max_notional,
        wallet_address=ticket.wallet_address,
        risk_checks=RiskChecks(**ticket.risk_checks) if ticket.risk_checks else None,
        risk_checks_at_submit=ticket.risk_checks_at_submit,
        created_at=ticket.created_at, confirmed_at=ticket.confirmed_at,
        submitted_at=ticket.submitted_at, expires_at=ticket.expires_at,
        order_id=ticket.order_id, tx_hash=ticket.tx_hash,
        error_message=ticket.error_message)


def question_market_id(ticket: TradeTicket) -> str:
    return getattr(ticket, "_gamma_market_id", "") or ""


async def load_ticket(db: AsyncSession, ticket_id: str) -> tuple[TradeTicket, Market]:
    row = (await db.execute(
        select(TradeTicket, Market).join(Market, TradeTicket.market_id == Market.id)
        .where(TradeTicket.ticket_uid == ticket_id))).one_or_none()
    if row is None:
        raise NotFoundError(f"trade ticket {ticket_id} not found")
    ticket, market = row
    ticket._gamma_market_id = market.polymarket_market_id  # type: ignore[attr-defined]
    return ticket, market


@router.post("", response_model=TradeTicketResponse, status_code=201)
async def create_ticket(body: TradeTicketCreateRequest,
                        db: AsyncSession = Depends(get_db),
                        container: Container = Depends(get_container)
                        ) -> TradeTicketResponse:
    norm, market_pk = await fetch_fresh_market(container, body.market_id)
    book = await fetch_side_book(container, norm, body.direction)
    geo = await container.risk.get_geoblock()
    checks = await container.risk.run_ticket_checks(
        market=norm, book=book, limit_price=body.limit_price,
        max_notional=body.max_notional, geo=geo)

    # Hard rejections (api-contract §7): region and market-state failures never
    # produce a ticket; spread/liquidity/price soft-fail into the checks object.
    if not checks["geoblock_ok"]:
        if checks["geoblock_mode"] == "CLOSE_ONLY":
            raise CloseOnlyRegionError(
                "This region is close-only. Opening new positions is disabled.",
                details={"risk_checks": checks})
        raise GeoblockedError("Trading is blocked for this region.",
                              details={"risk_checks": checks})
    if not checks["market_active"]:
        raise MarketNotTradableError("market is not tradable",
                                     details={"risk_checks": checks})
    if not checks["notional_ok"]:
        raise RiskCheckFailedError("notional exceeds the configured maximum",
                                   details={"risk_checks": checks})

    now = _utcnow()
    ticket = TradeTicket(
        signal_id=body.signal_id, market_id=market_pk,
        wallet_address=body.wallet_address.lower() if body.wallet_address else None,
        direction=body.direction, side=body.side, limit_price=body.limit_price,
        max_notional=body.max_notional, status="PENDING_USER_CONFIRMATION",
        risk_checks=checks, created_at=now,
        expires_at=now + timedelta(minutes=container.settings.ticket_ttl_minutes))
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    ticket._gamma_market_id = body.market_id  # type: ignore[attr-defined]
    return ticket_to_response(ticket, norm.question)


@router.get("", response_model=TradeTicketListResponse)
async def list_tickets(status: str | None = None,
                       limit: int = Query(default=50, ge=1, le=200),
                       db: AsyncSession = Depends(get_db)) -> TradeTicketListResponse:
    query = select(TradeTicket, Market).join(Market, TradeTicket.market_id == Market.id)
    count_q = select(func.count(TradeTicket.id))
    if status:
        query = query.where(TradeTicket.status == status)
        count_q = count_q.where(TradeTicket.status == status)
    total = (await db.execute(count_q)).scalar_one()
    rows = (await db.execute(query.order_by(TradeTicket.created_at.desc()).limit(limit))).all()
    tickets = []
    for ticket, market in rows:
        ticket._gamma_market_id = market.polymarket_market_id  # type: ignore[attr-defined]
        tickets.append(ticket_to_response(ticket, market.question))
    return TradeTicketListResponse(tickets=tickets, total=total)


@router.get("/{ticket_id}", response_model=TradeTicketResponse)
async def get_ticket(ticket_id: str, db: AsyncSession = Depends(get_db)
                     ) -> TradeTicketResponse:
    ticket, market = await load_ticket(db, ticket_id)
    return ticket_to_response(ticket, market.question)


@router.post("/{ticket_id}/confirm", response_model=TradeTicketResponse)
async def confirm_ticket(ticket_id: str, body: TradeTicketConfirmRequest,
                         db: AsyncSession = Depends(get_db)) -> TradeTicketResponse:
    if body.manual_confirmation is not True:
        raise ValidationFailed("manual_confirmation must be explicitly true "
                               "(this is not automated trading)")
    ticket, market = await load_ticket(db, ticket_id)
    if ticket.status != "PENDING_USER_CONFIRMATION":
        raise ValidationFailed(f"ticket is {ticket.status}, cannot confirm")
    now = _utcnow()
    if ticket.expires_at is not None and ticket.expires_at < now:
        ticket.status = "EXPIRED"
        await db.commit()
        raise ValidationFailed("ticket has expired — create a new one (stale prices)")
    ticket.wallet_address = body.wallet_address.lower()
    ticket.confirmed_at = now
    ticket.status = "CONFIRMED"
    await db.commit()
    return ticket_to_response(ticket, market.question)


@router.post("/{ticket_id}/cancel", response_model=TradeTicketResponse)
async def cancel_ticket(ticket_id: str, db: AsyncSession = Depends(get_db)
                        ) -> TradeTicketResponse:
    ticket, market = await load_ticket(db, ticket_id)
    if ticket.status in ("SUBMITTED",):
        raise ValidationFailed("submitted tickets cannot be cancelled here — manage the "
                               "order on Polymarket directly")
    ticket.status = "CANCELLED"
    await db.commit()
    return ticket_to_response(ticket, market.question)
