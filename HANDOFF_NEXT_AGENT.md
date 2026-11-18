## Status

Fixed a real robustness bug in `calculate_max_drawdown`: an equity curve that
drops below zero while its running peak is still zero returned `-inf`
(e.g. `pd.Series([0.0, -5.0, 10.0])`). That value then propagated into
`BacktestMetrics.max_drawdown` / `max_drawdown_pct` and `calmar_ratio`.

## What changed

- `quant_trading/risk/metrics.py`
  - `calculate_max_drawdown` now computes the drawdown ratio inside
    `np.errstate(divide="ignore", invalid="ignore")`, replaces `±inf` with
    `NaN`, and drops undefined (zero-peak) observations before taking the
    minimum. If no defined drawdown remains it returns `0.0`.
  - Added a short docstring note and a doctest:
    `calculate_max_drawdown(pd.Series([0.0, -5.0, 10.0])) == 0.0`.
- `tests/test_risk_metrics.py` (`TestCalculateMaxDrawdown`)
  - `test_negative_equity_against_zero_peak_is_finite`
  - `test_zero_peak_is_ignored_before_later_drawdown` (verifies a real later
    drawdown of `-0.5` is still reported).
- `tests/test_backtest_metrics.py`
  - `test_negative_equity_with_zero_peak_is_finite` asserts finite
    `max_drawdown`, `max_drawdown_pct`, and `calmar_ratio` at the
    `calculate_backtest_metrics` level.
- `tests/test_repository_integrity.py`
  - Shifted the `_EXAMPLES_ALLOWLIST` line numbers for 7 functions in
    `quant_trading/risk/metrics.py` by `+12` to match the new file positions
    (required by `test_documented_examples_are_valid`).

## What was actually verified

- `python -m pytest tests/test_risk_metrics.py tests/test_backtest_metrics.py quant_trading/risk/metrics.py -q` → 194 passed.
- `python -m pytest tests/test_repository_integrity.py -q` → 50 passed (after allowlist update).
- `python -m pytest tests/test_risk_manager.py tests/test_risk_attribution.py tests/test_backtest_engine.py tests/test_backtest_report.py tests/test_serialization_roundtrip.py tests/test_cost_accounting_invariants.py -q` → all passed (602 passed, 48 skipped).
- Full suite: `python -m pytest -q -p no:cacheprovider` → **3981 passed, 104 skipped, 142 deselected in 363.87s**.
- `ruff check`, `black --check`, and `mypy` clean on all touched Python files.

## Remaining work / unresolved

- `quant_trading/backtest/report.py` still computes drawdowns inline for charts
  (`_create_drawdown_chart` around line 200 and
  `_create_comparison_drawdown_chart` around line 1084). Those paths can still
  feed `±inf` into matplotlib for zero-peak equity curves. They are untested
  here because matplotlib is not installed in this environment (optional
  `reporting` extra; related tests are skipped).
- Allowlist line numbers are brittle: any change above an allowlisted function
  in `quant_trading/risk/metrics.py`, `examples/cli.py`, or `report.py` shifts
  them and requires the `+N` adjustment in `tests/test_repository_integrity.py`.
  Prefer not inserting code above allowlisted functions when avoidable.

## Approaches already tried and why (avoid repeating)

- Reviewed risk-metrics VaR/component-VaR semantics: tests deliberately define
  the component sum as CVaR (tail mean), not quantile VaR; do not "fix" this.
- Optional-dependency coverage gaps (`report.py` charts, `optimization/bayesian.py`
  and `sensitivity.py`) are due to missing matplotlib/skopt, not missing logic.

## One precise next task

Make drawdown rendering consistent with the metric fix: add a small pure helper
in `quant_trading/backtest/report.py` (e.g. `_drawdown_series(equity)`) that
replaces `±inf` with `NaN`, treats zero-peak points as neutral, and returns a
finite drawdown series; use it in `_create_drawdown_chart` and
`_create_comparison_drawdown_chart`. Add unit tests for the helper that do not
require matplotlib (import it directly) covering `[0, -5, 10]`, a normal
drawdown `[100, 110, 90]`, and a later drawdown after a zero prefix. Verify with
`python -m pytest tests/test_backtest_report.py tests/test_repository_integrity.py -q`,
`python -m ruff check`, `python -m black --check`, and `python -m mypy` on
`quant_trading/backtest/report.py`; update the allowlist line numbers if new
lines land above allowlisted functions.
