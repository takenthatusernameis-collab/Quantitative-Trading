## What changed (this session)

Added library-level input validation to `BaseOptimizer.__init__`
(`quant_trading/optimization/base.py:848-876`), mirroring the RiskManager /
Monte Carlo / WalkForwardOptimizer validation pattern. The constructor
previously accepted `initial_capital`, `commission`, `slippage`, and
`periods_per_year` without validation, so invalid values silently propagated to
GridSearch, RandomSearch, and BayesianOptimizer (all of which call
`super().__init__(...)`). `__init__` now raises `ValueError` at construction
when:

- `initial_capital <= 0`
- `periods_per_year < 1`
- `commission` not in `[0, 1]`
- `slippage` not in `[0, 1]`

The existing `n_jobs` clamping (`max(n_jobs, 1)`, `-1` -> `os.cpu_count()`) is
left unchanged.

Error messages mirror the WalkForwardOptimizer prefixes exactly
(`invalid initial_capital`, `invalid periods_per_year`, `invalid commission`,
`invalid slippage`) so the existing `pytest.raises(..., match=...)` style
aligns.

**Tests added** (`tests/test_optimization.py`, class
`TestBaseOptimizerInitValidation`, appended after `TestWalkForwardResultCombinedRestore`):
- parametrized rejection tests for `initial_capital`, `periods_per_year`,
  `commission`, `slippage`
- boundary-acceptance tests for `periods_per_year` (`1`), `commission`
  (`0.0`/`1.0`), `slippage` (`0.0`/`1.0`)
- `test_accepts_all_boundary_valid_values`

Files changed: `quant_trading/optimization/base.py` (+28), `tests/test_optimization.py` (~100).

## Verified (this session, evidence)

Previous agent's BaseOptimizer validation task:
- `python -m pytest tests/test_optimization.py -q -p no:cacheprovider` → 186 passed, 37 skipped
- `python -m ruff check quant_trading/optimization/base.py tests/test_optimization.py` → All checks passed
- `python -m mypy quant_trading/optimization/base.py --ignore-missing-imports` → Success: no issues found
- Full suite `python -m pytest -q -p no:cacheprovider` → 3280 passed; 17 failures are pre-existing environment gaps (missing `matplotlib` / `scikit-optimize` optional deps), none related to the validation change.

This session — new bounded task: library-level input validation on `BacktestConfig`
(`quant_trading/config/settings.py:268-302`), mirroring the `BaseOptimizer.__init__`
validation (same error-message prefixes). `__post_init__` now raises `ValueError`
at construction (covers direct construction, `from_dict`, and `from_yaml`) when:

- `initial_capital <= 0`
- `periods_per_year < 1`
- `commission` not in `[0, 1]`
- `slippage` not in `[0, 1]`

Previously `BacktestConfig` only type-checked these fields, so invalid values
silently propagated to the backtest engine (and only surfaced later, if an
optimizer was used).

**Tests added** (`tests/test_config.py`, class `TestBacktestConfig`):
- parametrized rejection tests for `initial_capital`, `periods_per_year`,
  `commission`, `slippage`
- boundary-acceptance test (`initial_capital=1.0`, `commission=0.0`, `slippage=1.0`, `periods_per_year=1`)
- `test_from_dict_rejects_invalid_values`
- `test_from_yaml_rejects_invalid_values`

Files changed: `quant_trading/config/settings.py` (+34), `tests/test_config.py` (~50).

- `python -m py_compile quant_trading/config/settings.py tests/test_config.py` → COMPILE OK
- `python -m pytest tests/test_config.py -q -p no:cacheprovider` → 60 passed
- `python -m ruff check quant_trading/config/settings.py tests/test_config.py` → All checks passed
- `python -m mypy quant_trading/config/settings.py --ignore-missing-imports` → Success: no issues found

## Unresolved / not completed

- None. Both assigned tasks are complete and verified.

## Failed approaches (do not repeat unchanged)

- None.

## Verification commands (re-run before starting)

```bash
python -m pytest tests/test_config.py tests/test_optimization.py -q -p no:cacheprovider
python -m ruff check quant_trading/config/settings.py quant_trading/optimization/base.py tests/test_config.py tests/test_optimization.py
python -m mypy quant_trading/config/settings.py quant_trading/optimization/base.py --ignore-missing-imports
```

## Git state

- Branch `main` up to date with `origin/main`.
- Working tree clean before this session; changes not yet committed.
  Do NOT commit unless explicitly asked.

## One precise next task

A natural follow-up bounded task: extend the same input validation to the
other config dataclasses (`RiskConfig` limits such as `max_position_size`,
`max_drawdown`, `max_leverage`, `stop_loss_pct`, `take_profit_pct`,
`trailing_stop_pct`; `PortfolioConfig.max_positions`/`min_position_size`),
mirroring the existing risk-limit validation in `quant_trading/risk/limits.py`
and `quant_trading/risk/manager.py`. Add parametrized rejection + boundary
tests to `tests/test_config.py`, then run the verification commands above.
Scope constraint: keep changes minimal (`__post_init__` only, same
error-message style) and do not alter `Config.update()` (bulk setter) unless a
separate issue motivates it.
