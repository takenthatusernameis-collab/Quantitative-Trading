## Status

**Prior assigned task complete:** regression tests for `calculate_calmar_ratio` and `calculate_information_ratio` with duplicate index labels exist in `tests/test_risk_metrics.py` and pass.

**This session:** added `TestCalculateCalmarRatio::test_calmar_duplicate_labels_get_loc_slice_branch` covering the `get_loc` slice/ndarray branch at `quant_trading/risk/metrics.py:518-524`.

- The `_align_series` refactor from the prior handoff (label alignment first; positional fallback only on cartesian expansion/insufficient overlap) was already committed (`5ec2e07 Fix _align_series crash on duplicate index labels`), so no implementation change was needed.
- The prior handoff's example (`equity index ["a","a","y","z"]`, `returns index ["y","z"]`) does NOT reach the slice branch: `pd.concat` raises `ValueError` on duplicate labels, so `_align_series` falls back to positional alignment and `get_loc` hits `KeyError`. The new test uses identical indexes with a contiguous duplicated leading label (`equity`/`returns` index `["a","a","a","b"]`), so label alignment is used and `equity_curve.index.get_loc("a")` returns `slice(0, 3)`, executing lines 518-519 and the `except (KeyError, TypeError, ValueError)` block (line 519's `int(slice)` raises `TypeError`).
- Coverage verified: lines 518, 519, 523-525 now executed; only the `pos > 0` seed sub-branch (lines 521-522) remains uncovered, which needs a case where `get_loc` returns positions whose first element is `> 0` without raising (e.g. index `["b","b","a","a"]` → `get_loc("a")` → `array([2, 3])` → `pos = 2`).

## What was verified

- `tests/test_risk_metrics.py tests/test_risk_attribution.py tests/test_backtest_metrics.py tests/test_backtest_engine.py tests/test_repository_integrity.py` → 431 passed (430 before + 1 new).
- `black --check`, `ruff check`, `mypy quant_trading/` all clean.

## Unresolved

- Lines 521-522 (seed bar prepended when `pos > 0`) still uncovered. Reaching them requires `get_loc` to return a slice/ndarray whose first position is `> 0` and the `int()` conversion not to raise (slice input raises `TypeError`, so use an ndarray case with non-overlapping leading labels).

## One precise next task

Add a test where `equity` and `returns` share an identical index whose first aligned label is duplicated at positions `> 0` in `equity` (e.g. `equity = pd.Series([...], index=["b","b","a","a"])`, `returns` same index), so `get_loc("a")` → `array([2, 3])`, `pos = 2 > 0`, the seed bar is prepended (lines 521-522), and `max_dd`/`calmar` are computed from the seeded sample. Verify coverage now includes 521-522, then re-run the five test files + black/ruff/mypy.
