from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)  # store naive UTC


class Market(Base):
    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    polymarket_market_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    condition_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    question: Mapped[str] = mapped_column(String(1024))
    slug: Mapped[str] = mapped_column(String(512), default="")
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    yes_token_id: Mapped[str] = mapped_column(String(120))
    no_token_id: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)
    accepting_orders: Mapped[bool] = mapped_column(Boolean, default=True)
    neg_risk: Mapped[bool] = mapped_column(Boolean, default=False)
    tick_size: Mapped[float] = mapped_column(Float, default=0.01)
    end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    volume: Mapped[float] = mapped_column(Float, default=0.0)
    volume_24h: Mapped[float] = mapped_column(Float, default=0.0)
    liquidity: Mapped[float] = mapped_column(Float, default=0.0)
    open_interest: Mapped[float | None] = mapped_column(Float, nullable=True)  # event-level, U5
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (Index("ix_markets_active_closed", "active", "closed"),)


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), index=True)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    yes_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    no_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    spread: Mapped[float | None] = mapped_column(Float, nullable=True)
    midpoint: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_bid: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_ask: Mapped[float | None] = mapped_column(Float, nullable=True)
    orderbook_depth: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    volume_24h: Mapped[float] = mapped_column(Float, default=0.0)
    liquidity: Mapped[float] = mapped_column(Float, default=0.0)
    open_interest: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (Index("ix_snapshots_market_time", "market_id", "snapshot_time"),)


class MarketHolder(Base):
    __tablename__ = "market_holders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime)
    direction: Mapped[str] = mapped_column(String(8))  # YES / NO
    shares: Mapped[float] = mapped_column(Float)  # token units (UNCERTAINTY-V2)
    current_position_value: Mapped[float] = mapped_column(Float)  # USDC
    average_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_notional_approx: Mapped[float | None] = mapped_column(Float, nullable=True)  # U3
    rank: Mapped[int] = mapped_column(Integer)
    value_is_approx: Mapped[bool] = mapped_column(Boolean, default=False)  # U4
    # Shares the account holds on the OTHER side of this market, from its full /positions
    # (not the other side's top-20). NULL = lookup failed or row predates 2026-10-20.
    opposite_shares: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (Index("ix_holders_market_time", "market_id", "snapshot_time"),)
