"""Auto paper-trade guards (ASSUMPTION-A9b): extreme-price / wide-relative-spread
signals are not auto-logged, and re-scans never stack duplicate OPEN positions."""
from __future__ import annotations

from app.services.paper_trade_service import should_auto_log


def decide(**over):
    base = dict(direction="YES", confidence_score=60.0, min_confidence=50.0,
                risk_flags=[], entry_price=0.61, spread=0.02, max_relative_spread=0.10)
    base.update(over)
    return should_auto_log(**base)


class TestShouldAutoLog:
    def test_clean_signal_logs(self):
        decision = decide()
        assert decision.should_log and decision.reason is None

    def test_neutral_skipped(self):
        decision = decide(direction="NEUTRAL")
        assert not decision.should_log
        assert "neutral" in decision.reason

    def test_low_confidence_skipped(self):
        decision = decide(confidence_score=49.9)
        assert not decision.should_log
        assert "confidence" in decision.reason

    def test_extreme_price_flag_skipped(self):
        """Long-shot markets: half-spread mark-down would dominate the notional."""
        decision = decide(risk_flags=["EXTREME_PRICE", "NEAR_RESOLUTION"])
        assert not decision.should_log
        assert "extreme price" in decision.reason

    def test_wide_relative_spread_skipped(self):
        # Czechia case: entry 0.002, spread 0.001 → 50% relative spread.
        decision = decide(entry_price=0.002, spread=0.001)
        assert not decision.should_log
        assert "relative spread" in decision.reason

    def test_relative_spread_at_boundary_logs(self):
        # 0.061 / 0.61 = exactly 10% → allowed (cap is exclusive).
        assert decide(entry_price=0.61, spread=0.061).should_log

    def test_missing_entry_price_skipped(self):
        assert not decide(entry_price=None).should_log

    def test_one_sided_book_unknown_spread_still_logs_if_price_ok(self):
        """spread=None means no book context — entry price gate already required a
        usable ask, so we don't double-penalize."""
        assert decide(spread=None).should_log

    def test_other_risk_flags_do_not_block(self):
        decision = decide(risk_flags=["LOW_SMART_SAMPLE", "NEAR_RESOLUTION"])
        assert decision.should_log
