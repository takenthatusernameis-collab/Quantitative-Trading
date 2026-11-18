## Status

Completed the previously queued task: drawdown chart rendering now shares the
metric-level robustness fix (`_finite_series` applied to all four rolling
Sharpe/volatility chart paths), plus matplotlib-free unit tests and an
allowlist entry. Separately completed in this session: hardened
`calculate_max_drawdown` against all-negative equity curves so it reports a
neutral 0.0 drawdown instead of a sign-flipped ratio, consistent with
`_drawdown_series`.

## What changed

- `quant_trading/risk/metrics.py`
  - `calculate_max_drawdown`: generalized the degenerate-peak guard from
    `running_max.eq(0).all()` to `running_max.max() <= 0`, so an all-negative
    (or all-zero/zero-and-negative) equity curve whose running peak is never
    strictly positive returns `0.0` instead of a sign-flipped ratio.
  - Updated the `Returns` docstring to document the neutral case.
- `tests/test_risk_metrics.py`
  - Added `test_all_negative_equity_reports_neutral_drawdown`
    (`[-5.0, -10.0, -3.0]` -> `0.0`) and
    `test_zero_and_negative_equity_reports_neutral_drawdown`
    (`[0.0, -5.0, -2.0]` -> `0.0`).
- `quant_trading/backtest/report.py`, `tests/test_backtest_report.py`,
  `tests/test_repository_integrity.py`: unchanged from prior session
  (`_finite_series` already present, applied to all four rolling chart paths,
  tested, and allowlisted at report.py:216).

## What was actually verified

- `python -m pytest tests/test_risk_metrics.py tests/test_backtest_metrics.py -q -p no:cacheprovider`
  -> 175 passed.
- `python -m pytest --doctest-modules quant_trading/risk/metrics.py -q -p no:cacheprovider`
  -> 21 passed (docstring example `calculate_max_drawdown([0.0, -5.0, 10.0])`
  still returns `0.0` via the normal path).
- `python -m pytest tests/test_backtest_report.py tests/test_repository_integrity.py -q -p no:cacheprovider`
  -> 89 passed, 48 skipped (matplotlib absent).
- `ruff check`, `black --check`, and `mypy quant_trading/risk/metrics.py`
  and `tests/test_risk_metrics.py` clean.

## Remaining work / unresolved

- Chart functions remain untested because matplotlib is not installed
  (optional `reporting` extra; chart tests skip). Only pure helpers are
  covered.
- `calculate_ulcer_index` (risk/metrics.py:1078) has the same all-negative
  sign-flip problem as `calculate_max_drawdown` had: an all-negative curve
  yields a non-zero ulcer index while `_drawdown_series` reports neutral
  0.0. It uses `fillna(0.0)` so it never raises, but it is inconsistent with
  the chart-level drawdown series.
- Allowlist line numbers in `tests/test_repository_integrity.py` remain
  brittle for `report.py`, `risk/metrics.py`, and `examples/cli.py`: inserting
  lines above an allowlisted def requires recomputing them.

## Approaches already tried and why (avoid repeating)

- Reviewed VaR/component-VaR semantics: tests deliberately define the
  component sum as CVaR (tail mean), not quantile VaR; do not "fix" this.
- Optional-dependency coverage gaps (`report.py` charts,
  `optimization/bayesian.py`, `optimization/sensitivity.py`) are due to missing
  matplotlib/skopt, not missing logic.
- Rolling Sharpe chart non-finite concerns: the linear test equity yields a
  huge but finite ratio (~1880), not `inf`, so no demonstrated defect there.

## One precise next task

Harden `calculate_ulcer_index` in `quant_trading/risk/metrics.py` against
all-negative equity curves the same way `calculate_max_drawdown` was just
hardened: return `0.0` when `running_max.max() <= 0` (running peak never
strictly positive), so an all-negative curve reports a neutral ulcer index
consistent with `_drawdown_series` (which returns all zeros). Add matplotlib-free
unit tests covering `[-5.0, -10.0, -3.0]` -> `0.0`, `[0.0, -5.0, -2.0]` ->
`0.0`, and the normal positive case still computing an RMS, then verify with
`python -m pytest tests/test_risk_metrics.py -q -p no:cacheprovider`,
`python -m pytest --doctest-modules quant_trading/risk/metrics.py -q`,
`python -m ruff check`, `python -m black --check`, and
`python -m mypy quant_trading/risk/metrics.py`. Do not touch
`minimize_max_drawdown` or risk-limit callers without re-checking their tests.
