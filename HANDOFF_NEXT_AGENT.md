## Status

Completed one bounded task: closed the last remaining branch-coverage gap in the
Monte Carlo parallel runners.

## What changed

- `tests/test_monte_carlo.py`: added
  `TestMonteCarloParallelExecution.test_monte_carlo_parallel_more_workers_than_simulations`
  (parametrized over `bootstrap` and `parametric`). It runs with
  `n_simulations=2, n_jobs=4`, which forces workers beyond the simulation count
  to be assigned zero simulations and exercises the `if n_sim > 0:` false
  (skip) branch in `_run_bootstrap_parallel` and `_run_parametric_parallel`
  (`quant_trading/monte_carlo/simulator.py` lines ~780 and ~830).

No production code was modified.

## What was verified

- Full suite baseline before change: `python -m pytest -q` → 4253 passed, 151 deselected.
- New focused tests: `pytest tests/test_monte_carlo.py -k more_workers_than_simulations` → 2 passed.
- Whole file: `pytest tests/test_monte_carlo.py` → 57 passed.
- Branch coverage proof (via `coverage run --branch`):
  - Baseline/deselecting the new test: simulator.py shows partial branches `780->778, 830->828` (BrPart=2).
  - With the new test: simulator.py BrPart=0. These were the only two partial branches in the entire `quant_trading` package.
- `black --check tests/test_monte_carlo.py` → unchanged.
- `ruff check tests/test_monte_carlo.py` → all checks passed.
- `mypy quant_trading` → success, no issues in 39 files.

## Unresolved / notes

- Tooling quirk (not caused by this change): `pytest --cov=quant_trading.monte_carlo.simulator`
  (a submodule path) triggers a numpy 2.5.5 / Python 3.14 `cannot load module more
  than once per process` ImportError. Use `coverage run --branch -m pytest ...` +
  `coverage report -m` (or `--cov=quant_trading` on the package) instead.
- Parallel Monte Carlo tests require a real importable `__main__` (forkserver);
  ad-hoc verification via `python - <<stdin` fails — write a temp `.py` file instead.

## Approaches already failed

- Attempted ad-hoc verification through a heredoc (`python - <<PY`) → forkserver
  `FileNotFoundError: <stdin>` / `ConnectionResetError`. Switched to a temp script file.

## One precise next task

The package is at ~100% line/branch coverage with a fully green suite; there is no
remaining coverage gap. Next agent: pick a genuine behavioral defect via targeted
review (e.g. numerical edge cases in `risk/metrics.py` or `backtest/metrics.py`
zero-division handling), or add a focused property/invariant test. Verify with the
focused test plus `black`/`ruff`/`mypy`, and do not weaken existing controls.