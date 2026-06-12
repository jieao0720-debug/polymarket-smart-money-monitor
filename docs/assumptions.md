# Assumptions（合理假设记录）

编号引用格式：代码注释中 `# ASSUMPTION-n`。

- **A1 二元市场限定**：v1 只分析 outcomes 恰为 {Yes, No}（大小写不敏感）的市场；多结局/scalar 市场跳过并记 warning。
- **A2 resolved 历史口径**：账户 resolved 历史 = Data-API `/closed-positions`（官方定义：已结算仓位含 realizedPnl）。
  该口径以"仓位"为单位（同一市场同一 outcome 聚合为一条），即 `resolved_trade_count` 实为 *resolved position count*。
  卖出止盈/止损产生的已实现盈亏由 `realizedPnl` 覆盖。win 定义：`curPrice == 1`（所持 outcome 结算为胜）。
- **A3 look-ahead 保守过滤**：closed position 仅当 `timestamp <= as_of` **且** `endDate <= as_of` 才计入 as_of 时点统计
  （timestamp 官方定义"position closed 时间"；双条件防止口径含糊导致未来函数）。
- **A4 历史分页上限**：每账户最多拉 `ACCOUNT_HISTORY_MAX_PAGES`(默认4)×50=200 条 closed positions
  （sortBy=TIMESTAMP，sortDirection=DESC，取最近的）。达到上限 → `history_truncated=true` 并在 UI/响应 warnings 提示。
- **A5 同类目匹配为近似**：closed-positions 不含类目字段。同类目战绩用关键词映射表
  （sports/politics/crypto/economy/pop-culture/science/world…）同时作用于当前市场 event tags 与历史 `eventSlug+title`。
  属 approximation，UI 标注 "category match is keyword-based"。
- **A6 anomaly_index 分子**：理想口径是"该市场首次开仓金额"。可靠可得的是 `/positions.initialValue`
  （= avgPrice×size，当前持仓成本）。v1 用 initialValue 命名为 `entry_notional_approx`；完全缺失时退化为
  current_position_value（仍标 approx）。已在 UI 与字段名中显式标注（任务书允许的临时替代）。
- **A7 标签优先级**：NEW_ACCOUNT > HIGH_WIN_RATE > ABNORMAL_POSITION > OTHER。
  同时满足 HWR 与 ABNORMAL 时取 HIGH_WIN_RATE，reason 中附注 abnormal sizing。
- **A8 smart money 计数口径**：market-level signal 中 "smart money holder" = label ≠ NEW_ACCOUNT 且
  smart_money_score ≥ `SMART_MONEY_SCORE_THRESHOLD`(默认60) 的 top holder；notional 用其 current_position_value。
- **A9 paper trade 自动入账价**：用信号时刻该方向 **best ask**（taker 视角可成交价），而非 midpoint/建议限价——
  避免用不可成交价虚增 paper 收益。shares=notional/entry_price 固化。
- **A9b 自动入账守门（2026-06-12 新增）**：带 EXTREME_PRICE 标志、或相对价差（spread/entry）>
  `PAPER_TRADE_MAX_RELATIVE_SPREAD`(默认10%) 的信号**不**自动入账——长尾价格市场上半个价差即吞掉
  两位数百分比的名义本金，paper PnL 会变成"交易成本测量器"而非信号质量测量器。同一市场同方向
  已存在 OPEN 状态的 AUTO 仓位时，后续扫描产生的新信号不再重复入账（防止每轮扫描堆叠仓位）。
  手动入账不受这些守门限制。
- **A10 数据库**：本地默认 SQLite（aiosqlite）零依赖跑通；Postgres 通过 DATABASE_URL/docker-compose（本机无 docker 环境，
  compose 文件按 Postgres 16 交付但未在本机验证容器运行）。建表用 create_all + seed 脚本，MVP 不引入 Alembic。
- **A11 钱包形态**：v1 仅支持 EOA 直连钱包（signatureType=0，资金在用户 EOA）。不支持 Polymarket 网页代理钱包
  （signatureType 1/2）资金账户。UI 在 trading 页注明。
- **A12 v1 交易形态**：只支持 BUY 开仓（买 YES 或买 NO token）。卖出/平仓走 Polymarket 官方界面；
  因此 close-only 地区在本系统内实际无法发出任何真实订单。
- **A13 scan 状态存进程内存**：单进程部署假设；重启后历史 scan 状态丢失（DB 中信号/快照不丢）。
- **A14 价格快照口径**：market_snapshots.yes_price 优先用 CLOB YES midpoint；订单簿单边/为空时退化用 gamma
  `outcomePrices`，并打 ONE_SIDED_BOOK/PARTIAL_DATA flag。
- **A15 bps 解释**：MAX_SPREAD_BPS/MAX_SLIPPAGE_BPS 中 1bp = 0.0001 价格单位（对 0–1 报价的绝对口径），
  即 300bps=0.03。对预测市场比"相对百分比"更稳定，文档与 Settings 页同口径展示。
- **A16 不引入 pandas**：统计仅需 mean/median/sum，用标准库 `statistics`，减少依赖面（任务书技术栈为"推荐"）。
- **A17 first_seen_at**：取该账户最早 closed-position `timestamp` 与本系统首次观察时间的较早者；均缺失为 NULL。
- **A18 同类目统计的 as_of 一致性**：same_category 统计使用与 overall 相同的 look-ahead 过滤。
- **A19 NEW_ACCOUNT 判定**：`resolved_trade_count_before_signal_time == 0`（按 A3 口径），与"地址注册时间"无关。
- **A20 confidence 公式**：见 scoring.py：0.40×notional 失衡 + 0.25×count + 0.35×dominant 侧平均 smart score − 市场风险惩罚，
  clamp 0–100。仅为透明启发式排序工具，**不是胜率**。
- **A21 Telegram**：仅在 signal_service 留 `notify_hook(signal)` 空实现接口，不实现 bot。
- **A23 国际化（2026-06-12 新增）**：前端为 EN/简体中文 双语，采用轻量自研 i18n
  （`frontend/src/lib/i18n.tsx` 字典 + Context；服务端安全原语在 `lib/locale.ts`），不引入路由级
  locale 或第三方库。语言偏好存浏览器 cookie `pm_locale`（非敏感 UI 偏好，服务端 layout 读取后
  首屏直出所选语言）。两条强制安全文案（manual confirmation / close-only）在中文模式下附带英文原文
  以保持任务书合规。市场问题、类目、后端生成的风控 reason 为数据原文，不翻译。
- **A22 本机地区限制**：开发环境出口 IP 为 SG（close-only），真实下单链路无法在本环境端到端实测；
  代码按官方文档实现并以单测+mock 验证，审计报告如实标注。
