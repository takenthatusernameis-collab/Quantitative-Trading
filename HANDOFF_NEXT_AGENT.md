## Status

**calculate_max_drawdown positive-peak engine-level regression test added and verified.**

The assigned task — add an engine-level regression test in `tests/test_backtest_engine.py` covering `calculate_max_drawdown` on a normal positive-peak equity curve — is complete.

## What changed

- `tests/test_backtest_engine.py`:
  - Added `TestMaxDrawdownPositivePeak` class after `TestMaxDrawdownNonPositivePeak`, mirroring `TestUlcerIndexPositivePeak`:
    - `test_positive_peak_reports_finite_negative_max_drawdown_matching_direct_call`: equity `[100.0, 110.0, 105.0, 90.0, 95.0]` (strictly positive running peak) reports finite, non-NaN, strictly negative max drawdown (~-0.181818) matching `quant_trading/risk/metrics.py:calculate_max_drawdown` directly, with `metrics.max_drawdown_pct == pytest.approx(expected * 100)`.
  - Drives the engine's metrics path via `calculate_backtest_metrics` (quant_trading/backtest/engine.py:929).
- No production behaviour change; `calculate_max_drawdown` logic untouched.

## What was verified

- `tests/test_backtest_engine.py tests/test_risk_metrics.py tests/test_risk_attribution.py tests/test_backtest_metrics.py tests/test_repository_integrity.py` → 422 passed (421 original + 1 new max-drawdown positive-peak).
- `black --check`, `ruff check`, `mypy` clean on `tests/test_backtest_engine.py`.

## Unresolved

- None from this assignment.

## One precise next task

Add an engine-level regression test in `tests/test_backtest_engine.py` covering `calculate_calmar_ratio` on a normal positive-peak equity curve with positive net return (e.g. `[100.0, 90.0, 110.0, 105.0, 120.0]`), verifying Calmar ratio is finite, non-NaN, strictly positive (> 0, since net return > 0 and max drawdown < 0), and matches `quant_trading/risk/metrics.py:calculate_calmar_ratio` directly, driven through `calculate_backtest_metrics` (quant_trading/backtest/engine.py:929). Assert `metrics.calmar_ratio == pytest.approx(expected)` and `metrics.calmar_ratio > 0.0`, mirroring `TestMaxDrawdownPositivePeak`. Note: `calculate_calmar_ratio(returns, equity_curve, periods_per_year)` takes a `returns` argument — derive `returns` consistently with how `calculate_backtest_metrics` computes it (quant_trading/backtest/metrics.py:342, BacktestMetrics.calmar_ratio at :123). Re-run the five test files + black/ruff/mypy. Do not touch workflows.
