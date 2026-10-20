# Polymarket Smart Money Quant Monitor

[中文文档 →](README.md)

A wallet-connected analytics tool for Polymarket: it scans hot markets, profiles the
top holders on **both** the YES and NO side from their on-chain resolved history,
derives transparent rule-based **smart money scores**, aggregates them into
market-level **analysis signals**, tracks every signal via **paper trading**, and —
only when explicitly enabled — supports **manually confirmed** real trading with a
hard multi-layer risk gate.

> **Disclaimer (read first):** This is an analysis tool, not financial advice.
> Signals are heuristic observations of positioning; confidence scores are **not win
> probabilities**. Historic performance does not predict outcomes. Trading prediction
> markets can lose your entire stake. Respect your local regulations — this tool
> enforces, and never bypasses, Polymarket's geographic restrictions.

---

## 1. Core features

- **Hot-market scanner** — pulls active Gamma markets, filters by liquidity / 24h
  volume / order-book state / time-to-resolution, analyzes the top N by volume.
- **Top-holders analysis** — top 20 holders per side (Data-API cap), ranked by
  `current_position_value`, enriched with per-account position data.
- **Account profiling (look-ahead safe)** — resolved history from `/closed-positions`:
  win rate, realized PnL, average ROI, median entry notional, same-category slices.
  Stats at any signal timestamp use only positions resolved **before** it.
- **Account labels** — `NEW_ACCOUNT` / `HIGH_WIN_RATE` / `ABNORMAL_POSITION` / `OTHER`
  per strict documented rules.
- **Smart money score** — transparent weighted rule-based score (0–100) with itemized
  penalties; every component is a separate, unit-tested function.
- **Market signals** — per-market YES/NO smart-money counts & notional, net direction,
  confidence (analysis aid), risk flags, suggested limit price & max notional.
- **Paper trading** — qualifying signals auto-log at the side's best ask (honest
  taker price); extreme-price / wide-relative-spread signals are skipped and re-scans
  never stack duplicate open positions, so paper PnL measures signal quality rather
  than spread cost; manual entries; open positions are marked at the side's best bid,
  and settle automatically at the official payout once the market resolves.
- **Position monitor (shadow exits)** — independent of the hot-market scan; tracks
  how much of their entry position the followed smart-money accounts still hold, and
  records what the exit rules *would* do without ever reducing or closing a position,
  so thresholds can be replayed offline (docs/assumptions.md A24–A27).
- **Wallet & manual live trading** — wagmi/viem wallet connect (address + EIP-712
  signatures only), geoblock/balance/allowance display, trade tickets with two-pass
  backend risk checks and an explicit manual confirmation step.
  `ENABLE_LIVE_TRADING=false` by default.
- **Bilingual UI** — English / 简体中文, switchable from the sidebar or Settings
  (cookie-persisted; mandated safety statements always include the English original).

## 2. Architecture

```
Next.js 15 dashboard (Vercel)  ──HTTP──►  FastAPI backend (Render/Railway)
  wagmi/viem wallet signing                 ├─ normalization layer (single point of
                                            │   Polymarket field interpretation)
                                            ├─ scanner / profiling / scoring services
                                            ├─ trading risk gate (2-pass, fail-closed)
                                            └─ SQLAlchemy async ──► SQLite (dev) /
                                                                    PostgreSQL (prod)
External: Gamma API · Data-API · CLOB API · polymarket.com geoblock · Polygon RPC
```

Full details: [docs/architecture.md](docs/architecture.md) ·
API: [docs/api-contract.md](docs/api-contract.md) ·
DB: [docs/database-schema.md](docs/database-schema.md)

## 3. Tech stack

**Backend** FastAPI · Python 3.11 · SQLAlchemy 2 (async) · pydantic v2 · httpx ·
APScheduler · pytest — **Frontend** Next.js 15 · TypeScript · Tailwind CSS v4 ·
shadcn-style local components · Recharts · wagmi v2 · viem · TanStack Query ·
vitest — **DB** SQLite (zero-setup dev) / PostgreSQL 16 (docker-compose / prod).

## 4. Data sources (all official, verified live on 2026-06-11)

| Source | Used for |
| --- | --- |
| `gamma-api.polymarket.com` | markets, events, tags, prices, liquidity/volume |
| `data-api.polymarket.com` | `/holders` (top-20/side), `/positions`, `/closed-positions` (resolved history) |
| `clob.polymarket.com` | order book, midpoint/spread, order submission (gated) |
| `polymarket.com/api/geoblock` | geographic restriction status |
| Polygon JSON-RPC | USDC.e balance / allowance reads |

Every uncertain field semantic is recorded in
[docs/data-field-uncertainties.md](docs/data-field-uncertainties.md) — including which
values are **approximations** (e.g. `entry_notional_approx`).

## 5. Smart money logic

```
smart_money_score = 0.25·win_rate + 0.25·realized_pnl + 0.15·sample_size
                  + 0.15·same_category + 0.10·anomaly + 0.10·position_size
                  − penalties(low sample, new account, wide spread, low liquidity,
                              near resolution, extreme price)        → clamp 0–100
```

- "Smart money" holder = labeled non-new account with score ≥ `SMART_MONEY_SCORE_THRESHOLD` (60).
- Market direction requires ≥ $`MIN_SMART_NOTIONAL` smart notional and a ≥55/45 imbalance, else `NEUTRAL`.
- `confidence_score` = 0.40·notional-imbalance + 0.25·holder-count + 0.35·avg-score − market risk penalties.
  **It is a ranking heuristic, not a probability.** Risk flags are always surfaced.
- Anomaly index = entry notional (approx) ÷ median historical entry notional.

## 6. Risk controls (see [docs/risk-control.md](docs/risk-control.md))

Two-pass enforcement (ticket creation + order submission), all server-side:
geoblock (fail-closed) → market active/closed/accepting → spread cap → liquidity floor
→ limit-price validity + slippage cap → notional cap → balance → allowance →
explicit manual confirmation → `ENABLE_LIVE_TRADING` hard gate → single non-retried
CLOB POST. Blocked regions cannot trade; close-only regions cannot open positions
(v1 only opens positions, so close-only regions cannot submit at all).

## 7. Paper trading vs live trading

| | Paper (default) | Live (opt-in) |
| --- | --- | --- |
| Enable | always on | `ENABLE_LIVE_TRADING=true` + every risk check |
| Entry | signal best-ask auto-log / manual | user-signed CLOB limit order |
| Risk | none (simulated) | real funds — manual confirmation required |
| Keys | none | signatures stay in the user's wallet |

## 8. Geoblock

The backend queries `polymarket.com/api/geoblock` from **its own egress IP** before
ticket creation and again at submission. `blocked=true` + close-only country
(officially PL/SG/TH/TW) → `CLOSE_ONLY` (no new positions); other blocked → `BLOCKED`;
lookup failure → treated as `BLOCKED` (fail-closed). There is no bypass switch.
Note: if you deploy the backend in a permitted region but browse from a restricted
one, Polymarket's own systems still apply their checks at order time — this tool
deliberately performs its own check as an additional barrier, not a workaround.

## 9. Wallet security

- Private keys / seed phrases are **never** requested, stored, transmitted, or logged.
- The frontend only requests your address and EIP-712 signatures (order + ClobAuth).
- CLOB API credentials derived for submission are held in memory for the request only.
- Backend logs run through a redaction filter (signatures/secrets/keys).
- v1 supports EOA wallets (signatureType 0); Polymarket proxy-wallet funds are not
  tradeable from this tool yet.

## 10. Environment variables

Copy `.env.example` → `backend/.env`. Key variables (safe defaults shown):

```
ENABLE_LIVE_TRADING=false   MAX_TRADE_NOTIONAL=100   MAX_SLIPPAGE_BPS=100
MAX_SPREAD_BPS=300          MIN_LIQUIDITY=1000       MIN_POSITION_VALUE=100
CLOSE_ONLY_COUNTRIES=PL,SG,TH,TW                     SCANNER_MAX_MARKETS=15
DATABASE_URL=sqlite+aiosqlite:///./data/polymarket_monitor.db
POLYMARKET_GAMMA_BASE / POLYMARKET_DATA_BASE / POLYMARKET_CLOB_BASE / GEOBLOCK_URL
POLYGON_RPC_URL=https://polygon-rpc.com              CORS_ORIGINS=http://localhost:3000
```

Frontend (`frontend/.env.local`): `NEXT_PUBLIC_API_BASE=http://localhost:8000`.

## 11. Local setup

```bash
# Backend (Python 3.11+; uv recommended)
cd backend
uv venv --python 3.11 .venv && uv pip install -r requirements-dev.txt --python .venv/bin/python
# or: python3.11 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

# Frontend (Node 18.18+)
cd ../frontend && npm install
```

## 12. Running

```bash
# Backend API (http://localhost:8000, docs at /api/docs)
cd backend && .venv/bin/python -m uvicorn app.main:app --reload

# One scanner pass from the CLI (read-only against Polymarket)
cd backend && .venv/bin/python ../scripts/run_scanner.py --max-markets 5

# Offline demo data instead of live scanning
cd backend && .venv/bin/python ../scripts/seed.py

# Frontend (http://localhost:3000)
cd frontend && npm run dev
```

Then open the dashboard → **Run Scanner** → explore markets/signals/paper trades.

**Troubleshooting — Node 23+ `localStorage.getItem is not a function` (SSR 500):**
recent Node versions expose an experimental global `localStorage` that breaks wallet
libraries' browser detection during SSR. The npm scripts already set
`NODE_OPTIONS=--no-experimental-webstorage`; if you run `next` directly (or on
Windows cmd, where inline env vars don't work), set that variable yourself.

## 13. Tests, lint, build

```bash
cd backend  && .venv/bin/python -m pytest -q   # 115 passed
cd backend  && .venv/bin/ruff check app/        # clean
cd frontend && npm test                         # 26 passed (vitest)
cd frontend && npm run typecheck                # clean
cd frontend && npm run lint                     # clean
cd frontend && npm run build                    # production build passes
```

## 14. Deployment

- **Local full stack:** `docker-compose up` (Postgres 16 + backend on :8000).
- **Backend → Render/Railway:** deploy `backend/` with its Dockerfile; set env vars
  from `.env.example` (`DATABASE_URL`, `CORS_ORIGINS=https://<your-vercel-app>`,
  keep `ENABLE_LIVE_TRADING=false`). Health check: `GET /api/health`.
- **Database → Supabase/Railway Postgres:** create a database, copy the connection
  string into `DATABASE_URL` (`postgresql://...` is auto-coerced to asyncpg). Tables
  are created on startup (`create_all`); run `scripts/seed.py` for demo data.
- **Frontend → Vercel:** import `frontend/`, set `NEXT_PUBLIC_API_BASE` to the backend
  URL. Build command `npm run build` (verified).

## 15. Known limitations

- Resolved-history = Data-API closed positions (position-level, ≤200 most recent per
  account by default; truncation is flagged). Intra-market round-trip trades are
  reflected via `realizedPnl`, not reconstructed fill-by-fill.
- `entry_notional_approx` is the current holding's cost basis, not the true first
  opening amount (UI-labeled; see data-field-uncertainties U3).
- Same-category matching is keyword-based (approximate).
- Open interest shown is event-level (market-level OI is not exposed).
- Live order submission is fully gated and unit-tested, but **not exercised against
  production CLOB** (development happened from a close-only region — by design the
  tool refuses to trade from there). Verify with a small order from a permitted
  region before relying on it. v1 = EOA wallets, BUY (open) orders only.
- Binary Yes/No markets only; scan state is in-process (single instance).
- Money values use float for MVP (Numeric migration recommended before serious use).

## 16. Future roadmap

Sell/close flow + position management · Polymarket proxy-wallet support ·
trade-level history reconstruction (true opening amounts) · signal performance
attribution dashboards (paper-trade hit rate per rule) · notification hooks
(Telegram interface stub exists in `signal_service.notify_hook`) · Alembic
migrations · multi-instance scan coordination.

## 17. License / final word

Provided as-is for research and education. No warranty. **Not financial advice.**
