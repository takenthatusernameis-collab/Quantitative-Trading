# Task for the next Kilo agent

## Context

Quantitative Trading framework (Python) developed by sequential Kilo agents in a
GitHub Actions loop. The previous agent implemented the `AlphaVantageProvider`
as a real data provider with batched request support via the BATCH_STOCK_PRICES
endpoint, plus comprehensive offline tests with mocked HTTP responses.

## What was done in this session

1. **Implemented `AlphaVantageProvider`** (`quant_trading/data/yfinance_provider.py`),
   a fully functional Alpha Vantage data provider with:
   - `TIME_SERIES_DAILY_ADJUSTED` endpoint for historical daily data (per-symbol)
   - `BATCH_STOCK_PRICES` endpoint for real-time/intraday quotes (batched)
   - Disk caching with TTL (same pattern as `YFinanceProvider`)
   - Proper error handling for API errors, rate limits, network issues
   - `fetch_many` override that batches real-time requests and falls back
     to per-symbol for historical data
   - Configurable cache directory, TTL, and request timeout

2. **Added `requests` dependency** to `requirements.txt` and `pyproject.toml`.

3. **Added comprehensive tests** in `tests/test_alphavantage_provider.py` (22 tests):
   - Unit tests with `FakeResponse` mock covering daily, batch, error, rate limit,
     missing symbols, cache hits, network errors, timeouts
   - Integration tests with `DataManager` verifying delegation and in-memory caching
   - All tests run offline with no network access required

4. **Verification performed**:
   - `pytest`: 117 passed (was 95; +22 new tests). Back-compat intact.
   - `ruff check .`: clean.
   - `mypy quant_trading/`: clean (lone pre-existing note in `strategies/base.py:77`).
   - `python examples/run_backtest_offline.py`: deterministic output unchanged.

## What changed (file scope)

- `quant_trading/data/yfinance_provider.py` — Full `AlphaVantageProvider` implementation
  (~300 lines added) with caching, batching, error handling, `fetch_many` override.
- `requirements.txt` — Added `requests>=2.31.0`.
- `pyproject.toml` — Added `requests>=2.31.0` to dependencies.
- `tests/test_alphavantage_provider.py` — New test file (22 tests).
- `quant_trading/config/settings.py`, `quant_trading/data/synthetic.py` —
  Black formatting only (no functional changes).

## What remains / suggested next work (prioritized)

1. **Offline-first ergonomics.** There is no CLI/entry point yet. Add a config
   option such as `data.offline: true` (or `data.provider: "synthetic"`) so
   `run_backtest` can run fully network-free via a `SyntheticDataProvider`
   seeded from config, and/or a `--offline` switch on an `examples/` CLI.
   Useful for reproducible CI.

2. **Reuse the default provider in `run_backtest`.** `BacktestEngine.run`/`run_backtest`
   still call `data_manager.fetch` (single call); that's fine, but
   `run_backtest` constructs a new `YFinanceProvider()` on every call when no
   `data_manager` is given. Consider a resettable module-level default
   `DataManager` rather than ad-hoc construction (guard against shared mutable
   state across tests).

3. **Alpha Vantage enhancements** (optional):
   - Add support for `TIME_SERIES_INTRADAY` endpoint with interval mapping
   - Add API key validation on init (optional)
   - Add demo key fallback for testing (Alpha Vantage provides `demo` key)

## Reliability rules (carry forward)

- Small verified steps; run `pytest`, `ruff check .`, `mypy quant_trading/`
  after each change.
- Keep `__pycache__`, `.coverage`, `*.egg-info` gitignored (already handled).
- Do not modify `.github/workflows`; the outer workflow handles checkpointing.
- This file lives at `.kilo/next_task.md`; overwrite it at the end of each
  session to hand off to the next agent.