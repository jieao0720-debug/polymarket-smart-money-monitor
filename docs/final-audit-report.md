# Final Audit Report — Polymarket Smart Money Quant Monitor v0.1.0

Audit date: **2026-06-12** · Auditor: Claude (Fable 5, `claude-fable-5`) acting as
sole engineer + final auditor · Environment: macOS, Python 3.11.x (uv venv), Node 25.8 / npm 11.

## 1. Verdict

## **PASS WITH WARNINGS**

All 20 completion criteria are met. Warnings concern items that are *implemented and
tested but not exercisable end-to-end from this development environment* (live CLOB
order submission — this machine sits in a close-only region, so the tool itself
correctly refuses to trade from here) and documented data approximations.

## 2. Completed features

- Hot-market scanner (Gamma fetch → normalize → filter → rank → analyze; manual
  trigger + optional APScheduler interval; scan status registry + `/api/scanner/*`).
- Top-holders analysis: top 20 per side (Data-API cap), both YES and NO, ranked by
  `current_position_value`, enriched per-account via `/positions`.
- Account profiling from `/closed-positions` with hard look-ahead guard (`as_of`),
  overall + same-category stats, first/last seen, truncation flag + cache.
- Account labels (NEW_ACCOUNT / HIGH_WIN_RATE / ABNORMAL_POSITION / OTHER) exactly per
  spec thresholds; anomaly index with explicit `_approx` semantics.
- Smart money score: 6 weighted components + 6 penalties, all separate unit-tested
  functions, clamped 0–100, full breakdown persisted (`score_breakdown` JSON).
- Market-level signals: counts/notional per side, net direction (with NEUTRAL),
  confidence (explicitly not a win probability), 8 risk flags, suggested limit price
  (tick-rounded, slippage-capped) and max notional (liquidity/depth-capped).
- Paper trading: auto-log per qualifying signal at side best-ask (honest taker price),
  manual entries, close with PnL, mark-to-market summary.
- Wallet integration: wagmi/viem injected connector, Polygon chain check, address-only
  access, EIP-712 signing; balances/allowance via hand-rolled Polygon RPC reads.
- Manual real-trading pipeline: trade tickets → first-pass risk checks → explicit
  manual confirmation endpoint → frontend EIP-712 order signing → CLOB credential
  derivation proxy → submission with second-pass full re-check + live-trading hard
  gate → result persisted on ticket. Default **OFF**.
- Frontend: dashboard (filters incl. risk-flag exclusion, scanner status, sortable
  table), market detail (price/liquidity stats, smart-money summary + Recharts
  notional chart, sortable holders table), account drawer, signals log, paper-trades
  page with summary, wallet/trading page, trade-ticket modal with full gating,
  settings page; loading/empty/error states everywhere; addresses copyable/shortened.
- Docs: product spec, architecture, API contract, DB schema, dev rules, risk control,
  assumptions (A1–A22), data-field uncertainties (V1–V6 verified, U1–U13 open), README.
- Deployment: docker-compose (Postgres 16 + backend), backend Dockerfile with
  healthcheck, Vercel/Render/Railway/Supabase instructions, `GET /api/health`.

## 3. Missing features (vs. spec, deliberate v1 scope)

- No sell/close-position live trading (v1 BUY-open only — ASSUMPTION-A12); paper
  trades can be closed.
- No Polymarket proxy-wallet (signatureType 1/2) support — EOA only (A11).
- Frontend tests cover gating/modal/states but not full page render harnesses for
  dashboard/market pages (would need next router + wagmi mocks; logic tested at
  component level instead).
- CLOB price-history charting, order cancellation UI, Telegram bot (hook stub only).

## 4. Critical issues

**None found.** Specifically re-verified: live trading default-off enforced
server-side at the service layer (not just UI); no private-key surface anywhere; no
geoblock bypass paths; look-ahead guard enforced in the единственный stats function.

## 5. High-priority issues (warnings)

1. **Live submission untested against production CLOB** (U10). The full path
   (signing → credential derivation → L2 HMAC → POST /order) is implemented per
   official docs and integration-tested against fakes, but never run against the real
   exchange (dev region is close-only; the tool itself blocks it). Action: first
   enablement should be a tiny order from a permitted region; verify U10/U12 notes.
2. **Float money columns** (MVP choice, documented): migrate to Numeric(18,6) before
   any serious accounting use.

## 6. Medium-priority issues

- Resolved history capped at ~200 most recent closed positions per account
  (A4; flagged via `history_truncated`) — heavy traders' early history is invisible.
- Same-category matching is keyword-based (A5) — mislabels possible; surfaced in UI.
- Hot long-shot markets (e.g. 0.0015 price World Cup outrights) can produce
  directional signals; EXTREME_PRICE flag + confidence penalty apply, but users
  should filter these (dashboard risk-flag exclusion supports it).
- Scan state in-process (A13): restart loses scan progress (not signal data).

## 7. Low-priority issues

- `volume_24h=0` markets from gamma occasionally carry stale `liquidityNum` — filter
  uses both, impact minimal. Recharts bundle adds ~110 kB to market page. The
  `starlette TestClient` deprecation warning (httpx pin) is cosmetic.

## 8. API contract consistency result — **PASS**

`docs/api-contract.md` ⇄ `backend/app/schemas/api.py` ⇄ `frontend/src/types/api.ts`
field-for-field aligned (manually cross-checked; pydantic response_model enforces the
backend side at runtime; integration tests assert key payload shapes). Unified error
envelope `{"error":{code,message,details}}` verified live (404/403/422/409 cases).

## 9. Database schema result — **PASS**

All 11 spec tables implemented (plus condition_id/neg_risk/tick_size and approx-flag
columns documented in database-schema.md). Indexes on hot paths (market+time,
account+time, unique address/market ids). `create_all` boot verified on SQLite;
Postgres URL coercion (`postgres://`→`postgresql+asyncpg://`) unit-path verified.
Alembic deliberately omitted (A10).

## 10. Data logic result — **PASS**

- Yes/No direction: derived only from `outcomes[]` value-matching aligned to
  `clobTokenIds`/`outcomeIndex`; reversed-order market test passes; non-binary
  markets rejected. Holder direction comes from token-id mapping, never index 0.
- shares vs USD: holders `amount` empirically verified as **shares** (V2); position
  value taken from `/positions.currentValue`, with explicit `value_is_approx`
  fallback (shares × price) when unavailable; `entry_notional_approx` named as such
  end-to-end (DB column → API field → UI tooltip).
- Book best bid/ask computed order-independently (live asks arrive descending — V5).
- Live verification: real scan persisted sane snapshots/holders/labels
  (e.g. account `0x5d18…4972`: 145 resolved, 75.2% win rate, +$260k realized →
  HIGH_WIN_RATE, score 74.5).

## 11. Look-ahead bias check result — **PASS**

`compute_resolved_stats(positions, as_of)` is the only stats entry point; inclusion
requires `closed_at ≤ as_of` **and** `end_date ≤ as_of`; missing timestamps are
excluded (conservative). 5 dedicated tests incl. same-history-two-timestamps and
boundary equality. Scanner passes the snapshot time as `as_of`.

## 12. Trading safety result — **PASS**

- `ENABLE_LIVE_TRADING=false` default in code, .env.example, docker-compose; the gate
  lives in `order_submit_service` (server-side), tested: submit with gate off → 403
  `LIVE_TRADING_DISABLED`, ticket → REJECTED, **zero** CLOB calls.
- Two-pass checks (creation + submission) cover market state, spread, liquidity,
  price validity/slippage, notional cap, balance, allowance (both fail-closed on RPC
  failure — tested), payload sanity (maker/tokenId/side/signature shape).
- Manual confirmation is a dedicated endpoint requiring `manual_confirmation: true`;
  unconfirmed tickets cannot submit (tested). Tickets expire (10 min TTL).
- No automated-trading code path: scheduler only triggers scans; grep-verified that
  scanner/signal/paper modules never import order submission.
- Orders are never auto-retried.

## 13. Geoblock result — **PASS (live-verified)**

Real geoblock endpoint integrated; close-only mapping uses the official country list
(PL/SG/TH/TW, env-tunable). **Live test from this SG environment:** `/api/trading/geoblock`
returned `mode=CLOSE_ONLY, can_open=false, can_close=true`, and ticket creation was
rejected with `CLOSE_ONLY_REGION` and the mandated message. Fail-closed behavior
(upstream failure → BLOCKED) unit- and API-tested. No bypass mechanism exists;
`GEOBLOCK_FORCE_MODE` is dev/test-only and documented as must-be-empty in production.

## 14. Wallet security result — **PASS**

No private-key input surface (grep-verified frontend); wagmi injected connector only
requests accounts + `signTypedData`. Backend stores only public addresses
(`wallet_connections`). CLOB credentials: in-memory per request, never persisted;
log redaction filter active (signatures/secrets/keys/passphrases + long hex);
ticket record verified to contain no signature/credential material after submission
(tested). No localStorage/sessionStorage usage. CORS restricted to configured
origins, GET/POST only, no credentials.

## 15. Test result — **PASS**

- Backend: **115 passed** (`pytest -q`, 1 cosmetic deprecation warning). Covers all
  16 mandated areas (labels ×4, anomaly, score, penalties, scanner filter, direction
  normalization, geoblock, close-only, live-default-off, tickets, paper trades,
  schema/API, look-ahead).
- Frontend: **26 passed** (vitest) — confirm gating (10 cases incl. all mandated
  disable conditions), modal rendering + mandated copy, loading/error/empty states,
  formatters.

## 16. Build result — **PASS**

- `ruff check app/` → clean. (mypy not configured — recorded; ruff covers lint scope.)
- `npm run typecheck` (tsc --noEmit) → clean.
- `npm run lint` (next lint, incl. no-console guard) → clean.
- `npm run build` (Next 15 production) → success, 9 routes, market page 256 kB first load.

## 17. Deployment readiness — **READY WITH NOTES**

docker-compose.yml (Postgres 16 + backend) and backend Dockerfile delivered with
healthcheck; **not run locally because Docker is unavailable on this machine** —
syntax follows current compose spec; verify `docker compose up` on a Docker host.
Vercel/Render/Railway/Supabase steps in README §14. `GET /api/health` implemented and
live-verified. SQLite fallback means the stack also runs with zero external services.

## 18. Exact commands run (final verification)

```
cd backend  && .venv/bin/python -m pytest -q          → 115 passed
cd backend  && .venv/bin/ruff check app/              → All checks passed!
cd frontend && npx vitest run                          → 3 files, 26 passed
cd frontend && npm run typecheck                       → clean
cd frontend && npm run lint                            → No ESLint warnings or errors
cd frontend && npm run build                           → ✓ Compiled successfully
cd backend  && .venv/bin/python ../scripts/run_scanner.py --max-markets 2
            → completed: found 73, analyzed 2, signals 2 (live Polymarket data)
uvicorn smoke: /api/health, /api/markets/hot, /api/markets/{id}/analysis,
  /api/accounts/{addr}/profile, /api/signals, /api/paper-trades,
  /api/trading/geoblock (live SG close-only), POST /api/trade-tickets (correctly
  rejected CLOSE_ONLY_REGION), 404 envelope — all verified
security greps: console.log=0, localStorage=0, key-material strings only in
  redaction/safety code, .env ignored, scanner→order-submit imports=0
```

## 19. Known limitations

See README §15 (authoritative list): closed-position-based history (≤200, flagged),
entry-notional approximation, keyword categories, event-level OI, live path untested
against production, EOA + BUY-only, binary markets only, float money columns,
in-process scan state, docker-compose unverified on this machine.

## 20. Next recommended steps

1. From a permitted region with a funded EOA: enable live trading, place a $1–5
   order, verify U10 (feeRateBps/owner semantics) and U12 (contract addresses), then
   record results in data-field-uncertainties.md.
2. Migrate money columns to Numeric + introduce Alembic before schema evolution.
3. Add sell/close live flow and proxy-wallet support (largest user-value gap).
4. Build signal-performance attribution on top of the paper-trade log (the data
   model already links signal_id → paper trade → PnL).
5. Track Polymarket's geoblock/close-only list for changes (U1) and pin a periodic
   re-verification of V1–V6 field semantics.
