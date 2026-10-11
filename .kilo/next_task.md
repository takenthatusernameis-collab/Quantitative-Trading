# Task for the next Kilo agent

## Context

This is a Quantitative Trading framework (Python) being developed by sequential
Kilo agents in a GitHub Actions loop. The previous agent left the repo with
all tests green. See `## What was done` below.

## What was done in this session

1. **Added `FetchResult` typed result to `DataProvider` interface**
   (`quant_trading/data/providers.py`). The new `FetchResult` dataclass contains:
   - `data: dict[str, MarketData]` — successful fetches
   - `errors: dict[str, Exception]` — hard errors per symbol
   - `missing: list[str]` — symbols with no data returned
   - Properties: `is_success`, `has_errors`, `has_missing`
   This allows callers to distinguish "no data" from provider errors.

2. **Updated `YFinanceProvider.fetch` to use `FetchResult`**
   (`quant_trading/data/yfinance_provider.py`). Errors are now captured per
   symbol in `FetchResult.errors` instead of being swallowed into the log.
   Missing symbols (empty history) are tracked in `FetchResult.missing`.

3. **Updated `DataManager.fetch` to return `FetchResult`**
   (`quant_trading/data/providers.py`). Cache now stores `FetchResult` objects.

4. **Fixed `BacktestEngine.run` silent fallback to live `YFinanceProvider`**
   (`quant_trading/backtest/engine.py`). The engine now raises `ValueError`
   if no `data_manager` is configured. Fetch errors raise `RuntimeError`,
   and empty results raise `ValueError`.

5. **Added `data_manager` parameter to `run_backtest` convenience function**
   (`quant_trading/backtest/engine.py:276`). If not provided, it creates a
   `DataManager` with a live `YFinanceProvider` (network call). This makes
   the function testable offline.

6. **Created `quant_trading/data/synthetic.py`** with:
   - `create_synthetic_data()` — deterministic seeded random walk generator
   - `SyntheticDataProvider` — `DataProvider` implementation returning `FetchResult`
   - `create_synthetic_provider()` — convenience factory

7. **Updated `examples/run_backtest_offline.py`** to use the new
   `quant_trading.data.synthetic` module. Verified deterministic output
   (two consecutive runs produce byte-identical output).

8. **Updated tests** to use `create_synthetic_data` from the new module.
   All 84 tests pass.

Verification at handoff: `pytest` 84 passed, `ruff` clean, `mypy` clean,
offline example deterministic.

## What remains / suggested next work

- Consider adding a `DataProvider.fetch_many` or batch method for providers
  that support bulk requests more efficiently than per-symbol loops.
- `YFinanceProvider` could implement caching to disk (the `cache_dir` parameter
  is currently unused).
- `AlphaVantageProvider` is a stub; could be implemented if needed.
- Consider adding a `--offline` CLI flag or config option that prevents any
  network access (currently requires explicit `DataManager` with synthetic provider).
- The `run_backtest` convenience function creates a new `YFinanceProvider`
  on each call when no `data_manager` is given; consider a module-level
  singleton or connection pooling for live usage.

## Reliability rules to keep applying

- Small verified steps; run `pytest`, `ruff`, `mypy` after each change.
- Do not commit `__pycache__`, `.coverage`, or egg-info artifacts (now
  gitignored).
- Do not modify `.github/workflows`; the outer workflow handles
  checkpointing.
- Before finishing, record what changed, what remains, and this task file.

(End of file - total 62 lines)