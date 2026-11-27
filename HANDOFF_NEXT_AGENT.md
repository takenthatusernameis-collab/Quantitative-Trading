## Session 2026-11-27 (allowlist cleanup - yfinance_provider.py `_group_cache_key`)

### What changed
- Documented `YFinanceProvider._group_cache_key` in `quant_trading/data/yfinance_provider.py` with a deterministic single-line doctest.
- Removed the matching `_group_cache_key` entry from `_EXAMPLES_ALLOWLIST` in `tests/test_repository_integrity.py`.
- No production behavior changed.

### What was actually verified
- `python -m pytest tests/test_repository_integrity.py --doctest-modules quant_trading/data/yfinance_provider.py` -> 54 passed, 1 skipped.
- `python -m pytest --doctest-modules quant_trading/data/yfinance_provider.py` -> 4 passed.
- `python -m ruff check .` -> all checks passed.
- `python -m black --check quant_trading/ tests/ examples/` -> 166 files unchanged.
- `git diff --check` -> passed.
- `python -m pytest` -> 5302 passed, 260 skipped, 151 deselected in 176.50s.

### What remains unresolved
- `quant_trading/data/yfinance_provider.py` still has many `_EXAMPLES_ALLOWLIST` entries. Continue one def per session.
- mypy unavailable in this environment; not independently rerun.

### Next task
Document `YFinanceProvider._is_cache_valid` in `quant_trading/data/yfinance_provider.py` with a deterministic single-line doctest, then remove one of its two allowlist entries (`("quant_trading/data/yfinance_provider.py", "_is_cache_valid")`). Note the method depends on filesystem mtime and `self._cache_ttl`; construct a provider with a cache dir and use a nonexistent path (returns False) for a deterministic offline example. Run the same focused integrity/module tests, Ruff, Black, `git diff --check`, and the full pytest suite before selecting another def.
