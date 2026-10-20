# API Contract — 内部 REST API（v1）

Base: `http://localhost:8000`。所有响应 JSON。时间一律 ISO-8601 UTC（`2026-06-11T08:00:00Z`）。
价格均为 0–1 的小数；notional/value 单位 USDC；shares 为 outcome token 数量。

**统一错误信封**（所有非 2xx）：

```json
{ "error": { "code": "STRING_CODE", "message": "human readable", "details": {} } }
```

常用 code：`VALIDATION_ERROR`(422) `NOT_FOUND`(404) `GEOBLOCKED`(403) `CLOSE_ONLY_REGION`(403)
`LIVE_TRADING_DISABLED`(403) `RISK_CHECK_FAILED`(400) `MARKET_NOT_TRADABLE`(400) `UPSTREAM_ERROR`(502)
`SCAN_ALREADY_RUNNING`(409) `INTERNAL_ERROR`(500)。

许多读取端点带 `warnings: string[]`，表示 partial data（上游部分失败但不致命）。

通用枚举：
- `Direction`: `"YES" | "NO"`；`SignalDirection`: `"YES" | "NO" | "NEUTRAL"`
- `AccountLabel`: `"NEW_ACCOUNT" | "HIGH_WIN_RATE" | "ABNORMAL_POSITION" | "OTHER"`
- `RiskFlag`: `"LOW_LIQUIDITY" | "WIDE_SPREAD" | "NEAR_RESOLUTION" | "EXTREME_PRICE" | "LOW_SMART_SAMPLE" | "NEW_ACCOUNT_HEAVY" | "ONE_SIDED_BOOK" | "PARTIAL_DATA"`
- `TicketStatus`: `"PENDING_USER_CONFIRMATION" | "CONFIRMED" | "SUBMITTED" | "REJECTED" | "FAILED" | "CANCELLED" | "EXPIRED"`
- `PaperTradeStatus`: `"OPEN" | "CLOSED" | "CANCELLED"`
- `GeoMode`: `"OK" | "CLOSE_ONLY" | "BLOCKED"`

---

## 1. POST /api/scanner/run

启动热门市场扫描（后台执行）。Body（可选）：`{ "max_markets": 15 }`（1–50，默认 env `SCANNER_MAX_MARKETS`）。

```json
{ "scan_id": "uuid", "started_at": "datetime", "markets_found": 0, "markets_analyzed": 0, "status": "running" }
```

`status`: `"running" | "completed" | "failed"`。已有 scan 在跑 → 409 `SCAN_ALREADY_RUNNING`。

## 2. GET /api/scanner/status/{scan_id}

```json
{ "scan_id": "uuid", "status": "running", "started_at": "dt", "finished_at": null,
  "markets_found": 42, "markets_analyzed": 7, "signals_generated": 3,
  "errors": ["string"], "current_step": "analyzing market 0x.. (8/15)" }
```

404 if unknown。`GET /api/scanner/latest` 返回最近一次 scan 的同构对象（无任何 scan → `{"scan_id": null, "status": "idle", ...}`）。

## 3. GET /api/markets/hot

Query：`limit`(默认50) `category` `min_liquidity` `min_confidence` `direction`。
返回最近一次扫描中分析过的市场 + 各自最新 signal。

```json
{ "markets": [ {
    "market_id": "string(gamma id)", "condition_id": "0x..", "question": "string",
    "category": "string", "slug": "string", "end_date": "dt|null",
    "volume_24h": 0, "liquidity": 0, "open_interest": 0,
    "yes_price": 0.5, "no_price": 0.5, "spread": 0.01, "midpoint": 0.5,
    "smart_money_direction": "YES|NO|NEUTRAL|null", "confidence_score": 0,
    "risk_flags": ["WIDE_SPREAD"], "last_analyzed_at": "dt|null"
  } ], "warnings": [] }
```

## 4. GET /api/markets/{market_id}/analysis

`market_id` 为 gamma market id。Query：`refresh=true` 时对该市场做一次即时分析（耗时数秒–数十秒）。

```json
{
  "market": { "market_id": "s", "condition_id": "0x..", "question": "s", "category": "s",
    "slug": "s", "active": true, "closed": false, "accepting_orders": true, "neg_risk": false,
    "end_date": "dt|null", "yes_token_id": "s", "no_token_id": "s",
    "yes_price": 0.6, "no_price": 0.4, "spread": 0.01, "midpoint": 0.6,
    "volume_24h": 0, "liquidity": 0, "open_interest": 0, "tick_size": 0.01 },
  "summary": { "snapshot_time": "dt|null",
    "yes_smart_money_count": 0, "no_smart_money_count": 0,
    "yes_smart_money_notional": 0, "no_smart_money_notional": 0,
    "net_direction": "YES|NO|NEUTRAL", "confidence_score": 0, "risk_flags": [],
    "suggested_limit_price": 0.62, "suggested_max_notional": 100, "signal_id": "s|null" },
  "holders": [ { "address": "0x..", "direction": "YES", "rank": 1,
    "current_position_value": 0, "shares": 0, "average_price": 0, "current_price": 0,
    "label": "HIGH_WIN_RATE", "label_reason": "s", "win_rate": 0, "resolved_trade_count": 0,
    "realized_pnl": 0, "same_category_win_rate": 0, "same_category_trade_count": 0,
    "anomaly_index": 0, "smart_money_score": 0 } ],
  "warnings": []
}
```

`win_rate`、`same_category_win_rate` 为 0–1 小数；`anomaly_index` 为倍数；holders 含 YES+NO 双边（direction 区分），按 current_position_value 降序、各边独立 rank。

## 5. GET /api/accounts/{address}/profile?market_id={gamma_id}

```json
{
  "address": "0x..", "profile_name": "string|null",
  "first_seen_at": "dt|null", "last_seen_at": "dt|null", "as_of": "dt",
  "overall": { "resolved_trade_count": 0, "win_rate": 0, "realized_pnl": 0,
    "average_roi": 0, "median_entry_notional": 0 },
  "same_category": { "category": "s|null", "trade_count": 0, "win_rate": 0, "average_roi": 0 },
  "current_market": { "market_id": "s", "direction": "YES", "shares": 0, "average_price": 0,
    "current_position_value": 0, "entry_notional_approx": 0, "anomaly_index": 0,
    "label": "ABNORMAL_POSITION", "label_reason": "s", "smart_money_score": 0 },
  "warnings": []
}
```

`market_id` 缺省时 `same_category`/`current_market` 为 null。`win_rate`/`average_roi` 0–1 小数（roi 可为负、可 >1）。

## 6. GET /api/signals

Query：`market_id` `direction` `min_confidence` `limit`(默认100) `offset`。

```json
{ "signals": [ { "signal_id": "s", "market_id": "s", "question": "s", "category": "s",
    "snapshot_time": "dt", "direction": "YES|NO|NEUTRAL", "confidence_score": 0,
    "yes_smart_money_count": 0, "no_smart_money_count": 0,
    "yes_smart_money_notional": 0, "no_smart_money_notional": 0,
    "risk_flags": [], "suggested_limit_price": 0, "suggested_max_notional": 0 } ],
  "total": 0 }
```

## 7. POST /api/trade-tickets

```json
// Request
{ "signal_id": "s|null", "market_id": "s", "direction": "YES",
  "limit_price": 0.62, "max_notional": 100, "wallet_address": "0x..|null", "side": "BUY" }
```

`side` 目前仅 `"BUY"`（v1 开仓只支持买入对应 outcome token；平仓/卖出非 v1）。

```json
// Response 201
{ "ticket_id": "s", "status": "PENDING_USER_CONFIRMATION",
  "market_id": "s", "question": "s", "direction": "YES",
  "limit_price": 0.62, "max_notional": 100, "expires_at": "dt",
  "risk_checks": { "geoblock_ok": true, "geoblock_mode": "OK", "market_active": true,
    "spread_ok": true, "liquidity_ok": true, "price_ok": true, "notional_ok": true,
    "live_trading_enabled": false, "all_passed": true, "reasons": [] },
  "created_at": "dt" }
```

风控硬失败（geoblocked / market closed / close-only 开仓 / notional 超限）→ 400/403 错误信封；
软信息（live_trading_enabled=false）不阻止创建票据（paper 模式下仍可走完 UI 流程，提交时被闸门拒绝）。

## 8. GET /api/trade-tickets/{ticket_id}

返回与 §7 Response 同构 + `confirmed_at` `submitted_at` `order_id` `tx_hash` `error_message` `wallet_address`。
`GET /api/trade-tickets`（列表，query: `status` `limit`）。

### 8b. POST /api/trade-tickets/{ticket_id}/confirm

Body: `{ "wallet_address": "0x..", "manual_confirmation": true }`。
`manual_confirmation` 必须为 true；状态必须是 PENDING_USER_CONFIRMATION 且未过期 → `CONFIRMED`，记录 `confirmed_at`。

### 8c. POST /api/trade-tickets/{ticket_id}/cancel → status CANCELLED。

## 9. POST /api/paper-trades

```json
// Request
{ "signal_id": "s|null", "market_id": "s", "direction": "YES",
  "notional": 50, "entry_price": 0.62 }
```

`entry_price` 缺省 → 用该市场最新快照对应方向的卖一价（A24）。Response 201 = PaperTrade 对象：

```json
{ "paper_trade_id": "s", "signal_id": "s|null", "market_id": "s", "question": "s",
  "direction": "YES", "entry_price": 0.62, "entry_time": "dt", "notional": 50,
  "shares": 80.6452, "exit_price": null, "exit_time": null, "pnl": null,
  "unrealized_pnl": 1.2, "current_price": 0.635, "price_basis": "BID",
  "price_as_of": "dt", "status": "OPEN", "source": "MANUAL", "exit_reason": null,
  "shadow": { "observed_at": "dt", "market_status": "OPEN", "retention": 0.82,
    "coverage": 1.0, "liquidation_return": -0.04, "target_fraction": 1.0, "triggers": [] } }
```

口径：`shares = notional / entry_price`；`pnl = shares * (exit_price - entry_price)`；
`unrealized_pnl = shares * (current_price - entry_price)`（仅 OPEN 且有最新价时返回，可为 null）。
`current_price` 为持有方向**买一价**（A24），`price_basis=MIDPOINT` 表示没有买一价记录、退回了中间价。
`exit_reason`：MANUAL / RESOLVED。`shadow` 为最新一次持仓监控的影子退出结果（A27，只记录，不执行），
`triggers` 是已触发过的规则（COHORT_REDUCE / COHORT_EXIT / SIGNAL_FLIP / STOP_LOSS）；未监控过为 null。

## 10. GET /api/paper-trades

Query：`status` `market_id` `limit` `offset`。

```json
{ "paper_trades": [ <PaperTrade> ], "total": 0,
  "summary": { "open_count": 0, "closed_count": 0, "total_realized_pnl": 0,
    "total_unrealized_pnl": 0, "win_count": 0, "loss_count": 0 } }
```

### 10b. POST /api/paper-trades/{id}/close

Body: `{ "exit_price": 0.8 }`（缺省 → 最新买一价，A24）。Response：更新后的 PaperTrade（status CLOSED，`exit_reason=MANUAL`，含 pnl）。

### 10c. POST /api/paper-trades/monitor/run

执行一轮持仓监控（同步返回）：已按官方结算的市场平仓入账（A25），其余 OPEN 仓位各写一条影子观察（A27）。
不会因其他任何原因平仓或减仓。也可通过 `POSITION_MONITOR_INTERVAL_MINUTES` 定时运行或 `scripts/run_monitor.py`。

```json
{ "started_at": "dt", "finished_at": "dt", "open_trades": 3, "observations": 3,
  "settled": 0, "cohorts_backfilled": 0, "errors": [] }
```

### 10d. GET /api/paper-trades/{id}/observations

Query：`limit`（默认 200）。返回入场跟随名单与观察记录（新到旧）：

```json
{ "paper_trade_id": "s",
  "cohort": [ { "wallet_address": "0x..", "entry_shares": 10000, "entry_opposite_shares": 0,
    "entry_net_exposure": 10000, "entry_value": 6000, "weight": 1.0,
    "smart_money_score": 78.5, "label": "HIGH_WIN_RATE", "source": "ENTRY" } ],
  "observations": [ { "observed_at": "dt", "market_status": "OPEN", "best_bid": 0.59,
    "best_ask": 0.61, "liquidation_price": 0.59, "liquidation_value": 96.7,
    "liquidation_fill_ratio": 1.0, "liquidation_return": -0.033, "retention": 0.5,
    "coverage": 1.0, "cohort_detail": [ { "wallet": "0x..", "weight": 1.0,
      "entry_net_exposure": 10000, "current_net_exposure": 5000, "status": "REDUCED" } ],
    "latest_signal_direction": "YES", "latest_signal_time": "dt",
    "shadow_state": { "streaks": { "COHORT_REDUCE": 2 }, "fired_at": { "COHORT_REDUCE": "dt" } },
    "shadow_triggers": ["COHORT_REDUCE"], "shadow_target_fraction": 0.5,
    "data_issues": null } ] }
```

## 11. GET /api/trading/geoblock

```json
{ "blocked": true, "country": "SG", "region": null, "mode": "CLOSE_ONLY",
  "can_open_position": false, "can_close_position": true, "checked_at": "dt", "fail_closed": false }
```

`fail_closed=true` 表示上游 geoblock 接口失败、按 blocked 保守处理。

## 12. GET /api/trading/balances?wallet_address=0x..

```json
{ "wallet_address": "0x..", "chain_id": 137,
  "usdc_balance": 123.45, "native_balance": 0.5, "checked_at": "dt", "warnings": [] }
```

## 13. GET /api/trading/allowance?wallet_address=0x..

```json
{ "wallet_address": "0x..",
  "ctf_exchange_allowance": 0, "neg_risk_exchange_allowance": 0,
  "ctf_exchange_ok": false, "neg_risk_exchange_ok": false, "checked_at": "dt" }
```

`*_ok` = allowance ≥ ticket 所需额度的一般判断（≥ MAX_TRADE_NOTIONAL 视为 ok）。

## 13b. POST /api/trading/clob-credentials/derive

仅 `ENABLE_LIVE_TRADING=true` 时可用（否则 403 `LIVE_TRADING_DISABLED`）。
前端用钱包对 Polymarket `ClobAuth` EIP-712 消息签名，后端代理 CLOB `derive-api-key`/`api-key`，
凭证只回传给调用方，**后端不持久化、不写日志**。

```json
// Request
{ "wallet_address": "0x..", "signature": "0x..(EIP-712 ClobAuth 签名)",
  "timestamp": 1781000000, "nonce": 0 }
// Response
{ "api_key": "uuid", "secret": "base64", "passphrase": "s", "derived_at": "dt" }
```

附注：§11 geoblock 支持可选 `wallet_address` query 参数；提供时 upsert `wallet_connections`
记录（地址、chain_id、最近连接时间、geoblock 快照）。

## 14. POST /api/trading/orders/submit

```json
// Request
{ "ticket_id": "s", "wallet_address": "0x..",
  "signed_order_payload": { "order": { "salt": "s", "maker": "0x..", "signer": "0x..",
      "taker": "0x0000000000000000000000000000000000000000", "tokenId": "s",
      "makerAmount": "s", "takerAmount": "s", "expiration": "s", "nonce": "s",
      "feeRateBps": "s", "side": "BUY", "signatureType": 0, "signature": "0x.." },
    "orderType": "GTC", "owner": "api-key-uuid" },
  "clob_credentials": { "api_key": "s", "secret": "s", "passphrase": "s" } }
```

`clob_credentials` 仅在内存中用于构造 L2 HMAC 头，**不持久化、不写日志**。

```json
// Response 200（仅当 ENABLE_LIVE_TRADING=true 且全部风控通过）
{ "status": "SUBMITTED", "order_id": "s", "submitted_at": "dt", "clob_status": "live" }
```

默认（live 关闭）→ 403 `LIVE_TRADING_DISABLED`，ticket → REJECTED（error_message 注明）。
风控复检失败 → 400 `RISK_CHECK_FAILED`（details 含逐项结果）。

## 15. GET /api/health

```json
{ "status": "ok", "version": "0.1.0", "database": "ok", "time": "dt",
  "live_trading_enabled": false, "scheduler_running": false }
```

## 16. GET /api/settings/public

只读暴露非敏感配置（前端 Settings 页用）：

```json
{ "enable_live_trading": false, "max_trade_notional": 100, "max_slippage_bps": 100,
  "max_spread_bps": 300, "min_liquidity": 1000, "min_position_value": 100,
  "smart_money_score_threshold": 60, "scanner_max_markets": 15,
  "scanner_interval_minutes": 0, "close_only_countries": ["PL","SG","TH","TW"],
  "near_resolution_hours": 48, "paper_trade_auto_log": true }
```
