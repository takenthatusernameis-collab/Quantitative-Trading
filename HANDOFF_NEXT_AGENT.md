## Session 2026-11-27 (allowlist cleanup - `_build_market_status_params`)

### What changed
- Documented `AlphaVantageProvider._build_market_status_params`
  in `quant_trading/data/yfinance_provider.py` (def `self`) with a
  deterministic single-line doctest:
  `AlphaVantageProvider(cache_dir="", warn_on_demo=False)._build_market_status_params()`
  -> `{'function': 'MARKET_STATUS', 'apikey': 'demo', 'datatype': 'json'}`.
- Removed the `("quant_trading/data/yfinance_provider.py",
  "_build_market_status_params")` line from `_EXAMPLES_ALLOWLIST` in
  `tests/test_repository_integrity.py` (no blank line left behind).
- No production behavior changed (docstring + allowlist only).

### What was actually verified (evidence)
- `python -m pytest --doctest-modules quant_trading/data/yfinance_provider.py`
  -> 40 passed (was 39 before this change).
- `python -m pytest tests/test_repository_integrity.py` -> 51 passed.
- `python -m ruff check .` -> All checks passed.
- `python -m black --check quant_trading/ tests/ examples/` -> 166 files unchanged.
- `git diff --check` -> clean.
- `git diff --stat`: `quant_trading/data/yfinance_provider.py | 4 ++++`,
  `tests/test_repository_integrity.py | 1 -`.

### What remains unresolved
- `quant_trading/data/yfinance_provider.py` still has allowlist entries.

### Next task
Inspect `_EXAMPLES_ALLOWLIST` for the next deterministic allowlisted method in
`quant_trading/data/yfinance_provider.py` (the next remaining `_build_*_params`
entries are `_build_monthly_adjusted_params`, `_build_monthly_params`,
`_build_sector_params`, `_build_symbol_search_params`,
`_build_technical_indicator_params`, `_build_weekly_adjusted_params`,
`_build_weekly_params`) and repeat the process: add a deterministic single-line
doctest, remove the allowlist entry, and re-run the verification commands above.
(End of file)