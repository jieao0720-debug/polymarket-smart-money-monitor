"""Yes/No direction normalization and field-semantics tests (spec test area 9)."""
from __future__ import annotations

import pytest

from app.services import normalization as norm
from app.tests.fakes import make_book, make_closed_positions, make_gamma_market


class TestMarketDirectionMapping:
    def test_standard_yes_no_order(self):
        market = norm.normalize_market(make_gamma_market())
        assert market.yes_token_id == "111"
        assert market.no_token_id == "222"
        assert market.yes_price_hint == 0.6
        assert market.no_price_hint == 0.4

    def test_reversed_outcome_order_is_not_assumed(self):
        """Index 0 must NEVER be assumed to be YES."""
        raw = make_gamma_market(outcomes=["No", "Yes"], token_ids=["333", "444"],
                                prices=["0.4", "0.6"])
        market = norm.normalize_market(raw)
        assert market.yes_token_id == "444"
        assert market.no_token_id == "333"
        assert market.yes_price_hint == 0.6
        assert market.token_directions == {"444": "YES", "333": "NO"}

    def test_case_insensitive_outcomes(self):
        raw = make_gamma_market(outcomes=["YES", "no"])
        market = norm.normalize_market(raw)
        assert market.yes_token_id == "111"

    def test_non_binary_market_rejected(self):
        raw = make_gamma_market(outcomes=["Yes", "Other"])
        with pytest.raises(norm.NotBinaryMarket):
            norm.normalize_market(raw)

    def test_multi_outcome_market_rejected(self):
        raw = make_gamma_market()
        raw["outcomes"] = '["A", "B", "C"]'
        raw["clobTokenIds"] = '["1", "2", "3"]'
        with pytest.raises(norm.NotBinaryMarket):
            norm.normalize_market(raw)

    def test_category_from_event_tags(self):
        market = norm.normalize_market(make_gamma_market())
        assert market.category == "politics"


class TestBookNormalization:
    def test_best_prices_do_not_rely_on_array_order(self):
        """Live API returns asks high→low; best ask must still be the minimum."""
        book = norm.normalize_book(make_book(0.59, 0.61), "111")
        assert book.best_bid == 0.59
        assert book.best_ask == 0.61
        assert book.midpoint == pytest.approx(0.60)
        assert book.spread == pytest.approx(0.02)
        assert not book.one_sided

    def test_one_sided_book(self):
        raw = {"bids": [{"price": "0.5", "size": "10"}], "asks": []}
        book = norm.normalize_book(raw, "111")
        assert book.one_sided
        assert book.spread is None

    def test_invalid_levels_dropped(self):
        raw = {"bids": [{"price": "1.5", "size": "10"}, {"price": "0.5", "size": "0"}],
               "asks": [{"price": "0.6", "size": "10"}]}
        book = norm.normalize_book(raw, "111")
        assert book.best_bid is None  # 1.5 out of range, size-0 dropped


class TestClosedPositionNormalization:
    def test_entry_notional_and_won(self):
        raw = make_closed_positions("0x" + "aa" * 20, count=1, wins=1, base_entry=50.0)[0]
        pos = norm.normalize_closed_position(raw)
        assert pos.entry_notional == pytest.approx(50.0)
        assert pos.won is True
        assert pos.roi == pytest.approx(50.0 / 50.0)  # win_pnl=50 over 50 entry

    def test_shares_vs_usd_not_conflated(self):
        """totalBought is shares; entry notional = avgPrice * totalBought."""
        raw = make_closed_positions("0x" + "aa" * 20, count=1, wins=0,
                                    base_entry=100.0)[0]
        pos = norm.normalize_closed_position(raw)
        assert pos.total_bought == pytest.approx(200.0)  # 100 / 0.5 avg price
        assert pos.entry_notional == pytest.approx(100.0)


class TestGeoblockNormalization:
    CLOSE_ONLY = ["PL", "SG", "TH", "TW"]

    def test_not_blocked(self):
        geo = norm.normalize_geoblock({"blocked": False, "country": "DE"}, self.CLOSE_ONLY)
        assert geo.mode == "OK" and geo.can_open_position and geo.can_close_position

    def test_close_only_country(self):
        geo = norm.normalize_geoblock({"blocked": True, "country": "SG"}, self.CLOSE_ONLY)
        assert geo.mode == "CLOSE_ONLY"
        assert not geo.can_open_position
        assert geo.can_close_position

    def test_fully_blocked_country(self):
        geo = norm.normalize_geoblock({"blocked": True, "country": "US"}, self.CLOSE_ONLY)
        assert geo.mode == "BLOCKED"
        assert not geo.can_open_position and not geo.can_close_position

    def test_missing_blocked_field_defaults_to_blocked(self):
        geo = norm.normalize_geoblock({}, self.CLOSE_ONLY)
        assert geo.blocked is True and geo.mode == "BLOCKED"

    def test_fail_closed(self):
        geo = norm.geoblock_fail_closed()
        assert geo.mode == "BLOCKED" and geo.fail_closed
        assert not geo.can_open_position and not geo.can_close_position
