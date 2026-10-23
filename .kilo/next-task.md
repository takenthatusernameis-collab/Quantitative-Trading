# Next Task

## Repository state

Checks: `python -m pytest -q` (all pass), `python -m ruff check .` (clean), `python -m black --check .` (clean), `python -m mypy quant_trading` (clean), `python -m mypy --explicit-package-bases examples` (clean).

## Completed this session

Added a Volume Oscillator (VOL) strategy — the 23rd registered strategy:

- `quant_trading/strategies/examples.py`: new `VolumeOscillatorStrategy(fast_period=5, slow_period=13, name="Volume_Oscillator")`. VOL = (fast_vol_ema - slow_vol_ema) / slow_vol_ema * 100, where the EMAs are exponential moving averages of the `"volume"` column over `fast_period` and `slow_period`. Emits a buy when VOL crosses above zero (volume expansion) and a sell when it crosses below zero (volume contraction), with NaN/zero guards and strength = min(1, |VOL|/(|VOL|+100)). Requires `"close"` and `"volume"` columns.
- `quant_trading/strategies/__init__.py`: imported `VolumeOscillatorStrategy`, registered `register_strategy("vol", VolumeOscillatorStrategy, aliases=["volume_oscillator"])`, added to `__all__` (alphabetical to keep ruff I001 clean).
- `tests/test_strategies_examples.py`: added `create_volume_oscillator_data` helper and `TestVolumeOscillatorStrategy` (8 tests: init, validation, insufficient data, cross-above-zero buy, cross-below-zero sell, flat volume no signals, multiple symbols, NaN volume skip). Exact VOL values verified against the implementation (buy cross: +16.666666666666693; sell cross: -10.256410256410259).
- `examples/cli.py`: added `"vol"` to `BUILTIN_STRATEGY_KEYS`.
- `README.md`: "25 registered strategies" -> "26", added Volume Oscillator to the built-in list, added `- \`vol\` (alias: \`volume_oscillator\`) → \`VolumeOscillatorStrategy\`` to the Strategy Registry table.
- `tests/test_cli.py::TestRunCombined::test_run_combined_all_strategies`: added `("Volume_Oscillator", 16.0)` to mocked combined-mode results and assertion.

## What was actually verified

- Full suite: 2088 passed (previously 2080), 0 failed (includes the 8 new VOL tests).
- `python -m ruff check quant_trading examples tests`: clean.
- `python -m black --check` on all files: clean (black also reformatted a pre-existing mis-indented block in `VolumeRateOfChangeStrategy` in `quant_trading/strategies/examples.py` that the prior session's black check had not caught; the baseline was not actually black-clean).
- `python -m mypy quant_trading`: clean.
- `tests/test_readme.py` README-vs-registry consistency passes (registry entry added to README).
- `tests/test_cli.py::TestRunCombined` (4 tests) pass with the new strategy entry.
- `python examples/cli.py --offline --strategy vol --symbols AAPL --days 60` runs end to end.
- `python examples/cli.py --list-strategies` lists `vol: VolumeOscillatorStrategy (fast_period=5, slow_period=13)`.

## What remains unresolved

None.

## One precise next task

Add another classic volume/momentum/oscillator strategy following the same pattern: class in `quant_trading/strategies/examples.py`, registration in `quant_trading/strategies/__init__.py` (alphabetical placement to keep ruff I001 clean), tests in `tests/test_strategies_examples.py`, README listing/registry entry (bump count to 27), and `BUILTIN_STRATEGY_KEYS` in `examples/cli.py`. Remember to also update `tests/test_cli.py::TestRunCombined` when the registry grows. If no strategy is added, no further work is needed — the baseline is green.

(End of file - total 37 lines)