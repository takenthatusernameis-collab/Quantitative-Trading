## Session 2026-11-27 (allowlist cleanup - `_build_daily_params`)

### What changed
- Documented `AlphaVantageProvider._build_daily_params` in
  `quant_trading/data/yfinance_provider.py` with a deterministic single-line
  doctest:
  `AlphaVantageProvider(cache_dir="", warn_on_demo=False)._build_daily_params("AAPL")`
  -> `{'function': 'TIME_SERIES_DAILY_ADJUSTED', 'symbol': 'AAPL', 'apikey': 'demo', 'outputsize': 'full', 'datatype': 'json'}`.
- Removed the `("quant_trading/data/yfinance_provider.py", "_build_daily_params")`
  line from `_EXAMPLES_ALLOWLIST` in `tests/test_repository_integrity.py`.
- No production behavior changed (docstring + allowlist only).

### Why `_build_daily_params`
- It is allowlisted but lacks an Examples section, so it is exempt from the
  `test_documented_examples_are_valid` guard until documented.
- It builds query parameters from `self._api_key` (defaults to `"demo"`), so
  its result is deterministic and independent of market hours/network — safe for
  a doctest.
- `cache_dir=""` skips `os.makedirs`; `warn_on_demo=False` skips the demo-key
  log warning, keeping construction deterministic.

### Note on the previous handoff's `name` suggestion
- `name` (both `YFinanceProvider.name` line 66 and `AlphaVantageProvider.name`
  line 790) already has a deterministic doctest and is NOT in the allowlist, so
  there is nothing to do for `name` in this tree. The prior handoff's `name`
  recommendation was stale.

### What was actually verified (evidence)
- `python -m pytest tests/test_repository_integrity.py --doctest-modules quant_trading/data/yfinance_provider.py`
  -> 76 passed (the new `_build_daily_params` doctest executed; was 73 after the
  `fetch_many` session).
- `python -m pytest tests/test_repository_integrity.py` -> all passed
  (including `test_examples_allowlist_names_exist` and
  `test_documented_examples_are_valid`).
- `python -m pytest tests/test_yfinance_provider.py
  tests/test_alphavantage_provider.py tests/test_data_providers.py
  tests/test_yfinance_fetch_many.py` -> 454 passed.
- `python -m ruff check .` -> All checks passed.
- `python -m black --check quant_trading/ tests/ examples/` -> 166 files unchanged.
- `git diff --check` -> clean. `git diff --stat` -> 2 files, +4/-1 only.

### What remains unresolved
- `quant_trading/data/yfinance_provider.py` still has many
  `_EXAMPLES_ALLOWLIST` entries (80 remain after this session).

### Next task
Inspect `_EXAMPLES_ALLOWLIST` for the next deterministic allowlisted method in
`quant_trading/data/yfinance_provider.py` (the `_build_*` param builders are good
candidates; `_build_economic_indicator_params` is next in allowlist order),
document it with a deterministic single-line doctest (prefer an `isinstance` or
structural check over a data-length assertion when the result depends on
market hours/network), remove its allowlist line, then run the same focused
integrity/module tests, Ruff, Black, `git diff --check`, and a broader pytest
subset before selecting another def.

(End of file)
