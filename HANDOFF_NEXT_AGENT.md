## Status

Completed the previously queued task: drawdown chart rendering now shares the
metric-level robustness fix (`_finite_series` applied to all four rolling
Sharpe/volatility chart paths), plus matplotlib-free unit tests and an
allowlist entry. Separately completed in prior sessions: hardened
`calculate_max_drawdown` against all-negative equity curves so it reports a
neutral 0.0 drawdown instead of a sign-flipped ratio, consistent with
`_drawdown_series`.

Completed in this session: hardened `calculate_ulcer_index` against
all-negative (and zero-and-negative) equity curves so it reports neutral 0.0
when the running peak is never strictly positive, consistent with
`_drawdown_series`.

## What changed

- `quant_trading/risk/metrics.py`
  - `calculate_ulcer_index`: generalized the degenerate-peak guard from
    `running_max.eq(0).all()` to `running_max.max() <= 0`, so an all-negative
    (or all-zero/zero-and-negative) equity curve whose running peak is never
    strictly positive returns `0.0` instead of a non-zero RMS of undefined
    drawdown ratios. Updated the `Returns` docstring and doctest example
    (`calculate_ulcer_index(pd.Series([-5.0, -10.0, -3.0]))` -> `0.0`).
- `tests/test_risk_metrics.py`
  - Added `test_all_negative_equity_reports_neutral_ulcer_index`
    (`[-5.0, -10.0, -3.0]` -> `0.0`) and
    `test_zero_and_negative_equity_reports_neutral_ulcer_index`
    (`[0.0, -5.0, -2.0]` -> `0.0`) to `TestCalculateUlcerIndex`.
- `quant_trading/backtest/report.py`, `tests/test_backtest_report.py`,
  `tests/test_repository_integrity.py`: unchanged from prior session
  (`_finite_series` already present, applied to all four rolling chart paths,
  tested, and allowlisted at report.py:216).

## What was actually verified

- `python -m pytest tests/test_risk_metrics.py -q -p no:cacheprovider`
  -> 133 passed (includes the two new ulcer index tests).
- `python -m pytest --doctest-modules quant_trading/risk/metrics.py -q`
  -> 21 passed (new doctest example `calculate_ulcer_index([-5.0, -10.0, -3.0])`
  returns `0.0`).
- `python -m pytest tests/test_backtest_report.py tests/test_repository_integrity.py -q -p no:cacheprovider`
  -> 89 passed, 48 skipped (matplotlib absent).
- `ruff check`, `black --check quant_trading/risk/metrics.py tests/test_risk_metrics.py`,
  and `mypy quant_trading/risk/metrics.py` clean.

## Remaining work / unresolved

- Chart functions remain untested because matplotlib is not installed
  (optional `reporting` extra; chart tests skip). Only pure helpers are
  covered.
- Allowlist line numbers in `tests/test_repository_integrity.py` remain
  brittle for `report.py`, `risk/metrics.py`, and `examples/cli.py`: inserting
  lines above an allowlisted def changes its `lineno`, so the allowlist entry
  `(rel, name, lineno)` no longer matches and docstring checks fail. E.g.
  `_EXAMPLES_ALLOWLIST` (test_repository_integrity.py:1783) and the metrics
  allowlist (around line 2219) are keyed by hardcoded line numbers.

## Approaches already tried and why (avoid repeating)

- Reviewed VaR/component-VaR semantics: tests deliberately define the
  component sum as CVaR (tail mean), not quantile VaR; do not "fix" this.
- Optional-dependency coverage gaps (`report.py` charts,
  `optimization/bayesian.py`, `optimization/sensitivity.py`) are due to missing
  matplotlib/skopt, not missing logic.
- Rolling Sharpe chart non-finite concerns: the linear test equity yields a
  huge but finite ratio (~1880), not `inf`, so no demonstrated defect there.

## One precise next task

Make the hardcoded allowlist line numbers in `tests/test_repository_integrity.py`
robust so inserting lines above an allowlisted def does not break the suite.
The allowlists are keyed by `(rel, name, lineno)` (e.g. `_EXAMPLES_ALLOWLIST`
at test_repository_integrity.py:1783 and the metrics allowlist around line 2219),
and are consulted at lines ~3700 and ~3710. Replace the line-number component
with a name-only match resolved through the AST (look up the def's current
`lineno` by name), or add a self-test that recomputes each entry's line number
from the AST and fails with a clear "stale allowlist entry, update line number"
message when it drifts. Verify with
`python -m pytest tests/test_repository_integrity.py -q -p no:cacheprovider`
plus `ruff check` and `black --check`. Do not renumber entries by hand without
the AST check in place, since that is exactly what goes stale again.

(End of file)
