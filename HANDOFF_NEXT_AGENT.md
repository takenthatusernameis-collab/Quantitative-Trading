## Session 2026-11-27 (allowlist cleanup - regime/detector.py, pass 2)

### What changed
- Rewrote the `Examples:` doctests of 4 public `quant_trading/regime/detector.py`
  callables from multi-line (`...` continuation) to SINGLE-LINE `>>>` form,
  preserving the exact calls and confirmed outputs:
  - `RegimeDetector.detect`
  - `detect_regimes`
  - `RegimeResult.summary`
  - `RegimeResult.to_dataframe`
- Removed their 4 allowlist entries from `_EXAMPLES_ALLOWLIST` in
  tests/test_repository_integrity.py (lines `detect`, `detect_regimes`,
  `summary`, `to_dataframe`).
- Allowlist shrank by 4 lines.

### What remains allowlisted in regime/detector.py (5 lines)
- `__init__` (RegimeDetector.__init__ has a docstring but NO Examples section yet -
  needs a single-line doctest added before it can be de-allowlisted)
- `_build_segments`, `_label_series`, `_make_segment`, `_merge_segments` (private;
  do NOT de-allowlist - not public API)

### What was verified (evidence)
- `pytest tests/test_repository_integrity.py --doctest-modules quant_trading/regime/detector.py`
  -> 64 passed, 1 skipped.
- `pytest tests/test_repository_integrity.py -k "examples or allowlist"` -> 3 passed.
- `python -m ruff check quant_trading/regime/detector.py tests/test_repository_integrity.py` -> All checks passed.
- `python -m black --check quant_trading/regime/detector.py tests/test_repository_integrity.py` -> 2 files unchanged.
- Full `pytest -q` -> 5278 passed, 260 skipped, 151 deselected (0 failures).

### IMPORTANT: failed approach / constraints this session (do not repeat)
- Do NOT try to de-allowlist private methods (`_build_segments`, `_label_series`,
  `_make_segment`, `_merge_segments`) - they are not public API.
- Do NOT de-allowlist `__init__` until it gains a non-empty Examples section
  (it currently has none; the guard flags docstring-having functions without
  Examples unless allowlisted).
- Only de-allowlist functions whose Examples use single-line `>>>` statements
  only, and confirm exact output first (the previous multi-line `pd.Series(...
  ...)` blocks required a single-line rewrite before de-allowlisting).
- Ruff uses default rules (no E501), so long single-line `>>>` lines are fine;
  black does not reformat docstring content.

### Notes for next session
- Pattern that works: build objects directly, keep each `>>>` single-line,
  confirm exact output first (outputs here confirmed by the passing doctest run:
  `n_segments` -> `1`, `current_regime.value` -> 'sideways_low_vol',
  `"regime_counts" in summary` -> `True`, `len(df)` -> `1`,
  `"regime" in df.columns` -> `True`).

### Next task
Pick one more bounded module and clear its PUBLIC single-line-doctestable
allowlist entries. Good candidates (public, data-only, no heavy runs):
- `quant_trading/risk/metrics.py`: already fully clean (80 doctests passed) -
  nothing to do there; this session's earlier suggestion was stale.
- Scan `_EXAMPLES_ALLOWLIST` (tests/test_repository_integrity.py ~line 1787)
  for a public function with a docstring but NO Examples section (the guard
  enforces these unless allowlisted). E.g. `quant_trading/backtest/analysis.py`
  or `quant_trading/risk/manager.py` public entries. Add a confirmed-output
  single-line doctest, then de-allowlist.
- Alternatively `quant_trading/portfolio/portfolio.py` `Holding.from_dict` /
  `Portfolio.from_dict` still need multi-line `>>>` rewrite to de-allowlist.
- Verify with `pytest tests/test_repository_integrity.py --doctest-modules <module>`
  and `ruff check`, then full `pytest -q`.

(End of file)
