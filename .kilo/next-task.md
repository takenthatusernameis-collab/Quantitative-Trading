# Next Task

## Repository state

Checks: `python -m pytest -q`, `python -m ruff check .`, `python -m black --check .`, `python -m mypy quant_trading examples`. Use venv at `/home/runner/work/_temp/kilo-tmp/venv`.

Baseline: 1991 passed, 0 failed; ruff clean, black clean, mypy clean (56 files).

## Completed this session

- `--mc-simulations` below 1 now raises `ValueError` in `parse_args` (`examples/cli.py`), printed as `Error: invalid --mc-simulations: ...` with exit 1.
- `parse_range` now also rejects minimum > maximum.
- Tests pass (1991).

## Next task (one precise item)

**Decide and implement validation for `--interval 3x` (unknown interval accepted silently).**

`resolve_periods_per_year` (examples/cli.py:94) falls back to 252 for unknown intervals, documented/tested behaviour. With a live provider the interval fails later. The two providers use different interval vocabularies (Yahoo Finance vs Alpha Vantage), so decide where validation belongs (provider vs CLI) and implement the smallest change. Keep existing fallback test passing or update it deliberately with rationale.

Scope: examples/cli.py and/or providers. Add subprocess test in tests/test_examples_smoke.py. Verify pytest/ruff/black/mypy.
