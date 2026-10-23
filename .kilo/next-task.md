# Next Task

## Repository state

Checks: `python -m pytest -q` (all pass), `python -m ruff check .` (clean), `python -m black --check .` (clean), `python -m mypy quant_trading` (clean), `python -m mypy --explicit-package-bases examples` (clean).

## Completed this session

Added a Volume Rate of Change (VROC) strategy — the 22nd registered strategy:

- `quant_trading/strategies/examples.py`: new `VolumeRateOfChangeStrategy(period=14, name="Volume_Rate_Of_Change")`. VROC = (volume - volume[n]) / volume[n] * 100, where n = `period`. Emits a buy when VROC crosses above zero (volume expansion) and a sell when it crosses below zero (volume contraction), with NaN/zero guards and strength = min(1, |VROC|/(|VROC|+100)). Requires `"close"` and `"volume"` columns.
- `quant_trading/strategies/__init__.py`: imported `VolumeRateOfChangeStrategy`, registered `register_strategy("vroc", VolumeRateOfChangeStrategy, aliases=["volume_rate_of_change"])`, added to `__all__` (alphabetical to keep ruff I001 clean).
- `tests/test_strategies_examples.py`: added `create_vroc_data` helper and `TestVolumeRateOfChangeStrategy` (7 tests: init, validation, insufficient data, cross-above-zero buy, cross-below-zero sell, flat volume no signals, multiple symbols, NaN volume skip). Exact VROC values verified against the implementation (buy cross: 100.0; sell cross: -50.0).
- `examples/cli.py`: added `"vroc"` to `BUILTIN_STRATEGY_KEYS`.
- `README.md`: "23 registered strategies" -> "24", added Volume Rate of Change to the built-in list, added `- \`vroc\` (alias: \`volume_rate_of_change\`) → \`VolumeRateOfChangeStrategy\`` to the Strategy Registry table.
- `tests/test_cli.py::TestRunCombined::test_run_combined_all_strategies`: added `("Volume_Rate_Of_Change", 15.0)` to mocked combined-mode results and assertion.

## What was actually verified

- Full suite: 2072 passed (previously 2064), 0 failed (includes the 8 new VROC tests).
- `python -m ruff check quant_trading examples tests`: clean.
- `python -m black --check` on all files: clean.
- `python -m mypy quant_trading`: clean.
- `tests/test_readme.py` README-vs-registry consistency passes (registry entry added to README).
- `tests/test_cli.py::TestRunCombined` (4 tests) pass with the new strategy entry.
- `python examples/cli.py --offline --strategy vroc --symbols AAPL --days 60` runs end to end.
- `python examples/cli.py --list-strategies` lists `vroc: VolumeRateOfChangeStrategy (period=14)`.

## What remains unresolved

None.

## One precise next task

Add another classic volume/momentum/oscillator strategy following the same pattern: class in `quant_trading/strategies/examples.py`, registration in `quant_trading/strategies/__init__.py` (alphabetical placement to keep ruff I001 clean), tests in `tests/test_strategies_examples.py`, README listing/registry entry (bump count to 23), and `BUILTIN_STRATEGY_KEYS` in `examples/cli.py`. Remember to also update `tests/test_cli.py::TestRunCombined` when the registry grows. If no strategy is added, no further work is needed — the baseline is green.

(End of file - total 33 lines)