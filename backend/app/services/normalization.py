"""Normalization layer — the ONLY place where raw Polymarket fields are interpreted.

Business logic consumes the Normalized* dataclasses below and never touches raw
camelCase/JSON-string fields (development-rules.md #7/#8).

Direction rule: YES/NO is derived by value-matching the `outcomes` array and aligning
indexes with `clobTokenIds` / `outcomeIndex`. Index 0 is NEVER assumed to be YES.
Markets whose outcomes are not exactly {Yes, No} are rejected (ASSUMPTION-A1).

Field semantics references: /docs/data-field-uncertainties.md (V1–V6, U1–U13).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

DIRECTION_YES = "YES"
DIRECTION_NO = "NO"

# Ordered keyword → category mapping (ASSUMPTION-A5: keyword-based approximation).
CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("sports", ["sport", "nba", "nfl", "mlb", "nhl", "soccer", "football", "tennis", "ufc",
                "mma", "boxing", "golf", "f1", "cricket", "olympic", "fifa", "world-cup",
                "world cup", "epl", "champions-league", "basketball", "baseball", "hockey",
                "premier-league", "laliga", "serie-a"]),
    ("politics", ["politic", "election", "president", "senate", "congress", "trump", "biden",
                  "governor", "parliament", "minister", "vote", "primary", "primaries",
                  "government", "supreme-court", "impeach", "mayor", "cabinet", "nominee"]),
    ("crypto", ["crypto", "bitcoin", "btc", "ethereum", " eth", "eth-", "solana", "sol-",
                "defi", "nft", "airdrop", "binance", "coinbase", "stablecoin", "xrp", "doge",
                "memecoin", "fdv", "token", "altcoin"]),
    ("economy", ["econom", "fed", "inflation", "cpi", "gdp", "interest-rate", "recession",
                 "stock", "s&p", "sp500", "nasdaq", "earnings", "ipo", "tariff",
                 "unemployment", "treasury", "market-cap"]),
    ("science-tech", ["science", "tech", "openai", " ai ", "ai-", "spacex", "nasa", "launch",
                      "climate", "weather", "temperature", "vaccine", "apple", "google",
                      "tesla", "microsoft", "nvidia", "gpt", "grok", "gemini"]),
    ("pop-culture", ["culture", "movie", "film", "oscar", "grammy", "music", "album",
                     "celebrity", "tv-", "series", "box-office", "esports", "gaming",
                     "game-awards", "gta", "rotten-tomatoes", "billboard"]),
    ("world", ["war", "ukraine", "russia", "israel", "iran", "gaza", "china", "taiwan",
               "north-korea", "ceasefire", "strike", "nato", "geopolit", "un-", "treaty"]),
]

META_TAG_SLUGS = {"hide-from-new", "recurring", "all", "new"}


def parse_dt(value: Any) -> datetime | None:
    """Parse Polymarket datetime strings ('2026-07-20T00:00:00Z' or '2026-07-20')
    or unix timestamps into naive-UTC datetimes."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, datetime):
        return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt
    except ValueError:
        return None


def parse_json_string_array(value: Any) -> list[Any]:
    """Gamma encodes arrays as JSON strings (V1). Accept either form."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def outcome_to_direction(outcome: Any) -> str | None:
    if not isinstance(outcome, str):
        return None
    norm = outcome.strip().lower()
    if norm == "yes":
        return DIRECTION_YES
    if norm == "no":
        return DIRECTION_NO
    return None


def _to_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def categorize(*texts: str) -> str | None:
    """Keyword-based category approximation (ASSUMPTION-A5/UNCERTAINTY-U6)."""
    haystack = " ".join(t.lower() for t in texts if t)
    if not haystack:
        return None
    for category, keywords in CATEGORY_KEYWORDS:
        for kw in keywords:
            if kw in haystack:
                return category
    return None


# --------------------------------------------------------------------------- markets

@dataclass
class NormalizedMarket:
    gamma_id: str
    condition_id: str
    question: str
    slug: str
    event_id: str | None
    category: str | None
    tags: list[str]
    yes_token_id: str
    no_token_id: str
    yes_price_hint: float | None  # gamma outcomePrices (may lag CLOB)
    no_price_hint: float | None
    active: bool
    closed: bool
    accepting_orders: bool
    enable_order_book: bool
    neg_risk: bool
    tick_size: float
    end_date: datetime | None
    volume_total: float
    volume_24h: float
    liquidity: float
    open_interest_event: float | None  # event-level OI (UNCERTAINTY-U5)
    spread_hint: float | None  # gamma `spread` field
    best_bid_hint: float | None
    best_ask_hint: float | None

    @property
    def token_directions(self) -> dict[str, str]:
        return {self.yes_token_id: DIRECTION_YES, self.no_token_id: DIRECTION_NO}


class NotBinaryMarket(ValueError):
    """Market outcomes are not exactly {Yes, No} — skipped in v1 (ASSUMPTION-A1)."""


def normalize_market(raw: dict[str, Any]) -> NormalizedMarket:
    outcomes = parse_json_string_array(raw.get("outcomes"))
    token_ids = parse_json_string_array(raw.get("clobTokenIds"))
    prices = parse_json_string_array(raw.get("outcomePrices"))

    directions = [outcome_to_direction(o) for o in outcomes]
    if (len(outcomes) != 2 or len(token_ids) != 2
            or set(directions) != {DIRECTION_YES, DIRECTION_NO}):
        raise NotBinaryMarket(
            f"market {raw.get('id')} outcomes={outcomes!r} is not a binary Yes/No market")
    yes_idx = directions.index(DIRECTION_YES)
    no_idx = directions.index(DIRECTION_NO)

    events = raw.get("events") or []
    event = events[0] if isinstance(events, list) and events else {}
    raw_tags = event.get("tags") or []
    tag_labels = [t.get("label", "") for t in raw_tags if isinstance(t, dict)]
    tag_slugs = [t.get("slug", "") for t in raw_tags if isinstance(t, dict)]
    usable_tags = [lbl for lbl, slug in zip(tag_labels, tag_slugs, strict=True)
                   if slug not in META_TAG_SLUGS and lbl]
    category = categorize(" ".join(tag_slugs), " ".join(tag_labels),
                          str(event.get("slug") or ""), str(raw.get("slug") or ""))

    return NormalizedMarket(
        gamma_id=str(raw.get("id")),
        condition_id=str(raw.get("conditionId") or ""),
        question=str(raw.get("question") or ""),
        slug=str(raw.get("slug") or ""),
        event_id=str(event.get("id")) if event.get("id") is not None else None,
        category=category,
        tags=usable_tags,
        yes_token_id=str(token_ids[yes_idx]),
        no_token_id=str(token_ids[no_idx]),
        yes_price_hint=_to_float(prices[yes_idx]) if len(prices) == 2 else None,
        no_price_hint=_to_float(prices[no_idx]) if len(prices) == 2 else None,
        active=bool(raw.get("active", False)),
        closed=bool(raw.get("closed", False)),
        accepting_orders=bool(raw.get("acceptingOrders", False)),
        enable_order_book=bool(raw.get("enableOrderBook", False)),
        neg_risk=bool(raw.get("negRisk", False)),
        tick_size=_to_float(raw.get("orderPriceMinTickSize"), 0.01) or 0.01,
        end_date=parse_dt(raw.get("endDate")),
        volume_total=_to_float(raw.get("volumeNum"), _to_float(raw.get("volume"), 0.0)) or 0.0,
        volume_24h=_to_float(raw.get("volume24hr"), 0.0) or 0.0,
        liquidity=_to_float(raw.get("liquidityNum"), _to_float(raw.get("liquidity"), 0.0)) or 0.0,
        open_interest_event=_to_float(event.get("openInterest")),
        spread_hint=_to_float(raw.get("spread")),
        best_bid_hint=_to_float(raw.get("bestBid")),
        best_ask_hint=_to_float(raw.get("bestAsk")),
    )


# --------------------------------------------------------------------------- order book

@dataclass
class NormalizedBook:
    token_id: str
    best_bid: float | None
    best_ask: float | None
    midpoint: float | None
    spread: float | None
    bid_depth_usdc: float
    ask_depth_usdc: float
    top3_ask_usdc: float
    one_sided: bool


def normalize_book(raw: dict[str, Any], token_id: str) -> NormalizedBook:
    """Order of bids/asks arrays is NOT relied upon (V5): best bid = max, best ask = min."""
    def levels(key: str) -> list[tuple[float, float]]:
        out = []
        for lvl in raw.get(key) or []:
            price = _to_float(lvl.get("price"))
            size = _to_float(lvl.get("size"))
            if price is not None and size is not None and 0 < price < 1 and size > 0:
                out.append((price, size))
        return out

    bids = levels("bids")
    asks = levels("asks")
    best_bid = max((p for p, _ in bids), default=None)
    best_ask = min((p for p, _ in asks), default=None)
    midpoint = (best_bid + best_ask) / 2 if best_bid is not None and best_ask is not None else None
    spread = (best_ask - best_bid) if best_bid is not None and best_ask is not None else None
    top3_asks = sorted(asks, key=lambda x: x[0])[:3]
    return NormalizedBook(
        token_id=token_id,
        best_bid=best_bid,
        best_ask=best_ask,
        midpoint=midpoint,
        spread=spread,
        bid_depth_usdc=round(sum(p * s for p, s in bids), 2),
        ask_depth_usdc=round(sum(p * s for p, s in asks), 2),
        top3_ask_usdc=round(sum(p * s for p, s in top3_asks), 2),
        one_sided=(best_bid is None) != (best_ask is None),
    )


# --------------------------------------------------------------------------- holders

@dataclass
class NormalizedHolderRow:
    wallet_address: str
    token_id: str
    direction: str
    shares: float  # `amount` is shares, NOT USD (V2)
    profile_name: str | None


def normalize_holders(raw: list[dict[str, Any]], token_directions: dict[str, str]
                      ) -> list[NormalizedHolderRow]:
    rows: list[NormalizedHolderRow] = []
    for token_group in raw or []:
        token_id = str(token_group.get("token") or "")
        direction = token_directions.get(token_id)
        if direction is None:
            continue  # token not part of this market mapping — never guess
        for h in token_group.get("holders") or []:
            address = str(h.get("proxyWallet") or "").lower()
            shares = _to_float(h.get("amount"))
            if not address.startswith("0x") or len(address) != 42 or not shares or shares <= 0:
                continue
            name = h.get("name") if h.get("displayUsernamePublic") else h.get("pseudonym")
            rows.append(NormalizedHolderRow(
                wallet_address=address, token_id=token_id, direction=direction,
                shares=shares, profile_name=(str(name)[:200] or None) if name else None))
    return rows


# --------------------------------------------------------------------------- positions

@dataclass
class NormalizedPosition:
    """Current (open or unredeemed) position from /positions (V3)."""
    wallet_address: str
    condition_id: str
    token_id: str
    direction: str | None  # from `outcome` value, None if not Yes/No
    shares: float
    average_price: float | None
    entry_notional_approx: float | None  # initialValue = cost basis approximation (U3)
    current_value: float | None
    current_price: float | None
    redeemable: bool
    end_date: datetime | None
    neg_risk: bool


def normalize_position(raw: dict[str, Any]) -> NormalizedPosition:
    return NormalizedPosition(
        wallet_address=str(raw.get("proxyWallet") or "").lower(),
        condition_id=str(raw.get("conditionId") or ""),
        token_id=str(raw.get("asset") or ""),
        direction=outcome_to_direction(raw.get("outcome")),
        shares=_to_float(raw.get("size"), 0.0) or 0.0,
        average_price=_to_float(raw.get("avgPrice")),
        entry_notional_approx=_to_float(raw.get("initialValue")),
        current_value=_to_float(raw.get("currentValue")),
        current_price=_to_float(raw.get("curPrice")),
        redeemable=bool(raw.get("redeemable", False)),
        end_date=parse_dt(raw.get("endDate")),
        neg_risk=bool(raw.get("negativeRisk", False)),
    )


@dataclass
class NormalizedClosedPosition:
    """Resolved position from /closed-positions (V4) — basis for account stats."""
    wallet_address: str
    condition_id: str
    direction: str | None
    average_price: float | None
    total_bought: float  # shares bought over the position's life
    realized_pnl: float
    final_price: float | None  # curPrice: 1.0 won / 0.0 lost
    closed_at: datetime | None  # `timestamp` = when position closed (official, U2)
    end_date: datetime | None
    title: str
    event_slug: str
    slug: str

    @property
    def entry_notional(self) -> float | None:
        if self.average_price is None or self.total_bought <= 0:
            return None
        return self.average_price * self.total_bought

    @property
    def won(self) -> bool:
        return self.final_price is not None and self.final_price >= 0.999

    @property
    def roi(self) -> float | None:
        notional = self.entry_notional
        if not notional:
            return None
        return self.realized_pnl / notional

    def category(self) -> str | None:
        return categorize(self.event_slug, self.slug, self.title)

    def resolved_before(self, as_of: datetime) -> bool:
        """Look-ahead guard (ASSUMPTION-A3): include only if BOTH the close timestamp
        and the market end date are at or before `as_of`. Missing closed_at → excluded
        (conservative: never let ambiguous rows leak future information)."""
        if self.closed_at is None or self.closed_at > as_of:
            return False
        if self.end_date is not None and self.end_date > as_of:
            return False
        return True


def normalize_closed_position(raw: dict[str, Any]) -> NormalizedClosedPosition:
    return NormalizedClosedPosition(
        wallet_address=str(raw.get("proxyWallet") or "").lower(),
        condition_id=str(raw.get("conditionId") or ""),
        direction=outcome_to_direction(raw.get("outcome")),
        average_price=_to_float(raw.get("avgPrice")),
        total_bought=_to_float(raw.get("totalBought"), 0.0) or 0.0,
        realized_pnl=_to_float(raw.get("realizedPnl"), 0.0) or 0.0,
        final_price=_to_float(raw.get("curPrice")),
        closed_at=parse_dt(raw.get("timestamp")),
        end_date=parse_dt(raw.get("endDate")),
        title=str(raw.get("title") or ""),
        event_slug=str(raw.get("eventSlug") or ""),
        slug=str(raw.get("slug") or ""),
    )


# --------------------------------------------------------------------------- geoblock

@dataclass
class GeoblockStatus:
    blocked: bool
    country: str | None
    region: str | None
    mode: str  # OK / CLOSE_ONLY / BLOCKED
    can_open_position: bool
    can_close_position: bool
    fail_closed: bool = False
    checked_at: datetime = field(default_factory=lambda: datetime.utcnow())


def normalize_geoblock(raw: dict[str, Any], close_only_countries: list[str]) -> GeoblockStatus:
    """UNCERTAINTY-U1: the endpoint returns blocked=true for close-only countries too;
    mode is derived from the official close-only country list (env-configurable)."""
    blocked = bool(raw.get("blocked", True))
    country = (str(raw.get("country")) or "").upper() or None
    region = str(raw.get("region")) if raw.get("region") else None
    if not blocked:
        mode = "OK"
    elif country in close_only_countries:
        mode = "CLOSE_ONLY"
    else:
        mode = "BLOCKED"
    return GeoblockStatus(
        blocked=blocked, country=country, region=region, mode=mode,
        can_open_position=(mode == "OK"),
        can_close_position=(mode in ("OK", "CLOSE_ONLY")),
    )


def geoblock_fail_closed() -> GeoblockStatus:
    """Upstream geoblock check failed → treat as fully blocked (risk-control.md §1)."""
    return GeoblockStatus(blocked=True, country=None, region=None, mode="BLOCKED",
                          can_open_position=False, can_close_position=False, fail_closed=True)
