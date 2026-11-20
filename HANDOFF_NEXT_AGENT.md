## Status

**calculate_ulcer_index zero/negative-peak engine-level regression test added and verified.**

The assigned task — add an engine-level regression test in `tests/test_backtest_engine.py` covering `calculate_ulcer_index` zero/negative-peak semantics — is complete.

## What changed

- `tests/test_backtest_engine.py`:
  - Added `calculate_ulcer_index` to the import from `quant_trading.risk.metrics`.
  - Added `TestUlcerIndexNonPositivePeak` class with three tests mirroring `TestMaxDrawdownNonPositivePeak`:
    - `test_zero_peak_reports_finite_ulcer_index_matching_direct_call`: equity `[0.0, -5.0, -10.0]` (running peak zero) reports finite, non-NaN ulcer index of 0.0 matching the direct call.
    - `test_negative_peak_reports_finite_ulcer_index_matching_direct_call`: equity `[-5.0, -10.0, -3.0]` (running peak negative) reports finite, non-NaN ulcer index of 0.0 matching the direct call.
    - `test_zero_start_then_recovery_reports_finite_ulcer_index_matching_direct_call`: equity `[0.0, -5.0, 10.0]` reports finite, non-NaN ulcer index matching the direct call.
  - Each test drives the engine's metrics path via `calculate_backtest_metrics` (the same call the engine makes at `quant_trading/backtest/engine.py:929`) and asserts `ulcer_index` matches `quant_trading/risk/metrics.py:calculate_ulcer_index` directly.
- No production behaviour change; `calculate_ulcer_index` logic untouched.

## What was verified

- `tests/test_backtest_engine.py tests/test_risk_metrics.py tests/test_risk_attribution.py tests/test_backtest_metrics.py tests/test_repository_integrity.py` → 420 passed (414 original + 3 max-drawdown + 3 new ulcer-index).
- `black --check`, `ruff check`, `mypy` clean on `tests/test_backtest_engine.py`.

## Unresolved

- None from the prior assignment.

## One precise next task

Add an engine-level regression test in `tests/test_backtest_engine.py` covering `calculate_ulcer_index` on a normal positive-peak equity curve (e.g. `[100, 110, 105, 90, 95]`), verifying the Ulcer Index is finite, non-NaN, strictly positive, and matches `quant_trading/risk/metrics.py:calculate_ulcer_index` directly, driven through `calculate_backtest_metrics` (the engine's path at `quant_trading/backtest/engine.py:929`). This complements the `TestUlcerIndexNonPositivePeak` class just added (which covers the undefined/neutral 0.0 branch) by covering the defined non-zero branch. Re-run the five test files + black/ruff/mypy. Do not touch workflows.
