"""Account classification rules (spec test areas 1–5)."""
from __future__ import annotations

import pytest

from app.services.account_profile_service import compute_anomaly_index
from app.services.smart_money_service import (
    LABEL_ABNORMAL_POSITION,
    LABEL_HIGH_WIN_RATE,
    LABEL_NEW_ACCOUNT,
    LABEL_OTHER,
    classify_account,
)

MIN_POSITION_VALUE = 100.0


def classify(**kwargs):
    defaults = dict(resolved_trade_count=0, win_rate=0.0, realized_pnl=0.0,
                    anomaly_index=None, current_position_value=0.0,
                    min_position_value=MIN_POSITION_VALUE)
    defaults.update(kwargs)
    return classify_account(**defaults)


class TestNewAccount:
    def test_zero_resolved_trades(self):
        assert classify(resolved_trade_count=0).label == LABEL_NEW_ACCOUNT

    def test_new_account_takes_precedence_over_everything(self):
        result = classify(resolved_trade_count=0, anomaly_index=100.0,
                          current_position_value=1_000_000.0)
        assert result.label == LABEL_NEW_ACCOUNT

    def test_one_trade_is_not_new(self):
        assert classify(resolved_trade_count=1).label != LABEL_NEW_ACCOUNT


class TestHighWinRate:
    def test_qualifies_at_thresholds(self):
        result = classify(resolved_trade_count=20, win_rate=0.60, realized_pnl=0.01)
        assert result.label == LABEL_HIGH_WIN_RATE

    def test_fails_below_trade_count(self):
        assert classify(resolved_trade_count=19, win_rate=0.9,
                        realized_pnl=1000).label == LABEL_OTHER

    def test_fails_below_win_rate(self):
        assert classify(resolved_trade_count=50, win_rate=0.59,
                        realized_pnl=1000).label == LABEL_OTHER

    def test_fails_with_nonpositive_pnl(self):
        """High win rate but net loser must NOT be labeled smart (data口径 guard)."""
        assert classify(resolved_trade_count=50, win_rate=0.9,
                        realized_pnl=0.0).label == LABEL_OTHER
        assert classify(resolved_trade_count=50, win_rate=0.9,
                        realized_pnl=-10.0).label == LABEL_OTHER


class TestAbnormalPosition:
    def test_qualifies_at_thresholds(self):
        result = classify(resolved_trade_count=10, win_rate=0.3, realized_pnl=-5,
                          anomaly_index=5.0, current_position_value=100.0)
        assert result.label == LABEL_ABNORMAL_POSITION

    def test_fails_below_anomaly_index(self):
        assert classify(resolved_trade_count=10, anomaly_index=4.99,
                        current_position_value=500.0).label == LABEL_OTHER

    def test_fails_below_position_value(self):
        assert classify(resolved_trade_count=10, anomaly_index=10.0,
                        current_position_value=99.0).label == LABEL_OTHER

    def test_fails_below_trade_count(self):
        assert classify(resolved_trade_count=9, anomaly_index=10.0,
                        current_position_value=500.0).label == LABEL_OTHER

    def test_unknown_anomaly_index_never_abnormal(self):
        assert classify(resolved_trade_count=50, anomaly_index=None,
                        current_position_value=10_000.0).label == LABEL_OTHER


class TestPrecedence:
    def test_high_win_rate_over_abnormal(self):
        """ASSUMPTION-A7: both qualify → HIGH_WIN_RATE, reason mentions sizing."""
        result = classify(resolved_trade_count=30, win_rate=0.7, realized_pnl=500,
                          anomaly_index=8.0, current_position_value=5000.0)
        assert result.label == LABEL_HIGH_WIN_RATE
        assert "abnormal sizing" in result.reason.lower()


class TestAnomalyIndex:
    def test_basic_ratio(self):
        assert compute_anomaly_index(500.0, 100.0) == pytest.approx(5.0)

    def test_none_when_entry_unknown(self):
        assert compute_anomaly_index(None, 100.0) is None
        assert compute_anomaly_index(0.0, 100.0) is None

    def test_none_when_no_history_median(self):
        assert compute_anomaly_index(500.0, 0.0) is None
