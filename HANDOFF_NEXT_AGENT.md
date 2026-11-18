## Status

Reporting-extra verification completed on 2026-11-18.

## What changed

- Installed the optional `reporting` dependency (matplotlib 3.11.2) in the
  runner environment; no dependency declarations changed.
- Added 7 focused chart tests in `tests/test_backtest_report.py`:
  - Direct PNG/base64 validation for `_create_equity_curve_chart`,
    `_create_drawdown_chart`, `_create_monthly_returns_heatmap`,
    `_create_rolling_sharpe_chart`, `_create_rolling_volatility_chart`.
  - Short equity-curve (<60 bars) placeholder paths for the two rolling charts.

## What was actually verified

- `MPLBACKEND=Agg python -m pytest tests/test_backtest_report.py -q -p no:cacheprovider`
  -> 94 passed (previously 87 passed, 48 skipped without matplotlib).
- Full suite: `MPLBACKEND=Agg python -m pytest -q -p no:cacheprovider`
  -> 4073 passed, 32 skipped, 142 deselected.
- `python -m black --check tests/test_backtest_report.py` -> unchanged.
- `python -m ruff check tests/test_backtest_report.py` -> all checks passed.
- `python -m mypy quant_trading` -> no issues in 39 source files.
- `python -m pytest tests/test_repository_integrity.py -q` -> 51 passed.

## Remaining work / unresolved

- Coverage percentages cannot be measured in this environment: both
  `pytest --cov=...` and `python -m coverage run -m pytest` fail during
  collection with `ImportError: cannot load module more than once per process`
  while importing numpy under coverage (Python 3.14). Plain pytest works.
  Do not repeat the same coverage invocation unchanged.
- 27 tests remain skipped because `scikit-optimize` (`skopt`, optional
  `bayesian` extra) is not installed: 18 skip markers plus 9 import-time skips
  in `tests/test_optimization.py`, and 1 in
  `tests/test_optional_extras_readme_commands.py`.

## One precise next task

Install the optional `bayesian` extra (`python -m pip install scikit-optimize`)
and run `python -m pytest tests/test_optimization.py
tests/test_optional_extras_readme_commands.py -q -rs`; all 27 previously
skipped Bayesian tests should now execute. Investigate and fix any genuine
failures with the smallest production change, then re-run the full suite plus
`black --check` and `ruff check` before updating this handoff.
Constraints: do not weaken or delete skip guards; skopt-specific failures
should be fixed in `quant_trading/optimization/bayesian.py`, not by relaxing
test expectations.
