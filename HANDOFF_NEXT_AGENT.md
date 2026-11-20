## Status

Fixed repository integrity test failure: `_run_bootstrap_parallel` and `_run_parametric_parallel` in `quant_trading/monte_carlo/simulator.py` were missing from the `_EXAMPLES_ALLOWLIST`, consistent with their sibling `_run_bootstrap`/`_run_parametric` entries. All 51 repository integrity tests pass.

## What changed

- `tests/test_repository_integrity.py`: added two allowlist entries for the parallel helper methods.

## What was verified

- `python -m pytest -q tests/test_repository_integrity.py` → 51 passed
- `python -m black --check` and `python -m ruff check` → clean

## Unresolved

None.

## One precise next task

Continue with feature/defect work or performance optimization; baseline green.