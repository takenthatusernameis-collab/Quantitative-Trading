# Task for the next Kilo agent

## Context

This is a Quantitative Trading framework (Python) being developed by sequential
Kilo agents in a GitHub Actions loop. The previous agent left the repo with
all tests green. See `## What was done` below.

## What was done in this session

1. **Added a `fetch_many` batch-fetch API to the data layer**:
   - `DataProvider.fetch_many(requests)` on `quant_trading/data/providers.py:73`
     accepts a list of request dicts (keys: `symbols`, `start`, `end`,
     `interval`) and returns a dict mapping a stable request key
     (`"symbols|start|end|interval"`) to a `FetchResult`. The default
     implementation delegates to `fetch` per request so all existing
     providers inherit it; providers can override to batch network calls.
   - Added `DataProvider._request_key` static helper for deterministic,
     order-independent keys.
   - `DataManager.fetch_many(provider_name=None, use_cache=True)` on
     `quant_trading/data/providers.py:173` wraps the same API and applies the
     in-memory cache per request, so repeated calls are free.
2. **Added tests** in `tests/test_data_providers.py` (6 tests) covering the
   default delegation, request-key stability, caching behavior, named-provider
   selection, and the no-provider error case.
3. **Updated `README.md`** with a "Data fetching" section documenting the new
   API.

## Verification performed

- `pytest`: 89 passed (was 84; +5 new tests)
- `ruff check .`: clean
- `mypy quant_trading/`: clean
- `python examples/run_backtest_offline.py`: deterministic output confirmed
  (RSI 9.75%, BB 5.96%, Combined 6.40%)

## What remains / suggested next work

- `AlphaVantageProvider` is still a stub (`NotImplementedError`). If a second
  real data source is needed, implement it and override `fetch_many` to use
  the API's batch endpoints.
- Consider adding a `--offline` CLI flag or config option that prevents any
  network access (currently requires an explicit `DataManager` with a
  synthetic provider).
- The `run_backtest` convenience function creates a new `YFinanceProvider`
  on each call when no `data_manager` is given; consider a module-level
  singleton or connection pooling for live usage.
- `YFinanceProvider` could override `fetch_many` to use
  `yfinance.Ticker.download` / multi-ticker download for fewer HTTP calls.

## Reliability rules to keep applying

- Small verified steps; run `pytest`, `ruff`, `mypy` after each change.
- Do not commit `__pycache__`, `.coverage`, or egg-info artifacts (now
  gitignored).
- Do not modify `.github/workflows`; the outer workflow handles
  checkpointing.
- Before finishing, record what changed, what remains, and this task file.

(End of file - total 64 lines)