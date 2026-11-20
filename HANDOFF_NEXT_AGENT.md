## Status

**Fixed a crash in `_align_series` when only one input series has duplicate index labels; verified.**

The assigned task (`TestCalmarRatioNonPositivePeak`) was already committed in `cbea7f6`; this session verified it and then fixed a reproducible defect found while probing the same metric path.

## What changed

- `quant_trading/risk/metrics.py` (`_align_series`): duplicate-label detection already existed, but the label-alignment `pd.concat` ran **before** the fallback and raised `ValueError: cannot reindex on an axis with duplicate labels` whenever one series had duplicate labels and the other needed reindexing. The duplicate case now pairs rows positionally before any label alignment. Affects `calculate_beta`, `calculate_alpha`, `calculate_treynor_ratio`, `calculate_information_ratio`, and `calculate_calmar_ratio`.
- `tests/test_risk_metrics.py` (`TestAlignSeries`):
  - `test_duplicate_labels_in_one_series_fall_back_instead_of_raising`: duplicate labels on one side, disjoint labels on the other; asserts positional pairing `[[0.01,0.10],[0.02,0.20],[0.03,0.30]]` instead of raising.
  - `test_duplicate_equity_labels_do_not_break_beta`: both sides carry duplicate labels (different positions); asserts `calculate_beta` stays finite.
- No other production behaviour changed; non-duplicate label alignment and the <2-overlap fallback are unchanged.

## What was verified

- Pre-fix reproduction: both new tests failed with `ValueError: cannot reindex on an axis with duplicate labels`; post-fix both pass.
- `tests/test_risk_metrics.py tests/test_risk_attribution.py tests/test_backtest_metrics.py tests/test_backtest_engine.py tests/test_repository_integrity.py` → 428 passed.
- Full suite → 4102 passed, 113 skipped, 151 deselected.
- `black --check`, `ruff check`, `mypy` clean on both changed files.
- Manual check: `calculate_calmar_ratio` on an equity curve with duplicate labels (`["a","a","b","b"]`) now returns 121.33 instead of raising.

## Unresolved

- `quant_trading/risk/metrics.py:515-517` (the `get_loc` slice/ndarray conversion used to seed the pre-return equity bar) is still uncovered by tests; it is only reachable with duplicate equity labels, the exact case just fixed.

## One precise next task

Add a regression test in `tests/test_risk_metrics.py` covering `calculate_calmar_ratio` with duplicate equity index labels so the `get_loc` slice/ndarray branch at `quant_trading/risk/metrics.py:515-517` executes: equity `pd.Series([100.0, 90.0, 80.0, 120.0], index=["a","a","b","b"])`, returns via `calculate_returns(equity)`. Assert no exception, finite positive result matching `pytest.approx(121.3333333333333)` computed from `annual_return / abs(max_drawdown)` over the seeded drawdown sample, and add an equivalent duplicate-label `calculate_information_ratio` finite assertion. Re-run the five/five-plus test files + black/ruff/mypy, and re-check coverage reports lines 515-517 as hit. Do not touch workflows.
