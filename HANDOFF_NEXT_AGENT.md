## Status

Completed the previously queued task: drawdown chart rendering now shares the
metric-level robustness fix. Equity curves whose running peak is zero (or
negative) no longer feed `±inf` into matplotlib chart data.

## What changed

- `quant_trading/backtest/report.py`
  - New pure helper `_drawdown_series(equity) -> pd.Series`:
    computes percentage drawdown against `equity.expanding().max()`, masks a
    running peak that is not strictly positive (`peak.where(peak > 0)`),
    replaces `±inf` with `NaN`, and `fillna(0.0)` so the result is always
    finite. Empty input returns an empty float series.
  - `_create_drawdown_chart` now uses `_drawdown_series(result.equity_curve)`
    instead of inline `(equity - peak) / peak * 100`.
  - `_create_comparison_drawdown_chart` now uses
    `_drawdown_series(equity)` for each result.
- `tests/test_backtest_report.py`
  - Imported `_drawdown_series` and added 4 matplotlib-free tests:
    `[0, -5, 10]` -> all zeros, normal `[100, 110, 90]` -> `-18.18%`,
    `[0, 100, 50]` -> later `-50%` preserved, and empty / all-negative
    curves -> finite neutral series.
- `tests/test_repository_integrity.py`
  - Shifted the report.py entries in `_EXAMPLES_ALLOWLIST` to their new
    line numbers (+22/+23 depending on the function) and added
    `("quant_trading/backtest/report.py", "_drawdown_series", 192)`.

## What was actually verified

- `python -m pytest tests/test_backtest_report.py tests/test_repository_integrity.py -q -p no:cacheprovider`
  -> 85 passed, 48 skipped.
- `python -m pytest tests/test_backtest_engine.py tests/test_backtest_metrics.py tests/test_serialization_roundtrip.py tests/test_core_only_imports.py tests/test_packaging.py -q`
  -> 216 passed.
- Full suite: `python -m pytest -q -p no:cacheprovider` ->
  **3985 passed, 104 skipped, 142 deselected in 363.05s**.
- `ruff check`, `black --check`, and `mypy` clean on
  `quant_trading/backtest/report.py`, `tests/test_backtest_report.py`, and
  `tests/test_repository_integrity.py`.

## Remaining work / unresolved

- The two chart functions themselves are still untested here because
  matplotlib is not installed (optional `reporting` extra; chart tests skip).
  Only the pure helper is covered.
- Allowlist line numbers in `tests/test_repository_integrity.py` remain
  brittle for `report.py`, `risk/metrics.py`, and `examples/cli.py`: inserting
  lines above an allowlisted def requires recomputing them.
- `_drawdown_series` deliberately treats all-negative equity curves as neutral
  (0.0). `calculate_max_drawdown` in `risk/metrics.py` only special-cases zero
  peaks, so an all-negative curve can still produce a positive "drawdown"
  ratio there. Do not change that metric without checking its callers/tests.

## Approaches already tried and why (avoid repeating)

- Reviewed VaR/component-VaR semantics: tests deliberately define the
  component sum as CVaR (tail mean), not quantile VaR; do not "fix" this.
- Optional-dependency coverage gaps (`report.py` charts,
  `optimization/bayesian.py`, `optimization/sensitivity.py`) are due to missing
  matplotlib/skopt, not missing logic. Do not chase coverage in those files
  without installing the extras.
- Rolling Sharpe chart non-finite concerns were investigated: the linear test
  equity yields a huge but finite ratio (~1880), not `inf`, so there is no
  demonstrated defect to fix there yet.

## One precise next task

Harden the remaining report chart paths against degenerate equity curves by
extracting a reusable finite-series guard, e.g.
`_finite_series(series)` in `quant_trading/backtest/report.py` that returns
`series.replace([np.inf, -np.inf], np.nan).dropna()`, and apply it to the
rolling Sharpe/volatility inputs in `_create_rolling_sharpe_chart`,
`_create_rolling_volatility_chart`, and their comparison counterparts so that
a zero-variance return window cannot push `inf` into the plotted values. Add
matplotlib-free unit tests for the helper covering `[0.0, np.inf, -np.inf, 1.0]`
and an empty series, then verify with
`python -m pytest tests/test_backtest_report.py tests/test_repository_integrity.py -q`,
`python -m ruff check`, `python -m black --check`, and `python -m mypy
quant_trading/backtest/report.py`; update `_EXAMPLES_ALLOWLIST` line numbers
in `tests/test_repository_integrity.py` for any function that moves.
