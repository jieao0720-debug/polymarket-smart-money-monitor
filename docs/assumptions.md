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
- **A24 模拟仓位按买一价计价（2026-10-20 新增）**：OPEN 模拟仓位的 `current_price`/浮动盈亏、手动平仓的
  默认价格，一律用持有方向的**买一价**（卖出实际能拿到的价格），不再用中间价；手动入账默认价改为该方向
  卖一价（与 A9 自动入账一致）。价格取最新扫描快照与最新持仓监控观察中**较新**的一个；两者都没有买一价时
  才退回中间价，并在接口中以 `price_basis=MIDPOINT` 标出。快照的 `orderbook_depth` 自此按方向记录
  `best_bid`/`best_ask`；此前的旧快照只有 YES 方向的买一价。
- **A25 结算入账**：仅当 Gamma 市场 `closed=true`，且 `outcomePrices` 是合法兑付向量（1/0、0/1 或 0.5/0.5），
  才按官方兑付价平仓（`exit_reason=RESOLVED`，`exit_time` 取 `closedTime`，缺失则取观察时间）。
  `umaResolutionStatus` 存在时必须为 `resolved`；该字段缺失时只接受精确 1/0（50/50 不推断）。
  到达 `endDate` 或 `closed=true` 但价格非兑付值的市场记为 `AWAITING_RESOLUTION`，**不平仓**。
- **A26 入场跟随名单**：开仓时冻结入场信号快照中、所买方向上的聪明钱账户（与 A8 同一判定），写入
  `paper_trade_cohort`；此后按地址独立查询 `/positions?user=&market=`，即使账户掉出前 20 也继续追踪。
  净敞口 = 本方向份额 − 反方向份额（单位为份额，不用市值，避免把价格下跌误判为撤退）；入场时的反方向份额
  取同一快照另一侧前 20，不在榜上按 0 计。权重 ∝ 入场时本方向持仓价值，合计为 1。
  仓位保留率 `R = Σ w·min(1, max(0, e_t)/e_0)`，只在**可获取数据**的账户上计算，并报告其权重合计
  `coverage`；查询失败记为 UNKNOWN，绝不当作清仓。`/positions` 返回空列表视为已知清仓。
  监控上线前已存在的 OPEN 仓位，由监控首次运行时按同一规则从 `market_holders`/`account_labels` 回填
  （`source=BACKFILL`）；没有信号的手动仓位没有跟随名单。
- **A27 影子退出（只记录，不执行）**：持仓监控独立于热门扫描，覆盖全部 OPEN 模拟仓位；每轮写一条
  `position_observations`，记录买一价、按买盘深度卖出的可变现价值与成交比例（扣 `PAPER_EXIT_FEE_BPS`）、
  R/coverage、入场后最新扫描方向，以及影子规则的结果：R<0.70 → 降至 50%；R<0.40、入场后扫描方向反转、
  可变现收益率 ≤ −25% → 降至 0。每条规则须**连续 2 次**确认；数据不可用（coverage<0.70、无买盘）时
  该规则的连续计数保持不变；目标仓位只降不升。阈值为待回放验证的起始参数，**任何影子结果都不会改变仓位**——
  监控唯一会改变仓位状态的动作是 A25 结算。尚未接入 `/activity` 成交类型确认，也未实现止盈和持有期限。
