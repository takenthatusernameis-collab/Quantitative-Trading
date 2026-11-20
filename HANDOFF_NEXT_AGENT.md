## Status

**calculate_calmar_ratio positive-peak engine-level regression test added and verified.**

The assigned task — add an engine-level regression test in `tests/test_backtest_engine.py` covering `calculate_calmar_ratio` on a normal positive-peak equity curve with positive net return — is complete.

## What changed

- `tests/test_backtest_engine.py`:
  - Added `TestCalmarRatioPositivePeak` class after `TestUlcerIndexPositivePeak`, mirroring `TestMaxDrawdownPositivePeak` / `TestUlcerIndexPositivePeak`:
    - `test_positive_peak_positive_return_reports_finite_positive_calmar_matching_direct_call`: equity `[100.0, 90.0, 110.0, 105.0, 120.0]` (positive running peak, positive net return) reports finite, non-NaN, strictly positive Calmar ratio (~138.36) matching `quant_trading/risk/metrics.py:calculate_calmar_ratio` directly, with `metrics.calmar_ratio == pytest.approx(expected)` and `metrics.calmar_ratio > 0.0`.
    - Derives `returns` consistently with `calculate_backtest_metrics` (via `calculate_returns` from `quant_trading/backtest/metrics.py:329`), then calls `calculate_calmar_ratio(returns, equity_curve)`.
- No production behaviour change; `calculate_calmar_ratio` logic untouched.

## What was verified

- `tests/test_backtest_engine.py tests/test_risk_metrics.py tests/test_risk_attribution.py tests/test_backtest_metrics.py tests/test_repository_integrity.py` → 423 passed (422 original + 1 new calmar positive-peak).
- `black --check`, `ruff check`, `mypy` clean on `tests/test_backtest_engine.py`.

## Unresolved

- None from this assignment.

## One precise next task

Add an engine-level regression test in `tests/test_backtest_engine.py` covering `calculate_calmar_ratio` on a **non-positive-peak** equity curve (mirroring `TestMaxDrawdownNonPositivePeak` / `TestUlcerIndexNonPositivePeak`): a `TestCalmarRatioNonPositivePeak` class with a `_metrics` staticmethod returning `calculate_backtest_metrics(equity_curve)`, and tests for an all-zero-peak curve (`[0.0, -5.0, -10.0]`), an all-negative-peak curve (`[-5.0, -10.0, -3.0]`), and a zero-start-then-recovery curve (`[0.0, -5.0, 10.0]`). Each must assert the direct `calculate_calmar_ratio(returns, equity_curve)` call is finite, non-NaN, equals `0.0` (since max drawdown is 0 on a non-positive peak), and that `metrics.calmar_ratio == pytest.approx(expected)`. Derive `returns` via `calculate_returns(equity_curve)` as in `quant_trading/backtest/metrics.py:329`. Re-run the five test files + black/ruff/mypy. Do not touch workflows.

(End of file - total 26 lines)