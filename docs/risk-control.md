# Risk Control（真实交易风控规范）

## 0. 总闸门

- `ENABLE_LIVE_TRADING=false`（默认）。订单提交端点在执行任何上游调用前先检查；关闭时返回
  403 `LIVE_TRADING_DISABLED` 并把 ticket 置为 REJECTED。该检查在**后端** `order_submit_service` 内强制。
- 即使开启，仍必须逐项通过下列检查（两道：ticket 创建时 + 订单提交时全量复检）。

## 1. Geoblock

- 数据源：`GET https://polymarket.com/api/geoblock` → `{blocked, ip, country, region}`（按服务器出口 IP）。
- 模式判定：
  - `blocked=false` → `OK`（可开可平）。
  - `blocked=true` 且 country ∈ `CLOSE_ONLY_COUNTRIES`（默认 `PL,SG,TH,TW`，官方文档名单）→ `CLOSE_ONLY`：
    can_open=false，can_close=true。**v1 只支持开仓（BUY 开新仓），因此 close-only 地区实际无法提交任何订单。**
  - `blocked=true` 其余 → `BLOCKED`：禁止一切下单。
- **fail-closed**：geoblock 请求超时/失败 → 视为 BLOCKED（响应带 `fail_closed: true`）。
- 不提供任何代理/绕过配置；不允许用户侧参数覆盖 geoblock 结果（仅测试环境可用 `GEOBLOCK_FORCE_MODE` 模拟，
  生产部署必须留空，.env.example 注明）。

## 2. 市场状态检查

- `active == true`、`closed == false`、`accepting_orders == true`、`end_date > now`，否则 400 `MARKET_NOT_TRADABLE`。
- 数据新鲜度：ticket 创建时实时拉 gamma+CLOB 确认；提交时复检。

## 3. Spread 检查

- YES token 盘口 `spread = best_ask - best_bid`；要求 `spread <= MAX_SPREAD_BPS / 10000`（默认 300 bps = 0.03 价格单位）。
- 盘口单边缺失（无 bid 或无 ask）→ ONE_SIDED_BOOK，禁止下单。

## 4. Slippage / 价格合法性

- `0 < limit_price < 1`，且对齐市场 tick_size。
- BUY：`limit_price <= min(best_ask, midpoint * (1 + MAX_SLIPPAGE_BPS/10000))`，防止追价超滑点上限。
- limit_price 不得低于 best_bid×(1−50%)（明显错价保护）。

## 5. Notional 限制

- `0 < max_notional <= MAX_TRADE_NOTIONAL`（默认 100 USDC）。
- 同时建议值受流动性约束：`suggested_max_notional = min(MAX_TRADE_NOTIONAL, 1% × liquidity, 25% × top3 ask depth)`。

## 6. 余额检查（提交时，live 模式）

- Polygon RPC 读 USDC.e `balanceOf(wallet)`；要求 `balance >= max_notional`。RPC 失败 → 拒绝提交（fail-closed）。

## 7. Allowance 检查（提交时，live 模式）

- `allowance(wallet → CTF Exchange)`（negRisk 市场用 Neg-Risk Exchange 地址）`>= max_notional`，否则拒绝并提示用户先在钱包侧 approve（本系统不代发 approve 交易）。

## 8. Manual Confirmation

- 前端 checkbox 明示 "This is not automated trading. You are manually confirming this order."
- `POST /trade-tickets/{id}/confirm` 必须显式传 `manual_confirmation: true`，记录 `confirmed_at`。
- 未确认的 ticket 不接受提交；ticket 创建后 `TICKET_TTL_MINUTES`（默认 10 分钟）过期 → EXPIRED（防陈旧价格）。

## 9. Order Status 处理

- CLOB 响应 `success/orderID/status(live|matched|delayed)/errorMsg` → 存入 trade_tickets
  （status=SUBMITTED，order_id、clob_status；errorMsg → FAILED + error_message）。
- 提交超时/网络错误：**不自动重试**（防重复下单），ticket → FAILED，提示用户在 Polymarket 端核对后再操作。

## 10. 前端 Confirm 按钮禁用条件（UX 层，非安全边界）

wallet 未连接 / geoblock BLOCKED / CLOSE_ONLY 且为开仓 / 后端任一风控失败 / live trading 关闭（提示走 paper）/
manual confirmation 未勾选 / ticket 过期。

## 11. 风控检查清单（代码 ↔ 文档对照）

| 检查 | 实现 | 时点 |
| --- | --- | --- |
| live_trading_enabled | order_submit_service + settings | 提交（硬闸门）；创建时注入状态 |
| geoblock / close-only | trading_risk_service.check_geoblock | 创建 + 提交 |
| market active/closed/accepting/end_date | check_market_state | 创建 + 提交 |
| spread ≤ 上限 / 单边盘口 | check_spread | 创建 + 提交 |
| liquidity ≥ MIN_LIQUIDITY | check_liquidity | 创建 + 提交 |
| limit_price 合法 + 滑点 | check_price | 创建 + 提交 |
| notional ≤ 上限 | check_notional | 创建 + 提交 |
| balance ≥ notional | check_balance | 提交（live） |
| allowance ≥ notional | check_allowance | 提交（live） |
| manual confirmation | ticket.confirm 端点 | 确认 |
| ticket 未过期/状态机合法 | order_submit_service | 提交 |
