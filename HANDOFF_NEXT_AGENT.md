## Status

Fixed the `test_documented_examples_are_valid` failure in `tests/test_repository_integrity.py` by updating the `_EXAMPLES_ALLOWLIST` with correct line numbers.

The test was failing because the allowlist contained outdated line numbers for grandfathered functions that have empty `Examples:`/`Example:` sections in their docstrings. Code changes had shifted line numbers, causing the allowlist entries to not match the current function locations.

## What was actually verified

- `python -m pytest tests/test_repository_integrity.py::test_documented_examples_are_valid -v` → PASSED
- `python -m ruff check tests/test_repository_integrity.py` → All checks passed
- `python -m black --check tests/test_repository_integrity.py` → Clean
- `python -m mypy tests/test_repository_integrity.py` → Success
- `python -m pytest tests/test_repository_integrity.py -q` → 50 passed
- `python -m pytest tests/test_backtest_report.py -q` → 31 passed, 48 skipped
- `python -m pytest tests/test_readme_cli.py -q` → 3 passed
- `python -m pytest tests/test_readme_cli_commands.py -q` → 116 passed, 5 skipped, 3 deselected

## Changes made

Updated `_EXAMPLES_ALLOWLIST` in `tests/test_repository_integrity.py` (lines 1783-1920) with current line numbers for 25 functions in `examples/cli.py` and `quant_trading/backtest/report.py` that are grandfathered with empty Examples sections.

Line number adjustments:
- `examples/cli.py`: +4 lines for most functions, +6 for `run_combined`
- `quant_trading/backtest/report.py`: +1 line for early functions, +2-3 for later comparison functions

## Remaining work / unresolved

- The grandfathered functions still have empty Examples sections. Per the allowlist comment: "Remove an entry when the section is fixed; never add entries for new code". Future work could add proper doctest examples to these functions and remove them from the allowlist.
- `tests/test_cli.py` takes ~2+ minutes to run (346 tests) but was verified passing in the previous session.

## One precise next task

Move to a new feature area (e.g., CLI validation/error-path coverage or another module), since the repository integrity test for documented examples is now passing and the mock gap for `ulcer_index` in CLI tests was closed in the previous session.