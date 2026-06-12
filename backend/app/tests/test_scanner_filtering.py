"""Market scanner filtering rules (spec test area 8)."""
from __future__ import annotations

from datetime import UTC, datetime

from app.services.market_scanner_service import filter_market
from app.services.normalization import normalize_market
from app.tests.conftest import make_test_settings
from app.tests.fakes import make_gamma_market

NOW = datetime.now(UTC).replace(tzinfo=None)
SETTINGS = make_test_settings()  # MIN_LIQUIDITY=1000, SCANNER_MIN_VOLUME_24H=1000


def check(raw) -> tuple[bool, str | None]:
    result = filter_market(normalize_market(raw), NOW, SETTINGS)
    return result.passed, result.reason


class TestScannerFilter:
    def test_good_market_passes(self):
        passed, reason = check(make_gamma_market())
        assert passed, reason

    def test_inactive_filtered(self):
        passed, reason = check(make_gamma_market(active=False))
        assert not passed and reason == "inactive_or_closed"

    def test_closed_filtered(self):
        passed, reason = check(make_gamma_market(closed=True))
        assert not passed and reason == "inactive_or_closed"

    def test_not_accepting_orders_filtered(self):
        passed, reason = check(make_gamma_market(accepting=False))
        assert not passed and reason == "not_accepting_orders"

    def test_low_liquidity_filtered(self):
        passed, reason = check(make_gamma_market(liquidity=999.0))
        assert not passed and reason == "low_liquidity"

    def test_low_volume_filtered(self):
        passed, reason = check(make_gamma_market(volume24hr=999.0))
        assert not passed and reason == "low_volume_24h"

    def test_near_resolution_filtered(self):
        passed, reason = check(make_gamma_market(end_in_hours=3.0))
        assert not passed and reason == "too_close_to_resolution"

    def test_missing_end_date_filtered(self):
        raw = make_gamma_market()
        raw["endDate"] = None
        passed, reason = check(raw)
        assert not passed and reason == "missing_end_date"

    def test_missing_condition_id_filtered(self):
        raw = make_gamma_market()
        raw["conditionId"] = ""
        passed, reason = check(raw)
        assert not passed and reason == "missing_identifiers"
