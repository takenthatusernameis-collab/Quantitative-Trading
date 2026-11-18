## Status

Added `ulcer_index` assertions to combined-run JSON tests:
- `tests/test_cli.py::TestRunCombined::test_run_combined_with_output`: asserts every `comparison` entry contains `ulcer_index`.
- `tests/test_cli.py::TestRunCombined::test_main_offline_combined_with_output`: asserts every `comparison` entry contains `ulcer_index` (alongside `total_pnl`, `unrealized_pnl`, `total_return`).

## What was actually verified

- `python -m pytest tests/test_cli.py -k "combined"` mocked branches pass (TestRunCombinedJsonOutputBranches + test_run_combined_with_output).
- `tests/test_cli.py::TestRunCombined::test_main_offline_combined_with_output` (end-to-end offline combined run) passes.
- `python -m ruff check tests/test_cli.py`, `python -m black --check tests/test_cli.py`, `python -m mypy tests/test_cli.py` all clean.

## Remaining work / unresolved

None for this task. The single-run test already asserts `"ulcer_index" in data` at top level; combined mode reports `ulcer_index` per strategy inside `comparison[].ulcer_index` (examples/cli.py:2807), not at top level.

## One precise next task

Move to a new feature area (e.g. CLI validation/error-path coverage or another module), since the `ulcer_index` JSON coverage for both single-run and combined-run output is now complete.
