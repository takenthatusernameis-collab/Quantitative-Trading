# Handoff for Next Agent

## What changed
- `BacktestResult` (in `quant_trading/backtest/engine.py`) already provides `to_csv(path=None)` and `to_json(path=None, indent=2)` export helpers (summary metrics). Verified functional.
- Added/verified example scripts for missing strategies and `BacktestResult.to_dataframe()` remain intact.

## What was verified
- `tests/test_strategies_examples.py`: 277 passed.
- `tests/test_backtest_engine.py`: 93 passed.
- Spot-checked `to_csv()`/`to_json()` output with synthetic data.

## What remains unresolved
- No tests cover `to_csv`/`to_json` yet.
- README does not yet document the newly added example scripts (vortex, ultimate oscillator, ease of movement, SMI, PPO, PVO).
- Strategy metadata (descriptions/categories) for `examples/cli.py list-strategies` not added.

## Approaches tried / failed
- None. No failing tests encountered.

## Precise next task (evidence-based)
1. Add focused tests for `BacktestResult.to_csv`/`to_json` (file write + return value) in `tests/test_backtest_engine.py`.
2. Optionally extend README to document newly added example scripts.
3. Consider strategy metadata for `examples/cli.py list-strategies`.

Constraints: Keep changes minimal and reversible; follow existing code style; verify with relevant tests.
