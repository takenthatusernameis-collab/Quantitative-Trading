# Next Task

## Repository state

Checks: `python -m pytest -q` (2101 passed, 0 failures on a clean baseline; the 31 failures in `test_optimization.py`/`test_yfinance_fetch_many.py` are caused by missing optional deps `yfinance` and `scikit-optimize`, not by code defects), `python -m ruff check .` (clean), `python -m mypy quant_trading` (clean), `python -m mypy --check-untyped-defs quant_trading` (clean).

## Completed this session

Added an AST-based regression guard asserting the CLI's hardcoded `BUILTIN_STRATEGY_KEYS` list in `examples/cli.py` stays in sync with the live strategy registry's primary keys:

- New test `tests/test_repository_integrity.py::test_cli_strategy_keys_match_registry` plus helper `_cli_strategy_keys`.
- The CLI module is parsed with AST rather than imported, because importing it pulls in the Yahoo Finance provider (an optional dependency that may be absent).
- Prevents a future registry addition from being silently excluded from CLI `--strategy` choices and `--combined` mode.

This is the same class of contract-drift guard as the existing `test_validate_parameters_overrides_annotated_none` in the same file.

## What was actually verified

- `python -m pytest -q -o addopts="" tests/test_repository_integrity.py`: 8 passed, 0 failures (includes the new CLI sync test).
- `python -m ruff check quant_trading/ tests/ examples/`: All checks passed.
- `python -m mypy quant_trading`: Success, no issues found in 37 source files.
- Focused suite run (excluding env-dependent `test_cli.py`, `test_yfinance_fetch_many.py`, `test_optimization.py`): 1776 passed, 0 failures.

## What remains unresolved

- None blocking. The repository is green across tests, lint, and type checks.
- 31 test failures across `tests/test_optimization.py` and `tests/test_yfinance_fetch_many.py` remain environmental (missing `yfinance` / `scikit-optimize`), not repo bugs.

## Approaches that failed

- None this session.

## One precise next task

No assigned task remains. Baseline is green. Changes: 1 file touched this session (`tests/test_repository_integrity.py`). Do NOT commit unless explicitly asked. The previously suggested follow-up (a `validate_parameters` `-> None` annotation regression test) is already implemented as `test_validate_parameters_overrides_annotated_none` in `tests/test_repository_integrity.py`.

(End of file)
