## Session 2026-11-27 (allowlist cleanup - regime/detector.py)

### What changed
- Added valid, runnable SINGLE-LINE `Examples:` doctests to 4 public
  `quant_trading/regime/detector.py` callables that lacked them, and removed
  their allowlist entries:
  - `RegimeSegment.to_dict`, `RegimeSegment.from_dict`
  - `RegimeResult.to_dict`, `RegimeResult.from_dict`
- Each example builds `RegimeSegment(...)` / `RegimeResult(...)` directly and
  prints a scalar / dict key - no backtest/heavy run. Fast + deterministic.
- Allowlist shrank by 4 lines (2 distinct names; `from_dict` and `to_dict`
  were each listed twice for the two classes).
- Remaining regime/detector.py entries (9 lines): `__init__`, `_build_segments`,
  `_label_series`, `_make_segment`, `_merge_segments`, `detect`,
  `detect_regimes`, `summary`, `to_dataframe` (all private or already have
  working Examples).

### What was verified (evidence)
- `pytest tests/test_repository_integrity.py --doctest-modules quant_trading/regime/detector.py`
  -> 64 passed, 1 skipped (4 new doctest assertions added).
- `python -m ruff check quant_trading/regime/detector.py tests/test_repository_integrity.py`
  -> All checks passed.
- `python -m black --check` on both files -> 2 files unchanged.
- Guard tests `pytest tests/test_repository_integrity.py -k "examples or allowlist"`
  -> 3 passed.
- Related tests `pytest tests/test_risk_metrics.py tests/test_regime.py -q`
  -> 378 passed.

### IMPORTANT: failed approach this session (do not repeat)
- Do NOT try to de-allowlist private methods (`_build_segments`, `_label_series`,
  `_make_segment`, `_merge_segments`) - they are not public API and don't need
  user-facing examples.
- The `__init__`, `detect`, `detect_regimes`, `summary`, `to_dataframe` methods
  already have working Examples and can be removed from the allowlist in a
  future cleanup pass (they are currently stale entries).

### Notes for next session
- Pattern that works: build result objects directly from `RegimeSegment(...)` /
  `RegimeResult(...)`; keep each `>>>` statement single-line and confirm exact
  output first. Timestamps serialize as `'2024-01-01 00:00:00'` format.
- Non-finite values (NaN/inf) in `from_dict` are sanitized to `0.0` for numeric
  fields and `0` for integer fields - verified with `float("nan")` / `float("inf")`.
- Ruff uses default rules (no E501), so long single-line `>>>` lines are fine;
  black does not reformat docstring content.

### Next task
Pick one more bounded module and clear its PUBLIC single-line-doctestable
allowlist entries. Good candidates (public, data-only, no heavy runs):
- `quant_trading/risk/metrics.py`: public `calculate_alpha`,
  `calculate_component_var`, `calculate_equal_risk_contribution_weights`,
  `calculate_marginal_var`, `calculate_risk_budget_weights`,
  `calculate_volatility_contributions`, `to_dict`/`from_dict` - need small
  numpy arrays / dataclass; verify exact float reprs with `python -c`.
- Alternatively scan `_EXAMPLES_ALLOWLIST` (tests/test_repository_integrity.py
  ~line 1787) for the next module whose public functions have NO Examples yet.
- Note: `quant_trading/portfolio/portfolio.py` still has 2 allowlist entries
  (`Holding.from_dict`, `Portfolio.from_dict`) that need multi-line `>>>`
  rewrite to de-allowlist.
- Verify with `pytest tests/test_repository_integrity.py --doctest-modules <module>`
  and `ruff check`, then full `pytest -q`. Only de-allowlist functions whose
  Examples use single-line `>>>` statements only, and confirm exact output first.

(End of file - total 65 lines)