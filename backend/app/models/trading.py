from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
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
    # MANUAL (user close) / RESOLVED (settled from the official market resolution, A25).
    exit_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Shares still held after partial exits (A24). NULL on legacy rows: OPEN → all shares.
    remaining_shares: Mapped[float | None] = mapped_column(Float, nullable=True)

    @property
    def open_shares(self) -> float:
        if self.remaining_shares is not None:
            return self.remaining_shares
        return self.shares if self.status == "OPEN" else 0.0


class PaperTradeExit(Base):
    """One simulated sale (or settlement) of part or all of a paper position (A24).
    `price` is the average NET proceeds per share after walking the bid ladder and fees."""
    __tablename__ = "paper_trade_exits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paper_trade_id: Mapped[int] = mapped_column(ForeignKey("paper_trades.id"), index=True)
    exit_time: Mapped[datetime] = mapped_column(DateTime)
    shares: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    proceeds: Mapped[float] = mapped_column(Float)  # net USDC
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(String(16))  # MANUAL / RESOLVED
    pnl: Mapped[float] = mapped_column(Float)  # proceeds − shares × entry_price


class PaperTradeCohortMember(Base):
    """Smart-money account followed at entry (A26). Frozen at entry, never re-ranked:
    an account that later drops out of the top-20 is still tracked by address."""
    __tablename__ = "paper_trade_cohort"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paper_trade_id: Mapped[int] = mapped_column(ForeignKey("paper_trades.id"), index=True)
    wallet_address: Mapped[str] = mapped_column(String(42))
    direction: Mapped[str] = mapped_column(String(8))  # the side we bought
    entry_shares: Mapped[float] = mapped_column(Float)  # shares on our side at entry
    entry_opposite_shares: Mapped[float] = mapped_column(Float, default=0.0)  # if seen
    entry_net_exposure: Mapped[float] = mapped_column(Float)  # e_i0 (shares, > 0)
    entry_value: Mapped[float] = mapped_column(Float)  # USDC value of our-side position
    # False/NULL: the account's full opposite-side holding at entry could not be read, so
    # e_i0 is unverified and the member is excluded from retention (A26).
    entry_baseline_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    weight: Mapped[float] = mapped_column(Float)  # w_i, sums to 1 per trade
    smart_money_score: Mapped[float] = mapped_column(Float)
    label: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(16), default="ENTRY")  # ENTRY / BACKFILL
    signal_snapshot_time: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (UniqueConstraint("paper_trade_id", "wallet_address",
                                       name="uq_cohort_trade_wallet"),)


class PositionObservation(Base):
    """One position-monitor pass over one OPEN paper trade (A27).

    Shadow mode: `shadow_*` fields record what the exit rules WOULD do. Nothing here is
    ever executed — the only automatic state change the monitor makes is settlement.
    """
    __tablename__ = "position_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paper_trade_id: Mapped[int] = mapped_column(ForeignKey("paper_trades.id"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    # OPEN / AWAITING_RESOLUTION / RESOLVED / UNKNOWN
    market_status: Mapped[str] = mapped_column(String(24))
    best_bid: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_ask: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Sell-side valuation of the whole position against the bid ladder, net of fees.
    liquidation_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    liquidation_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    liquidation_fill_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    liquidation_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    retention: Mapped[float | None] = mapped_column(Float, nullable=True)  # R_t over known
    coverage: Mapped[float | None] = mapped_column(Float, nullable=True)  # known weight
    cohort_detail: Mapped[list | None] = mapped_column(JSON, nullable=True)
    latest_signal_direction: Mapped[str | None] = mapped_column(String(8), nullable=True)
    latest_signal_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    shadow_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    shadow_triggers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    shadow_target_fraction: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_issues: Mapped[list | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (Index("ix_observations_trade_time", "paper_trade_id", "observed_at"),)


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
