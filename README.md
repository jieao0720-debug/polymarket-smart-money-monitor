# Polymarket 聪明钱量化监控（Smart Money Quant Monitor）

[English Documentation →](README.en.md)

一个连接钱包的 Polymarket 分析工具：自动扫描热门预测市场，对 **YES / NO 双边的 Top 持仓人**
做链上历史画像（已结算仓位的胜率、已实现盈亏、回报率），用透明的规则化评分识别**聪明钱（smart money）**，
聚合成市场级**分析信号**，并通过**模拟交易（paper trading）**持续追踪信号质量。
在显式开启后，也支持**逐笔手动确认**的真实交易（默认完全关闭）。

> **免责声明（请先阅读）**：本项目是分析工具，不构成任何投资建议。信号是对持仓现象的启发式
> 排序，**信心分不是胜率**，历史统计不预示未来结果。预测市场交易可能损失全部本金。
> 本工具严格遵守并执行 Polymarket 的地区限制，绝不提供绕过手段。

---

## ✨ 核心功能

- **热门市场扫描**：拉取 Polymarket 活跃市场，按流动性 / 24h 成交量 / 订单簿状态 / 距结算时间过滤
- **双边 Top 持仓人分析**：每边 Top 20，按当前仓位市值排序，逐户拉取持仓明细
- **账户历史画像（防未来函数）**：基于已结算仓位计算胜率、已实现盈亏、平均回报、开仓金额中位数、
  同类目战绩——任何信号时点只使用该时点**之前**已结算的数据
- **账户标签**：高胜率 / 异常仓位 / 新账户 / 其他（规则全部公开、可单测）
- **聪明钱评分**：六个加权分项 + 六类风险惩罚的透明规则评分（0–100）
- **市场级信号**：双边聪明钱人数与金额、净方向、信心分、风险标签、建议限价与金额上限
- **模拟交易**：合格信号自动按可成交价入账（极端价格/宽价差信号自动跳过、不重复叠仓），可平仓核算盈亏；
  持仓按买一价计价，市场正式结算后自动按兑付价入账
- **持仓监控（影子退出）**：独立于热门扫描，持续追踪入场时跟随的聪明钱账户的仓位保留率，记录退出规则
  “本会怎么做”，但**不执行**任何减仓或平仓，供日后离线回放验证阈值（见 docs/assumptions.md A24–A27）
- **钱包接入与手动真实交易**：wagmi/viem 连接钱包（只读地址 + EIP-712 签名，**绝不接触私钥**），
  地区限制 / 余额 / 授权检查，两道服务端风控 + 手动确认勾选，`ENABLE_LIVE_TRADING` 默认 `false`
- **双语界面**：English / 简体中文，侧边栏或设置页一键切换

## 🧱 技术栈

后端 FastAPI · Python 3.11 · SQLAlchemy 2（async）· pydantic v2 ——
前端 Next.js 15 · TypeScript · Tailwind CSS v4 · wagmi/viem · Recharts ——
数据库 SQLite（本地零配置）/ PostgreSQL 16（docker-compose / 生产）——
数据源均为 Polymarket 官方 API（Gamma / Data-API / CLOB / Geoblock）

---

## 🚀 如何使用和打开

### 0. 克隆与准备（首次一次性）

要求：Python 3.11+、Node.js 18.18+。

```bash
git clone https://github.com/jieao0720-debug/polymarket-smart-money-monitor.git
cd polymarket-smart-money-monitor

# 安装后端依赖（二选一）
cd backend
python3.11 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
# 或使用 uv（更快）：uv venv --python 3.11 .venv && uv pip install -r requirements-dev.txt --python .venv/bin/python
cd ..

# 安装前端依赖
cd frontend && npm install && cd ..
```

### 1. 启动后端（端口 8000）

```bash
cd backend
.venv/bin/python -m uvicorn app.main:app --reload
```

看到 `Uvicorn running on http://127.0.0.1:8000` 即成功，保持该终端开着。

- 健康检查：浏览器打开 **http://localhost:8000/api/health** （显示 `"status":"ok"`）
- 交互式 API 文档：**http://localhost:8000/api/docs**

### 2. 启动前端（端口 3000，另开一个终端）

```bash
cd frontend
npm run dev
```

看到 `Ready in ...` 后，浏览器打开 **http://localhost:3000**

### 3. 开始使用

1. 打开 http://localhost:3000 进入**仪表盘**，左下角可切换 EN / 中文
2. 点击**「运行扫描」**——拉取真实 Polymarket 数据并分析（约需几分钟）
3. 扫描完成后：市场列表 → 点进任意市场看**双边 Top 持仓人 + 聪明钱概览** → 点地址看**账户画像抽屉**
4. **信号记录** 页查看历史信号；**模拟交易** 页查看自动入账的仓位与盈亏
5. 不想连真实 API？注入离线演示数据：`cd backend && .venv/bin/python ../scripts/seed.py`（后端停止时执行）

> 端口被占用时：`pkill -f "uvicorn app.main:app"`（清后端）、`pkill -f "next dev"`（清前端）后重新启动。

---

## ⚙️ 环境变量（可选）

复制根目录 `.env.example` 为 `backend/.env` 后修改；不配置也能运行（SQLite + 安全默认值）。关键项：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `ENABLE_LIVE_TRADING` | `false` | 真实下单总闸门（请先读 docs/risk-control.md 再考虑开启） |
| `MAX_TRADE_NOTIONAL` | `100` | 单笔金额上限（USDC） |
| `MAX_SPREAD_BPS` / `MAX_SLIPPAGE_BPS` | `300` / `100` | 价差 / 滑点上限 |
| `CLOSE_ONLY_COUNTRIES` | `PL,SG,TH,TW` | 官方仅平仓地区名单 |
| `SCANNER_MAX_MARKETS` | `15` | 单次扫描分析的市场数 |
| `DATABASE_URL` | SQLite | 生产可填 PostgreSQL 连接串 |

前端：`frontend/.env.local` 中 `NEXT_PUBLIC_API_BASE=http://localhost:8000`（默认即此）。

## 🧪 测试与构建

```bash
cd backend  && .venv/bin/python -m pytest -q   # 125 passed
cd backend  && .venv/bin/ruff check app/        # 无告警
cd frontend && npm test                         # 35 passed（vitest）
cd frontend && npm run typecheck && npm run lint && npm run build
```

## 📦 部署

- 本地一键（含 PostgreSQL）：`docker-compose up`
- 后端 → Render / Railway（自带 Dockerfile，健康检查 `GET /api/health`）
- 前端 → Vercel（设置 `NEXT_PUBLIC_API_BASE` 指向后端地址）
- 数据库 → Supabase / Railway Postgres（填入 `DATABASE_URL`）

详见 [README.en.md](README.en.md) §14 与 [docs/architecture.md](docs/architecture.md)。

## 🔒 安全与风控设计

- 私钥零接触：前后端无任何私钥输入/存储/传输路径，签名只发生在你自己的钱包内
- 真实交易默认关闭，闸门在**服务端**强制；开启后每笔订单仍需手动勾选确认 + 钱包签名
- 两道风控：地区限制（fail-closed）→ 市场状态 → 价差/滑点/金额上限 → 余额/授权，下单前后各查一遍
- 地区为 blocked 禁止交易；close-only（如新加坡）禁止开新仓——无任何绕过开关
- 日志自动脱敏（签名/密钥/口令），API 错误不泄露堆栈

## 📚 文档

[产品规格](docs/product-spec.md) · [架构](docs/architecture.md) · [API 契约](docs/api-contract.md) ·
[数据库设计](docs/database-schema.md) · [风控规范](docs/risk-control.md) ·
[数据口径与不确定项](docs/data-field-uncertainties.md) · [假设记录](docs/assumptions.md) ·
[最终审计报告](docs/final-audit-report.md)

## ⚠️ 已知限制（节选）

账户历史最多取最近 200 笔已结算仓位（截断会标注）；“开仓成本”为近似口径（界面已注明）；
同类目匹配基于关键词；真实下单链路已完整实现并测试，但未对生产 CLOB 实测（开发环境位于
仅平仓地区，工具本身拒绝在此下单）；v1 仅支持 EOA 钱包、仅买入开仓、仅二元 Yes/No 市场。
完整清单见 [README.en.md](README.en.md) §15。

---

仅供研究与学习使用，按现状提供，不含任何担保。**不构成投资建议。**
