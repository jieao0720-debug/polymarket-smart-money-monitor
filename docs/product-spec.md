# Product Spec — Polymarket Smart Money Quant Monitor

## 1. 项目定义

一个钱包接入型预测市场量化工具：自动扫描 Polymarket 热门市场，分析每个市场 YES/NO 两侧的 top holders，
基于地址级历史 resolved 战绩识别 smart money，生成**分析参考信号（analysis signal）**，
将所有信号记入 paper trading 日志，并支持用户在**手动确认**后进行真实交易。

**第一版不做自动跟单。默认模式是 paper trading。`ENABLE_LIVE_TRADING` 默认为 `false`。**

## 2. 用户价值

- 不用手动翻每个市场的 holders 页面：系统自动扫描热门市场并拉出双边 top 20 holders。
- 不用手动查每个地址的历史：系统计算地址级 resolved 战绩（win rate / realized PnL / ROI / 同类目战绩）。
- 把"大户在买什么"转化为结构化、可回溯的信号流，并用 paper trading 持续验证信号质量。
- 想跟单时，提供带完整风控检查的 trade ticket，由用户钱包签名、手动确认后才提交。

## 3. 用户流程

1. 用户启动 backend + frontend，打开 `/dashboard`。
2. 点击 "Run Scanner"（或等待定时扫描）→ 系统拉取热门市场 → 过滤 → 分析双边 top holders → 生成账户画像、标签、smart money score → 聚合为 market-level signal。
3. Dashboard 展示热门市场卡片/表格（价格、流动性、smart money 方向、confidence、risk flags）。
4. 用户点进 `/markets/[marketId]`：查看 YES/NO 价格、spread/流动性、smart money summary、双边 top holders 表。
5. 点击任意地址 → Account Detail Drawer：整体战绩、同类目战绩、当前市场仓位、anomaly index、标签原因。
6. 所有合格信号自动进入 paper trading 日志（`/paper-trades`），可随时 mark-to-market / 平仓记录 PnL。
7. 用户若要真实交易：进入 `/trading` 连接钱包（不输入私钥）→ 查看 geoblock / balance / allowance →
   在市场页生成 trade ticket → modal 中查看风控检查结果 → 勾选 manual confirmation → 钱包签名 → 后端二次风控 → 提交 CLOB。
8. `ENABLE_LIVE_TRADING=false`（默认）时，提交在后端被拒绝并明确提示；所有真实交易必须显式开启该开关且通过全部风控。

## 4. MVP 范围（第一版必须完成）

1. 热门市场自动扫描（volume / liquidity / open interest / recent activity / spread 筛选；过滤低流动性、临近结算高风险、inactive/closed 市场）。
2. Top holders 分析：每市场 YES/NO 各 top 20（Data-API holders 上限即 20），按 `current_position_value` 排序，展示 address / direction / shares / current_position_value / average_price / current_price / rank。
3. 账户历史画像：基于 `/closed-positions` 计算 resolved_trade_count、win_rate、realized_pnl、average_roi、median_entry_notional、same_category_*、first_seen_at、last_seen_at。
4. 账户分类：NEW_ACCOUNT / HIGH_WIN_RATE / ABNORMAL_POSITION / OTHER（规则见 development-rules.md 与代码 `smart_money_service`）。
5. 透明 rule-based Smart Money Score（0–100，分项函数 + 单测）。
6. Market-level signal：双边 smart money count/notional、net direction、confidence_score、risk_flags、suggested_limit_price、suggested_max_notional。
7. Paper trading：信号自动入账 + 手动记录 + 平仓与 PnL。
8. 钱包接入（wagmi/viem，仅连接，不碰私钥）+ geoblock/balance/allowance 展示。
9. 手动真实交易链路：trade ticket → 风控 → 手动确认 → 前端签名 → 后端二次风控 → CLOB 提交（默认关闭）。
10. 前端 Dashboard 全套页面（见 §7）。
11. 测试、安全审计、部署文档、README、final audit report。

## 5. 非 MVP 范围（明确不做）

自动跟单；托管钱包/保存私钥；绕过地理限制；高频交易；机器学习模型；自建链上 indexer；
多用户权限系统；收益承诺；付费系统；移动端原生 App；Telegram bot（仅在 signal_service 预留 notifier 接口）。

## 6. 核心风险（产品层面）

| 风险 | 应对 |
| --- | --- |
| 数据口径错误（Yes/No 方向反、shares 与 USD 混用） | 集中 normalization 层 + 单测覆盖方向映射 + 实测验证（见 data-field-uncertainties.md） |
| Look-ahead bias（用未来 resolved 结果评估历史信号） | 所有账户统计带 `as_of` 参数，只统计 `timestamp <= as_of` 且 `endDate <= as_of` 的 closed positions；单测覆盖 |
| 把大户/异常仓位直接当聪明钱 | 标签与 score 透明规则化；confidence 不是胜率；UI 强制展示 risk flags 与 "analysis signal" 措辞 |
| 真实交易风险 | 默认关闭；geoblock/close-only/balance/allowance/spread/slippage/notional/market-state 八道检查；手动确认 |
| 地区合规 | geoblock 检查 fail-closed；blocked 禁止下单；close-only 禁止开新仓；绝不绕过 |
| 外部 API 不稳定 / 限流 | timeout + retry + 并发上限 + partial data warning，页面不整体崩溃 |
| Polymarket 字段语义不确定 | 全部记录在 data-field-uncertainties.md，approximation 字段在代码与 UI 显式命名 |

## 7. 页面列表

| 路由 | 内容 |
| --- | --- |
| `/dashboard` | 热门市场卡片+表格、筛选器（category/liquidity/volume/confidence/risk flags）、scanner 状态、refresh |
| `/markets/[marketId]` | 市场头、YES/NO 价格面板、spread/liquidity/volume/OI 卡片、smart money summary、双边 notional 图、top holders 表、risk flags、Generate Trade Ticket |
| Account Detail Drawer | 地址画像（overall / same-category / current market / label reason），从 holders 表点开 |
| `/signals` | 历史 smart money signals 列表（含过滤） |
| `/paper-trades` | paper trading 记录与 PnL 汇总 |
| `/trading` | 钱包连接、链状态、geoblock、balance/allowance、live trading 开关状态、区域警告 |
| Trade Ticket Modal | 票据详情 + 风控结果 + manual confirmation checkbox + 签名/确认 |
| `/settings` | 后端配置（只读展示：limits、live trading 状态、扫描参数）+ 前端偏好 |

## 8. 数据流

```
Gamma API (markets/events/tags)          CLOB API (book/midpoint/spread)
        │                                        │
        ▼                                        ▼
  market_scanner_service ──► normalization ──► market_snapshots / markets 表
        │
        ▼
Data-API /holders (双边 top20) ──► holder_analysis_service ──► market_holders 表
        │  每个 holder
        ▼
Data-API /closed-positions + /positions?market= ──► account_profile_service(as_of)
        │                                              │
        ▼                                              ▼
 account_resolved_stats 表                    smart_money_service（标签+score）──► account_labels 表
        │                                              │
        └──────────────► signal_service（市场级聚合）──► smart_money_signals 表
                                  │
                ┌─────────────────┴─────────────────┐
                ▼                                   ▼
        paper_trade_service（自动入账）        前端 Dashboard / Market Detail / Signals
                                                    │ 用户手动
                                                    ▼
                      trade ticket → trading_risk_service（8 项检查）→ 钱包签名 →
                      order_submit_service（二次风控 + ENABLE_LIVE_TRADING 闸门）→ CLOB POST /order
```

## 9. 措辞与合规要求

- 所有信号 UI 必须标注 **"Analysis signal — not financial advice, not a win probability."**
- confidence_score 任何地方不得写成 win probability / 胜率。
- 真实交易 UI 必须显示 **"This is not automated trading. You are manually confirming this order."**
- close-only 地区显示 **"This region is close-only. Opening new positions is disabled."**
