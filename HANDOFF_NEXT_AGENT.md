## Session 2026-11-27 (allowlist cleanup - `_build_gold_history_params`)

### What changed
- Documented `AlphaVantageProvider._build_gold_history_params`
  in `quant_trading/data/yfinance_provider.py` (def `symbol: str, interval: str = "daily"`) with a
  deterministic single-line doctest:
  `AlphaVantageProvider(cache_dir="", warn_on_demo=False)._build_gold_history_params("GOLD")`
  -> `{'function': 'GOLD_SILVER_HISTORY', 'symbol': 'GOLD', 'interval': 'daily', 'apikey': 'demo', 'datatype': 'json'}`.
- Removed the `("quant_trading/data/yfinance_provider.py",
  "_build_gold_history_params")` line from `_EXAMPLES_ALLOWLIST` in
  `tests/test_repository_integrity.py` (no blank line left behind).
- No production behavior changed (docstring + allowlist only).

### What was actually verified (evidence)
- Live `python -c` run confirmed output.
- `python -m pytest tests/test_repository_integrity.py --doctest-modules quant_trading/data/yfinance_provider.py` -> 88 passed.
- `python -m pytest tests/test_repository_integrity.py` -> 51 passed.
- `python -m ruff check .` -> All checks passed.
- `python -m black --check quant_trading/ tests/ examples/` -> 166 files unchanged.
- `git diff --check` -> clean.

### What remains unresolved
- `quant_trading/data/yfinance_provider.py` still has allowlist entries.

### Next task
Inspect `_EXAMPLES_ALLOWLIST` for the next deterministic allowlisted method in `quant_trading/data/yfinance_provider.py` and repeat the process.
(End of file)
