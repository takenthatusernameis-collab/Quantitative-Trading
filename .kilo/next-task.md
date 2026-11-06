# Next Task

## Repository state (verified this session)

- scikit-optimize 0.10.2 IS installed (resolves the prior handoff's "unresolved"
  item: the Bayesian optimizer was untested end-to-end only because skopt was
  missing).
- `examples/cli.py` is unchanged from the prior handoff (the `ImportError`
  → one-line-message guard is already in place).
- `tests/test_cli.py`: added `test_bayesian_optimizer_runs_cleanly_with_skopt`
  (end-to-end real `--optimizer bayesian` path, guarded for skopt). It passes.
- `tests/test_optimization.py -k bayesian` → 14 passed.
- End-to-end CLI `--optimizer bayesian` → exit 0, no traceback.
- `ruff check` / `black --check` / `mypy` on changed files → clean.

## Pre-existing failures (not caused by this session; on clean baseline too)
- `tests/test_cli.py::TestCsvOutput::test_main_optimize_output_csv`
- `tests/test_cli.py::TestCsvOutput::test_main_walk_forward_output_csv`
Both pass `--n-iter 1` with the default `--bayesian-n-initial` of 10, tripping
the `bayesian_n_initial <= n_iter` validation at `examples/cli.py:1015`
("got 10 > 1"). Confirmed pre-existing via `git stash`.
- Full `pytest tests/test_cli.py`: 205 passed, 1 skipped, 2 failed (the two
  above).

## One precise next task

Fix the 2 pre-existing `TestCsvOutput` failures so the CLI suite is green:
- `tests/test_cli.py::TestCsvOutput::test_main_optimize_output_csv`
- `tests/test_cli.py::TestCsvOutput::test_main_walk_forward_output_csv`

Smallest fix: add `--bayesian-n-initial 1` to those two test invocations
(valid since `--n-iter 1` and `n_initial <= n_iter`). Do not modify the
`examples/cli.py` validation unless evidence shows the test invocations are
intentional.

After fixing, verify:
- `pytest tests/test_cli.py` → green
- `ruff check examples/cli.py tests/test_cli.py`
- `black --check examples/cli.py tests/test_cli.py`
- `mypy examples/cli.py tests/test_cli.py`

Then prepare the next handoff.
