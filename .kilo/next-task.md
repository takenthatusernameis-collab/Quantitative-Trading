# Next Task

## Repository state

Checks: `python -m pytest -q`, `python -m ruff check .`, `python -m black --check .`, `python -m mypy quant_trading examples`.

Baseline: 1992 passed, 0 failed; ruff clean, black clean, mypy clean (56 files).

## Completed this session

- Added `test_cli_reports_an_unsupported_interval_without_a_traceback` to `tests/test_examples_smoke.py`: runs `cli.py --interval 3x --offline --symbols AAPL --days 30` and asserts exit 1, `invalid --interval` in output, no traceback.
- Fixed the prior session's `_is_supported_interval` in `examples/cli.py` (lines 186-201) so it stores each `re.fullmatch` result once and reads `.group(1)` from the non-None match. This removes the two `union-attr` mypy errors and drops the redundant double-`fullmatch` calls. Behavior is unchanged: `3x` still rejects, valid intervals still accept.

## Next task (one precise item)

None outstanding. The `--interval` validation feature and its subprocess smoke test are complete and verified.