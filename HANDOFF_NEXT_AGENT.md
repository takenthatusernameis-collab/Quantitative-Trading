## Status

**_align_series duplicate-index (both series) unit test added and verified.**

The assigned task — add a unit test in `tests/test_risk_metrics.py` directly exercising `_align_series` with duplicate indices in both input series to verify the positional fallback triggers and produces the expected paired frame — is complete.

## What changed

- `tests/test_risk_metrics.py`: Added `TestAlignSeries` class with two tests:
  - `test_duplicate_indices_both_series_positional_fallback`: both series carry duplicate labels ("a","a","b"); index alignment would cartesian-expand (5 rows), so `_align_series` must fall back to positional pairing. Asserts the paired frame equals `[[0.01,0.10],[0.02,0.20],[0.03,0.30]]`.
  - `test_positional_fallback_pairs_by_position_not_label`: verifies duplicate labels do not pair observations sharing a label across rows; each observation pairs with the one at the same position.
- No production behaviour change; `_align_series` logic untouched.

## What was verified

- `tests/test_risk_metrics.py tests/test_risk_attribution.py tests/test_backtest_engine.py tests/test_backtest_metrics.py tests/test_repository_integrity.py` → 414 passed (412 original + 2 new).
- `black --check`, `ruff check`, `mypy` clean.

## Unresolved

- `calculate_max_drawdown` zero/negative-peak semantics untested at engine level (pre-existing).

## One precise next task

Add an engine-level regression test in `tests/test_backtest_engine.py` covering `calculate_max_drawdown` zero/negative-peak semantics (e.g. an equity curve whose peak is zero or negative, verifying drawdown does not produce NaN/inf and matches `quant_trading/risk/metrics.py:calculate_max_drawdown` directly). Re-run the five test files + black/ruff/mypy. Do not touch workflows.
