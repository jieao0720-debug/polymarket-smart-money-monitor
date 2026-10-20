"""Pydantic models mirroring /docs/api-contract.md (field-for-field)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import (
    ADDRESS_PATTERN,
    AccountLabelValue,
    Direction,
    GeoMode,
    PaperTradeStatus,
    SignalDirection,
    TicketStatus,
)

# ----------------------------------------------------------------- scanner

class ScanRunRequest(BaseModel):
    max_markets: int | None = Field(default=None, ge=1, le=50)


class ScanStatusResponse(BaseModel):
    scan_id: str | None
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    markets_found: int = 0
    markets_analyzed: int = 0
    signals_generated: int = 0
    errors: list[str] = Field(default_factory=list)
    current_step: str | None = None


# ----------------------------------------------------------------- markets

class HotMarket(BaseModel):
    market_id: str
    condition_id: str
    question: str
    category: str | None
    slug: str
    end_date: datetime | None
    volume_24h: float
    liquidity: float
    open_interest: float | None
    yes_price: float | None
    no_price: float | None
    spread: float | None
    midpoint: float | None
    smart_money_direction: SignalDirection | None
    confidence_score: float | None
    risk_flags: list[str] = Field(default_factory=list)
    last_analyzed_at: datetime | None


class HotMarketsResponse(BaseModel):
    markets: list[HotMarket]
    warnings: list[str] = Field(default_factory=list)


class MarketInfo(BaseModel):
    market_id: str
    condition_id: str
    question: str
    category: str | None
    slug: str
    active: bool
    closed: bool
    accepting_orders: bool
    neg_risk: bool
    end_date: datetime | None
    yes_token_id: str
    no_token_id: str
    yes_price: float | None
    no_price: float | None
    spread: float | None
    midpoint: float | None
    volume_24h: float
    liquidity: float
    open_interest: float | None
    tick_size: float


class MarketSummary(BaseModel):
    snapshot_time: datetime | None
    yes_smart_money_count: int = 0
    no_smart_money_count: int = 0
    yes_smart_money_notional: float = 0
    no_smart_money_notional: float = 0
    net_direction: SignalDirection = "NEUTRAL"
    confidence_score: float = 0
    risk_flags: list[str] = Field(default_factory=list)
    suggested_limit_price: float | None = None
    suggested_max_notional: float | None = None
    signal_id: str | None = None


class HolderEntry(BaseModel):
    address: str
    profile_name: str | None = None
    direction: Direction
    rank: int
    current_position_value: float
    shares: float
    average_price: float | None
    current_price: float | None
    value_is_approx: bool = False
    label: AccountLabelValue
    label_reason: str = ""
    win_rate: float
    resolved_trade_count: int
    realized_pnl: float
    same_category_win_rate: float
    same_category_trade_count: int
    anomaly_index: float | None
    smart_money_score: float
    history_truncated: bool = False


class MarketAnalysisResponse(BaseModel):
    market: MarketInfo
    summary: MarketSummary
    holders: list[HolderEntry]
    warnings: list[str] = Field(default_factory=list)


# ----------------------------------------------------------------- accounts

class AccountOverallStats(BaseModel):
    resolved_trade_count: int
    win_rate: float
    realized_pnl: float
    average_roi: float
    median_entry_notional: float


class AccountCategoryStats(BaseModel):
    category: str | None
    trade_count: int
    win_rate: float
    average_roi: float


class AccountCurrentMarket(BaseModel):
    market_id: str
    direction: Direction | None
    shares: float | None
    average_price: float | None
    current_position_value: float | None
    entry_notional_approx: float | None
    anomaly_index: float | None
    label: AccountLabelValue
    label_reason: str
    smart_money_score: float


class AccountProfileResponse(BaseModel):
    address: str
    profile_name: str | None = None
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    as_of: datetime
    history_truncated: bool = False
    overall: AccountOverallStats
    same_category: AccountCategoryStats | None = None
    current_market: AccountCurrentMarket | None = None
    warnings: list[str] = Field(default_factory=list)


# ----------------------------------------------------------------- signals

class SignalEntry(BaseModel):
    signal_id: str
    market_id: str
    question: str
    category: str | None
    snapshot_time: datetime
    direction: SignalDirection
    confidence_score: float
    yes_smart_money_count: int
    no_smart_money_count: int
    yes_smart_money_notional: float
    no_smart_money_notional: float
    risk_flags: list[str] = Field(default_factory=list)
    suggested_limit_price: float | None
    suggested_max_notional: float | None


class SignalsResponse(BaseModel):
    signals: list[SignalEntry]
    total: int


# ----------------------------------------------------------------- trade tickets

class TradeTicketCreateRequest(BaseModel):
    signal_id: str | None = None
    market_id: str
    direction: Direction
    limit_price: float = Field(gt=0, lt=1)
    max_notional: float = Field(gt=0)
    wallet_address: str | None = Field(default=None, pattern=ADDRESS_PATTERN)
    side: str = Field(default="BUY", pattern="^BUY$")  # v1: BUY only (A12)


class RiskChecks(BaseModel):
    geoblock_ok: bool
    geoblock_mode: GeoMode
    market_active: bool
    spread_ok: bool
    liquidity_ok: bool
    price_ok: bool
    notional_ok: bool
    live_trading_enabled: bool
    all_passed: bool
    reasons: list[str] = Field(default_factory=list)


class TradeTicketResponse(BaseModel):
    ticket_id: str
    status: TicketStatus
    signal_id: str | None
    market_id: str
    question: str
    direction: Direction
    side: str
    limit_price: float
    max_notional: float
    wallet_address: str | None
    risk_checks: RiskChecks | None
    risk_checks_at_submit: dict[str, Any] | None = None
    created_at: datetime
    confirmed_at: datetime | None
    submitted_at: datetime | None
    expires_at: datetime | None
    order_id: str | None
    tx_hash: str | None
    error_message: str | None


class TradeTicketListResponse(BaseModel):
    tickets: list[TradeTicketResponse]
    total: int


class TradeTicketConfirmRequest(BaseModel):
    wallet_address: str = Field(pattern=ADDRESS_PATTERN)
    manual_confirmation: bool


# ----------------------------------------------------------------- paper trades

class PaperTradeCreateRequest(BaseModel):
    signal_id: str | None = None
    market_id: str
    direction: Direction
    notional: float = Field(gt=0)
    entry_price: float | None = Field(default=None, gt=0, lt=1)


class PaperTradeCloseRequest(BaseModel):
    exit_price: float | None = Field(default=None, ge=0, le=1)


class ShadowExitSummary(BaseModel):
    """Latest position-monitor view. Shadow mode: recorded, never executed (A27)."""
    observed_at: datetime
    market_status: str
    retention: float | None
    coverage: float | None
    liquidation_return: float | None
    target_fraction: float | None
    triggers: list[str] = Field(default_factory=list)


class PaperTradeEntry(BaseModel):
    paper_trade_id: str
    signal_id: str | None
    market_id: str
    question: str
    direction: Direction
    entry_price: float
    entry_time: datetime
    notional: float
    shares: float
    remaining_shares: float | None = None  # still held after partial exits
    exit_price: float | None  # average net exit price once fully CLOSED
    exit_time: datetime | None
    pnl: float | None  # realized so far (partial exits included)
    unrealized_pnl: float | None = None  # remaining_shares × (best bid − entry)
    current_price: float | None = None  # side best bid (A24)
    price_basis: str | None = None  # BID / MIDPOINT (fallback when no bid recorded)
    price_as_of: datetime | None = None
    status: PaperTradeStatus
    source: str
    exit_reason: str | None = None  # MANUAL / RESOLVED
    shadow: ShadowExitSummary | None = None


class PaperTradeSummary(BaseModel):
    open_count: int = 0
    closed_count: int = 0
    total_realized_pnl: float = 0
    total_unrealized_pnl: float = 0
    win_count: int = 0
    loss_count: int = 0


class PositionObservationEntry(BaseModel):
    observed_at: datetime
    market_status: str
    best_bid: float | None
    best_ask: float | None
    liquidation_price: float | None
    liquidation_value: float | None
    liquidation_fill_ratio: float | None
    liquidation_return: float | None
    retention: float | None
    coverage: float | None
    cohort_detail: list[dict[str, Any]] | None
    latest_signal_direction: str | None
    latest_signal_time: datetime | None
    shadow_state: dict[str, Any] | None
    shadow_triggers: list[str] | None
    shadow_target_fraction: float | None
    data_issues: list[str] | None


class CohortMemberEntry(BaseModel):
    wallet_address: str
    entry_shares: float
    entry_opposite_shares: float
    entry_net_exposure: float
    entry_value: float
    weight: float
    smart_money_score: float
    label: str
    source: str
    baseline_verified: bool


class PaperTradeExitEntry(BaseModel):
    exit_time: datetime
    shares: float
    price: float  # average net proceeds per share
    proceeds: float
    fee: float
    reason: str
    pnl: float


class PositionObservationsResponse(BaseModel):
    paper_trade_id: str
    cohort: list[CohortMemberEntry]
    exits: list[PaperTradeExitEntry]
    observations: list[PositionObservationEntry]


class MonitorRunResponse(BaseModel):
    started_at: datetime
    finished_at: datetime | None
    open_trades: int
    observations: int
    settled: int
    cohorts_backfilled: int
    errors: list[str]


class PaperTradesResponse(BaseModel):
    paper_trades: list[PaperTradeEntry]
    total: int
    summary: PaperTradeSummary


# ----------------------------------------------------------------- trading

class GeoblockResponse(BaseModel):
    blocked: bool
    country: str | None
    region: str | None
    mode: GeoMode
    can_open_position: bool
    can_close_position: bool
    checked_at: datetime
    fail_closed: bool = False


class BalancesResponse(BaseModel):
    wallet_address: str
    chain_id: int = 137
    usdc_balance: float | None
    native_balance: float | None
    checked_at: datetime
    warnings: list[str] = Field(default_factory=list)


class AllowanceResponse(BaseModel):
    wallet_address: str
    ctf_exchange_allowance: float | None
    neg_risk_exchange_allowance: float | None
    ctf_exchange_ok: bool
    neg_risk_exchange_ok: bool
    checked_at: datetime


class ClobCredentialsInput(BaseModel):
    api_key: str
    secret: str
    passphrase: str


class DeriveClobCredentialsRequest(BaseModel):
    """L1 wallet-signature material for the CLOB auth proxy. The signature is an
    EIP-712 `ClobAuth` signature produced in the user's wallet — never a private key."""
    wallet_address: str = Field(pattern=ADDRESS_PATTERN)
    signature: str = Field(min_length=10, max_length=300)
    timestamp: int
    nonce: int = 0


class DeriveClobCredentialsResponse(BaseModel):
    api_key: str
    secret: str
    passphrase: str
    derived_at: datetime


class OrderSubmitRequest(BaseModel):
    ticket_id: str
    wallet_address: str = Field(pattern=ADDRESS_PATTERN)
    signed_order_payload: dict[str, Any]
    clob_credentials: ClobCredentialsInput | None = None


class OrderSubmitResponse(BaseModel):
    status: str
    order_id: str | None
    submitted_at: datetime
    clob_status: str | None = None


# ----------------------------------------------------------------- misc

class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    time: datetime
    live_trading_enabled: bool
    scheduler_running: bool


class PublicSettingsResponse(BaseModel):
    enable_live_trading: bool
    max_trade_notional: float
    max_slippage_bps: int
    max_spread_bps: int
    min_liquidity: float
    min_position_value: float
    smart_money_score_threshold: float
    scanner_max_markets: int
    scanner_interval_minutes: int
    close_only_countries: list[str]
    near_resolution_hours: float
    paper_trade_auto_log: bool
