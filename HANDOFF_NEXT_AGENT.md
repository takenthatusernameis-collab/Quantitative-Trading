## Session 2026-11-27 (allowlist cleanup - `_save_cache`, both providers)

### What changed
- Documented `YFinanceProvider._save_cache` AND `AlphaVantageProvider._save_cache`
  in `quant_trading/data/yfinance_provider.py` with a deterministic single-line doctest
  (unwritable/nonexistent directory path -> return value is None).
- Removed the two identical `("quant_trading/data/yfinance_provider.py", "_save_cache")`
  lines from `_EXAMPLES_ALLOWLIST` in `tests/test_repository_integrity.py`.
- No production behavior changed.

### What was actually verified
- `python -m pytest tests/test_repository_integrity.py --doctest-modules quant_trading/data/yfinance_provider.py`
  -> 60 passed, 1 skipped.
- `python -m ruff check .` -> all checks passed.
- `python -m black --check quant_trading/ tests/ examples/` -> 166 files unchanged.
- `git diff --check` -> passed.
- Full pytest suite -> 5308 passed, 260 skipped, 151 deselected.

### What remains unresolved
- `quant_trading/data/yfinance_provider.py` still has many `_EXAMPLES_ALLOWLIST` entries.
- Next identical-pair candidate TBD; inspect allowlist for next duplicated def.

### Next task
Inspect `_EXAMPLES_ALLOWLIST` for the next duplicated `(path, name)` pair in
`quant_trading/data/yfinance_provider.py`, document both methods with a deterministic
single-line doctest, then remove the two allowlist lines. Run the same focused
integrity/module tests, Ruff, Black, `git diff --check`, and the full pytest suite
before selecting another def.
