## What changed (this session)
- Added a missing round-trip test for the `monte_carlo` serialization branch of
  `BacktestResult.from_dict` (`quant_trading/backtest/engine.py:654-658`), which had no
  dedicated test. New test: `TestBacktestResultSerialization.test_from_dict_reconstructs_nested_monte_carlo`
  in `tests/test_backtest_engine.py`.
- Corrected a stale/misleading docstring on the sibling
  `test_from_dict_reconstructs_nested_regime_analysis` test that falsely claimed the
  `monte_carlo` branch was "already covered".
- No source/library changes. Only test coverage + a docstring correction.

## What was actually verified (evidence)
- `python3 -m pytest -q` -> `3799 passed, 140 deselected` (full suite; was 3798 before,
  +1 new test). ~9 min runtime.
- Targeted: `pytest tests/test_backtest_engine.py -q` -> 119 passed.
- Coverage before this session: `quant_trading/backtest/engine.py` 97% with `656-658`
  (the monte_carlo branch) listed as missing. After the new test, that range is covered;
  remaining misses are TYPE_CHECKING imports (`82-84`) and defensive/unreachable branches
  (`954-956`, `1011`, `1018-1019`).
- `python3 -m ruff check quant_trading/ tests/` -> All checks passed.
- `python3 -m black --check quant_trading/ tests/test_backtest_engine.py` -> 39 files unchanged.
- `python3 -m mypy quant_trading/ --disallow-untyped-defs --no-incremental` -> Success (38 source files).

## What remains unresolved
Nothing for the core `quant_trading/` library. Fully verified working state.
The remaining uncovered `engine.py` lines are TYPE_CHECKING-only imports and defensive
guards that cannot be exercised meaningfully without contrived inputs.

## Failed or corrected approaches this session
- `pytest --cov=quant_trading.backtest.engine` (submodule-scoped `--cov`) triggers a numpy
  "cannot load module more than once per process" ImportError in this environment. Use the
  full `--cov=quant_trading` form instead (works fine). This is an environment quirk, not a
  code defect.

## One precise next task
No further work required for correctness. The suite is green (3799 passed), ruff/black/mypy
clean, working tree contains only the intended test addition. A future session need only
re-run `python3 -m pytest -q` and `mypy quant_trading/ --disallow-untyped-defs` to confirm
no regression. If deeper coverage is desired, the only remaining `engine.py` gaps are
defensive branches (benchmark alignment failure at 1018-1019, empty-position risk attribution
at 954-956) that are low value to exercise.