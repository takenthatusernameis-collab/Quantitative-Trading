## Session 2026-11-27 (allowlist cleanup - `_parse_global_quote_response`)

### What changed
- Documented `AlphaVantageProvider._parse_global_quote_response`
  in `quant_trading/data/yfinance_provider.py` (def at line ~1858) with a
  deterministic doctest that avoids the fragile `datetime.now().date()` index by
  projecting stable properties only: the `None` case, `list(df.columns)`, `df.shape`.
- Removed the `("quant_trading/data/yfinance_provider.py",
  "_parse_global_quote_response")` line from `_EXAMPLES_ALLOWLIST` in
  `tests/test_repository_integrity.py` (no blank line left behind).
- No production behavior changed (docstring + allowlist only).
- Commit: `64f0173`.

### Note on prior handoff
- The previous handoff's "Next task" (`_parse_currency_exchange_rate_response`)
  was ALREADY completed and committed in `1c0cdac` before this session. The stale
  handoff was superseded; this session verified that baseline was green and moved on.

### What was actually verified (evidence)
- `python -m pytest --doctest-modules quant_trading/data/yfinance_provider.py`
  -> 52 passed (was 51; +1 for the new doctest).
- `python -m pytest tests/test_repository_integrity.py` -> 51 passed.
- `python -m pytest` (full suite, config excludes slow/network)
  -> 5441 passed, 170 skipped, 151 deselected.
- `python -m ruff check .` -> All checks passed.
- `python -m black --check quant_trading/ tests/ examples/` -> 166 files unchanged.
- `git diff --check` -> clean.
- `git diff --stat`: `quant_trading/data/yfinance_provider.py | 10 ++++++++++`,
  `tests/test_repository_integrity.py | 1 -`.

### What remains unresolved
- `quant_trading/data/yfinance_provider.py` still has many allowlist entries:
  `_fetch_*`, `_get_yf`, most `_parse_*`, `get_*`, `search_symbols`.
- Remaining `_parse_*` allowlist entries (as of this session):
  `_parse_batch_response`, `_parse_crypto_response`, `_parse_daily_response`,
  `_parse_download`, `_parse_fx_daily_response`, `_parse_fx_intraday_response`,
  `_parse_intraday_response`, `_parse_monthly_adjusted_response`,
  `_parse_monthly_response`, `_parse_sector_performance_response`,
  `_parse_single_series_response`, `_parse_technical_indicator_response`,
  `_parse_weekly_adjusted_response`, `_parse_weekly_response`.
- Several `_parse_*` methods build a `date` index from `datetime.now().date()`
  (e.g. `_parse_global_quote_response`, `_parse_currency_exchange_rate_response`).
  These ARE viable doctest candidates if you project only stable properties
  (`... is None`, `list(df.columns)`, `df.shape`) and never print the index/date.

### Key lesson (constrains the next doctest)
- `test_documented_examples_are_valid` compiles EACH `>>>` line in isolation
  (`_validate_doctest_lines`). A multi-line call whose first `>>>` line opens a
  paren (e.g. `>>> md = MarketData(`) FAILS with "(' was never closed", even
  though it is a valid doctest. Every `>>>` line must be independently valid
  Python. Prefer single-line statements, or build inputs across several `>>>`
  statements. (Class docstrings are NOT checked by this guard - only
  FunctionDef/AsyncFunctionDef.)
- The integrity guard only checks that `>>>` lines PARSE; the actual doctest
  OUTPUT is executed by `pytest --doctest-modules`, so any shown output must
  match exactly (no `datetime.now()`, no DataFrame repr unless stable).
- Always run a quick `python -c "..."` snippet to confirm the exact `columns`
  order / `shape` / values BEFORE writing them into the docstring.

### Next task
Continue the allowlist cleanup with `_parse_sector_performance_response`
(def at line ~2352). It is a pure `(self, data) -> pd.DataFrame | None` method
and is FULLY deterministic (no `datetime.now()`), so you may print the frame or
project stable properties. The following snippet was VERIFIED working this session
(output shown):

    >>> provider = AlphaVantageProvider(cache_dir="", warn_on_demo=False)
    >>> provider._parse_sector_performance_response({}) is None
    True
    >>> df = provider._parse_sector_performance_response({"Rank A: Real-Time Performance": {"Technology": "1.5"}})
    >>> list(df.columns)
    ['sector', 'period', 'performance']
    >>> df.shape
    (1, 3)

(For reference, `df.to_dict("records")` yields
`[{'sector': 'Technology', 'period': 'A: Real-Time', 'performance': 1.5}]`.)

Then remove `("quant_trading/data/yfinance_provider.py",
"_parse_sector_performance_response")` from `_EXAMPLES_ALLOWLIST` and re-run the
verification commands above (doctest module, integrity test, ruff, black,
`git diff --check`, full `pytest`). Keep each `>>>` line independently compilable.
(End of file)