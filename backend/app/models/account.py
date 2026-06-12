from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.market import utcnow


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wallet_address: Mapped[str] = mapped_column(String(42), unique=True, index=True)  # lowercase
    profile_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AccountResolvedStats(Base):
    """Resolved-history stats for an account as of `snapshot_time` (look-ahead safe).

    category=NULL row = overall stats; category set = same-category slice.
    """
    __tablename__ = "account_resolved_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime)
    resolved_trade_count: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    average_roi: Mapped[float] = mapped_column(Float, default=0.0)
    median_entry_notional: Mapped[float] = mapped_column(Float, default=0.0)
    same_category_trade_count: Mapped[int] = mapped_column(Integer, default=0)
    same_category_win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    same_category_roi: Mapped[float] = mapped_column(Float, default=0.0)
    history_truncated: Mapped[bool] = mapped_column(Boolean, default=False)  # ASSUMPTION-A4

    __table_args__ = (Index("ix_stats_account_time", "account_id", "snapshot_time"),)


class AccountLabel(Base):
    __tablename__ = "account_labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), index=True)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime)
    label: Mapped[str] = mapped_column(String(32))  # AccountLabel enum values
    anomaly_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    smart_money_score: Mapped[float] = mapped_column(Float, default=0.0)
    score_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(String(512), default="")
