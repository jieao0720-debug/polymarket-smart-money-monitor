"""End-to-end API tests with fake Polymarket clients: scanner → analysis → signals →
paper trades → trade tickets → live-trading gate (spec test areas 8, 10–15)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.tests import fakes
from app.tests.conftest import build_test_app, make_test_settings, run_scan_and_wait


class TestHealthAndSettings:
    def test_health(self, client):
        data = client.get("/api/health").json()
        assert data["status"] == "ok"
        assert data["database"] == "ok"
        assert data["live_trading_enabled"] is False  # default-off (area 12)

    def test_public_settings_defaults_safe(self, client):
        data = client.get("/api/settings/public").json()
        assert data["enable_live_trading"] is False
        assert data["max_trade_notional"] == 100.0
        assert "SG" in data["close_only_countries"]

    def test_error_envelope_shape(self, client):
        resp = client.get("/api/scanner/status/nonexistent")
        assert resp.status_code == 404
        body = resp.json()
        assert set(body["error"].keys()) == {"code", "message", "details"}
        assert body["error"]["code"] == "NOT_FOUND"


class TestScannerAndAnalysis:
    def test_full_scan_pipeline(self, app_bundle):
        client, container, dataset = app_bundle
        status = run_scan_and_wait(client)
        assert status["status"] == "completed", status
        assert status["markets_found"] == 1
        assert status["markets_analyzed"] == 1
        assert status["signals_generated"] == 1

        # /hot
        hot = client.get("/api/markets/hot").json()
        assert len(hot["markets"]) == 1
        market = hot["markets"][0]
        assert market["market_id"] == "1001"
        assert market["smart_money_direction"] == "YES"
        assert market["yes_price"] is not None and 0 < market["yes_price"] < 1
        assert market["confidence_score"] > 0

        # /analysis
        analysis = client.get("/api/markets/1001/analysis").json()
        summary = analysis["summary"]
        assert summary["net_direction"] == "YES"
        assert summary["yes_smart_money_count"] == 1
        assert summary["no_smart_money_count"] == 0
        assert summary["yes_smart_money_notional"] > summary["no_smart_money_notional"]
        assert summary["suggested_limit_price"] is not None
        assert 0 < summary["suggested_limit_price"] < 1
        assert summary["suggested_max_notional"] is not None
        assert summary["suggested_max_notional"] <= 100.0  # MAX_TRADE_NOTIONAL cap

        holders = analysis["holders"]
        assert len(holders) == 3
        by_addr = {h["address"]: h for h in holders}
        smart = by_addr[fakes.ADDR_SMART]
        assert smart["label"] == "HIGH_WIN_RATE"
        assert smart["direction"] == "YES"
        assert smart["rank"] == 1
        assert smart["smart_money_score"] >= 60
        assert smart["resolved_trade_count"] == 25
        assert abs(smart["win_rate"] - 18 / 25) < 1e-6
        # shares vs USD value must differ (semantics guard, area: data口径)
        assert smart["shares"] == 10000
        assert abs(smart["current_position_value"] - 6000.0) < 1.0
        assert smart["average_price"] == 0.55

        new = by_addr[fakes.ADDR_NEW]
        assert new["label"] == "NEW_ACCOUNT"
        assert new["resolved_trade_count"] == 0

        abnormal = by_addr[fakes.ADDR_ABNORMAL]
        assert abnormal["label"] == "ABNORMAL_POSITION"
        assert abnormal["direction"] == "NO"
        assert abnormal["anomaly_index"] is not None and abnormal["anomaly_index"] >= 5

    def test_scan_conflict_409(self, app_bundle):
        client, container, dataset = app_bundle
        first = client.post("/api/scanner/run", json={})
        assert first.status_code == 200
        # Immediately try again — may conflict or the first may have finished already.
        second = client.post("/api/scanner/run", json={})
        assert second.status_code in (200, 409)
        if second.status_code == 409:
            assert second.json()["error"]["code"] == "SCAN_ALREADY_RUNNING"

    def test_signals_endpoint(self, app_bundle):
        client, _, _ = app_bundle
        run_scan_and_wait(client)
        data = client.get("/api/signals").json()
        assert data["total"] >= 1
        signal = data["signals"][0]
        assert signal["direction"] == "YES"
        assert signal["market_id"] == "1001"
        assert isinstance(signal["risk_flags"], list)

    def test_account_profile(self, app_bundle):
        client, _, _ = app_bundle
        run_scan_and_wait(client)
        resp = client.get(f"/api/accounts/{fakes.ADDR_SMART}/profile",
                          params={"market_id": "1001"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall"]["resolved_trade_count"] == 25
        assert data["overall"]["median_entry_notional"] > 0
        assert data["same_category"]["category"] == "politics"
        assert data["same_category"]["trade_count"] == 25
        assert data["current_market"]["direction"] == "YES"
        assert data["current_market"]["label"] == "HIGH_WIN_RATE"

    def test_account_profile_invalid_address(self, client):
        resp = client.get("/api/accounts/not-an-address/profile")
        assert resp.status_code == 422


class TestPaperTrades:
    def test_auto_logged_from_signal(self, app_bundle):
        client, _, _ = app_bundle
        run_scan_and_wait(client)
        data = client.get("/api/paper-trades").json()
        assert data["total"] == 1
        trade = data["paper_trades"][0]
        assert trade["source"] == "AUTO_SIGNAL"
        assert trade["direction"] == "YES"
        assert trade["entry_price"] == 0.61  # best ask of YES book (ASSUMPTION-A9)
        assert abs(trade["shares"] - trade["notional"] / trade["entry_price"]) < 1e-4
        assert trade["status"] == "OPEN"
        assert trade["unrealized_pnl"] is not None

    def test_rescan_does_not_stack_duplicate_auto_trades(self, app_bundle):
        """A9b dedupe: a second scan emits a fresh signal for the same market+direction
        but must not open a second auto paper position."""
        client, _, _ = app_bundle
        run_scan_and_wait(client)
        run_scan_and_wait(client)
        data = client.get("/api/paper-trades").json()
        assert data["summary"]["open_count"] == 1
        auto = [t for t in data["paper_trades"] if t["source"] == "AUTO_SIGNAL"]
        assert len(auto) == 1
        # ...and signals were still recorded for both scans
        assert client.get("/api/signals").json()["total"] >= 2

    def test_manual_create_and_close_pnl(self, app_bundle):
        client, _, _ = app_bundle
        run_scan_and_wait(client)
        created = client.post("/api/paper-trades", json={
            "market_id": "1001", "direction": "NO", "notional": 50,
            "entry_price": 0.40}).json()
        assert created["shares"] == 125.0
        closed = client.post(f"/api/paper-trades/{created['paper_trade_id']}/close",
                             json={"exit_price": 0.50}).json()
        assert closed["status"] == "CLOSED"
        assert abs(closed["pnl"] - 125.0 * 0.10) < 1e-6
        summary = client.get("/api/paper-trades").json()["summary"]
        assert summary["closed_count"] == 1
        assert summary["win_count"] == 1

    def test_invalid_entry_price_rejected(self, app_bundle):
        client, _, _ = app_bundle
        run_scan_and_wait(client)
        resp = client.post("/api/paper-trades", json={
            "market_id": "1001", "direction": "YES", "notional": 50, "entry_price": 1.5})
        assert resp.status_code == 422


class TestTradeTicketsAndLiveGate:
    def make_ticket(self, client, **overrides):
        body = {"market_id": "1001", "direction": "YES", "limit_price": 0.61,
                "max_notional": 50.0}
        body.update(overrides)
        return client.post("/api/trade-tickets", json=body)

    def test_create_confirm_flow(self, app_bundle):
        client, _, _ = app_bundle
        resp = self.make_ticket(client)
        assert resp.status_code == 201, resp.text
        ticket = resp.json()
        assert ticket["status"] == "PENDING_USER_CONFIRMATION"
        checks = ticket["risk_checks"]
        assert checks["geoblock_ok"] is True
        assert checks["market_active"] is True
        assert checks["spread_ok"] is True
        assert checks["liquidity_ok"] is True
        assert checks["price_ok"] is True
        assert checks["notional_ok"] is True
        assert checks["live_trading_enabled"] is False
        assert checks["all_passed"] is True

        # confirm requires explicit manual confirmation
        bad = client.post(f"/api/trade-tickets/{ticket['ticket_id']}/confirm", json={
            "wallet_address": fakes.ADDR_SMART, "manual_confirmation": False})
        assert bad.status_code == 422

        ok = client.post(f"/api/trade-tickets/{ticket['ticket_id']}/confirm", json={
            "wallet_address": fakes.ADDR_SMART, "manual_confirmation": True})
        assert ok.status_code == 200
        assert ok.json()["status"] == "CONFIRMED"
        assert ok.json()["confirmed_at"] is not None

    def test_notional_over_cap_rejected(self, app_bundle):
        client, _, _ = app_bundle
        resp = self.make_ticket(client, max_notional=101.0)
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "RISK_CHECK_FAILED"

    def test_live_trading_disabled_blocks_submit(self, app_bundle):
        """Default-deny: ENABLE_LIVE_TRADING=false must reject submission (area 12)."""
        client, container, _ = app_bundle
        ticket = self.make_ticket(client).json()
        client.post(f"/api/trade-tickets/{ticket['ticket_id']}/confirm", json={
            "wallet_address": fakes.ADDR_SMART, "manual_confirmation": True})
        order = {"salt": "1", "maker": fakes.ADDR_SMART, "signer": fakes.ADDR_SMART,
                 "taker": "0x0000000000000000000000000000000000000000", "tokenId": "111",
                 "makerAmount": "30500000", "takerAmount": "50000000", "expiration": "0",
                 "nonce": "0", "feeRateBps": "0", "side": "BUY", "signatureType": 0,
                 "signature": "0x" + "ab" * 65}
        resp = client.post("/api/trading/orders/submit", json={
            "ticket_id": ticket["ticket_id"], "wallet_address": fakes.ADDR_SMART,
            "signed_order_payload": {"order": order, "owner": "key", "orderType": "GTC"},
            "clob_credentials": {"api_key": "k", "secret": "czM=", "passphrase": "p"}})
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "LIVE_TRADING_DISABLED"
        # no order ever reached the CLOB client
        assert container.clob.posted_orders == []
        # ticket got rejected with an explanation
        after = client.get(f"/api/trade-tickets/{ticket['ticket_id']}").json()
        assert after["status"] == "REJECTED"
        assert "disabled" in after["error_message"]

    def test_unconfirmed_ticket_cannot_submit(self, app_bundle):
        client, container, _ = app_bundle
        ticket = self.make_ticket(client).json()
        resp = client.post("/api/trading/orders/submit", json={
            "ticket_id": ticket["ticket_id"], "wallet_address": fakes.ADDR_SMART,
            "signed_order_payload": {"order": {}},
        })
        assert resp.status_code == 422
        assert container.clob.posted_orders == []


class TestGeoblockRegions:
    def test_geoblock_endpoint_ok_region(self, app_bundle):
        client, _, _ = app_bundle
        data = client.get("/api/trading/geoblock").json()
        assert data["mode"] == "OK"
        assert data["can_open_position"] is True

    def test_close_only_region_blocks_new_positions(self):
        """Close-only region: geoblock endpoint reports it and ticket creation fails
        with CLOSE_ONLY_REGION (area 11)."""
        settings = make_test_settings()
        dataset = fakes.default_dataset()
        dataset["geoblock"] = {"blocked": True, "ip": "1.1.1.1", "country": "SG",
                               "region": ""}
        app, container, _ = build_test_app(settings, dataset)
        with TestClient(app) as client:
            geo = client.get("/api/trading/geoblock").json()
            assert geo["mode"] == "CLOSE_ONLY"
            assert geo["can_open_position"] is False
            assert geo["can_close_position"] is True
            resp = client.post("/api/trade-tickets", json={
                "market_id": "1001", "direction": "YES", "limit_price": 0.61,
                "max_notional": 50.0})
            assert resp.status_code == 403
            assert resp.json()["error"]["code"] == "CLOSE_ONLY_REGION"

    def test_blocked_region_rejected(self):
        settings = make_test_settings()
        dataset = fakes.default_dataset()
        dataset["geoblock"] = {"blocked": True, "ip": "1.1.1.1", "country": "US",
                               "region": ""}
        app, _, _ = build_test_app(settings, dataset)
        with TestClient(app) as client:
            resp = client.post("/api/trade-tickets", json={
                "market_id": "1001", "direction": "YES", "limit_price": 0.61,
                "max_notional": 50.0})
            assert resp.status_code == 403
            assert resp.json()["error"]["code"] == "GEOBLOCKED"

    def test_geoblock_upstream_failure_fails_closed(self):
        settings = make_test_settings()
        app, _, _ = build_test_app(settings, geoblock_fail=True)
        with TestClient(app) as client:
            data = client.get("/api/trading/geoblock").json()
            assert data["fail_closed"] is True
            assert data["mode"] == "BLOCKED"
            assert data["can_open_position"] is False


class TestLiveSubmissionPathWhenExplicitlyEnabled:
    """With the gate explicitly opened and all checks green, the signed payload reaches
    the (fake) CLOB exactly once and credentials never leak into the ticket record."""

    def test_submit_happy_path(self):
        settings = make_test_settings(ENABLE_LIVE_TRADING=True)
        app, container, _ = build_test_app(settings)
        with TestClient(app) as client:
            ticket = client.post("/api/trade-tickets", json={
                "market_id": "1001", "direction": "YES", "limit_price": 0.61,
                "max_notional": 50.0}).json()
            client.post(f"/api/trade-tickets/{ticket['ticket_id']}/confirm", json={
                "wallet_address": fakes.ADDR_SMART, "manual_confirmation": True})
            order = {"salt": "1", "maker": fakes.ADDR_SMART, "signer": fakes.ADDR_SMART,
                     "taker": "0x0000000000000000000000000000000000000000",
                     "tokenId": "111", "makerAmount": "30500000",
                     "takerAmount": "50000000", "expiration": "0", "nonce": "0",
                     "feeRateBps": "0", "side": "BUY", "signatureType": 0,
                     "signature": "0x" + "ab" * 65}
            resp = client.post("/api/trading/orders/submit", json={
                "ticket_id": ticket["ticket_id"], "wallet_address": fakes.ADDR_SMART,
                "signed_order_payload": {"order": order, "owner": "key",
                                         "orderType": "GTC"},
                "clob_credentials": {"api_key": "k", "secret": "czM=", "passphrase": "p"}})
            assert resp.status_code == 200, resp.text
            assert resp.json()["status"] == "SUBMITTED"
            assert resp.json()["order_id"] == "0xorder1"
            assert len(container.clob.posted_orders) == 1
            headers = container.clob.posted_orders[0]["headers"]
            assert headers["POLY_API_KEY"] == "k"

            after = client.get(f"/api/trade-tickets/{ticket['ticket_id']}").json()
            assert after["status"] == "SUBMITTED"
            assert after["order_id"] == "0xorder1"
            # credentials/signature must not be persisted on the ticket
            assert "czM=" not in str(after)
            assert "ab" * 65 not in str(after)

    def test_insufficient_balance_fails_closed(self):
        settings = make_test_settings(ENABLE_LIVE_TRADING=True)
        app, container, _ = build_test_app(
            settings, rpc=fakes.FakeRpcClient(usdc=10.0))  # balance < notional
        with TestClient(app) as client:
            ticket = client.post("/api/trade-tickets", json={
                "market_id": "1001", "direction": "YES", "limit_price": 0.61,
                "max_notional": 50.0}).json()
            client.post(f"/api/trade-tickets/{ticket['ticket_id']}/confirm", json={
                "wallet_address": fakes.ADDR_SMART, "manual_confirmation": True})
            order = {"salt": "1", "maker": fakes.ADDR_SMART, "signer": fakes.ADDR_SMART,
                     "taker": "0x0000000000000000000000000000000000000000",
                     "tokenId": "111", "makerAmount": "1", "takerAmount": "1",
                     "expiration": "0", "nonce": "0", "feeRateBps": "0", "side": "BUY",
                     "signatureType": 0, "signature": "0x" + "ab" * 65}
            resp = client.post("/api/trading/orders/submit", json={
                "ticket_id": ticket["ticket_id"], "wallet_address": fakes.ADDR_SMART,
                "signed_order_payload": {"order": order, "owner": "key",
                                         "orderType": "GTC"},
                "clob_credentials": {"api_key": "k", "secret": "czM=", "passphrase": "p"}})
            assert resp.status_code == 400
            assert container.clob.posted_orders == []


class TestClobCredentialDerivation:
    BODY = {"wallet_address": fakes.ADDR_SMART, "signature": "0x" + "cd" * 32,
            "timestamp": 1781000000, "nonce": 0}

    def test_disabled_by_default(self, client):
        resp = client.post("/api/trading/clob-credentials/derive", json=self.BODY)
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "LIVE_TRADING_DISABLED"

    def test_derives_when_live_enabled(self):
        settings = make_test_settings(ENABLE_LIVE_TRADING=True)
        app, _, _ = build_test_app(settings)
        with TestClient(app) as client:
            resp = client.post("/api/trading/clob-credentials/derive", json=self.BODY)
            assert resp.status_code == 200
            data = resp.json()
            assert data["api_key"] == "fake-key"
            assert data["passphrase"] == "fake-pass"


class TestTradingInfoEndpoints:
    def test_balances(self, client):
        data = client.get("/api/trading/balances",
                          params={"wallet_address": fakes.ADDR_SMART}).json()
        assert data["usdc_balance"] == 1000.0
        assert data["chain_id"] == 137

    def test_balances_invalid_address(self, client):
        resp = client.get("/api/trading/balances", params={"wallet_address": "0x123"})
        assert resp.status_code == 422

    def test_allowance(self, client):
        data = client.get("/api/trading/allowance",
                          params={"wallet_address": fakes.ADDR_SMART}).json()
        assert data["ctf_exchange_ok"] is True
        assert data["neg_risk_exchange_allowance"] == 1000.0
