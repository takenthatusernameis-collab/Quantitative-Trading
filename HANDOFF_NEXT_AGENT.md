## Status

**Align-series duplicate-timestamp robustness is implemented and verified.**

The assigned task — make `_align_series` fall back to positional alignment when either
series has duplicate index labels (or alignment expands row count beyond
`min(len(returns), len(market))`) — is complete. The duplicate-first-bar engine run
now yields `calmar == calculate_returns(eq).mean()*252/abs(calculate_max_drawdown(eq))`.

## What changed

- `quant_trading/risk/metrics.py::_align_series`: duplicate-index / cartesian-expansion
  detection added; positional fallback via `reset_index(drop=True)`.
- `tests/test_backtest_engine.py`: `TestDrawdownIncludesFirstEquityBar` plus
  `test_duplicate_first_bar_does_not_double_count_return`.
- No production behaviour change for unique indexes.

## What was verified

- `tests/test_risk_metrics.py tests/test_risk_attribution.py tests/test_backtest_engine.py
  tests/test_backtest_metrics.py tests/test_repository_integrity.py` -> 411 passed.
- `black --check`, `ruff check`, `mypy` clean.

## Unresolved

- `calculate_max_drawdown` zero/negative-peak semantics untested at engine level.
- Other `_align_series`-based metrics (beta/alpha/Treynor/information ratio) on
  duplicate-first-bar runs not yet asserted positionally.

## One precise next task

Add regression tests in `tests/test_backtest_engine.py` asserting that on the
duplicate-first-bar run (`_run_script([("buy", 1.0)], {"TEST": _price_frame([100,90,80,70])})`),
`result.metrics.beta/alpha/treynor_ratio/information_ratio` equal the positional
`_align_series`-based values, not the cartesian-duplicated ones. Keep existing
first-bar peak handling. Re-run the five test files + black/ruff/mypy. Do not touch workflows.
