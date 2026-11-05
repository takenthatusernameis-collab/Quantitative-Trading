# Handoff to next agent

## What changed
- Added two new CLI flags to `examples/cli.py`: `--synthetic-days` (int) and `--synthetic-seed` (int), placed after `--offline`.
- These flags were previously referenced in `create_config()` (cli.py:1298-1302) via `getattr` but never defined in the parser, so the config-wiring code paths were dead. Now they are real parser args and reach `DataConfig.synthetic_days`/`DataConfig.synthetic_seed`.
- Documented both flags in README.md (backtick-quoted prose + an end-to-end code-block example under "Data Providers").

## Verified (evidence)
- `python examples/cli.py --offline --synthetic-days 120 --synthetic-seed 7 --symbols AAPL --days 30` → exit 0, no traceback (the exact README code-block command).
- Parser wiring check: with flags → `data.synthetic_days=120, data.synthetic_seed=7`; without → defaults `365`/`42` applied.
- `python -m black --check .` → 141 files unchanged.
- `python -m ruff check .` → All checks passed.
- `python -m mypy quant_trading/` → Success: no issues in 37 source files.
- `pytest tests/test_readme_cli.py tests/test_readme.py tests/test_repository_integrity.py -q` → 29 passed.
- `pytest tests/test_readme_cli_commands.py -q -k "synthetic-days"` → 1 passed (end-to-end README command run).
- `pytest --doctest-modules examples/cli.py` → 1 passed.

## Unresolved
- None.

## Approaches that failed / constraints
- None. The prior `.kilo/next-task.md` suggestion to document undocumented CLI flags was exhausted by inspection: the only parser flag not in the README is `--help` (standard argparse, not worth documenting). The real gap found was the missing `--synthetic-days`/`--synthetic-seed` parser flags.

## Next task (precise)
- Re-run `pytest -q`, `python -m ruff check .`, `python -m black --check .`, and `python -m mypy quant_trading/` to confirm the tree is still green, then select a new bounded task (the tree is currently green with 100% coverage and no documented gaps).
