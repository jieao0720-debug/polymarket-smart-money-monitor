"""Smart money score components, penalties, and market confidence (areas 6–7)."""
from __future__ import annotations

import pytest

from app.services import scoring as sc

CTX_CLEAN = sc.MarketRiskContext(spread=0.01, liquidity=20000.0, hours_to_resolution=500.0,
                                 entry_price=0.6)


class TestComponents:
    def test_win_rate_score(self):
        assert sc.win_rate_score(0.0) == 0.0
        assert sc.win_rate_score(0.65) == pytest.approx(65.0)
        assert sc.win_rate_score(1.5) == 100.0  # clamped

    def test_realized_pnl_score(self):
        assert sc.realized_pnl_score(-100.0) == 0.0
        assert sc.realized_pnl_score(0.0) == 0.0
        assert sc.realized_pnl_score(99.0) == pytest.approx(40.0, abs=0.5)
        assert sc.realized_pnl_score(9_999.0) == pytest.approx(80.0, abs=0.5)
        assert sc.realized_pnl_score(10**9) == 100.0

    def test_sample_size_score(self):
        assert sc.sample_size_score(0) == 0.0
        assert sc.sample_size_score(25) == 50.0
        assert sc.sample_size_score(50) == 100.0
        assert sc.sample_size_score(500) == 100.0

    def test_same_category_score_blends_to_neutral(self):
        assert sc.same_category_score(0.9, 0) == 50.0  # no data → neutral
        assert sc.same_category_score(0.9, 10) == pytest.approx(90.0)
        assert sc.same_category_score(0.9, 5) == pytest.approx(70.0)  # half blend

    def test_anomaly_score(self):
        assert sc.anomaly_score(None) == 0.0
        assert sc.anomaly_score(1.0) == 10.0
        assert sc.anomaly_score(5.0) == 50.0
        assert sc.anomaly_score(50.0) == 100.0

    def test_position_size_score(self):
        assert sc.position_size_score(0.0) == 0.0
        assert sc.position_size_score(1000.0) == 10.0
        assert sc.position_size_score(10_000.0) == 100.0
        assert sc.position_size_score(10**7) == 100.0


class TestPenalties:
    def test_low_sample_penalty_tiers(self):
        assert sc.low_sample_penalty(25) == 0.0
        assert sc.low_sample_penalty(15) == 10.0
        assert sc.low_sample_penalty(7) == 20.0
        assert sc.low_sample_penalty(2) == 25.0
        assert sc.low_sample_penalty(0) == 0.0  # handled by new_account_penalty

    def test_new_account_penalty(self):
        assert sc.new_account_penalty(0) == 30.0
        assert sc.new_account_penalty(1) == 0.0

    def test_high_spread_penalty(self):
        assert sc.high_spread_penalty(0.05, 0.03) == 10.0
        assert sc.high_spread_penalty(0.01, 0.03) == 0.0
        assert sc.high_spread_penalty(None, 0.03) == 10.0  # unknown → risky

    def test_low_liquidity_penalty(self):
        assert sc.low_liquidity_penalty(500.0, 1000.0) == 10.0
        assert sc.low_liquidity_penalty(5000.0, 1000.0) == 0.0

    def test_near_resolution_penalty(self):
        assert sc.near_resolution_penalty(10.0, 48.0) == 10.0
        assert sc.near_resolution_penalty(100.0, 48.0) == 0.0
        assert sc.near_resolution_penalty(None, 48.0) == 0.0

    def test_extreme_price_penalty(self):
        assert sc.extreme_price_penalty(0.02) == 10.0
        assert sc.extreme_price_penalty(0.97) == 10.0
        assert sc.extreme_price_penalty(0.5) == 0.0
        assert sc.extreme_price_penalty(None) == 0.0


class TestTotalScore:
    def kwargs(self, **over):
        base = dict(win_rate=0.7, realized_pnl=900.0, resolved_trade_count=25,
                    same_category_win_rate=0.7, same_category_trade_count=10,
                    anomaly_index=2.0, current_position_value=5000.0,
                    market_ctx=CTX_CLEAN)
        base.update(over)
        return base

    def test_score_in_range_and_breakdown(self):
        score, breakdown = sc.smart_money_score(**self.kwargs())
        assert 0.0 <= score <= 100.0
        assert set(breakdown["components"]) == {
            "win_rate_score", "realized_pnl_score", "sample_size_score",
            "same_category_score", "anomaly_score", "position_size_score"}
        assert set(breakdown["penalties"]) == {
            "low_sample_penalty", "new_account_penalty", "high_spread_penalty",
            "low_liquidity_penalty", "near_resolution_penalty", "extreme_price_penalty"}
        assert breakdown["final"] == pytest.approx(score, abs=0.01)

    def test_never_below_zero_or_above_100(self):
        low, _ = sc.smart_money_score(**self.kwargs(
            win_rate=0.0, realized_pnl=-1000.0, resolved_trade_count=1,
            same_category_win_rate=0.0, same_category_trade_count=0,
            anomaly_index=None, current_position_value=0.0,
            market_ctx=sc.MarketRiskContext(spread=None, liquidity=0.0,
                                            hours_to_resolution=1.0, entry_price=0.99)))
        assert low == 0.0
        high, _ = sc.smart_money_score(**self.kwargs(
            win_rate=1.0, realized_pnl=10**8, resolved_trade_count=500,
            same_category_win_rate=1.0, same_category_trade_count=100,
            anomaly_index=100.0, current_position_value=10**7))
        assert high <= 100.0

    def test_better_win_rate_scores_higher(self):
        lo, _ = sc.smart_money_score(**self.kwargs(win_rate=0.4))
        hi, _ = sc.smart_money_score(**self.kwargs(win_rate=0.8))
        assert hi > lo

    def test_market_risk_lowers_score(self):
        risky = sc.MarketRiskContext(spread=0.10, liquidity=100.0, hours_to_resolution=2.0,
                                     entry_price=0.98)
        clean_score, _ = sc.smart_money_score(**self.kwargs())
        risky_score, _ = sc.smart_money_score(**self.kwargs(market_ctx=risky))
        assert risky_score < clean_score


class TestMarketConfidence:
    def test_zero_without_dominant_holders(self):
        assert sc.market_confidence(dominant_notional=0, other_notional=0,
                                    dominant_count=0, dominant_avg_score=0,
                                    market_penalty=0) == 0.0

    def test_more_imbalance_more_confidence(self):
        even = sc.market_confidence(dominant_notional=5500, other_notional=4500,
                                    dominant_count=3, dominant_avg_score=70,
                                    market_penalty=0)
        skewed = sc.market_confidence(dominant_notional=9000, other_notional=1000,
                                      dominant_count=3, dominant_avg_score=70,
                                      market_penalty=0)
        assert skewed > even

    def test_penalty_reduces_confidence(self):
        base = sc.market_confidence(dominant_notional=9000, other_notional=1000,
                                    dominant_count=3, dominant_avg_score=70,
                                    market_penalty=0)
        penalized = sc.market_confidence(dominant_notional=9000, other_notional=1000,
                                         dominant_count=3, dominant_avg_score=70,
                                         market_penalty=30)
        assert penalized == pytest.approx(base - 30, abs=0.01)

    def test_clamped_0_100(self):
        assert 0 <= sc.market_confidence(dominant_notional=1, other_notional=10**9,
                                         dominant_count=1, dominant_avg_score=0,
                                         market_penalty=100) <= 100
