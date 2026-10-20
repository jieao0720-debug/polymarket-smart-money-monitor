"""Application settings. All env vars are defined here (see /docs and .env.example).

Safety-critical defaults: ENABLE_LIVE_TRADING is False and must stay False by default.
"""
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Polymarket Smart Money Quant Monitor"
    version: str = "0.1.0"
    debug: bool = Field(default=False, alias="DEBUG")

    # --- database ---
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/polymarket_monitor.db", alias="DATABASE_URL"
    )

    # --- trading safety (defaults are the safe values) ---
    enable_live_trading: bool = Field(default=False, alias="ENABLE_LIVE_TRADING")
    max_trade_notional: float = Field(default=100.0, alias="MAX_TRADE_NOTIONAL")
    max_slippage_bps: int = Field(default=100, alias="MAX_SLIPPAGE_BPS")
    max_spread_bps: int = Field(default=300, alias="MAX_SPREAD_BPS")
    min_liquidity: float = Field(default=1000.0, alias="MIN_LIQUIDITY")
    min_position_value: float = Field(default=100.0, alias="MIN_POSITION_VALUE")
    ticket_ttl_minutes: int = Field(default=10, alias="TICKET_TTL_MINUTES")
    # Official close-only list (docs.polymarket.com/api-reference/geoblock) — UNCERTAINTY-U1.
    close_only_countries: str = Field(default="PL,SG,TH,TW", alias="CLOSE_ONLY_COUNTRIES")
    # Test-only override: "", "OK", "CLOSE_ONLY", "BLOCKED". MUST be empty in production.
    geoblock_force_mode: str = Field(default="", alias="GEOBLOCK_FORCE_MODE")

    # --- polymarket API bases ---
    polymarket_gamma_base: str = Field(
        default="https://gamma-api.polymarket.com", alias="POLYMARKET_GAMMA_BASE"
    )
    polymarket_data_base: str = Field(
        default="https://data-api.polymarket.com", alias="POLYMARKET_DATA_BASE"
    )
    polymarket_clob_base: str = Field(
        default="https://clob.polymarket.com", alias="POLYMARKET_CLOB_BASE"
    )
    # Generic base kept for spec compatibility (unused by clients, which use the三 specific bases).
    polymarket_api_base: str = Field(default="https://polymarket.com", alias="POLYMARKET_API_BASE")
    geoblock_url: str = Field(default="https://polymarket.com/api/geoblock", alias="GEOBLOCK_URL")
    polygon_rpc_url: str = Field(default="https://polygon-rpc.com", alias="POLYGON_RPC_URL")

    # --- scanner ---
    scanner_max_markets: int = Field(default=15, alias="SCANNER_MAX_MARKETS")
    scanner_market_fetch_limit: int = Field(default=100, alias="SCANNER_MARKET_FETCH_LIMIT")
    scanner_min_volume_24h: float = Field(default=5000.0, alias="SCANNER_MIN_VOLUME_24H")
    scanner_min_hours_to_resolution: float = Field(
        default=6.0, alias="SCANNER_MIN_HOURS_TO_RESOLUTION")
    scanner_interval_minutes: int = Field(
        default=0, alias="SCANNER_INTERVAL_MINUTES")  # 0 = disabled
    near_resolution_hours: float = Field(default=48.0, alias="NEAR_RESOLUTION_HOURS")
    extreme_price_low: float = Field(default=0.05, alias="EXTREME_PRICE_LOW")
    extreme_price_high: float = Field(default=0.95, alias="EXTREME_PRICE_HIGH")
    holders_per_side: int = Field(default=20, alias="HOLDERS_PER_SIDE")  # data-api hard cap is 20
    external_concurrency: int = Field(default=8, alias="EXTERNAL_CONCURRENCY")
    account_history_max_pages: int = Field(default=4, alias="ACCOUNT_HISTORY_MAX_PAGES")  # x50 rows
    account_stats_cache_hours: float = Field(default=6.0, alias="ACCOUNT_STATS_CACHE_HOURS")

    # --- smart money ---
    smart_money_score_threshold: float = Field(default=60.0, alias="SMART_MONEY_SCORE_THRESHOLD")
    min_smart_notional: float = Field(default=500.0, alias="MIN_SMART_NOTIONAL")
    paper_trade_auto_log: bool = Field(default=True, alias="PAPER_TRADE_AUTO_LOG")
    paper_trade_min_confidence: float = Field(default=50.0, alias="PAPER_TRADE_MIN_CONFIDENCE")
    paper_trade_default_notional: float = Field(default=100.0, alias="PAPER_TRADE_DEFAULT_NOTIONAL")
    # A9b guard: skip auto paper trades when spread / entry price exceeds this ratio.
    paper_trade_max_relative_spread: float = Field(
        default=0.10, alias="PAPER_TRADE_MAX_RELATIVE_SPREAD")

    # --- position monitor / settlement / shadow exits (A24–A27) ---
    # Independent of the scanner: 0 disables the periodic pass (manual run still works).
    position_monitor_interval_minutes: int = Field(
        default=0, alias="POSITION_MONITOR_INTERVAL_MINUTES")
    # Taker fee assumed when valuing a sale into the bid ladder (0 = fee-free market).
    paper_exit_fee_bps: float = Field(default=0.0, alias="PAPER_EXIT_FEE_BPS")
    # Shadow exit rules are RECORDED ONLY — they never close or reduce a position.
    # Starting parameters for offline replay, not validated values.
    shadow_exit_retention_reduce: float = Field(
        default=0.70, alias="SHADOW_EXIT_RETENTION_REDUCE")
    shadow_exit_retention_exit: float = Field(default=0.40, alias="SHADOW_EXIT_RETENTION_EXIT")
    shadow_exit_min_coverage: float = Field(default=0.70, alias="SHADOW_EXIT_MIN_COVERAGE")
    shadow_exit_confirmations: int = Field(default=2, alias="SHADOW_EXIT_CONFIRMATIONS")
    shadow_exit_stop_loss_return: float = Field(
        default=-0.25, alias="SHADOW_EXIT_STOP_LOSS_RETURN")

    # --- http ---
    http_timeout_seconds: float = Field(default=15.0, alias="HTTP_TIMEOUT_SECONDS")
    http_retries: int = Field(default=3, alias="HTTP_RETRIES")
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        # Accept common Postgres URL shapes and coerce to async drivers.
        if v.startswith("postgres://"):
            v = "postgresql+asyncpg://" + v[len("postgres://"):]
        elif v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://"):]
        elif v.startswith("sqlite:///"):
            v = "sqlite+aiosqlite:///" + v[len("sqlite:///"):]
        return v

    @property
    def close_only_country_list(self) -> list[str]:
        return [c.strip().upper() for c in self.close_only_countries.split(",") if c.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_spread_abs(self) -> float:
        """ASSUMPTION-A15: 1 bp = 0.0001 absolute price units on the 0-1 scale."""
        return self.max_spread_bps / 10000.0

    @property
    def max_slippage_abs(self) -> float:
        return self.max_slippage_bps / 10000.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
