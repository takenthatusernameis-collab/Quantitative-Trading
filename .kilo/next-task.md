# Next Task

## Repository state

Checks: `python -m pytest -q` (all pass), `python -m ruff check .` (clean), `python -m black --check .` (clean), `python -m mypy quant_trading` (clean), `python -m mypy --explicit-package-bases examples` (clean).

## Completed this session

Added a Chaikin Money Flow (CMF) strategy — the 19th registered strategy:

- `quant_trading/strategies/examples.py`: new `CMFStrategy(period=20, name="Chaikin_Money_Flow")`. CMF = sum(Money Flow Volume, period) / sum(volume, period), where Money Flow Multiplier = ((close - low) - (high - close)) / (high - low). Emits a buy when CMF crosses above zero and a sell when it crosses below zero, with NaN/zero guards and strength scaled by |CMF| + 0.5 (capped at 1.0). Requires ``"high"``, ``"low"``, ``"close"``, ``"volume"`` columns.
- `quant_trading/strategies/__init__.py`: imported `ChaikinMoneyFlowStrategy`, registered `register_strategy("cmf", ChaikinMoneyFlowStrategy, aliases=["chaikin_money_flow"])`, added to `__all__` (kept alphabetical to satisfy ruff I001).
- `tests/test_strategies_examples.py`: added `create_cmf_data` helper and `TestChaikinMoneyFlowStrategy` (8 tests: init, validation, insufficient data, cross-above-zero buy, cross-below-zero sell, flat range no signals, multiple symbols, NaN close skip).
- `examples/cli.py`: added `"cmf"` to `BUILTIN_STRATEGY_KEYS` (defaults path via `factory_create_strategy`, no strategy-specific CLI flag).
- `README.md`: "18 registered strategies" -> "19", added Chaikin Money Flow to the built-in list, added `- \`cmf\` (alias: \`chaikin_money_flow\`) → \`ChaikinMoneyFlowStrategy\`` to the Strategy Registry table.
- `tests/test_cli.py::TestRunCombined::test_run_combined_all_strategies`: added `("Chaikin_Money_Flow", 11.5)` to mocked combined-mode results and assertion.

## What was actually verified

- Full suite: 2051 passed (previously 2043), 0 failed (includes the 8 new CMF tests).
- `python -m ruff check quant_trading examples tests`: clean.
- `python -m black --check` on all files: clean.
- `python -m mypy quant_trading` and `python -m mypy --explicit-package-bases examples`: clean.
- `tests/test_readme.py` README-vs-registry consistency passes (registry entry added to README).

## What remains unresolved

None.

## One precise next task

Add another classic volume/momentum strategy (e.g. Force Index) following the same pattern: class in `quant_trading/strategies/examples.py`, registration in `quant_trading/strategies/__init__.py` (alphabetical placement to keep ruff I001 clean), tests in `tests/test_strategies_examples.py`, README listing/registry entry (bump count to 20), and `BUILTIN_STRATEGY_KEYS` in `examples/cli.py`. Remember to also update `tests/test_cli.py::TestRunCombined` when the registry grows. If no strategy is added, no further work is needed — the baseline is green.
