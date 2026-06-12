# Architecture — Polymarket Smart Money Quant Monitor

## 1. 总览

```
┌──────────────────────────┐        ┌───────────────────────────────┐
│  Frontend (Next.js 15)   │  HTTP  │  Backend (FastAPI, async)     │
│  TS / Tailwind / wagmi   │ ─────► │  /api/* （REST, JSON）        │
│  Vercel 部署             │        │  Render/Railway 部署          │
└──────────┬───────────────┘        └──────┬─────────────┬──────────┘
           │ 钱包签名（viem signTypedData） │             │
           ▼                               ▼             ▼
   用户钱包 (MetaMask 等)        PostgreSQL/SQLite   Polymarket APIs
   私钥永远只在钱包内             (SQLAlchemy 2 async)  Gamma / Data-API /
                                                      CLOB / Geoblock
                                                      + Polygon JSON-RPC
```

- 单进程后端，APScheduler 可选定时扫描；扫描也可由 `POST /api/scanner/run` 手动触发（后台 task）。
- 前端不直接调 Polymarket API（CORS 与口径统一），一切经后端。例外：钱包余额也可由 wagmi 直接读链（展示用），后端 RPC 读数为准。

## 2. 前端架构

- Next.js 15（App Router）+ TypeScript + Tailwind CSS v4。
- UI 组件：本地实现的 shadcn 风格组件（`src/components/ui/*`：button/card/badge/table/dialog/drawer/skeleton/select/switch/tooltip 等），不引入 shadcn CLI，保持依赖轻量。风格：专业金融 Dashboard。
- 图表：Recharts（YES vs NO smart money notional 等）。
- 数据获取：`@tanstack/react-query`；所有请求经 `src/lib/api-client.ts`（统一 base URL、错误信封解析、超时）。组件内禁止散写 fetch。
- 钱包：wagmi v2 + viem（injected connector，Polygon mainnet 137）。仅 `eth_requestAccounts` + `signTypedData`，**绝不**要求/接触私钥；不在 console 打印 signed payload。
- 类型：`src/types/api.ts` 与 `/docs/api-contract.md` 一一对应。
- 页面状态：每页都有 loading skeleton / empty state / error state；表格支持排序；地址可复制、缩短展示。
- 国际化：EN/简体中文双语（A23）。自研字典式 i18n（`lib/i18n.tsx`，server-safe 原语在 `lib/locale.ts`），
  语言偏好存 `pm_locale` cookie 由服务端 layout 读取，首屏即为所选语言；侧边栏与 Settings 页均有切换入口。

## 3. 后端架构

```
backend/app/
  main.py                 # FastAPI app、CORS、异常处理、lifespan（DB init + scheduler）
  core/
    config.py             # pydantic-settings，全部环境变量（含风控阈值）
    errors.py             # AppError + 统一错误信封 {"error":{code,message,details}}
    logging_utils.py      # 日志脱敏 filter（signature/secret/key/passphrase）
  db/  session.py, base.py, init_db.py
  models/                 # SQLAlchemy 2.0 models（11+ 张表，见 database-schema.md）
  schemas/                # pydantic v2 响应/请求模型（与 api-contract.md 对齐）
  clients/                # 外部 API 客户端（全部 async httpx，timeout+retry+fetch log）
    base.py               # BaseHTTPClient：超时、指数退避重试、api_fetch_logs 记录、并发信号量
    gamma_client.py       # gamma-api.polymarket.com
    data_client.py        # data-api.polymarket.com
    clob_client.py        # clob.polymarket.com（含 POST /order，仅在 live 开启时可达）
    geoblock_client.py    # polymarket.com/api/geoblock
    polygon_rpc_client.py # eth_call: USDC balanceOf / allowance（手工 ABI 编码，无 web3 依赖）
    clob_auth.py          # L2 HMAC 请求头构造（不持久化任何凭证）
  services/
    normalization.py      # ★ 唯一的外部字段 → 内部模型转换层（Yes/No 方向、价格、book）
    market_scanner_service.py   # 扫描编排：拉市场→过滤→逐市场分析→落库→生成信号
    holder_analysis_service.py  # 双边 top holders + 每户当前市场仓位
    account_profile_service.py  # closed-positions 分页拉取 + as_of 统计（防 look-ahead）
    smart_money_service.py      # 账户分类（4 标签）+ scoring.py 分项 + 总分
    scoring.py                  # score 分项函数（每项独立、可单测）
    signal_service.py           # 市场级聚合：方向/confidence/risk flags/建议价与额度
    paper_trade_service.py      # 信号自动入账、手动记录、平仓 PnL
    trading_risk_service.py     # 8 项风控检查（geoblock/market/spread/notional/balance/allowance/live flag/价格合法性）
    order_submit_service.py     # 二次风控 + ENABLE_LIVE_TRADING 闸门 + CLOB 提交
    scan_registry.py            # 进程内 scan 状态注册表
  api/routes/             # scanner, markets, accounts, signals, trade_tickets, paper_trades, trading, health, settings
  tests/                  # pytest（anyio），fake clients 注入
```

- **依赖注入**：clients 经 `api/deps.py` provider 暴露，service 构造时注入 → 测试用 Fake clients 覆盖。
- **Normalization 原则**：业务逻辑只消费 `NormalizedMarket / NormalizedBook / NormalizedHolder / NormalizedPosition / NormalizedClosedPosition / GeoblockStatus`，外部 camelCase/JSON-string 字段只在 normalization.py 出现。
- **错误处理**：外部调用失败 → 记录 api_fetch_logs → service 返回 partial 结果并在响应 `warnings[]` 标注；HTTP 层错误统一信封，不泄露 stack trace。

## 4. 数据库架构

- SQLAlchemy 2.0 async。本地默认 `sqlite+aiosqlite:///./data/polymarket_monitor.db`（零依赖跑通）；
  生产 `DATABASE_URL=postgresql://...`（自动改写为 `postgresql+asyncpg://`）。docker-compose 提供 Postgres 16。
- 建表：启动时 `create_all`（MVP 不引入 Alembic，见 assumptions.md）；`scripts/seed.py` 注入演示数据。
- 金额/价格用 Float（MVP），口径见 database-schema.md；生产建议迁移 Numeric（见 known limitations）。

## 5. Polymarket API 接入方式（实测验证于 2026-06-11）

| Client | Base | 用途 | 关键端点 |
| --- | --- | --- | --- |
| gamma_client | `https://gamma-api.polymarket.com` | 市场/事件元数据、热门排序 | `GET /markets?active=true&closed=false&order=volume24hr&ascending=false&limit=N`；`GET /events?id=` |
| data_client | `https://data-api.polymarket.com` | holders、持仓、resolved 历史 | `GET /holders?market=<conditionId>&limit=20`（上限 20）；`GET /positions?user=&market=`；`GET /closed-positions?user=&limit=50&offset=&sortBy=TIMESTAMP` |
| clob_client | `https://clob.polymarket.com` | 订单簿/价格/下单 | `GET /book?token_id=`、`/midpoint`、`/spread`、`/price?side=`；`POST /order`（L2 HMAC 头） |
| geoblock_client | `https://polymarket.com/api/geoblock` | 地区限制 | 返回 `{blocked, ip, country, region}` |
| polygon_rpc_client | `POLYGON_RPC_URL`（默认 polygon-rpc.com） | USDC.e 余额/授权 | `eth_call` balanceOf / allowance |

字段口径与不确定项详见 `data-field-uncertainties.md`。重试策略：GET 幂等请求最多 3 次指数退避；`POST /order` **绝不自动重试**（防重复下单）。

## 6. 钱包连接方式

- wagmi injected connector（MetaMask 等浏览器钱包），目标链 Polygon (137)。
- 前端仅获取 address、签名（EIP-712 `signTypedData`）。**第一版仅支持 EOA 直连钱包（signatureType=0）**，
  不支持 Polymarket 网页代理钱包（signatureType 1/2）——见 assumptions.md。
- CLOB 鉴权流（live 模式）：前端用钱包签 `ClobAuth` EIP-712 → 后端代理 `derive-api-key` → 凭证仅在内存中用于本次请求头构造，**不落库、不写日志、不进 localStorage**。
- 合约常量（Polygon mainnet，公开已知）：
  - USDC.e: `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174`
  - CTF Exchange: `0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E`
  - Neg-Risk CTF Exchange: `0xC5d563A36AE78145C45a50134d48A1215220f80a`
  - Conditional Tokens: `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045`

## 7. Trading Safety Architecture

```
用户点击 Generate Trade Ticket
   └► POST /api/trade-tickets ── trading_risk_service.run_checks()（第一道）
         geoblock → market active/closed → spread ≤ MAX_SPREAD_BPS → liquidity ≥ MIN_LIQUIDITY
         → limit_price ∈ (0,1) 且与盘口偏离 ≤ MAX_SLIPPAGE_BPS → notional ≤ MAX_TRADE_NOTIONAL
         → live_trading_enabled 状态注入响应
   └► 前端 Modal 展示全部检查结果；任何 blocker → Confirm 按钮禁用
   └► 用户勾选 manual confirmation → POST /api/trade-tickets/{id}/confirm（记录 confirmed_at）
   └► 前端钱包 signTypedData(Order) → POST /api/trading/orders/submit
         └► order_submit_service：ticket 状态校验 + 风控全量复检（第二道）
             + ENABLE_LIVE_TRADING==true 硬闸门（默认 false → 403 LIVE_TRADING_DISABLED）
             + balance/allowance 复核 → CLOB POST /order → 保存 order_id/status
```

- geoblock fail-closed：geoblock 接口请求失败时按 **blocked** 处理，禁止开仓。
- close-only（官方名单 PL/SG/TH/TW，env 可调）：can_open=false、can_close=true；开新仓票据直接拒绝。
- 后端无任何自动下单代码路径；scheduler 只做扫描，不触达 order_submit_service。

## 8. Deployment Architecture

- Frontend → Vercel（环境变量 `NEXT_PUBLIC_API_BASE`）。
- Backend → Render/Railway（Docker，`backend/Dockerfile`，`GET /api/health` 健康检查）。
- DB → Supabase / Railway Postgres（`DATABASE_URL`）。
- 本地：`docker-compose up`（postgres + backend）或裸跑 uvicorn + sqlite。详见 README Deployment 章节。

## 9. 目录结构偏差说明

与任务书结构一致；补充说明：pytest 套件位于 `backend/app/tests/`（与任务书一致），根目录 `/tests/README.md`
指明测试位置；前端组件测试位于 `frontend/src/__tests__/`（vitest）。
