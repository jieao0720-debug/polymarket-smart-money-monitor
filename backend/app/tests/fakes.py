"""Fake Polymarket clients with realistic payload shapes (mirroring live responses
captured 2026-06-11 — see /docs/data-field-uncertainties.md)."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from app.clients.clob_client import ClobClient
from app.clients.data_client import DataClient
from app.clients.gamma_client import GammaClient
from app.clients.geoblock_client import GeoblockClient
from app.clients.polygon_rpc_client import PolygonRpcClient
from app.core.errors import UpstreamError

ADDR_SMART = "0x" + "aa" * 20
ADDR_NEW = "0x" + "bb" * 20
ADDR_ABNORMAL = "0x" + "cc" * 20


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def make_gamma_market(*, gamma_id: str = "1001", condition_id: str = "0xc1",
                      outcomes: list[str] | None = None,
                      token_ids: list[str] | None = None,
                      prices: list[str] | None = None,
                      volume24hr: float = 50000.0, liquidity: float = 20000.0,
                      end_in_hours: float = 24 * 30, active: bool = True,
                      closed: bool = False, accepting: bool = True,
                      question: str = "Will the test candidate win the election?",
                      tag_label: str = "Politics", tag_slug: str = "politics",
                      neg_risk: bool = False) -> dict[str, Any]:
    outcomes = outcomes or ["Yes", "No"]
    token_ids = token_ids or ["111", "222"]
    prices = prices or ["0.6", "0.4"]
    end = now_utc() + timedelta(hours=end_in_hours)
    return {
        "id": gamma_id, "conditionId": condition_id, "question": question,
        "slug": f"test-market-{gamma_id}", "outcomes": json.dumps(outcomes),
        "outcomePrices": json.dumps(prices), "clobTokenIds": json.dumps(token_ids),
        "active": active, "closed": closed, "acceptingOrders": accepting,
        "enableOrderBook": True, "negRisk": neg_risk, "orderPriceMinTickSize": 0.01,
        "orderMinSize": 5, "endDate": _iso(end), "volumeNum": 1_000_000.0,
        "volume24hr": volume24hr, "liquidityNum": liquidity, "spread": 0.02,
        "bestBid": 0.59, "bestAsk": 0.61,
        "events": [{"id": "5001", "slug": "test-election-event",
                    "openInterest": 100000.0,
                    "tags": [{"id": "1", "label": tag_label, "slug": tag_slug}]}],
    }


def make_book(best_bid: float, best_ask: float, *, deep: bool = True) -> dict[str, Any]:
    # asks intentionally listed high→low to mirror live behaviour (order must not matter)
    asks = [{"price": str(round(best_ask + 0.01, 3)), "size": "500"},
            {"price": str(best_ask), "size": "800"}]
    bids = [{"price": str(best_bid), "size": "1000"},
            {"price": str(round(best_bid - 0.01, 3)), "size": "700"}]
    if not deep:
        asks, bids = asks[:1], bids[:1]
    return {"market": "0xc1", "asset_id": "111", "bids": bids, "asks": asks}


def make_closed_positions(address: str, *, count: int, wins: int, base_entry: float = 50.0,
                          win_pnl: float = 50.0, loss_pnl: float = -30.0,
                          event_slug: str = "presidential-election-2024",
                          title: str = "Will candidate X win the presidency?",
                          days_ago_start: int = 400) -> list[dict[str, Any]]:
    rows = []
    for i in range(count):
        won = i < wins
        closed_at = now_utc() - timedelta(days=days_ago_start - i * 10)
        end_date = closed_at - timedelta(days=2)
        avg_price = 0.5
        total_bought = base_entry / avg_price
        rows.append({
            "proxyWallet": address, "asset": f"90{i}", "conditionId": f"0xhist{i}",
            "avgPrice": avg_price, "totalBought": total_bought,
            "realizedPnl": win_pnl if won else loss_pnl,
            "curPrice": 1 if won else 0, "outcome": "Yes" if i % 2 == 0 else "No",
            "outcomeIndex": 0 if i % 2 == 0 else 1, "oppositeOutcome": "No",
            "oppositeAsset": f"91{i}", "endDate": _iso(end_date),
            "timestamp": int(closed_at.replace(tzinfo=UTC).timestamp()),
            "title": title, "slug": f"hist-{i}", "eventSlug": event_slug,
        })
    return rows


def make_position(address: str, condition_id: str, token_id: str, outcome: str, *,
                  size: float, avg_price: float, cur_price: float) -> dict[str, Any]:
    return {
        "proxyWallet": address, "asset": token_id, "conditionId": condition_id,
        "size": size, "avgPrice": avg_price, "initialValue": round(size * avg_price, 4),
        "currentValue": round(size * cur_price, 4), "cashPnl": 0.0,
        "totalBought": size, "realizedPnl": 0.0, "curPrice": cur_price,
        "redeemable": False, "mergeable": False, "title": "t", "slug": "s",
        "eventId": "5001", "eventSlug": "test-election-event", "outcome": outcome,
        "outcomeIndex": 0 if outcome == "Yes" else 1, "oppositeOutcome": "No",
        "oppositeAsset": "x", "endDate": _iso(now_utc() + timedelta(days=30)),
        "negativeRisk": False,
    }


def default_dataset() -> dict[str, Any]:
    """One politics market; YES side: smart whale + new account; NO side: abnormal sizer."""
    market = make_gamma_market()
    return {
        "gamma_markets": [market],
        "holders": {
            "0xc1": [
                {"token": "111", "holders": [
                    {"proxyWallet": ADDR_SMART, "amount": 10000, "outcomeIndex": 0,
                     "name": "smartwhale", "pseudonym": "Wise-Owl",
                     "displayUsernamePublic": True},
                    {"proxyWallet": ADDR_NEW, "amount": 5000, "outcomeIndex": 0,
                     "name": "", "pseudonym": "Fresh-Face", "displayUsernamePublic": False},
                ]},
                {"token": "222", "holders": [
                    {"proxyWallet": ADDR_ABNORMAL, "amount": 3000, "outcomeIndex": 1,
                     "name": "yolo", "pseudonym": "Big-Swing", "displayUsernamePublic": True},
                ]},
            ],
        },
        "books": {
            "111": make_book(0.59, 0.61),
            "222": make_book(0.39, 0.41),
        },
        "closed_positions": {
            ADDR_SMART: make_closed_positions(ADDR_SMART, count=25, wins=18),
            ADDR_NEW: [],
            ADDR_ABNORMAL: make_closed_positions(
                ADDR_ABNORMAL, count=12, wins=5, base_entry=50.0, win_pnl=20.0,
                loss_pnl=-15.0, event_slug="bitcoin-150k-by-march",
                title="Will Bitcoin hit $150k?"),
        },
        "positions": {
            (ADDR_SMART, "0xc1"): [make_position(ADDR_SMART, "0xc1", "111", "Yes",
                                                 size=10000, avg_price=0.55, cur_price=0.60)],
            (ADDR_NEW, "0xc1"): [make_position(ADDR_NEW, "0xc1", "111", "Yes",
                                               size=5000, avg_price=0.60, cur_price=0.60)],
            (ADDR_ABNORMAL, "0xc1"): [make_position(ADDR_ABNORMAL, "0xc1", "222", "No",
                                                    size=3000, avg_price=0.42,
                                                    cur_price=0.41)],
        },
        "geoblock": {"blocked": False, "ip": "1.2.3.4", "country": "DE", "region": ""},
    }


class FakeGammaClient(GammaClient):
    def __init__(self, dataset: dict[str, Any]) -> None:
        super().__init__("http://fake-gamma")
        self.dataset = dataset

    async def list_markets(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.dataset["gamma_markets"]

    async def get_market(self, gamma_market_id: str) -> dict[str, Any] | None:
        for m in self.dataset["gamma_markets"]:
            if m["id"] == gamma_market_id:
                return m
        return None

    async def aclose(self) -> None:  # no real connection
        pass


class FakeDataClient(DataClient):
    def __init__(self, dataset: dict[str, Any]) -> None:
        super().__init__("http://fake-data")
        self.dataset = dataset

    async def get_holders(self, condition_id: str, **kwargs: Any) -> list[dict[str, Any]]:
        return self.dataset["holders"].get(condition_id, [])

    async def get_positions(self, user: str, *, condition_id: str | None = None,
                            **kwargs: Any) -> list[dict[str, Any]]:
        return self.dataset["positions"].get((user.lower(), condition_id), [])

    async def get_closed_positions(self, user: str, *, max_pages: int = 4
                                   ) -> tuple[list[dict[str, Any]], bool]:
        return self.dataset["closed_positions"].get(user.lower(), []), False

    async def aclose(self) -> None:
        pass


class FakeClobClient(ClobClient):
    def __init__(self, dataset: dict[str, Any]) -> None:
        super().__init__("http://fake-clob")
        self.dataset = dataset
        self.posted_orders: list[dict[str, Any]] = []
        self.post_response: tuple[int, dict[str, Any]] = (
            200, {"success": True, "orderID": "0xorder1", "status": "live",
                  "transactionsHashes": []})

    async def get_book(self, token_id: str) -> dict[str, Any]:
        book = self.dataset["books"].get(token_id)
        if book is None:
            raise UpstreamError("no book for token")
        return book

    async def post_order(self, body: dict[str, Any],
                         headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
        self.posted_orders.append({"body": body, "headers": headers})
        return self.post_response

    async def derive_api_key(self, l1_headers: dict[str, str]) -> dict[str, Any] | None:
        if l1_headers.get("POLY_SIGNATURE", "").startswith("0x"):
            return {"apiKey": "fake-key", "secret": "ZmFrZQ==", "passphrase": "fake-pass"}
        return None

    async def create_api_key(self, l1_headers: dict[str, str]) -> dict[str, Any] | None:
        return None

    async def aclose(self) -> None:
        pass


class FakeGeoblockClient(GeoblockClient):
    def __init__(self, dataset: dict[str, Any], *, fail: bool = False) -> None:
        super().__init__("http://fake-geoblock")
        self.dataset = dataset
        self.fail = fail

    async def check(self) -> dict[str, Any]:
        if self.fail:
            raise UpstreamError("geoblock unreachable")
        return self.dataset["geoblock"]

    async def aclose(self) -> None:
        pass


class FakeRpcClient(PolygonRpcClient):
    def __init__(self, *, usdc: float | None = 1000.0, native: float | None = 1.0,
                 allowance: float | None = 1000.0) -> None:
        super().__init__("http://fake-rpc")
        self.usdc = usdc
        self.native = native
        self.allowance = allowance

    async def get_usdc_balance(self, wallet: str) -> float | None:
        return self.usdc

    async def get_native_balance(self, wallet: str) -> float | None:
        return self.native

    async def get_usdc_allowance(self, owner: str, spender: str) -> float | None:
        return self.allowance

    async def aclose(self) -> None:
        pass
