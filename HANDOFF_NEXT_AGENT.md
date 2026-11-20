## Status

Extended README CLI command coverage: `tests/test_readme_cli_commands.py` now extracts and executes the CLI commands documented in the four README sections beyond `## Command Line Interface` (`## Market Regime Analysis`, `## Monte Carlo Simulation`, `## Trade Analysis`, `## Annualization Periods`), deduplicating commands that appear in multiple sections. This covers 7 previously unexecuted documented CLI commands (`--regime`, `--monte-carlo`, `--trade-analysis`, `--interval`) that had zero end-to-end test coverage.

## What changed

- `tests/test_readme_cli_commands.py`: refactored `_cli_section` into a general `_readme_section(title)` and added `_commands_from_section`; `_readme_commands` now iterates over the CLI section plus the four later sections, skipping already-seen argument tuples so duplicate invocations (e.g. `--offline --regime --symbols AAPL --days 120` and `--offline --interval 1wk --periods-per-year 52`, each documented twice) produce unique parametrize ids.

## What was verified

- `python -m pytest -q tests/test_readme_cli_commands.py` → 125 passed, 3 deselected (pre-existing slow `--combined` commands); the 7 newly covered commands all run end-to-end with exit code 0.
- `python -m pytest -q tests/test_cli.py tests/test_readme.py` → 373 passed.
- `python -m pytest -q tests/test_repository_integrity.py` → 51 passed.
- `python -m black --check`, `python -m ruff check`, `python -m mypy` on the changed file → clean.

## Unresolved

None.

## One precise next task

Continue with feature/defect work or performance optimization; baseline green. The repo is fully green (4249 unit tests + integrity + README CLI commands, black/ruff/mypy clean), so pick a bounded defect or a new regression guard for a genuine coverage gap.
