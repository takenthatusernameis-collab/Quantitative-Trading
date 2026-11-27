## Session 2026-11-27 (allowlist cleanup - `_parse_monthly_adjusted_response`)

### What changed
- Documented `AlphaVantageProvider._parse_monthly_adjusted_response`
  in `quant_trading/data/yfinance_provider.py` (def at line ~1854) with a
  deterministic doctest projecting stable properties only: the `None` case,
  `list(df.columns)`, `df.shape`. Method is fully deterministic (no
  `datetime.now()`); its date index comes from the INPUT.
- Removed the `("quant_trading/data/yfinance_provider.py",
  "_parse_monthly_adjusted_response")` line from `_EXAMPLES_ALLOWLIST` in
  `tests/test_repository_integrity.py` (no blank line left behind).
- No production behavior changed (docstring + allowlist only).

### What was actually verified (evidence)
- `python -m pytest --doctest-modules quant_trading/data/yfinance_provider.py`
  -> 62 passed (was 61; +1 for the new doctest).
- `python -m pytest tests/test_repository_integrity.py` -> 51 passed.
- `python -m ruff check .` -> All checks passed.
- `python -m black --check quant_trading/ tests/ examples/` -> 166 files unchanged.
- `git diff --check` -> clean.
- `python -m mypy quant_trading/ tests/ examples/` -> Success: no issues found.
- `python -m pytest -q` (full) -> 5451 passed, 170 skipped, 151 deselected.
- `git diff --stat`: `quant_trading/data/yfinance_provider.py | 10 ++++++++++`,
  `tests/test_repository_integrity.py | 1 -`.
- Doctest output confirmed with a live `python -c` snippet BEFORE writing:
  `None` case True, columns `['open', 'high', 'low', 'close', 'adjusted_close', 'volume', 'dividend_amount', 'split_coefficient']`,
  shape `(1, 8)`, index `['2024-01-31']`.

### What remains unresolved
- `quant_trading/data/yfinance_provider.py` still has many allowlist entries:
  `_fetch_*`, `_get_yf`, most `_parse_*`, `get_*`, `search_symbols`.
- Remaining `_parse_*` allowlist entries (as of this session):
  `_parse_batch_response`, `_parse_download`, `_parse_single_series_response`,
  `_parse_technical_indicator_response`.
- Determinism note for the next agent: `_parse_batch_response` (line ~1613)
  builds a `date` index from `datetime.now().date()` -> NOT deterministic, skip
  for now. The other remaining `_parse_*` methods
  (download/single_series/technical) are FULLY deterministic - safe to print columns/shape/index.

### Key lesson (constrains the next doctest)
- `test_documented_examples_are_valid` compiles EACH `>>>` line in isolation
  (`_validate_doctest_lines`). A multi-line call whose first `>>>` line opens a
  paren FAILS with "(' was never closed", even though it is a valid doctest.
  Every `>>>` line must be independently valid Python. Prefer single-line
  statements, or build inputs across several `>>>` statements. (Class docstrings
  are NOT checked by this guard - only FunctionDef/AsyncFunctionDef.)
- The integrity guard only checks that `>>>` lines PARSE; the actual doctest
  OUTPUT is executed by `pytest --doctest-modules`, so any shown output must
  match exactly (no `datetime.now()`, no DataFrame repr unless stable).
- Always run a quick `python -c "..."` snippet to confirm the exact `columns`
  order / `shape` / index BEFORE writing them into the docstring.

### Next task
Continue the allowlist cleanup with `_parse_single_series_response`
(def at line ~1760). Signature:
`(self, symbol: str, data: dict, start: datetime | None, end: datetime | None)`.
It is FULLY deterministic (no `datetime.now()`) and its date index comes from
the INPUT, so it is stable. The following snippet was VERIFIED working this
session (output shown) - keep the call on ONE `>>>` line:

    >>> provider = AlphaVantageProvider(cache_dir="", warn_on_demo=False)
    >>> provider._parse_single_series_response("AAPL", {}, None, None) is None
    True
    >>> df = provider._parse_single_series_response("AAPL", {"Time Series (Daily)": {"2024-01-05": {"1. open": "150.0", "2. high": "151.0", "3. low": "149.0", "4. close": "150.5", "5. volume": "1000"}}}, None, None)
    >>> list(df.columns)
    ['open', 'high', 'low', 'close', 'volume']
    >>> df.shape
    (1, 5)

(For reference, the index is `2024-01-05`, i.e. `[str(i.date()) for i in df.index]`
-> `['2024-01-05']`.)

Then remove `("quant_trading/data/yfinance_provider.py",
"_parse_single_series_response")` from `_EXAMPLES_ALLOWLIST` and re-run the
verification commands above (doctest module, integrity test, ruff, black,
`git diff --check`, mypy, full `pytest`). Keep each `>>>` line independently
compilable and single-line where a call has multiple args.