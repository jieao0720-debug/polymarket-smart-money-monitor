# Tests

Test suites live next to the code they cover:

- **Backend (pytest, 115 tests):** `backend/app/tests/`
  - `test_normalization.py` — Yes/No direction mapping (incl. reversed outcome order), book/holders/closed-position parsing, geoblock modes
  - `test_lookahead.py` — look-ahead bias guard (`as_of` filtering)
  - `test_labels.py` — NEW_ACCOUNT / HIGH_WIN_RATE / ABNORMAL_POSITION rules + anomaly index
  - `test_scoring.py` — every smart-money score component & penalty, clamping, market confidence
  - `test_scanner_filtering.py` — hot-market inclusion filter
  - `test_trading_risk.py` — geoblock enforcement, close-only, price/spread/notional checks, signed-payload validation
  - `test_api.py` — full API flows with fake Polymarket clients (scanner → analysis → signals → paper trades → tickets → live-trading gate, geoblock regions, credential derivation)

  Run: `cd backend && .venv/bin/python -m pytest -q`

- **Frontend (vitest, 26 tests):** `frontend/src/__tests__/`
  - `confirm-gating.test.ts` — every confirm-button blocker
  - `trade-ticket-modal.test.tsx` — modal renders, mandated copy, disabled states (wallet disconnected, close-only, live-off, unchecked)
  - `components.test.tsx` — loading/error/empty states, formatters

  Run: `cd frontend && npm test`
