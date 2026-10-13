# Task for the next Kilo agent

## Context

Quantitative Trading framework. Previous handoff requested closing `backtest/trade_analysis.py` coverage gaps (14 missed lines; 93%→100%). This session executed that task.

## What was done in this session

- Added comprehensive tests to `tests/test_trade_analysis.py` to cover all missing branches in `quant_trading/backtest/trade_analysis.py`:
  - Line 92: `_calculate_holding_periods` empty trades / trades without "pnl" column (early return)
  - Lines 124-125: partial fill in `_calculate_holding_periods` (else branch when qty_sold < entry_qty)
  - Line 133: `_calculate_consecutive_streaks` empty / no-pnl early return
  - Lines 156-158: loss-streak branch in consecutive streaks (`elif current_losses > 0`)
  - Lines 166, 170: `_calculate_monthly_returns` short series cases (< 2 points, < 2 months after resample)
  - Lines 179, 183: `_calculate_weekly_returns` short series cases (< 2 points, < 2 weeks after resample)
  - Line 192: `_calculate_symbol_stats` empty / no-pnl early return
  - Lines 281-282: `analyze_trades` with single completed trade (len(pnl_series) <= 1) to hit sharpe/sortino = 0.0 branch
- Also added direct tests for empty cases in `_calculate_symbol_stats` to ensure line 192 is fully covered.

No source code modifications were made to `quant_trading/`; all changes are test additions/formatting only.

## Verification

- `python -m coverage run -m pytest tests/test_trade_analysis.py -v` → 18 passed (was 10 passed; 8 new tests added)
- `python -m coverage report -m quant_trading/backtest/trade_analysis.py` → 192 statements, 0 missed, **100% coverage**
- `python -m ruff check .` → All checks passed (after auto-fix)
- `python -m mypy quant_trading/` → Success: no issues found in 36 source files

## What changed (working-tree diff at checkpoint)

- `tests/test_trade_analysis.py` — added tests for: holding periods empty cases, partial fill execution path, consecutive streaks empty/no-pnl and loss-streak branches, monthly/weekly short-series cases, single-trade analyze case, and symbol_stats empty cases. Minor import ordering cleanup via ruff --fix.

## What remains unresolved

None blocking. No environment stubs needed to pass mypy on source (mypy is green). The environment previously had numpy/pandas import issues when running all tests together due to environment state; isolated test runs work fine.

## Approaches already tried

N/A - straightforward coverage test additions following existing test patterns (using synthetic DataFrames, synthetic equity curves).

## Next task (precise, prioritized)

**Close `backtest/engine.py` coverage gaps (17 missed; 88%→100%).** Analyze missed lines (notably around signal price validation paths like lines ~258, 276-280, 298, 302 and possibly data manager default path at ~27-31, 365) and add deterministic, offline tests. Focus on testable non-network branches first (price is None/<=0 early returns). Avoid requiring live YFinance network access - use mocks/fakes. Add minimal tests to `tests/test_backtest_engine.py`.

Other remaining small pure-Python gaps (lower priority): `config/settings.py` (2), `data/synthetic.py` (4), `regime/detector.py` (4), `risk/limits.py` (1), `monte_carlo/simulator.py` (2) - total ~11 trivial lines.
