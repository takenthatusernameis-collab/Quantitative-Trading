# Next Task

## Repository state

Checks: `python -m pytest -q`, `python -m ruff check .`, `python -m black --check .`, `python -m mypy quant_trading examples`.

Baseline: 1991 passed, 0 failed; ruff clean, black clean, mypy clean (56 files).

## Completed this session

- Implemented CLI validation for `--interval`: `_is_supported_interval` helper plus check in `parse_args` raises `ValueError` reported as `Error: invalid --interval: ...` with exit 1 for unknown intervals like `3x`. Existing `resolve_periods_per_year` fallback behavior/tests unchanged.

## Next task (one precise item)

Add a subprocess smoke test in `tests/test_examples_smoke.py` asserting `--interval 3x` exits 1 and prints `invalid --interval`. Verify pytest/ruff/black/mypy.
