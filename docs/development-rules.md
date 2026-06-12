# Development Rules（强制）

## 交易安全红线

1. **不允许自动交易。** 任何代码路径不得在没有"用户本次手动确认 + 前端钱包签名"的情况下提交订单。
   scheduler、scanner、signal、paper trade 模块**禁止 import** `order_submit_service`。
2. **不允许保存私钥。** 后端/前端/数据库/日志/localStorage 不得出现 private key、助记词、raw key 材料。
   前端不得渲染任何"输入私钥"的 UI。CLOB API credentials 仅允许内存中单请求使用，不持久化、不打日志。
3. `ENABLE_LIVE_TRADING` 默认 `false`；order submit 路径必须在**后端**硬检查该开关（前端禁用按钮只是 UX，不是安全边界）。
4. geoblock fail-closed：检查失败一律视为 blocked。blocked 不得下单；close-only 不得开新仓。不得提供任何绕过手段。

## API contract 优先

5. 改接口先改 `/docs/api-contract.md`，再改后端 `schemas/`，再改前端 `src/types/api.ts`，三处字段必须一致（snake_case 贯穿 API 层）。
6. 错误一律走统一信封 `{"error":{code,message,details}}`；不得向客户端泄露 stack trace。

## 数据口径优先

7. 外部字段只在 `services/normalization.py`（及 clients 的薄返回层）出现；业务逻辑只消费 Normalized* 模型。
8. Yes/No 方向**永远**通过 `outcomes[]` 与 `clobTokenIds[]`/`outcomeIndex` 的索引对齐推导，禁止假设 index 0 = YES。
   非二元（非 Yes/No outcome）市场在 v1 一律跳过并记 warning。
9. 严格区分：`shares`（token 数量）/ `current_position_value`（USDC 现值）/ `average_price`（开仓均价）/
   `entry_notional`（开仓成本 = avgPrice×totalBought）。变量命名必须自证口径；近似值必须带 `_approx` 后缀并在 UI 标注。
10. 任何账户历史统计函数必须接受 `as_of` 参数并过滤 `timestamp <= as_of AND endDate <= as_of`（look-ahead 防护）。
    禁止用信号时点之后才 resolved 的结果评估该信号。
11. 字段含义不确定 → 写入 `/docs/data-field-uncertainties.md` + 代码注释引用编号，不得硬编码猜测。
12. 价格必须校验 0–1；金额必须为正且受 env 上限约束；wallet address 必须正则校验 `^0x[0-9a-fA-F]{40}$`。

## 工程纪律

13. 测试必须覆盖关键逻辑：标签分类、anomaly index、score 分项、scanner 过滤、方向归一、look-ahead 防护、
    geoblock/close-only 强制、live trading 默认关闭、ticket/paper trade 流程、API schema。
14. 外部 HTTP 调用必须有 timeout + 幂等 GET 重试（指数退避）+ api_fetch_logs 记录；`POST /order` 永不自动重试。
15. 上游失败返回 partial data + `warnings[]`，不许让整页 5xx。
16. 前端所有请求经 `lib/api-client.ts`；组件内禁止散写 fetch；不得 console 输出签名 payload/凭证。
17. 信号相关 UI 文案必须用 "analysis signal"；`confidence_score` 不得表述为胜率/win probability。
18. 提交物中不得包含 `.env`（`.gitignore` 强制）；`.env.example` 不含真实 secret。
