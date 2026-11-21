## Status

Completed audit and fix of genuine numerical defects in `quant_trading/optimization/*.py`. Found and fixed 4 related issues:

1. **BayesianOptimizer crashed when parameter bounds collapsed to a single point** (min_val == max_val) — scikit-optimize requires lower < upper for Integer/Real dimensions
2. **Objective functions returned NaN when metrics were NaN** — the `or 0.0` pattern only handled None, not NaN
3. **Optimizers stored NaN scores in all_results** — `_evaluate_params` didn't guard against non-finite scores
4. **BayesianOptimizer crashed on NaN/inf scores** — `gp_minimize` cannot handle infinite values

All fixes are minimal, reversible, and preserve the existing green baseline.

## What Changed

### `quant_trading/optimization/base.py`
- Added `_finite_or_zero(value)` helper that returns 0.0 for None, NaN, or inf
- Updated all 7 objective functions to use `_finite_or_zero`:
  - `maximize_sharpe`, `maximize_calmar`, `maximize_sortino`, `maximize_profit_factor`, `maximize_win_rate` — now guard against NaN
  - `maximize_total_return` — now guards against NaN (previously had no fallback)
  - `minimize_max_drawdown` — now guards against NaN (previously had no fallback)
- Modified `_evaluate_params` to check `math.isfinite(score)` and convert non-finite scores to `-inf` with verbose logging

### `quant_trading/optimization/bayesian.py`
- Added `import math`
- Modified `_create_skopt_space` to detect collapsed bounds (min_val == max_val) and convert them to `Categorical` with a single value instead of `Integer`/`Real` which require lower < upper
- Modified `objective_func` wrapper to return a large finite penalty (1e10) instead of `inf` when score is non-finite, preventing `gp_minimize` "Input y contains infinity" errors

### `tests/test_optimization.py`
Added 12 regression tests:
- `TestObjectiveFunctionNaNHandling` (7 tests) — all objective functions return 0.0 for NaN metrics
- `TestOptimizerNaNScoreHandling` (2 tests) — `_evaluate_params` converts NaN to -inf; GridSearch doesn't select NaN as best
- `TestBayesianOptimizerCollapsedBounds` (3 tests) — BayesianOptimizer works with collapsed integer/float/all bounds

## What Was Verified

- Full optimization test suite: **241 passed** (229 original + 12 new)
- `black --check`, `ruff check`, `mypy` — all clean on optimization module and tests
- Example script `examples/run_optimization.py` runs successfully
- Smoke test `tests/test_run_optimization_smoke.py` passes
- Strategy registry coverage tests pass (including new `test_every_strategy_emits_only_finite_signal_values`)

## Unresolved / Notes

- The fix for collapsed bounds uses `Categorical` with a single value. This means the parameter is technically "optimizable" but only has one possible value. This is the correct behavior — if the user specifies min_val == max_val, they intend that parameter to be fixed.
- The penalty value `1e10` for failed Bayesian evaluations is arbitrary but sufficiently large to be worse than any realistic score.
- No changes were made to `grid_search.py`, `random_search.py`, `walk_forward.py`, or `sensitivity.py` — they already handled edge cases correctly or inherited the fixed behavior from `BaseOptimizer`.

## One Precise Next Task

Audit `quant_trading/risk/metrics.py` and `quant_trading/backtest/metrics.py` for similar numerical defects:
- Check for divisions that could produce NaN/inf without guards
- Verify all public metric functions return finite values for degenerate inputs (empty series, constant series, single observation, all zeros, etc.)
- Add focused property-based tests using `hypothesis` or manual fuzz inputs if not already covered
- If no defects reproduce, add one non-redundant invariant test asserting finiteness of all metric outputs across degenerate inputs and say so plainly rather than inventing a fix

(End of file)