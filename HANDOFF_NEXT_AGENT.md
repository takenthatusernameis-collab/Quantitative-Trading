## Status

Added focused CLI test assertion that `ulcer_index` appears in single-run JSON output (`tests/test_cli.py`, `test_main_with_regime_monte_carlo_trade_analysis_output`).

## What was actually verified

- `python -m pytest tests/test_cli.py -k "regime_monte_carlo_trade_analysis_output"` passed.

## Remaining work / unresolved

- Combined-run JSON (`per-strategy + best`) could gain analogous assertions if desired.

## One precise next task

Add `ulcer_index` assertions to combined-run JSON tests or move to a new feature area.
