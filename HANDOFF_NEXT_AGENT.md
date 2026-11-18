## Status

Fixed the `ulcer_index` mock attribute gap in `tests/test_cli.py` so the CLI's
`Ulcer Index:` print line (examples/cli.py:2583) and the combined-mode JSON
output (examples/cli.py:2807) no longer crash the mock-backed tests.

Added `mock_metrics.ulcer_index = 0.0` to every MagicMock metrics object in
`tests/test_cli.py` that previously omitted it (13 occurrences).

## What was actually verified

- `python -m pytest tests/test_cli.py -q` → 346 passed, 9 skipped, 3 deselected.
- `python -m ruff check tests/test_cli.py`, `python -m black --check tests/test_cli.py`,
  `python -m mypy tests/test_cli.py` all clean.

## Remaining work / unresolved

- `tests/test_repository_integrity.py::test_documented_examples_are_valid` fails,
  but it was already failing before this change (pre-existing). It flags many
  functions in `quant_trading/backtest/report.py` and `examples/cli.py` whose
  docstrings have an empty `Examples/Example` section. Not related to this fix.

## One precise next task

Move to a new feature area (e.g. CLI validation/error-path coverage or another
module), since the `ulcer_index` JSON coverage for both single-run and
combined-run output is complete and the mock gap is closed.