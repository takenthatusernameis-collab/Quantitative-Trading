# Task for the next Kilo agent

## Context

Quantitative Trading framework. Coverage-focused work. Previous sessions closed
`config/settings.py`, `risk/limits.py`, and `monte_carlo/simulator.py` to 100%
via test-only additions. This session closed two more modules.

## What was done in this session

- **`regime/detector.py`** — closed 97% → 100% (4 missed lines → 0).
  Added 4 tests to `tests/test_regime.py`:
  - `test_regime_result_to_dict` — exercises `RegimeResult.to_dict()` (line 59).
  - `test_regime_result_empty_to_dict_and_to_dataframe` — `to_dict()` on empty
    result (line 59) and `to_dataframe()` empty branch (line 70).
  - `test_detect_regimes_non_series_input_list` — passes a `list` (not `pd.Series`)
    to `detect_regimes`, exercising the `prices = pd.Series(prices)` conversion (line 107).
  - `test_detect_regimes_returns_empty_after_dropna` — passes `pd.Series([100.0, np.nan])`
    so `pct_change().dropna()` is empty, exercising the `len(returns) < 1` branch (line 113).
  Verified: `coverage report -m quant_trading/regime/detector.py` -> 117 stmts, 0 missed, 100%.
  Note: `black` reformatted pre-existing multi-line expressions in test_regime.py to fit
  line-length=100 (no logic changes).

- **`data/synthetic.py`** — closed 90% → 100% (4 missed lines → 0).
  Added 3 tests to `tests/test_data_providers.py` + expanded imports:
  - `test_synthetic_data_provider_missing_symbol` — `fetch()` with a symbol not in
    the provider's data (line 88: `result.missing.append(symbol)`).
  - `test_synthetic_data_provider_fetch_latest` — calls `fetch_latest()` (line 92:
    `return self.fetch(symbols)`).
  - `test_create_synthetic_provider` — calls the convenience function (lines 102-103).
  Note: `black` reformatted some pre-existing code in test_data_providers.py for compliance.

- Full suite: `pytest tests/ -q` -> **658 passed** (+7 tests total: 4 regime + 3 synthetic).
- Quality gates: `ruff check` passed on entire repo (also fixed 2 pre-existing
  `I001` import-sorting issues in `tests/test_monte_carlo.py` via `ruff --fix`);
  `mypy` passed; `black --check` passed on all modified files.

## What remains unresolved

Remaining pure-Python coverage gaps (from full-suite coverage run):

| Module                        | Stmts | Miss | Cover | Missing lines            |
|-------------------------------|------:|-----:|------:|--------------------------|
| `data/providers.py`           |  143  |    8 |   94% | 50, 128, 135, 157, 173, 275-276, 293 |
| `data/yfinance_provider.py`   | 1534  | 279 |   82% | (many lines — large module, 3070 lines; not bounded) |

(The `yfinance_provider.py` gap is too large for a single session and mostly requires
network-mocked tests; skip it for now.)

## Next task (precise, prioritized)

**Close `data/providers.py` to 100%** — 8 missed lines, all small and testable
offline with the existing `CountingProvider`/`MockDataProvider` patterns or simple
`DataConfig` objects. Add tests to `tests/test_data_providers.py`:

1. **Line 50** — `FetchResult.has_missing` property (`return bool(self.missing)`):
   Build a `FetchResult` with `result.missing.append("X")` and assert `has_missing is True`.
2. **Line 128** — `DataManager.add_provider`: create an empty `DataManager([])` then call
   `add_provider(CountingProvider(...))` and assert the provider is in `mgr.providers`.
3. **Line 135** — `DataManager.get_provider` no-match: call `get_provider("nonexistent")`
   and assert it returns `None`.
4. **Line 157** — `DataManager.fetch` with no provider: `DataManager([])` then call
   `fetch(["AAPL"])` and assert `ValueError` is raised.
5. **Line 173** — `DataManager.clear_cache`: add data to the cache then call `clear_cache()`
   and assert the cache is empty.
6. **Lines 275-276** — `LazySyntheticProvider.fetch_latest`: exercise via
   `create_data_manager_from_config(DataConfig(provider="synthetic", offline=True))`
   then call `mgr.fetch_latest(["AAPL"])` — this hits lines 275-276 in the lazy provider's
   `fetch_latest` override (delegates to `super().fetch_latest`).
7. **Line 293** — `create_data_manager_from_config` unknown provider: pass a `DataConfig`
   with `provider="unknown"` and assert `ValueError` is raised.

Run `python -m coverage report -m --include="*/data/providers.py"` to verify 100%,
then `pytest tests/ -q` + `ruff` + `mypy` + `black --check` on modified test file.
Update this handoff with new missed lines and proof.
