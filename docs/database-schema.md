# Database Schema

SQLAlchemy 2.0；本地 SQLite / 生产 PostgreSQL。所有表带自增整型主键 `id`、UTC 时间戳。
价格 0–1 Float；notional/value/pnl 为 USDC Float；shares 为 token 数量 Float。`JSON` 列在两种数据库均原生支持。
（MVP 用 Float，生产建议 Numeric(18,6)，见 final-audit-report Known limitations。）

## 1. markets

| 列 | 类型 | 说明 |
| --- | --- | --- |
| id | int PK | |
| polymarket_market_id | str UNIQUE INDEX | gamma market id（如 "558956"） |
| condition_id | str UNIQUE INDEX | 0x.. conditionId（Data-API/CLOB 主键） |
| event_id | str NULL | gamma event id |
| question | str | |
| slug | str | |
| category | str NULL | 由 event tags 推导的主类目（见 uncertainties §7） |
| tags | JSON | tag label 列表 |
| yes_token_id | str | CLOB token id（与 outcomes 索引对齐后归一） |
| no_token_id | str | |
| active | bool | gamma `active` |
| closed | bool | gamma `closed` |
| accepting_orders | bool | gamma `acceptingOrders` |
| neg_risk | bool | gamma `negRisk`（决定交易所合约） |
| tick_size | float | gamma `orderPriceMinTickSize` |
| end_date | datetime NULL | gamma `endDate` |
| volume | float | 累计成交额（USDC 口径，gamma `volumeNum`） |
| volume_24h | float | gamma `volume24hr` |
| liquidity | float | gamma `liquidityNum` |
| open_interest | float NULL | event 级 openInterest（市场级缺失，见 uncertainties §6） |
| created_at / updated_at | datetime | |

索引：`polymarket_market_id`、`condition_id`、`(active, closed)`。

## 2. market_snapshots

| 列 | 类型 | 说明 |
| --- | --- | --- |
| id | int PK | |
| market_id | FK markets.id INDEX | |
| snapshot_time | datetime INDEX | |
| yes_price | float | YES midpoint（book 双边存在时）否则 gamma outcomePrices[yes] |
| no_price | float | |
| spread | float | best_ask − best_bid（YES token，绝对价差） |
| midpoint | float | (best_bid + best_ask)/2 |
| best_bid / best_ask | float NULL | YES token 盘口 |
| orderbook_depth | JSON | {yes:{bid_depth_usdc, ask_depth_usdc, top3_ask_usdc,...}, no:{...}} |
| volume_24h | float | |
| liquidity | float | |
| open_interest | float NULL | |

复合索引 `(market_id, snapshot_time)`。

## 3. accounts

| 列 | 类型 |
| --- | --- |
| id | int PK |
| wallet_address | str UNIQUE INDEX（小写 0x40hex） |
| profile_name | str NULL（data-api `name`/`pseudonym`） |
| first_seen_at | datetime NULL（该地址最早 closed-position timestamp 或首次被本系统观察到） |
| created_at / updated_at | datetime |

## 4. account_resolved_stats

某账户在 `as_of`（=snapshot_time）时点、按 look-ahead 安全口径计算的 resolved 统计。

| 列 | 类型 | 说明 |
| --- | --- | --- |
| id | int PK | |
| account_id | FK accounts.id INDEX | |
| category | str NULL | NULL=overall；非 NULL=同类目切片 |
| snapshot_time | datetime | as_of |
| resolved_trade_count | int | timestamp≤as_of 且 endDate≤as_of 的 closed positions 数 |
| win_rate | float | curPrice==1 占比（0–1） |
| realized_pnl | float | Σ realizedPnl |
| average_roi | float | mean(realizedPnl / entry_notional)，entry_notional=avgPrice*totalBought |
| median_entry_notional | float | median(avgPrice*totalBought) |
| same_category_trade_count | int | category 行冗余存储（overall 行=0） |
| same_category_win_rate | float | |
| same_category_roi | float | |
| history_truncated | bool | 分页达到上限未取完整历史（partial 标记） |

复合索引 `(account_id, snapshot_time)`。

## 5. market_holders

| 列 | 类型 | 说明 |
| --- | --- | --- |
| id | int PK | |
| market_id | FK INDEX | |
| account_id | FK INDEX | |
| snapshot_time | datetime | |
| direction | str | "YES"/"NO"（token→方向在 normalization 层完成） |
| shares | float | holders.amount（实测=token 数量） |
| current_position_value | float | /positions currentValue；缺失时 shares*current_price（approx，见 uncertainties） |
| average_price | float NULL | /positions avgPrice |
| current_price | float NULL | /positions curPrice 或快照价 |
| entry_notional_approx | float NULL | /positions initialValue（≈开仓成本，命名即口径） |
| rank | int | 边内按 current_position_value 降序 1..20 |
| value_is_approx | bool | current_position_value 是否为 shares*price 近似 |

复合索引 `(market_id, snapshot_time)`。

## 6. account_labels

| 列 | 类型 | 说明 |
| --- | --- | --- |
| id | int PK | |
| account_id | FK INDEX | |
| market_id | FK INDEX | 标签依附于"账户×市场×时点" |
| snapshot_time | datetime | |
| label | str | NEW_ACCOUNT / HIGH_WIN_RATE / ABNORMAL_POSITION / OTHER |
| anomaly_index | float NULL | entry_notional_approx / median_historical_entry_notional |
| smart_money_score | float | 0–100 |
| score_breakdown | JSON | 各分项与惩罚明细（透明可审计） |
| reason | str | 人类可读标签原因 |

## 7. smart_money_signals

| 列 | 类型 |
| --- | --- |
| id | int PK |
| signal_uid | str UNIQUE（uuid，对外 signal_id） |
| market_id | FK INDEX |
| snapshot_time | datetime INDEX |
| direction | str YES/NO/NEUTRAL |
| confidence_score | float 0–100 |
| yes_smart_money_count / no_smart_money_count | int |
| yes_smart_money_notional / no_smart_money_notional | float |
| risk_flags | JSON string[] |
| suggested_limit_price | float NULL |
| suggested_max_notional | float NULL |
| score_inputs | JSON（聚合输入快照，可复算） |

## 8. trade_tickets

| 列 | 类型 |
| --- | --- |
| id | int PK |
| ticket_uid | str UNIQUE（对外 ticket_id） |
| signal_id | str NULL（signal_uid） |
| market_id | FK |
| wallet_address | str NULL（确认时绑定） |
| direction | str YES/NO |
| side | str（v1 恒 "BUY"） |
| limit_price | float |
| max_notional | float |
| status | str TicketStatus INDEX |
| risk_checks | JSON（创建时第一道检查结果） |
| risk_checks_at_submit | JSON NULL（第二道复检结果） |
| created_at / confirmed_at / submitted_at / expires_at | datetime（后三者 NULL） |
| order_id | str NULL（CLOB orderID） |
| tx_hash | str NULL |
| error_message | str NULL |

## 9. paper_trades

| 列 | 类型 |
| --- | --- |
| id | int PK |
| trade_uid | str UNIQUE（对外 paper_trade_id） |
| signal_id | str NULL |
| market_id | FK INDEX |
| direction | str YES/NO |
| entry_price | float（0–1） |
| entry_time | datetime |
| notional | float |
| shares | float（= notional/entry_price，固化存储） |
| exit_price | float NULL |
| exit_time | datetime NULL |
| pnl | float NULL（= shares*(exit−entry)） |
| status | str OPEN/CLOSED/CANCELLED INDEX |
| source | str AUTO_SIGNAL / MANUAL |

## 10. wallet_connections

| 列 | 类型 |
| --- | --- |
| id | int PK |
| wallet_address | str UNIQUE INDEX |
| chain_id | int |
| last_connected_at | datetime |
| geoblock_status | JSON NULL（最近一次检查结果快照） |
| created_at / updated_at | datetime |

仅存公开地址与连接元数据。**永不存储私钥/助记词/签名凭证/CLOB credentials。**

## 11. api_fetch_logs

| 列 | 类型 |
| --- | --- |
| id | int PK |
| source | str（gamma/data/clob/geoblock/rpc） |
| endpoint | str |
| status | str（ok/error/timeout）+ http_status int NULL |
| request_params | JSON（脱敏后） |
| response_summary | str（截断 ≤500 字符） |
| error_message | str NULL |
| duration_ms | int NULL |
| fetched_at | datetime INDEX |

## 关系图（简化）

```
markets 1─n market_snapshots
markets 1─n market_holders n─1 accounts
markets 1─n account_labels n─1 accounts
accounts 1─n account_resolved_stats
markets 1─n smart_money_signals 1─n paper_trades(逻辑FK signal_uid)
markets 1─n trade_tickets
```
