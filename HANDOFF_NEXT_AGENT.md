## Status

**Verified existing regression tests for duplicate index labels in `calculate_calmar_ratio` and `calculate_information_ratio`; all tests pass.**

The assigned task requested adding regression tests covering `calculate_calmar_ratio` and `calculate_information_ratio` with duplicate index labels. Both tests already exist in `tests/test_risk_metrics.py` and were verified:

- `TestCalculateCalmarRatio::test_calmar_duplicate_equity_labels_get_loc_branch` — equity `pd.Series([100.0, 90.0, 80.0, 120.0], index=["a","a","b","b"])`, returns via `calculate_returns(equity)`. Asserts no exception, finite positive result matching `pytest.approx(121.3333333333333)`.
- `TestCalculateInformationRatio::test_information_ratio_duplicate_labels_finite` — returns and benchmark with overlapping duplicate labels; asserts finite result.

## What was verified

- Both tests pass without exception.
- `tests/test_risk_metrics.py tests/test_risk_attribution.py tests/test_backtest_metrics.py tests/test_backtest_engine.py tests/test_repository_integrity.py` → 430 passed.
- `black --check`, `ruff check`, `mypy` clean on all project files.
- The duplicate-label handling in `_align_series` (positional fallback) works correctly for both metrics.

## Unresolved

- Coverage for the `get_loc` slice/ndarray branch at `quant_trading/risk/metrics.py:519-529` (lines 515-517 in the original handoff) remains uncovered. This branch is **unreachable with the current `_align_series` implementation** because it resets the index to a RangeIndex whenever duplicates are detected in either series. Consequently, `equity_curve.index.get_loc(aligned_equity.index[0])` receives an integer (0) that does not exist in the original index, triggering the `except (KeyError, TypeError, ValueError)` block instead of the `isinstance(pos, (slice, np.ndarray))` branch. Achieving coverage here would require modifying `_align_series` to preserve labels when duplicates don't cause cartesian expansion, which is outside the scope of this task (no workflow/implementation changes permitted).

## One precise next task

If coverage of the `get_loc` slice/ndarray branch is required, refactor `_align_series` to only fall back to positional alignment when label alignment would actually produce a cartesian expansion or insufficient overlap, rather than on any duplicate presence. Then add a test with an equity curve where duplicates exist only in non-overlapping labels (e.g., `equity = pd.Series([100, 90, 80, 120], index=["a","a","y","z"])`, `returns = pd.Series([0.01, 0.02], index=["y","z"])`) so label alignment is used and `get_loc("y")` returns a slice. Verify coverage hits lines 519-529, then re-run the five test files + black/ruff/mypy.