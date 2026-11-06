# Next Task

## Repository state (verified this session)

All checks clean:
- `python -m ruff check .` → All checks passed.
- `python -m black --check .` → 141 files unchanged.
- `python -m mypy quant_trading/` → Success: no issues found in 37 source files.
- `python -m pytest tests/test_cli.py -q` → 207 passed (120s).
- `python -m pytest -q` (full suite) → 2880 passed, 15 skipped, 131 deselected.

## Completed this session

Fixed the one user-error path in `examples/cli.py` that still produced a raw
traceback instead of a one-line message: `ImportError` raised by an optional
dependency (scikit-optimize for `--optimizer bayesian`) was not caught by the
top-level `main()` handler, which only caught `OSError`/`ValueError`.

- `examples/cli.py` (`main`): added `ImportError` to the caught exception tuple.
- `tests/test_cli.py` (`TestUserErrorReporting`): added `test_import_error_is_reported`
  (fast, deterministic, patches `_run_cli`) and
  `test_bayesian_optimizer_without_skopt_is_reported` (skipped when skopt is
  installed, runs the real `--optimizer bayesian` path).

## One precise next task

No further action required unless the project's CI enforces `black --check` on
these files, in which case run `black examples/cli.py tests/test_cli.py` and
re-run `ruff`, `mypy`, and `pytest tests/test_cli.py` to confirm no regressions.