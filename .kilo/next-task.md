# Next Task

## Repository state (verified this session)
- Branch `main` up to date with `origin/main`; working tree clean except for the changes below.
- The `BayesianOptimizer` `noise` wiring described in the prior `.kilo/next-task.md` is **already committed** (present in `quant_trading/optimization/bayesian.py`; `HEAD = cc45c0f` is ahead of `cfac267`). That prior next-task (commit the noise wiring) is complete.

## Completed this session
**Removed yfinance gating from 6 optimization tests and closed the remaining real coverage gaps in `grid_search.py` / `random_search.py`.**
- `tests/test_optimization.py`: 6 tests previously behind `@skip_if_no_yfinance` now run offline using synthetic data (`Config(data=DataConfig(offline=True, ...))`) or a patched synthetic default data manager (`unittest.mock.patch` on `get_default_data_manager`).
- `quant_trading/optimization/grid_search.py` coverage → **100%** (was 98%).
- `quant_trading/optimization/random_search.py` coverage → **100%** (was 98%).

**Added direct unit tests for pure `examples.cli` helpers with zero prior coverage.**
- `tests/test_cli.py`: new `TestCliHelpers` class with 9 tests covering `_save_json_output`, `_print_regime_analysis`, `_print_monte_carlo_analysis`, `_print_trade_analysis` directly (no backtest runs needed).

## Verified (this session, evidence)
- `python -m pytest tests/test_optimization.py -q -p no:cacheprovider` → **134 passed, 11 skipped** (remaining skips are genuinely network-dependent).
- `python -m pytest tests/test_cli.py::TestCliHelpers -q -p no:cacheprovider` → **9 passed**.
- `python -m ruff check tests/test_cli.py` → **All checks passed!**
- `python -m mypy tests/test_cli.py --ignore-missing-imports` → no new errors from added tests.

## Unresolved / not completed
- Remaining coverage gaps are environment-only (`engine.py:82-84` TYPE_CHECKING, `report.py:29-30` matplotlib, `yfinance_provider.py:85`) or unreachable dead branches (`risk/metrics.py:511, 591`); not logic gaps.
- `examples/cli.py` is not in the coverage source (`source = ["quant_trading"]`), so its remaining uncovered lines (mostly `main()`, `run_optimization()`, `run_walk_forward()`, `run_combined()`) are not measured. The new `TestCliHelpers` tests cover the pure helpers directly.

## One precise next task
- None outstanding for bounded logic coverage. If a new task is assigned, re-run the verification set above first:
  `python -m pytest tests/test_optimization.py -q -p no:cacheprovider`,
  `python -m pytest tests/test_cli.py::TestCliHelpers -q -p no:cacheprovider`,
  `python -m ruff check .`,
  `python -m mypy quant_trading --ignore-missing-imports`.

## Git state
- Working tree has uncommitted changes: `tests/test_optimization.py` (+53/-16 lines), `tests/test_cli.py` (+TestCliHelpers, 9 new tests).
- Do NOT commit unless explicitly asked.

(End of file)
