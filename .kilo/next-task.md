# Next Task

## Repository state

Checks: `python -m pytest -q` (all pass), `python -m ruff check .` (clean), `python -m black --check .` (clean), `python -m mypy quant_trading` (clean), `python -m mypy --explicit-package-bases examples` (clean).

## Completed this session

Added an On-Balance Volume (OBV) strategy — the 18th registered strategy:

- `quant_trading/strategies/examples.py`: new `OBVStrategy(signal_period=20, name="OBV")`. OBV cumulatively adds/subtracts volume on up/down days; emits a buy when OBV crosses above its SMA signal line and a sell when it crosses below, with NaN/zero guards and strength scaled by the cross magnitude.
- `quant_trading/strategies/__init__.py`: imported `OBVStrategy`, registered `register_strategy("obv", OBVStrategy, aliases=["on_balance_volume"])`, added to `__all__`.
- `tests/test_strategies_examples.py`: added `create_obv_data` helper and `TestOBVStrategy` (7 tests: init, validation, insufficient data, cross-above buy, cross-below sell, flat data no signal, multiple symbols, NaN close skip).
- `examples/cli.py`: added `"obv"` to `BUILTIN_STRATEGY_KEYS` (defaults path via `factory_create_strategy`, no strategy-specific CLI flag).
- `README.md`: "17 registered strategies" -> "18", added On-Balance Volume to the built-in list, added `- \`obv\` (alias: \`on_balance_volume\`) → \`OBVStrategy\`` to the Strategy Registry table.

Also updated `tests/test_cli.py::TestRunCombined::test_run_combined_all_strategies` to include the new `"OBV"` strategy in mocked combined-mode results and assertions.

## What was actually verified

- Full suite: 1955 passed (previously 1947), 0 failed.
- `python -m ruff check quant_trading examples tests`: clean.
- `python -m black --check` on the four changed Python files: unchanged/clean.
- `python -m mypy quant_trading` and `python -m mypy --explicit-package-bases examples`: clean.
- `tests/test_readme.py` README-vs-registry consistency passes (registry entry added to README).

## What remains unresolved

None.

## One precise next task

None outstanding. A future session may add another classic volume/momentum strategy (e.g. Force Index or Chaikin Money Flow) following the same pattern: class in `quant_trading/strategies/examples.py`, registration in `quant_trading/strategies/__init__.py`, tests in `tests/test_strategies_examples.py`, README listing/registry entry, and `BUILTIN_STRATEGY_KEYS` in `examples/cli.py`. Remember to also update any hardcoded strategy lists in `tests/test_cli.py` (e.g. `TestRunCombined`) when the registry grows.
