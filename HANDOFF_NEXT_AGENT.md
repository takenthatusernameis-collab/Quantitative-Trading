## Status

**Duplicate-first-bar market-relative metrics regression test added and verified.**

The assigned task — add regression tests in `tests/test_backtest_engine.py` asserting that on the duplicate-first-bar run, `result.metrics.beta/alpha/treynor_ratio/information_ratio` equal the `_align_series`-based values — is complete.

## What changed

- `tests/test_backtest_engine.py`: Added `TestDrawdownIncludesFirstEquityBar.test_duplicate_first_bar_market_relative_metrics_use_align_series` (lines 2714–2760).
  - Runs a duplicate-first-bar backtest via `_run_script([("buy", 1.0)], data, benchmark="BENCH")` with both TEST and BENCH price frames.
  - Replicates the engine's `_benchmark_returns` alignment logic (unique equity dates, forward-fill).
  - Calls `_align_series` directly on the portfolio returns and aligned benchmark returns.
  - Asserts `result.metrics.beta`, `alpha`, `treynor_ratio`, `information_ratio` match the metrics computed from the `_align_series` frame.
  - No production behaviour change; existing first-bar peak handling preserved.

## What was verified

- `tests/test_risk_metrics.py tests/test_risk_attribution.py tests/test_backtest_engine.py tests/test_backtest_metrics.py tests/test_repository_integrity.py` → 412 passed (411 original + 1 new).
- `black --check`, `ruff check`, `mypy` clean.

## Unresolved

- `calculate_max_drawdown` zero/negative-peak semantics untested at engine level (pre-existing).
- Other `_align_series`-based metrics on duplicate-first-bar runs with *both* series carrying duplicate indices not yet asserted positionally (the current engine path avoids this by dropping benchmark duplicates in `_benchmark_returns`).

## One precise next task

If desired, add a unit test in `tests/test_risk_metrics.py` directly exercising `_align_series` with duplicate indices in *both* input series to verify the positional fallback triggers and produces the expected paired frame. This would be a pure unit test for the alignment logic, independent of the engine. Re-run the five test files + black/ruff/mypy. Do not touch workflows.