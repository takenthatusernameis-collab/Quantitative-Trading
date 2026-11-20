## Status

**calculate_ulcer_index positive-peak engine-level regression test added and verified.**

The assigned task — add an engine-level regression test in `tests/test_backtest_engine.py` covering `calculate_ulcer_index` on a normal positive-peak equity curve — is complete.

## What changed

- `tests/test_backtest_engine.py`:
  - Added `TestUlcerIndexPositivePeak` class with one test mirroring `TestUlcerIndexNonPositivePeak`:
    - `test_positive_peak_reports_finite_positive_ulcer_index_matching_direct_call`: equity `[100.0, 110.0, 105.0, 90.0, 95.0]` (strictly positive running peak) reports finite, non-NaN, strictly positive ulcer index (~0.10365) matching `quant_trading/risk/metrics.py:calculate_ulcer_index` directly.
  - Drives the engine's metrics path via `calculate_backtest_metrics` (quant_trading/backtest/engine.py:929).
- No production behaviour change; `calculate_ulcer_index` logic untouched.

## What was verified

- `tests/test_backtest_engine.py tests/test_risk_metrics.py tests/test_risk_attribution.py tests/test_backtest_metrics.py tests/test_repository_integrity.py` → 421 passed (414 original + 3 max-drawdown + 3 ulcer-index non-positive + 1 new ulcer-index positive-peak).
- `black --check`, `ruff check`, `mypy` clean on `tests/test_backtest_engine.py`.

## Unresolved

- None from this assignment.

## One precise next task

Add an engine-level regression test in `tests/test_backtest_engine.py` covering `calculate_max_drawdown` on a normal positive-peak equity curve (e.g. `[100, 110, 105, 90, 95]`), verifying Max Drawdown is finite, non-NaN, strictly negative (< 0), and matches `quant_trading/risk/metrics.py:calculate_max_drawdown` directly, driven through `calculate_backtest_metrics` (the engine's path at `quant_trading/backtest/engine.py:929`). Assert both `metrics.max_drawdown` and `metrics.max_drawdown_pct` (== expected * 100), mirroring `TestMaxDrawdownNonPositivePeak`. This complements `TestMaxDrawdownNonPositivePeak` (which covers the neutral 0.0 branch) by covering the defined non-zero branch. Re-run the five test files + black/ruff/mypy. Do not touch workflows.
