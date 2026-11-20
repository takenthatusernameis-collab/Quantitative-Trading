## Status

**Calmar/drawdown "first bar is the peak" invariant is now covered end-to-end.**

The previous handoff's assigned task — an engine-level regression proving
`BacktestResult.metrics.max_drawdown` and `.calmar_ratio` use the full equity
curve rather than `curve.iloc[1:]` — is implemented and passing.

## What changed

- `tests/test_backtest_engine.py`
  - New `TestDrawdownIncludesFirstEquityBar`:
    - `_run_declining` buys on the first data bar via a full-size `RiskConfig`
      and holds while prices fall `[100, 90, 80, 70]`. It starts the run one
      day before the data so the initial-capital equity bar has a unique
      timestamp instead of duplicating the first data bar.
    - `test_first_bar_peak_counts_in_max_drawdown_and_calmar` asserts:
      `equity.iloc[0] == equity.max()`,
      `calculate_max_drawdown(equity) < calculate_max_drawdown(equity.iloc[1:])`,
      `metrics.max_drawdown == calculate_max_drawdown(equity)`,
      `result.max_drawdown == calculate_max_drawdown(equity)`, and
      `metrics.calmar_ratio == annual_return / abs(full_drawdown)`.
      It also asserts the ratio is **not** the first-bar-dropped value.
  - Imported `calculate_max_drawdown` / `calculate_returns` from
    `quant_trading.risk.metrics` (ruff-sorted).
- No production code changed.

## What was verified (this session)

- New test passes: `pytest tests/test_backtest_engine.py::TestDrawdownIncludesFirstEquityBar`.
- Negative control: temporarily deleting the seed block in
  `quant_trading/risk/metrics.py` (`calculate_calmar_ratio`) makes the new
  test fail with `-70.8978 == -70.6510 ± 7.1e-05` (dropped-bar denominator).
  `metrics.py` was restored with `git checkout --`, working tree only has the
  test change.
- `python -W error::FutureWarning -m pytest tests/test_backtest_metrics.py
  tests/test_backtest_engine.py tests/test_risk_metrics.py
  tests/test_repository_integrity.py -q -p no:randomly` -> **363 passed**.
- `python -m black --check`, `python -m ruff check`,
  `python -m mypy tests/test_backtest_engine.py` -> clean.

## Unresolved / confirmed

- **Duplicate-timestamp equity curves are mishandled by Calmar.**
  When a backtest starts on the first data date (the default `_run_script`
  path), `equity_curve` has two rows at that timestamp (initial capital, then
  post-trade mark). `_align_series` (`pd.concat(axis=1)`) then produces a
  cartesian 2x1 match for that label, so the aligned frame has 5 rows from 4
  returns, and the Calmar numerator is computed over a duplicated return.
  Repro: `_run_script([("buy", 1.0)], {"TEST": _price_frame([100.0, 90.0, 80.0, 70.0])})`
  gives `calmar = -51.1684` while `calculate_returns(eq).mean()*252/abs(calculate_max_drawdown(eq))`
  is `-63.6471`. This affects every metric routed through `_align_series`
  (beta/alpha/Treynor/information ratio too).
- `calculate_max_drawdown` zero/negative-peak semantics were left untouched.

## Gotchas (do not repeat)

- Do **not** modify `.github/workflows/*` from an agent session; the controller
  reverts/removes those files and excludes them from checkpoint commits.
- `pytest --cov` (`pytest-cov`) fails at collection; use
  `python -m coverage run` + `python -m coverage report`.
- Invoke `black`/`ruff`/`mypy` as `python -m <tool>` (not on PATH).
- Any function with an `Examples:` section needs at least one parseable `>>>`
  line or `test_repository_integrity.py::test_documented_examples_are_valid`
  fails.
- New imports must be ruff/I001-sorted before `test_repository_integrity.py`
  passes.

## One precise next task

Make return-to-equity alignment robust to duplicate timestamps. In
`quant_trading/risk/metrics.py::_align_series`, detect when either series has
duplicate index labels (or when index alignment expands the row count beyond
`min(len(returns), len(equity))`) and fall back to positional alignment —
because the engine derives returns positionally from the curve, so label
matching over duplicated bars is wrong. Add a regression in
`tests/test_risk_metrics.py` (or `test_backtest_engine.py` for the engine path)
asserting the `_run_script` duplicate-first-bar run above yields
`calculate_calmar_ratio(...) == pytest.approx(calculate_returns(eq).mean()*252 / abs(calculate_max_drawdown(eq)))`.

Constraints/evidence:

- Keep the existing behaviour for unique indexes (index alignment preferred,
  positional fallback only when overlap < 2).
- Preserve the seeded-drawdown logic added previously; do not remove the
  first-bar peak handling.
- Verify for both `_align_series`-based metrics and the engine run; re-run
  `tests/test_risk_metrics.py tests/test_risk_attribution.py
  tests/test_backtest_engine.py tests/test_backtest_metrics.py
  tests/test_repository_integrity.py` plus black/ruff/mypy.
- Do not touch workflow files.
