# Next Task

## What changed

Closed the remaining statement/branch coverage gaps in `quant_trading/backtest/engine.py` (the backtest engine, the core of the framework), bringing it to **100% statement and branch coverage** (was 96%).

Added 6 tests in `tests/test_backtest_engine.py` under a new `TestStopExitAndShortCoveringEdges` class, driving the engine's private exit/sizing methods directly with hand-built portfolios (no network, no full backtest run):

1. `test_process_stop_exits_skips_symbol_without_price` — held symbol missing from the bar's prices is skipped (engine.py:647).
2. `test_process_stop_exits_skips_zero_quantity_holding` — zero-quantity holding is skipped (engine.py:651).
3. `test_open_short_returns_when_no_available_value` — short with no available position value is not opened (engine.py:845).
4. `test_cover_short_returns_when_zero_quantity` — cover signal with zero strength covers nothing (engine.py:906).
5. `test_cover_short_returns_when_cash_constrained_to_zero` — cover trimmed to zero cash is not executed (engine.py:910-914).
6. `test_cover_short_trims_to_affordable_positive_quantity` — cover trimmed by cash still executes when trimmed size is positive (engine.py:915 not-taken branch).

Also added `from quant_trading.portfolio.portfolio import Holding` import.

## What was actually verified

- `tests/test_backtest_engine.py`: **91 passed** (including the 6 new ones).
- `quant_trading/backtest/engine.py`: **100%** statement and branch coverage.
- `python -m ruff check quant_trading tests examples` -> All checks passed.
- `python -m black --check quant_trading tests examples` -> 89 files unchanged (file reformatted by black, then re-checked clean).
- `python -m mypy quant_trading` -> Success: no issues found.

## What remains unresolved

- `quant_trading/backtest/trade_analysis.py` is still at 97% (missing: 243->246 partial branch, 399-400, 425, 505, 515).
- Several other modules sit at 98-99%: `data/synthetic.py`, `regime/detector.py`, `strategies/examples.py`.
- `quant_trading/data/providers.py` is at 67% (its offline tests exist in `test_data_providers.py` but were excluded from the coverage scan because that file triggers a numpy/coverage toolchain issue — see below).

## Approaches that already failed

- `python -m pytest --cov=quant_trading.data.providers` raises `ImportError: cannot load module more than once per process` (numpy/pandas re-import under coverage's import hook). Plain `pytest tests/test_data_providers.py` works fine (28 passed). This is a toolchain flakiness, not a code defect; do not blindly retry the narrow `--cov` target. If you need providers.py coverage, run its tests with plain pytest and measure coverage another way, or accept the network-gated provider branches are intentionally untestable offline.

## Next task

Close `quant_trading/backtest/trade_analysis.py` to 100% by adding focused tests for its uncovered lines/branches (243->246 partial branch, 399-400, 425, 505, 515), then re-run ruff/black/mypy and the full non-network suite. Follow the same pattern: smallest reversible change, additive tests, verify with coverage, keep lint/format/typecheck clean.
