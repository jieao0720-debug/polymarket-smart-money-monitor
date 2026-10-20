"""Settlement, bid-side marking, entry cohort and SHADOW exit observations (A24–A27)."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from functools import partial

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text

from app.core.errors import ConflictError
from app.db.init_db import add_missing_nullable_columns
from app.models import (
    Market,
    MarketSnapshot,
    PaperTrade,
    PaperTradeCohortMember,
    PositionObservation,
    SmartMoneySignal,
)
from app.services.exit_rules import (
    MARKET_AWAITING_RESOLUTION,
    MARKET_OPEN,
    MARKET_RESOLVED,
    TRIGGER_COHORT_EXIT,
    TRIGGER_COHORT_REDUCE,
    TRIGGER_STOP_LOSS,
    HolderRecord,
    MemberExposure,
    ShadowThresholds,
    build_cohort,
    compute_retention,
    evaluate_shadow,
    liquidation_quote,
    resolve_market,
)
from app.services.normalization import normalize_market
from app.services.paper_trade_service import MARK_BASIS_BID, MARK_BASIS_MIDPOINT, pick_mark
from app.tests import fakes
from app.tests.conftest import build_test_app, make_test_settings, run_scan_and_wait

NOW = datetime(2026, 10, 20, 12, 0, 0)


# ----------------------------------------------------------------- settlement

def _market(**kw):
    raw = fakes.make_gamma_market(**{k: v for k, v in kw.items()
                                     if k not in ("uma", "closed_time")})
    if "uma" in kw:
        raw["umaResolutionStatus"] = kw["uma"]
    if "closed_time" in kw:
        raw["closedTime"] = kw["closed_time"]
    return normalize_market(raw)


class TestResolveMarket:
    def test_open_market(self):
        assert resolve_market(_market()).status == MARKET_OPEN

    def test_resolved_yes(self):
        res = resolve_market(_market(closed=True, prices=["1", "0"], uma="resolved"))
        assert res.status == MARKET_RESOLVED
        assert res.payout("YES") == 1.0 and res.payout("NO") == 0.0

    def test_payout_respects_outcome_order(self):
        """Index 0 is never assumed YES: outcomes [No, Yes] with prices [1, 0] → NO wins."""
        res = resolve_market(_market(closed=True, outcomes=["No", "Yes"],
                                     prices=["1", "0"], uma="resolved"))
        assert res.payout("NO") == 1.0 and res.payout("YES") == 0.0

    def test_closed_but_uma_not_final(self):
        res = resolve_market(_market(closed=True, prices=["1", "0"], uma="proposed"))
        assert res.status == MARKET_AWAITING_RESOLUTION

    def test_closed_with_non_payout_prices(self):
        res = resolve_market(_market(closed=True, prices=["0.985", "0.015"]))
        assert res.status == MARKET_AWAITING_RESOLUTION

    def test_split_needs_explicit_uma_status(self):
        assert resolve_market(_market(closed=True, prices=["0.5", "0.5"])).status \
            == MARKET_AWAITING_RESOLUTION
        res = resolve_market(_market(closed=True, prices=["0.5", "0.5"], uma="resolved"))
        assert res.status == MARKET_RESOLVED and res.payout("YES") == 0.5

    def test_past_end_date_is_not_settlement(self):
        market = _market(end_in_hours=-3)
        assert resolve_market(market, fakes.now_utc()).status == MARKET_AWAITING_RESOLUTION

    def test_closed_time_parsed(self):
        market = _market(closed=True, closed_time="2026-10-19 08:30:00+00")
        assert market.closed_time == datetime(2026, 10, 19, 8, 30)


# ----------------------------------------------------------------- valuation

class TestLiquidationQuote:
    def test_walks_ladder_best_first(self):
        q = liquidation_quote([(0.55, 100), (0.59, 50)], 100)
        assert q.fill_ratio == 1.0
        assert q.value == pytest.approx(50 * 0.59 + 50 * 0.55)
        assert q.price == pytest.approx(0.57)

    def test_partial_fill_counts_only_filled(self):
        q = liquidation_quote([(0.5, 40)], 100)
        assert q.fill_ratio == pytest.approx(0.4)
        assert q.value == pytest.approx(20.0)

    def test_fee_and_empty_book(self):
        assert liquidation_quote([(0.5, 100)], 100, fee_bps=100).value == pytest.approx(49.5)
        empty = liquidation_quote([], 100)
        assert empty.price is None and empty.fill_ratio == 0


class TestPickMark:
    def _snap(self, t, **kw):
        return MarketSnapshot(market_id=1, snapshot_time=t, **kw)

    def test_bid_not_midpoint(self):
        snap = self._snap(NOW, yes_price=0.60, no_price=0.40, best_bid=0.59,
                          orderbook_depth={"no": {"best_bid": 0.39}})
        assert pick_mark(direction="YES", snapshot=snap, observation=None).price == 0.59
        mark = pick_mark(direction="NO", snapshot=snap, observation=None)
        assert (mark.price, mark.basis) == (0.39, MARK_BASIS_BID)

    def test_newest_source_wins(self):
        snap = self._snap(NOW, best_bid=0.59)
        obs = PositionObservation(observed_at=NOW + timedelta(minutes=5), best_bid=0.52)
        assert pick_mark(direction="YES", snapshot=snap, observation=obs).price == 0.52

    def test_midpoint_fallback_is_labelled(self):
        snap = self._snap(NOW, yes_price=0.6, no_price=0.4)  # legacy: no NO-side bid
        mark = pick_mark(direction="NO", snapshot=snap, observation=None)
        assert (mark.price, mark.basis) == (0.4, MARK_BASIS_MIDPOINT)


# ----------------------------------------------------------------- cohort & retention

def _h(wallet, direction, shares, value, smart=True):
    return HolderRecord(wallet, direction, shares, value, 80.0, "HIGH_WIN_RATE", smart)


class TestCohort:
    def test_weights_and_net_exposure(self):
        cohort = build_cohort([
            _h("a", "YES", 1000, 600), _h("b", "YES", 500, 300),
            _h("b", "NO", 200, 80, smart=False),  # opposite holding nets against b
            _h("c", "YES", 900, 540, smart=False),  # not smart → excluded
            _h("d", "NO", 800, 300),  # other side → excluded
        ], "YES")
        by_wallet = {c.wallet_address: c for c in cohort}
        assert set(by_wallet) == {"a", "b"}
        assert by_wallet["b"].entry_net_exposure == 300
        assert by_wallet["a"].weight == pytest.approx(600 / 900)
        assert sum(c.weight for c in cohort) == pytest.approx(1.0)

    def test_fully_hedged_account_excluded(self):
        assert build_cohort([_h("a", "YES", 100, 60), _h("a", "NO", 100, 40)], "YES") == []


class TestRetention:
    def test_unknown_excluded_not_zero(self):
        r, cov = compute_retention([MemberExposure(0.6, 1000, 500),
                                    MemberExposure(0.4, 500, None)])
        assert cov == pytest.approx(0.6)
        assert r == pytest.approx(0.5)

    def test_adds_capped_reversal_floored(self):
        r, _ = compute_retention([MemberExposure(0.5, 1000, 3000),  # added: capped at 1
                                  MemberExposure(0.5, 1000, -400)])  # reversed: 0
        assert r == pytest.approx(0.5)

    def test_all_unknown(self):
        assert compute_retention([MemberExposure(1.0, 10, None)]) == (None, 0.0)


class TestShadowEvaluation:
    T = ShadowThresholds(confirmations=2, min_confirm_interval_minutes=0)

    def _eval(self, prev=None, prev_target=None, at=NOW, thresholds=None, **kw):
        args = dict(retention=1.0, coverage=1.0, liquidation_return=0.0,
                    signal_flipped=False)
        args.update(kw)
        return evaluate_shadow(previous_state=prev, previous_target=prev_target,
                               observed_at=at, thresholds=thresholds or self.T, **args)

    def test_min_interval_between_confirmations(self):
        spaced = ShadowThresholds(confirmations=2, min_confirm_interval_minutes=30)
        first = self._eval(retention=0.6, thresholds=spaced)
        soon = self._eval(prev=first.state, retention=0.6, thresholds=spaced,
                          at=NOW + timedelta(minutes=5))
        assert soon.fired == [] and soon.state["streaks"][TRIGGER_COHORT_REDUCE] == 1
        later = self._eval(prev=soon.state, retention=0.6, thresholds=spaced,
                           at=NOW + timedelta(minutes=31))
        assert later.fired == [TRIGGER_COHORT_REDUCE]

    def test_no_new_signal_keeps_flip_streak(self):
        first = self._eval(signal_flipped=True)
        gap = self._eval(prev=first.state, signal_flipped=None)
        assert gap.fired == []
        assert self._eval(prev=gap.state, signal_flipped=True).fired == ["SIGNAL_FLIP"]

    def test_needs_consecutive_confirmation(self):
        first = self._eval(retention=0.6)
        assert first.fired == [] and first.target_fraction == 1.0
        second = self._eval(prev=first.state, retention=0.6)
        assert second.fired == [TRIGGER_COHORT_REDUCE]
        assert second.target_fraction == 0.5

    def test_recovery_resets_streak(self):
        first = self._eval(retention=0.6)
        reset = self._eval(prev=first.state, retention=0.9)
        assert self._eval(prev=reset.state, retention=0.6).fired == []

    def test_unknown_data_keeps_streak(self):
        first = self._eval(retention=0.3)
        gap = self._eval(prev=first.state, retention=None, coverage=0.0)
        assert gap.state["streaks"][TRIGGER_COHORT_EXIT] == 1
        low_cov = self._eval(prev=gap.state, retention=0.3, coverage=0.5)
        assert low_cov.fired == []
        done = self._eval(prev=low_cov.state, retention=0.3)
        assert TRIGGER_COHORT_EXIT in done.fired and done.target_fraction == 0.0

    def test_target_is_sticky(self):
        r = self._eval(prev={"streaks": {TRIGGER_COHORT_REDUCE: 5}}, retention=0.95,
                       prev_target=0.5)
        assert r.target_fraction == 0.5  # cohort re-bought; a reduction is not undone

    def test_stop_loss(self):
        first = self._eval(liquidation_return=-0.3)
        assert TRIGGER_STOP_LOSS in self._eval(prev=first.state,
                                               liquidation_return=-0.3).fired


# ----------------------------------------------------------------- end-to-end

def _run_monitor(client):
    resp = client.post("/api/paper-trades/monitor/run")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _open_trade(client):
    trades = client.get("/api/paper-trades").json()["paper_trades"]
    assert len(trades) == 1
    return trades[0]


def _observations(client, trade_id):
    return client.get(f"/api/paper-trades/{trade_id}/observations").json()


def _two_spaced_passes(client, container):
    entry = datetime.fromisoformat(_open_trade(client)["entry_time"])
    _monitor_at(client, container, entry + timedelta(hours=1))
    _monitor_at(client, container, entry + timedelta(hours=2))


class TestPositionMonitorFlow:
    def test_entry_freezes_cohort_and_marks_at_bid(self, app_bundle):
        client, _, _ = app_bundle
        run_scan_and_wait(client)
        trade = _open_trade(client)
        assert trade["current_price"] == 0.59  # YES best bid, not the 0.60 midpoint
        assert trade["price_basis"] == "BID"
        cohort = _observations(client, trade["paper_trade_id"])["cohort"]
        assert [m["wallet_address"] for m in cohort] == [fakes.ADDR_SMART]
        assert cohort[0]["entry_net_exposure"] == 10000
        assert cohort[0]["weight"] == pytest.approx(1.0)
        assert cohort[0]["source"] == "ENTRY"

    def test_holding_cohort_records_full_retention(self, app_bundle):
        client, _, _ = app_bundle
        run_scan_and_wait(client)
        result = _run_monitor(client)
        assert (result["open_trades"], result["observations"], result["settled"]) == (1, 1, 0)
        trade = _open_trade(client)
        obs = _observations(client, trade["paper_trade_id"])["observations"][0]
        assert obs["market_status"] == "OPEN"
        assert obs["retention"] == 1.0 and obs["coverage"] == 1.0
        assert obs["best_bid"] == 0.59
        assert obs["shadow_target_fraction"] == 1.0
        assert trade["shadow"]["retention"] == 1.0

    def test_cohort_reduction_is_shadow_only(self, app_bundle):
        client, container, dataset = app_bundle
        run_scan_and_wait(client)
        dataset["positions"][(fakes.ADDR_SMART, "0xc1")] = [fakes.make_position(
            fakes.ADDR_SMART, "0xc1", "111", "Yes", size=5000, avg_price=0.55,
            cur_price=0.60)]
        _two_spaced_passes(client, container)
        trade = _open_trade(client)
        assert trade["status"] == "OPEN"  # shadow mode never acts
        obs = _observations(client, trade["paper_trade_id"])["observations"]
        assert obs[1]["shadow_triggers"] is None  # first sighting: not yet confirmed
        assert obs[0]["retention"] == 0.5
        assert obs[0]["shadow_triggers"] == [TRIGGER_COHORT_REDUCE]
        assert obs[0]["shadow_target_fraction"] == 0.5
        assert obs[0]["cohort_detail"][0]["status"] == "REDUCED"
        assert trade["shadow"]["triggers"] == [TRIGGER_COHORT_REDUCE]

    def test_cohort_exit_and_reversal(self, app_bundle):
        client, container, dataset = app_bundle
        run_scan_and_wait(client)
        dataset["positions"][(fakes.ADDR_SMART, "0xc1")] = [fakes.make_position(
            fakes.ADDR_SMART, "0xc1", "222", "No", size=4000, avg_price=0.4,
            cur_price=0.41)]
        _two_spaced_passes(client, container)
        trade = _open_trade(client)
        obs = _observations(client, trade["paper_trade_id"])["observations"][0]
        assert obs["retention"] == 0.0
        assert obs["cohort_detail"][0]["status"] == "REVERSED"
        assert obs["shadow_target_fraction"] == 0.0

    def test_fetch_failure_is_unknown_not_exit(self, app_bundle):
        client, _, dataset = app_bundle
        run_scan_and_wait(client)
        dataset["positions_fail"] = {fakes.ADDR_SMART}
        _run_monitor(client)
        _run_monitor(client)
        trade = _open_trade(client)
        obs = _observations(client, trade["paper_trade_id"])["observations"][0]
        assert obs["retention"] is None and obs["coverage"] == 0.0
        assert obs["cohort_detail"][0]["status"] == "UNKNOWN"
        assert obs["shadow_target_fraction"] == 1.0
        assert any("unknown" in issue for issue in obs["data_issues"])

    def test_flat_account_is_known_exit(self, app_bundle):
        client, _, dataset = app_bundle
        run_scan_and_wait(client)
        dataset["positions"][(fakes.ADDR_SMART, "0xc1")] = []
        _run_monitor(client)
        trade = _open_trade(client)
        obs = _observations(client, trade["paper_trade_id"])["observations"][0]
        assert obs["retention"] == 0.0 and obs["coverage"] == 1.0
        assert obs["cohort_detail"][0]["status"] == "EXITED"

    def test_settles_resolved_market(self, app_bundle):
        client, _, dataset = app_bundle
        run_scan_and_wait(client)
        market = dataset["gamma_markets"][0]
        market.update(closed=True, active=False, outcomePrices=json.dumps(["1", "0"]),
                      umaResolutionStatus="resolved", closedTime="2026-10-19 08:30:00+00")
        result = _run_monitor(client)
        assert result["settled"] == 1
        trade = _open_trade(client)
        assert trade["status"] == "CLOSED"
        assert trade["exit_reason"] == "RESOLVED"
        assert trade["exit_price"] == 1.0
        assert trade["exit_time"].startswith("2026-10-19T08:30")
        assert trade["pnl"] == pytest.approx(trade["shares"] * (1.0 - 0.61), abs=1e-3)
        assert _run_monitor(client)["open_trades"] == 0  # settled once, never again

    def test_settles_losing_side_at_zero(self, app_bundle):
        client, _, dataset = app_bundle
        run_scan_and_wait(client)
        dataset["gamma_markets"][0].update(
            closed=True, outcomePrices=json.dumps(["0", "1"]),
            umaResolutionStatus="resolved")
        _run_monitor(client)
        trade = _open_trade(client)
        assert trade["exit_price"] == 0.0
        assert trade["pnl"] == pytest.approx(-trade["notional"], abs=1e-3)

    def test_closed_unresolved_market_stays_open(self, app_bundle):
        client, _, dataset = app_bundle
        run_scan_and_wait(client)
        dataset["gamma_markets"][0].update(closed=True,
                                          outcomePrices=json.dumps(["0.99", "0.01"]))
        assert _run_monitor(client)["settled"] == 0
        trade = _open_trade(client)
        assert trade["status"] == "OPEN"
        obs = _observations(client, trade["paper_trade_id"])["observations"][0]
        assert obs["market_status"] == "AWAITING_RESOLUTION"

    def test_backfills_cohort_for_existing_trades(self, app_bundle):
        client, container, _ = app_bundle
        run_scan_and_wait(client)

        async def wipe() -> None:
            async with container.session_factory() as session:
                await session.execute(PaperTradeCohortMember.__table__.delete())
                await session.commit()

        client.portal.call(wipe)
        result = _run_monitor(client)
        assert result["cohorts_backfilled"] == 1
        trade = _open_trade(client)
        cohort = _observations(client, trade["paper_trade_id"])["cohort"]
        assert cohort[0]["source"] == "BACKFILL"

    def test_manual_trade_without_signal_has_no_cohort(self, app_bundle):
        client, _, _ = app_bundle
        run_scan_and_wait(client)
        manual = client.post("/api/paper-trades", json={
            "market_id": "1001", "direction": "NO", "notional": 50}).json()
        assert manual["entry_price"] == 0.41  # default entry = NO best ask
        _run_monitor(client)
        obs = _observations(client, manual["paper_trade_id"])["observations"][0]
        assert obs["retention"] is None and obs["coverage"] is None
        assert obs["best_bid"] == 0.39

    def test_manual_close_defaults_to_bid(self, app_bundle):
        client, _, _ = app_bundle
        run_scan_and_wait(client)
        trade = _open_trade(client)
        closed = client.post(f"/api/paper-trades/{trade['paper_trade_id']}/close",
                             json={}).json()
        assert closed["exit_price"] == 0.59
        assert closed["exit_reason"] == "MANUAL"


# ----------------------------------------------------------------- migration

def test_add_missing_nullable_columns_on_legacy_table():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE paper_trades (id INTEGER PRIMARY KEY, trade_uid VARCHAR(32), "
            "market_id INTEGER, direction VARCHAR(8), entry_price FLOAT, "
            "entry_time DATETIME, notional FLOAT, shares FLOAT, status VARCHAR(16), "
            "source VARCHAR(16))"))
        added = add_missing_nullable_columns(conn)
        assert "paper_trades.exit_reason" in added
        cols = {c["name"] for c in inspect(conn).get_columns("paper_trades")}
        assert "exit_reason" in cols
        assert add_missing_nullable_columns(conn) == []  # idempotent


# ----------------------------------------------------------------- regressions (review 96aa677)

def _monitor_at(client, container, when):
    return client.portal.call(partial(container.position_monitor.run_once, now=when))


def _add_signal(client, container, direction, at):
    async def add() -> None:
        async with container.session_factory() as session:
            market = (await session.execute(select(Market))).scalars().first()
            session.add(SmartMoneySignal(
                market_id=market.id, snapshot_time=at, direction=direction,
                confidence_score=70.0, yes_smart_money_notional=0.0,
                no_smart_money_notional=5000.0))
            await session.commit()

    client.portal.call(add)


class TestReviewRegressions:
    def test_wallet_on_both_sides_still_logs_trade_with_one_member(self, app_bundle):
        """P1: a wallet in both YES and NO top-20 produced duplicate cohort rows →
        IntegrityError → the auto paper trade was rolled back."""
        client, _, dataset = app_bundle
        dataset["holders"]["0xc1"][1]["holders"].append(
            {"proxyWallet": fakes.ADDR_SMART, "amount": 2000, "outcomeIndex": 1,
             "name": "smartwhale", "pseudonym": "Wise-Owl", "displayUsernamePublic": True})
        dataset["positions"][(fakes.ADDR_SMART, "0xc1")] = [
            fakes.make_position(fakes.ADDR_SMART, "0xc1", "111", "Yes", size=10000,
                                avg_price=0.55, cur_price=0.60),
            fakes.make_position(fakes.ADDR_SMART, "0xc1", "222", "No", size=2000,
                                avg_price=0.40, cur_price=0.41)]
        status = run_scan_and_wait(client)
        assert status["errors"] == []
        trade = _open_trade(client)
        cohort = _observations(client, trade["paper_trade_id"])["cohort"]
        assert len(cohort) == 1
        assert cohort[0]["entry_shares"] == 10000
        assert cohort[0]["entry_opposite_shares"] == 2000
        assert cohort[0]["entry_net_exposure"] == 8000

    def test_unranked_opposite_holding_is_in_entry_baseline(self, app_bundle):
        """P2: NO 7000 outside the NO top-20 was taken as 0 at entry but counted by the
        monitor → an untouched account showed R = 30%."""
        client, _, dataset = app_bundle
        dataset["positions"][(fakes.ADDR_SMART, "0xc1")] = [
            fakes.make_position(fakes.ADDR_SMART, "0xc1", "111", "Yes", size=10000,
                                avg_price=0.55, cur_price=0.60),
            fakes.make_position(fakes.ADDR_SMART, "0xc1", "222", "No", size=7000,
                                avg_price=0.40, cur_price=0.41)]
        run_scan_and_wait(client)
        trade = _open_trade(client)
        cohort = _observations(client, trade["paper_trade_id"])["cohort"]
        assert cohort[0]["entry_net_exposure"] == 3000
        assert cohort[0]["baseline_verified"] is True
        _run_monitor(client)
        obs = _observations(client, trade["paper_trade_id"])["observations"][0]
        assert obs["retention"] == 1.0

    def test_unverifiable_baseline_is_unknown_not_exit(self, app_bundle):
        """If the entry position lookup failed, the baseline cannot be verified: the member
        is excluded from R (lower coverage) instead of producing a fake retention."""
        client, _, dataset = app_bundle
        dataset["positions_fail"] = {fakes.ADDR_SMART}
        run_scan_and_wait(client)
        dataset["positions_fail"] = set()
        trade = _open_trade(client)
        cohort = _observations(client, trade["paper_trade_id"])["cohort"]
        assert cohort[0]["baseline_verified"] is False
        _run_monitor(client)
        obs = _observations(client, trade["paper_trade_id"])["observations"][0]
        assert obs["retention"] is None and obs["coverage"] == 0.0
        assert obs["cohort_detail"][0]["status"] == "UNVERIFIED_BASELINE"

    def test_same_stale_flip_signal_is_not_confirmed_twice(self, app_bundle):
        """P2: one 3-day-old reversal signal was counted again on every pass."""
        client, container, _ = app_bundle
        run_scan_and_wait(client)
        entry = datetime.fromisoformat(_open_trade(client)["entry_time"])
        _add_signal(client, container, "NO", entry + timedelta(minutes=1))
        later = entry + timedelta(days=3)
        _monitor_at(client, container, later)
        _monitor_at(client, container, later + timedelta(hours=1))
        trade = _open_trade(client)
        obs = _observations(client, trade["paper_trade_id"])["observations"][0]
        assert obs["shadow_target_fraction"] == 1.0
        assert "SIGNAL_FLIP" not in (obs["shadow_state"]["fired_at"])

    def test_two_distinct_fresh_flip_signals_confirm(self, app_bundle):
        client, container, _ = app_bundle
        run_scan_and_wait(client)
        entry = datetime.fromisoformat(_open_trade(client)["entry_time"])
        t1 = entry + timedelta(hours=1)
        _add_signal(client, container, "NO", t1)
        _monitor_at(client, container, t1 + timedelta(minutes=5))
        _monitor_at(client, container, t1 + timedelta(minutes=50))  # no new signal
        t2 = entry + timedelta(hours=2)
        _add_signal(client, container, "NO", t2)
        _monitor_at(client, container, t2 + timedelta(minutes=5))
        trade = _open_trade(client)
        obs = _observations(client, trade["paper_trade_id"])["observations"]
        assert obs[1]["shadow_triggers"] is None
        assert obs[0]["shadow_triggers"] == ["SIGNAL_FLIP"]
        assert obs[0]["shadow_target_fraction"] == 0.0

    def test_back_to_back_passes_do_not_confirm(self, app_bundle):
        """Two passes seconds apart are one observation, not two confirmations."""
        client, container, dataset = app_bundle
        run_scan_and_wait(client)
        dataset["positions"][(fakes.ADDR_SMART, "0xc1")] = []
        entry = datetime.fromisoformat(_open_trade(client)["entry_time"])
        t = entry + timedelta(hours=1)
        _monitor_at(client, container, t)
        _monitor_at(client, container, t + timedelta(seconds=30))
        obs = _observations(client, _open_trade(client)["paper_trade_id"])["observations"]
        assert obs[0]["shadow_triggers"] is None
        _monitor_at(client, container, t + timedelta(minutes=45))
        obs = _observations(client, _open_trade(client)["paper_trade_id"])["observations"]
        assert "COHORT_EXIT" in obs[0]["shadow_triggers"]

    def test_manual_close_fills_only_book_depth(self, app_bundle):
        """P2: a 1-share bid closed a ~163.9-share position in full at the best bid."""
        client, _, dataset = app_bundle
        run_scan_and_wait(client)
        trade = _open_trade(client)
        dataset["books"]["111"] = {"bids": [{"price": "0.58", "size": "1"}],
                                   "asks": [{"price": "0.61", "size": "800"}]}
        closed = client.post(f"/api/paper-trades/{trade['paper_trade_id']}/close",
                             json={}).json()
        assert closed["status"] == "OPEN"
        assert closed["remaining_shares"] == pytest.approx(trade["shares"] - 1, abs=1e-6)
        assert closed["pnl"] == pytest.approx(1 * (0.58 - 0.61), abs=1e-6)
        exits = _observations(client, trade["paper_trade_id"])["exits"]
        assert len(exits) == 1 and exits[0]["shares"] == 1 and exits[0]["price"] == 0.58

    def test_manual_close_refuses_without_bids(self, app_bundle):
        client, _, dataset = app_bundle
        run_scan_and_wait(client)
        trade = _open_trade(client)
        dataset["books"]["111"] = {"bids": [], "asks": [{"price": "0.61", "size": "800"}]}
        resp = client.post(f"/api/paper-trades/{trade['paper_trade_id']}/close", json={})
        assert resp.status_code == 422
        assert _open_trade(client)["status"] == "OPEN"

    def test_manual_close_applies_fee_and_walks_ladder(self, app_bundle):
        client, container, dataset = app_bundle
        container.settings.paper_exit_fee_bps = 100
        run_scan_and_wait(client)
        trade = _open_trade(client)
        shares = trade["shares"]
        dataset["books"]["111"] = {"bids": [{"price": "0.59", "size": "100"},
                                            {"price": "0.50", "size": "1000"}],
                                   "asks": [{"price": "0.61", "size": "800"}]}
        closed = client.post(f"/api/paper-trades/{trade['paper_trade_id']}/close",
                             json={}).json()
        gross = 100 * 0.59 + (shares - 100) * 0.50
        assert closed["status"] == "CLOSED"
        assert closed["exit_price"] == pytest.approx(gross * 0.99 / shares, abs=1e-6)
        assert closed["pnl"] == pytest.approx(gross * 0.99 - trade["notional"], abs=1e-3)

    def test_partial_exit_then_settlement_accounts_both_fills(self, app_bundle):
        client, _, dataset = app_bundle
        run_scan_and_wait(client)
        trade = _open_trade(client)
        dataset["books"]["111"] = {"bids": [{"price": "0.58", "size": "10"}],
                                   "asks": [{"price": "0.61", "size": "800"}]}
        client.post(f"/api/paper-trades/{trade['paper_trade_id']}/close", json={})
        summary = client.get("/api/paper-trades").json()["summary"]
        assert summary["total_realized_pnl"] == pytest.approx(10 * (0.58 - 0.61), abs=0.01)
        dataset["gamma_markets"][0].update(closed=True, outcomePrices=json.dumps(["1", "0"]),
                                          umaResolutionStatus="resolved")
        _run_monitor(client)
        closed = _open_trade(client)
        rest = trade["shares"] - 10
        assert closed["status"] == "CLOSED" and closed["exit_reason"] == "RESOLVED"
        assert closed["pnl"] == pytest.approx(10 * (0.58 - 0.61) + rest * (1 - 0.61),
                                              abs=1e-3)
        assert closed["exit_price"] == pytest.approx((10 * 0.58 + rest) / trade["shares"],
                                                     abs=1e-6)
        exits = _observations(client, trade["paper_trade_id"])["exits"]
        assert [x["reason"] for x in exits] == ["MANUAL", "RESOLVED"]


# ----------------------------------------------------------------- regressions (review 9c6fbce)

@pytest.fixture
def file_db_bundle(tmp_path):
    app, container, dataset = build_test_app(
        make_test_settings(), database_url=f"sqlite+aiosqlite:///{tmp_path / 'race.db'}")
    with TestClient(app) as client:
        yield client, container, dataset


def _ledger(client, trade_id):
    """(trade row as listed, Σ exit shares, Σ exit pnl)."""
    trade = next(t for t in client.get("/api/paper-trades").json()["paper_trades"]
                 if t["paper_trade_id"] == trade_id)
    exits = _observations(client, trade_id)["exits"]
    return trade, sum(x["shares"] for x in exits), sum(x["pnl"] for x in exits)


class TestConcurrentExits:
    def test_two_simultaneous_closes_never_oversell(self, file_db_bundle):
        client, container, _ = file_db_bundle
        run_scan_and_wait(client)
        opened = _open_trade(client)
        url = f"/api/paper-trades/{opened['paper_trade_id']}/close"
        real_get_book = container.clob.get_book

        async def race():
            both_in = asyncio.Event()
            arrived = 0

            async def gated_get_book(token_id):
                # Both requests have read the OPEN trade before either may proceed.
                nonlocal arrived
                arrived += 1
                if arrived == 2:
                    both_in.set()
                await asyncio.wait_for(both_in.wait(), 5)
                return await real_get_book(token_id)

            container.clob.get_book = gated_get_book
            try:
                transport = httpx.ASGITransport(app=client.app)
                async with httpx.AsyncClient(transport=transport,
                                             base_url="http://test") as ac:
                    return await asyncio.gather(ac.post(url, json={}),
                                                ac.post(url, json={}))
            finally:
                del container.clob.get_book

        responses = client.portal.call(race)
        codes = sorted(r.status_code for r in responses)
        assert codes[0] == 200 and codes[1] in (409, 422), [r.text for r in responses]
        trade, exited, fill_pnl = _ledger(client, opened["paper_trade_id"])
        assert trade["status"] == "CLOSED"
        assert exited == pytest.approx(opened["shares"])
        assert fill_pnl == pytest.approx(trade["pnl"], abs=1e-3)

    def test_stale_exit_is_refused_not_booked_twice(self, file_db_bundle):
        client, container, _ = file_db_bundle
        run_scan_and_wait(client)
        opened = _open_trade(client)
        svc = container.paper_trades

        async def race() -> None:
            factory = container.session_factory
            async with factory() as s1, factory() as s2:
                t1 = (await s1.execute(select(PaperTrade))).scalar_one()
                t2 = (await s2.execute(select(PaperTrade))).scalar_one()  # same snapshot
                await svc.record_exit(s1, t1, shares=t1.open_shares, price=0.5,
                                      at=fakes.now_utc(), reason="MANUAL")
                await s1.commit()
                with pytest.raises(ConflictError):
                    await svc.record_exit(s2, t2, shares=t2.open_shares, price=0.5,
                                          at=fakes.now_utc(), reason="MANUAL")
                await s2.rollback()

        client.portal.call(race)
        trade, exited, fill_pnl = _ledger(client, opened["paper_trade_id"])
        assert trade["status"] == "CLOSED"
        assert exited == pytest.approx(opened["shares"])
        assert fill_pnl == pytest.approx(trade["pnl"], abs=1e-3)

    def test_settlement_after_concurrent_partial_close_books_only_the_rest(
            self, file_db_bundle):
        client, container, _ = file_db_bundle
        run_scan_and_wait(client)
        opened = _open_trade(client)
        svc = container.paper_trades
        half = opened["shares"] / 2

        async def race() -> None:
            factory = container.session_factory
            async with factory() as monitor, factory() as manual:
                stale = (await monitor.execute(select(PaperTrade))).scalar_one()
                t = (await manual.execute(select(PaperTrade))).scalar_one()
                await svc.record_exit(manual, t, shares=half, price=0.5,
                                      at=fakes.now_utc(), reason="MANUAL")
                await manual.commit()
                # The monitor still holds the pre-close copy; settle must re-read it.
                await svc.settle(monitor, stale, 1.0, fakes.now_utc())
                await monitor.commit()

        client.portal.call(race)
        trade, exited, fill_pnl = _ledger(client, opened["paper_trade_id"])
        assert trade["status"] == "CLOSED" and trade["exit_reason"] == "RESOLVED"
        assert exited == pytest.approx(opened["shares"])
        assert fill_pnl == pytest.approx(trade["pnl"], abs=1e-3)


# ----------------------------------------------------------------- regressions (review 38c4e26)

class TestSettlementObservations:
    @pytest.mark.parametrize("payout", [0.0, 0.5, 1.0])
    @pytest.mark.parametrize("fee_bps", [0, 100])
    @pytest.mark.parametrize("close_all", [False, True])
    def test_monitor_uses_actual_settlement_after_manual_close(
            self, file_db_bundle, monkeypatch, payout, fee_bps, close_all):
        client, container, dataset = file_db_bundle
        run_scan_and_wait(client)
        opened = _open_trade(client)
        trade_id = opened["paper_trade_id"]
        container.settings.paper_exit_fee_bps = fee_bps
        dataset["gamma_markets"][0].update(
            closed=True, outcomePrices=json.dumps([str(payout), str(1 - payout)]),
            umaResolutionStatus="resolved")
        dataset["books"]["111"] = {
            "bids": [{"price": "0.5", "size": "1000" if close_all else "10"}],
            "asks": []}
        real_settle = container.paper_trades.settle

        async def race():
            entered = asyncio.Event()
            release = asyncio.Event()

            async def gated_settle(*args, **kwargs):
                # The monitor has loaded the old position; the manual exit commits
                # before settle can refresh it. This exercises the full HTTP flow.
                entered.set()
                await asyncio.wait_for(release.wait(), 5)
                return await real_settle(*args, **kwargs)

            monkeypatch.setattr(container.paper_trades, "settle", gated_settle)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app),
                                         base_url="http://test") as ac:
                monitor = asyncio.create_task(ac.post("/api/paper-trades/monitor/run"))
                try:
                    await asyncio.wait_for(entered.wait(), 5)
                    manual = await ac.post(f"/api/paper-trades/{trade_id}/close", json={})
                finally:
                    release.set()
                    monitored = await asyncio.wait_for(monitor, 5)
            assert manual.status_code == 200, manual.text
            assert monitored.status_code == 200, monitored.text
            return monitored.json()

        result = client.portal.call(race)
        assert result["errors"] == []
        expected_count = 0 if close_all else 1
        assert result["settled"] == result["observations"] == expected_count
        trade, exited, fill_pnl = _ledger(client, trade_id)
        details = _observations(client, trade_id)
        assert trade["status"] == "CLOSED"
        assert exited == pytest.approx(opened["shares"])
        assert fill_pnl == pytest.approx(trade["pnl"], abs=1e-3)
        if close_all:
            assert trade["exit_reason"] == "MANUAL"
            assert [x["reason"] for x in details["exits"]] == ["MANUAL"]
            assert details["observations"] == []
        else:
            assert sorted(x["reason"] for x in details["exits"]) == ["MANUAL", "RESOLVED"]
            settlement = next(x for x in details["exits"] if x["reason"] == "RESOLVED")
            obs = details["observations"][0]
            assert settlement["shares"] == pytest.approx(opened["shares"] - 10)
            assert obs["market_status"] == "RESOLVED"
            assert obs["liquidation_price"] == payout
            assert obs["liquidation_value"] == pytest.approx(settlement["proceeds"], abs=1e-4)
            proceeds = sum(x["proceeds"] for x in details["exits"])
            assert obs["liquidation_return"] == pytest.approx(
                proceeds / opened["notional"] - 1, abs=1e-6)
        # A later pass does not manufacture another settlement or observation.
        repeated = _run_monitor(client)
        assert repeated["settled"] == repeated["observations"] == 0
        assert _observations(client, trade_id) == details

    @pytest.mark.parametrize("resolved", [False, True])
    def test_failed_market_rolls_back_counts_and_continues(
            self, file_db_bundle, monkeypatch, resolved):
        client, container, dataset = file_db_bundle
        run_scan_and_wait(client)
        opened = _open_trade(client)
        dataset["gamma_markets"].append(fakes.make_gamma_market(
            gamma_id="1002", condition_id="0xc2", token_ids=["333", "444"]))
        dataset["books"]["333"] = fakes.make_book(0.49, 0.51)
        if resolved:
            for market in dataset["gamma_markets"]:
                market.update(closed=True, outcomePrices=json.dumps(["1", "0"]),
                              umaResolutionStatus="resolved")

        async def seed_second_market():
            async with container.session_factory() as session:
                market = Market(polymarket_market_id="1002", condition_id="0xc2",
                                question="Second market", yes_token_id="333", no_token_id="444")
                session.add(market)
                await session.flush()
                trade = await container.paper_trades.create_manual(
                    session, market_row=market, direction="YES", notional=50,
                    entry_price=0.5, signal_id=None)
                await session.commit()
                return trade.trade_uid

        second_id = client.portal.call(seed_second_market)
        real_process = container.position_monitor._process_market

        async def fail_after_writes(session, market, trades, now, result):
            await real_process(session, market, trades, now, result)
            if market.polymarket_market_id == "1001":
                raise ConflictError("forced concurrent exit after pending monitor writes")

        with monkeypatch.context() as patch:
            patch.setattr(container.position_monitor, "_process_market", fail_after_writes)
            result = _run_monitor(client)
        assert result["open_trades"] == 2
        assert result["errors"] == ["1001: ConflictError"]
        assert result["observations"] == 1
        assert result["settled"] == int(resolved)
        assert _ledger(client, opened["paper_trade_id"])[0]["status"] == "OPEN"
        assert _observations(client, opened["paper_trade_id"])["exits"] == []
        assert _observations(client, opened["paper_trade_id"])["observations"] == []
        second = _observations(client, second_id)
        assert len(second["observations"]) == 1
        assert len(second["exits"]) == int(resolved)
        # The market whose transaction rolled back remains eligible for another pass.
        assert _run_monitor(client)["errors"] == []
