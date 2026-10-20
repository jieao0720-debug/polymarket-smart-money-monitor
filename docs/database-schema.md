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
| exit_reason | str NULL（MANUAL 手动平仓 / RESOLVED 按官方结算入账，A25） |

### 9b. paper_trade_cohort（入场跟随名单，A26）

| 列 | 类型 |
| --- | --- |
| id | int PK |
| paper_trade_id | FK paper_trades INDEX |
| wallet_address | str（UNIQUE 与 paper_trade_id 组合） |
| direction | str（所买方向） |
| entry_shares / entry_opposite_shares | float（入场时本方向 / 反方向份额） |
| entry_net_exposure | float（e_0，> 0） |
| entry_value | float（入场时本方向持仓价值，权重基数） |
| weight | float（同一仓位合计 1） |
| smart_money_score / label | 入场时评分与标签 |
| source | str ENTRY / BACKFILL |
| signal_snapshot_time | datetime（入场信号快照时间） |
| created_at | datetime |

### 9c. position_observations（持仓监控观察，A27；影子模式，只记录）

| 列 | 类型 |
| --- | --- |
| id | int PK |
| paper_trade_id | FK INDEX；(paper_trade_id, observed_at) INDEX |
| observed_at | datetime INDEX |
| market_status | str OPEN / AWAITING_RESOLUTION / RESOLVED / UNKNOWN |
| best_bid / best_ask | float NULL（持有方向） |
| liquidation_price / liquidation_value / liquidation_fill_ratio / liquidation_return | float NULL（按买盘逐档卖出整笔仓位，扣费；未成交部分不计价值） |
| retention / coverage | float NULL（R 与已知权重合计） |
| cohort_detail | JSON（每个账户 e_0、e_t、HOLDING/REDUCED/EXITED/REVERSED/UNKNOWN） |
| latest_signal_direction / latest_signal_time | 入场后最新扫描信号 |
| shadow_state | JSON（各规则连续计数 streaks、首次触发时间 fired_at） |
| shadow_triggers | JSON NULL（本轮确认的规则） |
| shadow_target_fraction | float（影子目标仓位比例，只降不升） |
| data_issues | JSON NULL（数据缺失说明） |

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
paper_trades 1─n paper_trade_cohort
paper_trades 1─n position_observations
markets 1─n trade_tickets
```

## 增量迁移

仍不引入 Alembic（A10）。`init_db` 在 `create_all` 之后，为已有表补齐模型中新增的**可空**列
（`ALTER TABLE ... ADD COLUMN`，可重复执行）；非空列或类型变更仍需正式迁移。
