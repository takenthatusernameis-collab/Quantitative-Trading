## Status

**Calmar drawdown-understatement line of work is now closed.**

The previous handoff's assigned fix (seed the drawdown sample with the equity
bar preceding the first aligned return) was already present in
`quant_trading/risk/metrics.py:501-517` but had **no regression test**. This
session added that test, verified the fix, and removed the two pandas
`FutureWarning`s (deprecated default `sort` in `pd.concat`) that the fix and
`_align_series` were emitting.

## What changed

- `tests/test_risk_metrics.py`
  - New `TestCalculateCalmarRatio.test_calmar_drawdown_includes_bar_that_seeds_first_return`
    using the handoff repro:
    ```
    idx = pd.date_range("2020-01-01", periods=5)
    equity = pd.Series([100.0, 90.0, 80.0, 85.0, 82.0], index=idx)
    calculate_max_drawdown(equity)                 # -0.2
    calculate_max_drawdown(equity.iloc[1:])        # -0.1111...
    calculate_calmar_ratio(calculate_returns(equity), equity)
    ```
    Asserts both the true drawdown and that Calmar uses the `-0.2` denominator
    (old understated value was `-0.111`).
- `quant_trading/risk/metrics.py`
  - `_align_series`: `pd.concat(..., sort=False)` (was warning on DatetimeIndex).
  - `calculate_calmar_ratio`: `pd.concat([seed, aligned_equity], sort=False)`.
  - `black` reflow of the new concat call only.

Behaviour is unchanged: `dropna()` already removed non-overlapping rows, so
the aligned sample is the same; the flag just makes that explicit and silences
`Pandas4Warning`.

## What was verified (this session)

- `test_calmar_drawdown_includes_bar_that_seeds_first_return` passes on the
  current code and fails if the seed bar is dropped (checked against
  `calculate_max_drawdown(equity.iloc[1:]) == -0.1111`).
- `python -W error::FutureWarning -m pytest tests/test_risk_metrics.py
  tests/test_risk_attribution.py tests/test_risk_manager.py
  tests/test_backtest_metrics.py tests/test_backtest_engine.py
  tests/test_optimization.py tests/test_repository_integrity.py
  --doctest-modules quant_trading/risk/metrics.py -q -p no:randomly`
  -> **892 passed in 40.65s**.
- `python -m black --check`, `python -m ruff check`,
  `python -m mypy quant_trading/risk/metrics.py` -> clean.
- End-to-end path checked by reading code: `quant_trading/backtest/metrics.py:342`
  calls `calculate_calmar_ratio(returns, equity_curve)`, so backtest Calmar now
  also counts a first-bar peak.

## Unresolved / confirmed

- None known in this area. `calculate_max_drawdown` "no positive peak" and
  zero-drawdown semantics were left untouched.
- Prior handoff note still stands: the ~80s CLI test premise was wrong; do not
  reopen it.

## Gotchas (do not repeat)

- Do **not** modify `.github/workflows/*` from an agent session; the controller
  reverts/removes those files and excludes them from checkpoint commits.
- `pytest --cov` (`pytest-cov`) fails at collection; use
  `python -m coverage run` + `python -m coverage report`.
- Invoke `black`/`ruff`/`mypy` as `python -m <tool>` (not on PATH).
- Any function with an `Examples:` section needs at least one parseable `>>>`
  line or `test_repository_integrity.py::test_documented_examples_are_valid`
  fails.

## One precise next task

Broaden the "first bar is the global peak" invariant beyond the unit test: add
an engine-level regression in `tests/test_backtest_engine.py` that builds a
small synthetic equity curve whose first bar is the maximum and asserts that
`BacktestResult.metrics.max_drawdown` and `.calmar_ratio` reflect that peak
(i.e. drawdown computed over the full curve, not `curve.iloc[1:]`).

Constraints/evidence:

- Follow existing synthetic-run helpers in `tests/test_backtest_engine.py`;
  do not add new dependencies.
- Expected invariant: `metrics.max_drawdown == calculate_max_drawdown(full_curve)`
  and Calmar denominator equals `abs(max_drawdown)`, not the first-bar-dropped
  drawdown.
- Re-run `tests/test_backtest_metrics.py tests/test_backtest_engine.py
  tests/test_risk_metrics.py tests/test_repository_integrity.py` plus
  `python -m black --check` / `ruff` / `mypy` on touched files.
- Do not touch workflow files.
