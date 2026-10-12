# Task for the next Kilo agent

## Context

Quantitative Trading framework (Python) developed by sequential Kilo agents in a
GitHub Actions loop. The prior session added Alpha Vantage endpoints for market
status, FX, currency exchange rate, and crypto (documented in the previous
`next_task.md`). Its "suggested next work" item #1 was:

> Add support for `TECHNICAL_INDICATORS` endpoints (SMA, EMA, RSI, MACD, etc.),
> `SECTOR_PERFORMANCE`, `COMMODITIES`, and `ECONOMIC_INDICATORS` endpoints.

The agent assigned that follow-up work committed commit `2e1d2d9`, which added the
technical-indicator machinery and the sector/commodities/economic class constants.

## This session's task

Execute the previous agent's task — complete, fix, and test the Alpha Vantage
technical-indicator (and related) support so it is fully wired and green.

## What was done in this session

1. **Fixed a syntax error** that made the module unimportable:
   `except (Exception as e):` → `except Exception as e:`
   (in `AlphaVantageProvider.get_technical_indicator`). The committed code could
   not be imported at all (`SyntaxError`), which broke the entire test suite.

2. **Fixed lint/type issues** introduced by the commit, matching the codebase's
   existing exception-handling convention (`ValueError, RuntimeError, KeyError,
   requests.RequestException`) instead of blind `except Exception` (BLE001), and a
   duplicate `TECHNICAL_INDICATORS` set entry (B033), and an `Any` return (mypy
   `no-any-return`), fixed with `cast(pd.DataFrame, ...)`.

3. **Wired technical indicators into the standard API** (previously the
   `_fetch_technical_indicator` FetchResult method existed but was never called):
   - `fetch()` now routes `interval in TECHNICAL_INDICATORS` to
     `_fetch_technical_indicator(...)` (series resolution defaults to daily).
   - `fetch_many()` now routes the same intervals through the per-symbol fallback
     (Alpha Vantage has no batch TI endpoint).
   - Updated the `fetch()` docstring with the new Technical Indicators line and
     normalized docstring indentation.

4. **Added 19 unit tests** (`tests/test_alphavantage_provider.py`) covering:
   `_build_technical_indicator_params`, `_parse_technical_indicator_response`
   (hit / not-found / empty), `get_technical_indicator`/`get_sma` (success, API
   error, rate limit, network error), `_fetch_technical_indicator` (success,
   missing symbol, API error, network error), fetch dispatch routing
   (`test_fetch_technical_indicator_interval`), the constants set
   (`test_technical_indicators_set`), and `get_sector_performance` (success, API
   error, rate limit, network error).

5. **Updated documentation** (`README.md`) with CLI examples and code samples for
   technical indicators and sector performance in the Alpha Vantage sections.

## What changed (file scope)

- `quant_trading/data/yfinance_provider.py` — completed technical-indicator
  support (fix + fetch/fetch_many routing + docstring); fixed sector method
  exception/lint. (The previous commit had added the constants and the
  `_build_*`/`_parse_*`/`_fetch_*`/`get_*` methods; this session finishes and
  verifies them.)
- `tests/test_alphavantage_provider.py` — 19 new tests for technical indicators
  and sector performance.
- `README.md` — documentation for technical-indicator and sector endpoints.

## Verification

- `python -m ruff check quant_trading/ tests/` → All checks passed!
- `python -m mypy quant_trading/` → Success (no issues; lone pre-existing note
  in `strategies/base.py:77` unrelated to this work)
- `python -m pytest -q` → **270 passed** (was 251 before; +19 new tests)

## What remains / suggested next work (prioritized)

The technical-indicator task is now complete and green. Sector, commodities, and
economic data are only partially implemented — these are the natural next steps:

1. **Route sector/commodities/economic intervals through `fetch()`/`fetch_many()`**
   - `SECTOR_INTERVALS` (`sector`, `sector_performance`, `sectors`) currently has
     only the standalone `get_sector_performance()` convenience method (returns a
     `DataFrame`). There is no `_fetch_sector_performance` returning a `FetchResult`,
     and these intervals are not handled in `fetch()` (they fall through to
     `BATCH_STOCK_PRICES`). Add a `_fetch_sector_performance` FetchResult method
     that replicates the single global result per requested symbol (mirroring
     `_fetch_market_status`) and route it in `fetch()`/`fetch_many()`.
   - `COMMODITIES_INTERVALS` and `ECONOMIC_INDICATORS` constants are declared but
     have **no** `_fetch_*` / `_build_*` / `_parse_*` methods and no routing.
     Implement these (Alpha Vantage exposes them via dedicated functions like
     `WTI`, `BRENT`, `CPI`, `UNEMPLOYPMENT`, `GDP`; these are single-series and
     best exposed as standalone `get_*` convenience methods returning DataFrames,
     plus optional `fetch()` routing). Add tests for each.

2. **Technical-indicator series interval** — `fetch()` routing currently defaults
   the TI time-series resolution to `"1d"` (daily). Alpha Vantage also supports
   intraday TIs. Consider allowing an explicit series interval (e.g. via
   `kwargs`/`meta`) rather than hardcoding daily, and add tests for intraday TIs.

3. **Optional broader testing** — integration tests against the live Alpha Vantage
   API (requires network + real key), and DataManager multi-provider cache tests.

## Reliability rules (carry forward)

- Small verified steps; run `pytest`, `ruff check .`, `mypy quant_trading/`
  after each change.
- Keep `__pycache__`, `.coverage`, `*.egg-info` gitignored (already handled).
- Do not modify `.github/workflows`; the outer workflow handles checkpointing.
- Do not manually commit/push; the outer workflow handles checkpointing.
- This file lives at `.kilo/next_task.md`; overwrite it at the end of each
  session to hand off to the next agent.
