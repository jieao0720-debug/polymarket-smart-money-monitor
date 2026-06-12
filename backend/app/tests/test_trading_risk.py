"""Trading risk checks: geoblock enforcement, close-only, price/spread/notional
(spec test areas 10–12 unit level) and signed-payload validation."""
from __future__ import annotations

import pytest

from app.core.errors import ValidationFailed
from app.services import normalization as norm
from app.services.normalization import GeoblockStatus
from app.services.order_submit_service import validate_signed_payload
from app.services.trading_risk_service import (
    TradingRiskService,
    check_geoblock_for_open,
    check_notional,
    check_price,
    check_spread,
)
from app.tests.conftest import make_test_settings
from app.tests.fakes import FakeGeoblockClient, default_dataset, make_book

WALLET = "0x" + "ab" * 20


def geo(mode: str, fail_closed: bool = False) -> GeoblockStatus:
    return GeoblockStatus(blocked=mode != "OK", country="XX", region=None, mode=mode,
                          can_open_position=mode == "OK",
                          can_close_position=mode in ("OK", "CLOSE_ONLY"),
                          fail_closed=fail_closed)


class TestGeoblockEnforcement:
    def test_ok_can_open(self):
        assert check_geoblock_for_open(geo("OK")).ok

    def test_close_only_cannot_open(self):
        outcome = check_geoblock_for_open(geo("CLOSE_ONLY"))
        assert not outcome.ok
        assert "close-only" in (outcome.reason or "")

    def test_blocked_cannot_open(self):
        assert not check_geoblock_for_open(geo("BLOCKED")).ok

    def test_fail_closed_reason(self):
        outcome = check_geoblock_for_open(geo("BLOCKED", fail_closed=True))
        assert not outcome.ok
        assert "failing closed" in (outcome.reason or "")

    @pytest.mark.anyio
    async def test_upstream_failure_fails_closed(self):
        settings = make_test_settings()
        service = TradingRiskService(FakeGeoblockClient(default_dataset(), fail=True),
                                     settings)
        result = await service.get_geoblock()
        assert result.mode == "BLOCKED" and result.fail_closed

    @pytest.mark.anyio
    async def test_close_only_country_mapped(self):
        dataset = default_dataset()
        dataset["geoblock"] = {"blocked": True, "country": "SG", "region": ""}
        service = TradingRiskService(FakeGeoblockClient(dataset), make_test_settings())
        result = await service.get_geoblock()
        assert result.mode == "CLOSE_ONLY"
        assert not result.can_open_position and result.can_close_position


class TestPriceChecks:
    BOOK = norm.normalize_book(make_book(0.59, 0.61), "111")  # mid 0.60
    SETTINGS = make_test_settings()  # MAX_SLIPPAGE_BPS=100 → 0.01

    def test_valid_marketable_limit(self):
        assert check_price(0.61, self.BOOK, 0.01, 0.01).ok

    def test_above_slippage_ceiling_rejected(self):
        # ceiling = min(best_ask 0.61, mid 0.60 + 0.01) = 0.61 → 0.62 rejected
        assert not check_price(0.62, self.BOOK, 0.01, 0.01).ok

    def test_out_of_range_rejected(self):
        assert not check_price(0.0, self.BOOK, 0.01, 0.01).ok
        assert not check_price(1.0, self.BOOK, 0.01, 0.01).ok

    def test_tick_misaligned_rejected(self):
        assert not check_price(0.605, self.BOOK, 0.01, 0.01).ok
        assert check_price(0.605, self.BOOK, 0.005, 0.01).ok

    def test_implausibly_low_rejected(self):
        assert not check_price(0.01, self.BOOK, 0.01, 0.01).ok

    def test_missing_book_rejected(self):
        assert not check_price(0.61, None, 0.01, 0.01).ok


class TestSpreadAndNotional:
    def test_wide_spread_rejected(self):
        wide = norm.normalize_book(make_book(0.40, 0.60), "111")
        assert not check_spread(wide, 0.03).ok
        tight = norm.normalize_book(make_book(0.59, 0.61), "111")
        assert check_spread(tight, 0.03).ok

    def test_one_sided_rejected(self):
        book = norm.normalize_book({"bids": [], "asks": [{"price": "0.6", "size": "5"}]},
                                   "111")
        assert not check_spread(book, 0.03).ok

    def test_notional_cap(self):
        settings = make_test_settings()  # MAX_TRADE_NOTIONAL=100
        assert check_notional(100.0, settings).ok
        assert not check_notional(100.01, settings).ok
        assert not check_notional(0.0, settings).ok
        assert not check_notional(-5.0, settings).ok


class TestSignedPayloadValidation:
    def payload(self, **order_overrides):
        order = {
            "salt": "123", "maker": WALLET, "signer": WALLET,
            "taker": "0x0000000000000000000000000000000000000000", "tokenId": "111",
            "makerAmount": "61000000", "takerAmount": "100000000",
            "expiration": "0", "nonce": "0", "feeRateBps": "0", "side": "BUY",
            "signatureType": 0, "signature": "0x" + "ab" * 65,
        }
        order.update(order_overrides)
        return {"order": order, "owner": "api-key-uuid", "orderType": "GTC"}

    def test_valid_payload_passes(self):
        body = validate_signed_payload(self.payload(), wallet_address=WALLET,
                                       expected_token_id="111")
        assert body["orderType"] == "GTC"

    def test_maker_mismatch_rejected(self):
        with pytest.raises(ValidationFailed):
            validate_signed_payload(self.payload(maker="0x" + "cd" * 20),
                                    wallet_address=WALLET, expected_token_id="111")

    def test_token_mismatch_rejected(self):
        """Yes/No direction safety: payload token must match the ticket side."""
        with pytest.raises(ValidationFailed):
            validate_signed_payload(self.payload(tokenId="222"),
                                    wallet_address=WALLET, expected_token_id="111")

    def test_sell_rejected_in_v1(self):
        with pytest.raises(ValidationFailed):
            validate_signed_payload(self.payload(side="SELL"),
                                    wallet_address=WALLET, expected_token_id="111")

    def test_missing_fields_rejected(self):
        broken = self.payload()
        del broken["order"]["signature"]
        with pytest.raises(ValidationFailed):
            validate_signed_payload(broken, wallet_address=WALLET, expected_token_id="111")
