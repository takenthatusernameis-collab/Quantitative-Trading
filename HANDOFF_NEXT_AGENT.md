## Session 2026-11-27 (allowlist cleanup - `__init__`, both providers)

### What changed
- Documented `YFinanceProvider.__init__` AND `AlphaVantageProvider.__init__`
  in `quant_trading/data/yfinance_provider.py` with a deterministic single-line doctest
  (constructor with temp cache directory -> `name` property returns expected value).
- Removed the two identical `("quant_trading/data/yfinance_provider.py", "__init__")`
  lines from `_EXAMPLES_ALLOWLIST` in `tests/test_repository_integrity.py`.
- No production behavior changed.

### What was actually verified
- `python -m pytest tests/test_repository_integrity.py --doctest-modules quant_trading/data/yfinance_provider.py`
  -> 66 passed, 1 skipped.
- `python -m pytest tests/test_repository_integrity.py` -> 50 passed, 1 skipped.
- `python -m ruff check .` -> all checks passed.
- `python -m black --check quant_trading/ tests/ examples/` -> 166 files unchanged.
- `git diff --check` -> passed.

### What remains unresolved
- `quant_trading/data/yfinance_provider.py` still has many `_EXAMPLES_ALLOWLIST` entries.
- Next identical-pair candidates (both providers have these methods):
  - `fetch` (lines 1933-1934 in allowlist)
  - `fetch_latest` (lines 1935-1936)
  - `fetch_many` (lines 1937-1938)
  - `name` (lines 1953-1954)
  - Many `_build_*` / `_parse_*` / `_fetch_*` method pairs

### Next task
Inspect `_EXAMPLES_ALLOWLIST` for the next duplicated `(path, name)` pair in
`quant_trading/data/yfinance_provider.py` (suggest `fetch` next), document both methods with a deterministic
single-line doctest, then remove the two allowlist lines. Run the same focused
integrity/module tests, Ruff, Black, `git diff --check`, and a broader pytest
subset before selecting another def.

(End of file - total 28 lines)