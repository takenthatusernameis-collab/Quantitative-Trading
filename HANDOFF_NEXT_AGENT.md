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

- `python -m py_compile quant_trading/optimization/base.py
  tests/test_optimization.py` → COMPILE OK
- `ast.parse` of both files → PARSE OK
- Confirmed `grid_search.py`, `random_search.py`, `bayesian.py` all call
  `super().__init__(...)`, so the validation covers GridSearch, RandomSearch,
  and BayesianOptimizer in one place.
- Existing tests that instantiate `BaseOptimizer` subclasses
  (test_optimization.py:1052-1149) use valid defaults
  (`initial_capital=100000.0`, default commission/slippage, default
  `periods_per_year=252`), so they are unaffected.

**Could not execute:** `pytest`, `ruff`, `mypy`, and the runtime dependency
`pandas` are not installed in this environment (`ModuleNotFoundError`), so the
test suite and lint/type checks could not be run. The validation logic was
sanity-checked by mirroring the WalkForwardOptimizer implementation whose
tests pass in the proper environment; the new tests use the same error-message
prefixes.

## Unresolved / not completed

- Test suite / ruff / mypy not run (environment missing `pandas`, `pytest`,
  `ruff`, `mypy`). Re-run the verification commands below in an environment
  with dev dependencies installed before treating this task as complete.

## Failed approaches (do not repeat unchanged)

- None for this task.

## Verification commands (re-run before starting)

```bash
python -m pytest tests/test_optimization.py -q -p no:cacheprovider
python -m ruff check quant_trading/optimization/base.py tests/test_optimization.py
python -m mypy quant_trading/optimization/base.py --ignore-missing-imports
```

## Git state

- Branch `main` up to date with `origin/main`.
- Working tree clean before this session; changes not yet committed.
  Do NOT commit unless explicitly asked.

## One precise next task

- Run the verification commands above (pytest on `tests/test_optimization.py`,
  ruff + mypy on `quant_trading/optimization/base.py`) in an environment with
  dev dependencies (`pandas`, `pytest`, `ruff`, `mypy`) installed, and fix any
  failures. This is the final gate for the BaseOptimizer validation task.
- Once green, a natural follow-up bounded task: add tests confirming
  `GridSearch`, `RandomSearch`, and `BayesianOptimizer` inherit the
  `BaseOptimizer.__init__` validation (they delegate via `super().__init__`,
  so no new library code is needed—just parametrized rejection tests for
  `initial_capital`/`commission`/`slippage`/`periods_per_year` on each
  subclass, mirroring `TestBaseOptimizerInitValidation`).
