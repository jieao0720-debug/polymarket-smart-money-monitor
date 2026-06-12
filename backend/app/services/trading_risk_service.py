"""Pre-trade risk checks (risk-control.md). Each check is a standalone function;
`run_ticket_checks` aggregates them into the api-contract risk_checks object.

geoblock is fail-closed: any failure to verify → BLOCKED (no new positions).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.clients.geoblock_client import GeoblockClient
from app.core.config import Settings
from app.core.errors import UpstreamError
from app.services.normalization import (
    GeoblockStatus,
    NormalizedBook,
    NormalizedMarket,
    geoblock_fail_closed,
    normalize_geoblock,
)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass
class CheckOutcome:
    ok: bool
    reason: str | None = None


def check_market_state(market: NormalizedMarket, now: datetime) -> CheckOutcome:
    if market.closed:
        return CheckOutcome(False, "market is closed")
    if not market.active:
        return CheckOutcome(False, "market is inactive")
    if not market.accepting_orders:
        return CheckOutcome(False, "market is not accepting orders")
    if market.end_date is not None and market.end_date <= now:
        return CheckOutcome(False, "market end date has passed")
    return CheckOutcome(True)


def check_spread(book: NormalizedBook | None, max_spread_abs: float) -> CheckOutcome:
    if book is None or book.spread is None:
        return CheckOutcome(False, "order book unavailable or one-sided")
    if book.one_sided:
        return CheckOutcome(False, "one-sided order book")
    if book.spread > max_spread_abs:
        return CheckOutcome(False, f"spread {book.spread:.4f} exceeds max {max_spread_abs:.4f}")
    return CheckOutcome(True)


def check_liquidity(liquidity: float, min_liquidity: float) -> CheckOutcome:
    if liquidity < min_liquidity:
        return CheckOutcome(False, f"liquidity {liquidity:.0f} below minimum {min_liquidity:.0f}")
    return CheckOutcome(True)


def check_price(limit_price: float, book: NormalizedBook | None, tick_size: float,
                max_slippage_abs: float) -> CheckOutcome:
    if not (0 < limit_price < 1):
        return CheckOutcome(False, "limit price must be strictly between 0 and 1")
    tick = tick_size if tick_size > 0 else 0.01
    steps = limit_price / tick
    if abs(steps - round(steps)) > 1e-6:
        return CheckOutcome(False, f"limit price not aligned to tick size {tick}")
    if book is None or book.midpoint is None or book.best_ask is None or book.best_bid is None:
        return CheckOutcome(False, "order book unavailable for price validation")
    ceiling = min(book.best_ask, book.midpoint + max_slippage_abs)
    if limit_price > ceiling + 1e-9:
        return CheckOutcome(
            False, f"BUY limit {limit_price:.4f} above slippage ceiling {ceiling:.4f}")
    if limit_price < book.best_bid * 0.5:
        return CheckOutcome(False, "limit price implausibly far below the market")
    return CheckOutcome(True)


def check_notional(max_notional: float, settings: Settings) -> CheckOutcome:
    if max_notional <= 0:
        return CheckOutcome(False, "notional must be positive")
    if max_notional > settings.max_trade_notional:
        return CheckOutcome(
            False, f"notional {max_notional:.2f} exceeds MAX_TRADE_NOTIONAL "
                   f"{settings.max_trade_notional:.2f}")
    return CheckOutcome(True)


def check_geoblock_for_open(geo: GeoblockStatus) -> CheckOutcome:
    """Opening a new position requires mode OK. CLOSE_ONLY may only close (v1 only
    opens — ASSUMPTION-A12 — so CLOSE_ONLY effectively blocks all orders here)."""
    if geo.mode == "OK":
        return CheckOutcome(True)
    if geo.mode == "CLOSE_ONLY":
        return CheckOutcome(False, "region is close-only: opening new positions is disabled")
    reason = "region is blocked for trading"
    if geo.fail_closed:
        reason = "geoblock verification failed — failing closed (treated as blocked)"
    return CheckOutcome(False, reason)


class TradingRiskService:
    def __init__(self, geoblock_client: GeoblockClient, settings: Settings) -> None:
        self.geoblock_client = geoblock_client
        self.settings = settings

    async def get_geoblock(self) -> GeoblockStatus:
        forced = self.settings.geoblock_force_mode.strip().upper()
        if forced in {"OK", "CLOSE_ONLY", "BLOCKED"}:  # test/dev only (risk-control §1)
            return GeoblockStatus(
                blocked=forced != "OK", country="XX", region=None, mode=forced,
                can_open_position=forced == "OK",
                can_close_position=forced in ("OK", "CLOSE_ONLY"))
        try:
            raw = await self.geoblock_client.check()
            return normalize_geoblock(raw, self.settings.close_only_country_list)
        except UpstreamError:
            return geoblock_fail_closed()

    async def run_ticket_checks(self, *, market: NormalizedMarket,
                                book: NormalizedBook | None, limit_price: float,
                                max_notional: float,
                                geo: GeoblockStatus | None = None) -> dict:
        """First-pass checks at ticket creation; reused for the submit-time re-check."""
        now = _utcnow()
        if geo is None:
            geo = await self.get_geoblock()
        geo_check = check_geoblock_for_open(geo)
        market_check = check_market_state(market, now)
        spread_check = check_spread(book, self.settings.max_spread_abs)
        liquidity_check = check_liquidity(market.liquidity, self.settings.min_liquidity)
        price_check = check_price(limit_price, book, market.tick_size,
                                  self.settings.max_slippage_abs)
        notional_check = check_notional(max_notional, self.settings)

        reasons = [c.reason for c in (geo_check, market_check, spread_check, liquidity_check,
                                      price_check, notional_check) if not c.ok and c.reason]
        return {
            "geoblock_ok": geo_check.ok,
            "geoblock_mode": geo.mode,
            "market_active": market_check.ok,
            "spread_ok": spread_check.ok,
            "liquidity_ok": liquidity_check.ok,
            "price_ok": price_check.ok,
            "notional_ok": notional_check.ok,
            "live_trading_enabled": self.settings.enable_live_trading,
            "all_passed": all(c.ok for c in (geo_check, market_check, spread_check,
                                             liquidity_check, price_check, notional_check)),
            "reasons": reasons,
        }
