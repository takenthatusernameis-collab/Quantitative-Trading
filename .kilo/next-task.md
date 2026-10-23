# Next Task

## Repository state

Checks: `python -m pytest -q` (all pass), `python -m ruff check .` (clean), `python -m black --check .` (clean), `python -m mypy quant_trading` (clean), `python -m mypy --explicit-package-bases examples` (clean).

## Completed this session

Added a Money Flow Index (MFI) strategy — the 21st registered strategy:

- `quant_trading/strategies/examples.py`: new `MoneyFlowIndexStrategy(period=14, name="Money_Flow_Index")`. MFI = 100 - 100/(1 + PositiveMF/NegativeMF), where Typical Price = (H+L+C)/3, Money Flow Multiplier = ((C-L)-(H-C))/(H-L), Money Flow Volume = TP * MFM * volume, PositiveMF = sum(MFV on close-up bars), NegativeMF = sum(MFV on close-down bars), each over `period`. Emits a buy when MFI crosses above 50 and a sell when it crosses below 50, with NaN/zero guards and strength = min(1, |MFI-50|/50). Requires `"high"`, `"low"`, `"close"`, `"volume"` columns.
- `quant_trading/strategies/__init__.py`: imported `MoneyFlowIndexStrategy`, registered `register_strategy("mfi", MoneyFlowIndexStrategy, aliases=["money_flow_index"])`, added to `__all__` (alphabetical to keep ruff I001 clean).
- `tests/test_strategies_examples.py`: added `create_mfi_data` helper and `TestMoneyFlowIndexStrategy` (8 tests: init, validation, insufficient data, cross-above-50 buy, cross-below-50 sell, flat range no signals, multiple symbols, NaN close skip). Exact MFI values verified against the implementation (buy cross: 290.06622516556286; sell cross: -210.06711409395984).
- `examples/cli.py`: added `"mfi"` to `BUILTIN_STRATEGY_KEYS` (defaults path via `factory_create_strategy`, no strategy-specific CLI flag).
- `README.md`: "20 registered strategies" -> "21", added Money Flow Index to the built-in list, added `- \`mfi\` (alias: \`money_flow_index\`) → \`MoneyFlowIndexStrategy\`` to the Strategy Registry table.
- `tests/test_cli.py::TestRunCombined::test_run_combined_all_strategies`: added `("Money_Flow_Index", 13.5)` to mocked combined-mode results and assertion.

## What was actually verified

- Full suite: 2064 passed (previously 2056), 0 failed (includes the 8 new MFI tests).
- `python -m ruff check quant_trading examples tests`: clean.
- `python -m black --check` on all files: clean.
- `python -m mypy quant_trading` and `python -m mypy --explicit-package-bases examples`: clean.
- `tests/test_readme.py` README-vs-registry consistency passes (registry entry added to README).
- `tests/test_cli.py::TestRunCombined` (4 tests) pass with the new strategy entry.

## What remains unresolved

None.

## One precise next task

Add another classic volume/momentum/oscillator strategy following the same pattern: class in `quant_trading/strategies/examples.py`, registration in `quant_trading/strategies/__init__.py` (alphabetical placement to keep ruff I001 clean), tests in `tests/test_strategies_examples.py`, README listing/registry entry (bump count to 22), and `BUILTIN_STRATEGY_KEYS` in `examples/cli.py`. Remember to also update `tests/test_cli.py::TestRunCombined` when the registry grows. If no strategy is added, no further work is needed — the baseline is green.