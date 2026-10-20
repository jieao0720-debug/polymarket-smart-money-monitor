# Data Field Uncertainties（Polymarket 字段口径：已验证 / 不确定项）

实测时间 **2026-06-11**（curl 直连生产 API + docs.polymarket.com 官方文档）。
代码注释引用格式：`# UNCERTAINTY-n`。每项给出：现状、我们的处理、后续验证方法。

## 已实测确认（高置信）

- **V1 Gamma `/markets`**：`outcomes`、`outcomePrices`、`clobTokenIds` 是 **JSON 编码字符串**（非数组），
  三者按索引对齐；`outcomes` 不保证 ["Yes","No"] 顺序 → 必须按值匹配映射方向（normalization 层完成）。
  `volumeNum/liquidityNum` 为数值版字段；`volume24hr` 数值；`active/closed/acceptingOrders/negRisk/orderPriceMinTickSize` 存在。
- **V2 Data-API `/holders?market=<conditionId>&limit=20`**：按 token 分组返回，`holders[].amount` 实测为 **shares**
  （官方文档未注明单位；NO 侧账户 amount=20.8M 而该 token 价格 0.9985，若是 USD 不可能）→ 以 shares 处理。limit 官方上限 20。
- **V3 Data-API `/positions`**：字段 `size/avgPrice/initialValue/currentValue/cashPnl/realizedPnl/curPrice/redeemable/outcome/outcomeIndex/oppositeAsset/endDate/negativeRisk` 实测存在；支持 `user`、`market`(conditionId csv)、`limit`、`sortBy=CURRENT` 等参数。
- **V4 Data-API `/closed-positions`**：官方文档确认：`timestamp` = "when the position closed"；
  `limit` 上限 50/页，`offset` 上限 100000；`sortBy ∈ {REALIZEDPNL, TITLE, PRICE, AVGPRICE, TIMESTAMP}`、`sortDirection`。
  字段 `avgPrice/totalBought/realizedPnl/curPrice(0|1)/endDate/outcome` 实测存在。
- **V5 CLOB**：`/book` bids/asks 为字符串 price/size；**数组排序不可依赖**（实测 asks 自高到低排列）→
  best_bid=max(bids)、best_ask=min(asks) 计算。`/midpoint→{mid}`、`/spread→{spread}`、`/price?side=buy→{price}`(=best bid)。
  `POST /order` 需 L2 HMAC 头（POLY_API_KEY/POLY_SIGNATURE/POLY_TIMESTAMP/POLY_PASSPHRASE/POLY_ADDRESS），
  body 含 order 结构（salt/maker/signer/taker/tokenId/makerAmount/takerAmount/expiration/nonce/feeRateBps/side/signatureType/signature）+ owner(api key uuid) + orderType(GTC/FOK/GTD/FAK)。
- **V6 Geoblock**：`GET https://polymarket.com/api/geoblock` → `{blocked, ip, country, region}` 实测可用
  （本机 SG 返回 blocked=true）。官方文档：close-only 国家 = **PL/SG/TH/TW**；完全屏蔽含 US/RU/CU/IR/KP 及
  Ontario、Crimea/Donetsk/Luhansk 等区域；日本为前端限制。

## 不确定 / 近似项（必须知悉）

- **U1 `blocked` 与 close-only 的关系**：geoblock 接口对 close-only 国家（SG 实测）也返回 `blocked=true`，
  接口本身不区分两种模式。处理：country ∈ CLOSE_ONLY_COUNTRIES(env, 默认官方名单) → CLOSE_ONLY，否则 BLOCKED。
  风险：官方名单变更需同步 env。验证方法：关注 docs.polymarket.com/api-reference/geoblock 更新。
- **U2 `closed-positions.timestamp` 精确语义**：官方说 "when the position closed"，实测一例 timestamp(01-13) >
  endDate(01-01)，推测为结算/赎回确认时间。处理：look-ahead 过滤同时要求 timestamp≤as_of 且 endDate≤as_of（保守）。
- **U3 "opening amount" 不可直接获得**：`/positions.initialValue` = 当前持仓成本（avgPrice×size），
  非严格"首次开仓金额"（加减仓后漂移）。处理：字段命名 `entry_notional_approx`，anomaly_index 用它做分子，
  UI 注明口径。验证方法：用 `/trades?user&market` 重建首笔买入（v2 工作量大，暂不做）。
- **U4 holders 端点无价格/价值**：只有 shares。current_position_value 必须二次拉 `/positions?user=&market=`；
  该调用失败时退化 shares×current_price 并置 `value_is_approx=true`。
- **U5 市场级 open_interest 缺失**：gamma market 对象无 OI；event 对象有 `openInterest`（事件级，可能涵盖多市场）。
  处理：存 event 级 OI 并在 UI 标注 "event-level OI"。备选：data-api `/oi`（misc Get open interest）后续验证。
- **U6 类目体系**：gamma market.category 实测为 null；类目信息在 event.tags。处理：A5 关键词映射，主类目取
  tags 与已知顶级类目交集的第一个，否则第一个非 meta tag。属近似。
- **U7 `/positions?closedOnly=true` 参数无效**（实测仍返回开放仓位）→ 不使用；resolved 历史一律走 `/closed-positions`。
- **U8 closed-positions 是否含未平稳但已 resolve 未 redeem 的仓位**：实测含 curPrice∈{0,1} 的已结算仓位，
  与 `/positions?redeemable=true`（已结算未赎回）存在衔接窗口期口径问题——刚结算未进 closed-positions 的仓位可能两边短暂不一致。
  处理：v1 只采 closed-positions；统计可能轻微滞后（偏保守）。
- **U9 Data-API 限流策略未公开**：处理：并发信号量(默认8)+重试退避+ SCANNER_MAX_MARKETS 默认 15 + 账户画像 TTL 缓存(6h)。
  风险：大规模扫描可能 429，已在 api_fetch_logs 记录并 partial 降级。
- **U10 CLOB `feeRateBps`/`taker` 默认值**：公开市场单按惯例 taker=0x0、feeRateBps=0（实测 gamma `takerBaseFee=1000`
  存在于部分市场对象，含义与下单 feeRateBps 的关系未完全确认）。处理：下单构造时 feeRateBps 取 CLOB
  `GET /markets/{condition_id}`（或保守 0），live 启用前需以小额实单验证。**本环境（SG close-only）无法实测下单链路。**
- **U11 `liquidityNum` 的精确定义**（做市深度的聚合口径）官方未给公式。处理：仅作相对筛选阈值用，不作绝对额度依据；
  额度建议另用订单簿 top3 深度。
- **U12 Polygon 合约地址**：USDC.e/CTF Exchange/NegRisk Exchange 取自官方文档与公开部署记录（高置信但未在本项目内
  以链上调用验证 allowance 目标的正确性）。live 启用前用 polygonscan 核对一次。
- **U13 `profile_name`**：data-api 返回 `name` 与 `pseudonym` 两字段，公开展示规则由 `displayUsernamePublic` 控制；
  我们优先 name(若 displayUsernamePublic) 否则 pseudonym。仅展示用途。
- **U14 Gamma 结算字段**：`umaResolutionStatus`（如 `resolved`/`proposed`）、`closedTime`、`closed` 后的 `outcomePrices`
  2026-10-20 用一个已结算市场实测（gamma id 2270330：`closed=true`、`outcomePrices=["1","0"]`、
  `umaResolutionStatus="resolved"`、`closedTime="2026-06-18 00:32:19+00"`，注意已结算时 `active` 仍为 true），
  字段与解析一致；50/50 结算与争议中市场的字段形态仍未实测。处理：结算判定取保守口径（见 assumptions A25），
  任一条件不满足即保持 OPEN 并标 AWAITING_RESOLUTION。
- **U15 `/positions` 小额门槛**：Data-API 默认 `sizeThreshold` 会过滤极小持仓，低于门槛的残余份额会被视为 0。
  对跟随名单的保留率影响可忽略（入场账户都是大额持仓）。
