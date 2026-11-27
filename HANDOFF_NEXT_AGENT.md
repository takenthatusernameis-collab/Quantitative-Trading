## Session 2026-11-27 (allowlist cleanup - `_is_cache_valid`, both providers)

### What changed
- Documented `YFinanceProvider._is_cache_valid` AND `AlphaVantageProvider._is_cache_valid`
  in `quant_trading/data/yfinance_provider.py` with a deterministic single-line doctest
  (nonexistent path -> `False`).
- Removed the `_is_cache_valid` entry from `_EXAMPLES_ALLOWLIST` in
  `tests/test_repository_integrity.py` (there were two identical lines; both removed).
- No production behavior changed.

### Why both methods were documented (not one)
- `_EXAMPLES_ALLOWLIST` is a `frozenset` keyed by `(rel, name)` only, so the two
  identical `_is_cache_valid` lines collapsed to ONE effective entry.
- The guard `_tree_examples_mismatches` matches by `(rel, node.name)`, so that single
  entry exempted BOTH `_is_cache_valid` defs (one per provider class). Removing the
  entry while documenting only one def would leave the other undocumented and FAIL the
  guard. The two methods are byte-identical, so they form one atomic unit.
- The prior handoff's "remove one of its two allowlist entries" reflected a miscount;
  removing one line is a no-op on the frozenset. Both lines were removed.

### What was actually verified
- `python -m pytest tests/test_repository_integrity.py --doctest-modules quant_trading/data/yfinance_provider.py`
  -> 56 passed, 1 skipped (was 50 passed; +2 module doctests, integrity still green).
- `python -m ruff check .` -> all checks passed.
- `python -m black --check quant_trading/ tests/ examples/` -> 166 files unchanged.
- `git diff --check` -> passed.
- `python -m pytest` -> 5304 passed, 260 skipped, 151 deselected in 179.21s
  (was 5302 passed; +2 new doctests).

### Notes / gotchas for the next agent
- `quant_trading/utils/logging.py::setup_logger` attaches a `StreamHandler(sys.stdout)`,
  so `logger.warning(...)` writes to stdout. Under `pytest --doctest-modules` pytest
  captures logging separately, so logged warnings do NOT pollute doctest stdout (proven:
  the AlphaVantage class docstring already constructs a demo-key provider that logs a
  warning and its doctest passes). The AlphaVantage `_is_cache_valid` doctest still
  passes `warn_on_demo=False` defensively.
- mypy is unavailable in this environment; not independently rerun.

### What remains unresolved
- `quant_trading/data/yfinance_provider.py` still has many `_EXAMPLES_ALLOWLIST` entries.
- The next identical-pair is `_load_cache` (two identical defs, one per provider; the
  allowlist still has two identical `_load_cache` lines).

### Next task
Document BOTH `_load_cache` methods (YFinanceProvider and AlphaVantageProvider) in
`quant_trading/data/yfinance_provider.py` with a deterministic single-line doctest, then
remove the two identical `("quant_trading/data/yfinance_provider.py", "_load_cache")`
lines from `_EXAMPLES_ALLOWLIST`. Suggested deterministic offline example (nonexistent
path -> `None`; the method logs a warning that pytest captures):
`>>> YFinanceProvider(cache_dir="/tmp/yt_cache", cache_ttl_hours=1)._load_cache("/nonexistent/cache.pkl") is None`
-> `True` (and the analogous `AlphaVantageProvider(..., warn_on_demo=False)` line).
Run the same focused integrity/module tests, Ruff, Black, `git diff --check`, and the
full pytest suite before selecting another def.