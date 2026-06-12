from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.market import utcnow


def new_uid() -> str:
    return uuid.uuid4().hex


class SmartMoneySignal(Base):
    __tablename__ = "smart_money_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_uid: Mapped[str] = mapped_column(String(32), unique=True, default=new_uid)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), index=True)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    direction: Mapped[str] = mapped_column(String(8))  # YES / NO / NEUTRAL
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    yes_smart_money_count: Mapped[int] = mapped_column(Integer, default=0)
    no_smart_money_count: Mapped[int] = mapped_column(Integer, default=0)
    yes_smart_money_notional: Mapped[float] = mapped_column(Float, default=0.0)
    no_smart_money_notional: Mapped[float] = mapped_column(Float, default=0.0)
    risk_flags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    suggested_limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    suggested_max_notional: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_inputs: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (Index("ix_signals_market_time", "market_id", "snapshot_time"),)


class TradeTicket(Base):
    __tablename__ = "trade_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_uid: Mapped[str] = mapped_column(String(32), unique=True, default=new_uid)
    signal_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), index=True)
    wallet_address: Mapped[str | None] = mapped_column(String(42), nullable=True)
    direction: Mapped[str] = mapped_column(String(8))
    side: Mapped[str] = mapped_column(String(8), default="BUY")  # ASSUMPTION-A12
    limit_price: Mapped[float] = mapped_column(Float)
    max_notional: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(40), index=True, default="PENDING_USER_CONFIRMATION")
    risk_checks: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    risk_checks_at_submit: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tx_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_uid: Mapped[str] = mapped_column(String(32), unique=True, default=new_uid)
    signal_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), index=True)
    direction: Mapped[str] = mapped_column(String(8))
    entry_price: Mapped[float] = mapped_column(Float)
    entry_time: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    notional: Mapped[float] = mapped_column(Float)
    shares: Mapped[float] = mapped_column(Float)  # = notional / entry_price, frozen at entry
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True, default="OPEN")
    source: Mapped[str] = mapped_column(String(16), default="MANUAL")  # AUTO_SIGNAL / MANUAL


class WalletConnection(Base):
    """Public wallet metadata only. NEVER store keys or credentials here."""
    __tablename__ = "wallet_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wallet_address: Mapped[str] = mapped_column(String(42), unique=True, index=True)
    chain_id: Mapped[int] = mapped_column(Integer, default=137)
    last_connected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    geoblock_status: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ApiFetchLog(Base):
    __tablename__ = "api_fetch_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(16))
    endpoint: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(16))  # ok / error / timeout
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # sanitized
    response_summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
