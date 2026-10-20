# Next Task

## What changed (this session)

Closed the realized-PnL vs cash reconciliation gap by capitalizing entry fees into the cost basis of long positions.

- `quant_trading/portfolio/portfolio.py` (`add_holding`):
  - New long position: `avg_cost = price * (1 + commission + slippage)` (was `price`).
  - Adding to an existing long: the added lot is averaged in at its fee-inclusive cost `price * (1 + commission + slippage) * quantity` (was gross `cost = quantity * price`).
  - Reductions of a long and new short positions are unchanged (engine only sells longs via `remove_holding` and never opens shorts).
  - Docstring updated to document the fee-inclusive basis semantics.
- `quant_trading/backtest/engine.py`:
  - No logic change needed: `realized_pnl = quantity * price * (1 - commission - slippage) - avg_cost * quantity` (engine.py:569-572) now nets both buy-side and sell-side fees because `avg_cost` includes entry fees.
  - `BacktestResult` class docstring updated: `sum(Trade.pnl)` is now net of both fee sides and equals `final_value - initial_capital` for fully liquidated round trips.
- `tests/test_backtest_engine.py`:
  - `test_signed_trade_cost_reconciles_with_final_value`: flipped the pnl-sum assertion from `!=` to `==` (gap closed); docstring updated.
  - `test_total_costs_reconciles_with_pnl_and_final_value`: `cash_change == pnl.sum()` (was `== pnl.sum() - buy_fees`); inequality assertion replaced with equality; docstring updated.
- `tests/test_portfolio.py`: added `test_add_holding_capitalizes_entry_fees`, `test_add_holding_averaging_includes_entry_fees`, `test_short_position_keeps_execution_price_as_basis`.

## What was actually verified (this session)

- `python -m pytest tests/test_portfolio.py tests/test_backtest_engine.py -q` → 59 passed (56 baseline + 3 new).
- Full non-dependency subset: `python -m pytest tests/ --ignore=tests/test_cli.py --ignore=tests/test_optimization.py --ignore=tests/test_alphavantage_provider.py --ignore=tests/test_yfinance_fetch_many.py -q` → 624 passed, 1 skipped (baseline was 621 passed, 1 skipped; delta is the 3 new portfolio tests).
- `python -m pytest tests/test_cli.py -q` → 92 passed, 2 failed (pre-existing: `TestSaveStrategyConfig::test_optimize_saves_best_params_config` and `test_walk_forward_saves_last_window_params_config` fail due to missing `yfinance`; unchanged from baseline).
- The closed reconciliation is asserted directly: for the costed BuyThenSell round trip, `trades["pnl"].sum() == final_value - initial_capital` now passes.

All changes are minimal and localized to `portfolio.py` `add_holding`, the engine docstring, and affected tests.

## What remains unresolved

- **Pre-existing coverage gaps in engine.py** (not caused by this change): `available_value <= 0` early return at engine.py:535-536 and the `config is not None` data-manager branch at engine.py:666-668.
- **Pre-existing environment constraints:** `yfinance` not installed (2 CLI test failures), `scikit-optimize` not installed (optimization test failures); `ruff`, `black`, `mypy`, `coverage` not installed locally.

## Approaches already failed

- None in this session. Previous session established that `total_costs == sum(all fees)` and `final_value - initial_capital == sum(pnl)` cannot hold simultaneously under the old PnL semantics (buy fees excluded from cost basis); this session resolves it by capitalizing entry fees into `avg_cost`, at the cost of a documented semantics change for `Holding.avg_cost`/`Position.avg_price` (stop-loss/take-profit triggers in risk/manager.py:310-327 now use a fee-inclusive breakeven).

## One precise next task

**Add tests covering the two pre-existing uncovered branches in `quant_trading/backtest/engine.py` and confirm engine coverage.**

1. `engine.py:535-536` (`if available_value <= 0: return` in the buy path): add a test where a buy signal arrives when the existing position already meets/exceeds the risk-target value (e.g. pre-load a holding via `add_holding`, then issue a low-strength buy signal), asserting no trade is executed and no cash changes.
2. `engine.py:666-668` (`if data_manager is None: if config is not None:` in `run_backtest`): add a test calling `run_backtest(..., config=<Config or DataConfig>, data_manager=None)` with an offline/synthetic-backed config so the `create_data_manager_from_config` path runs, asserting a result is returned.
3. Run `python -m pytest tests/test_backtest_engine.py -q` and, if `coverage` is available, `python -m coverage run -m pytest tests/test_backtest_engine.py && python -m coverage report --include=quant_trading/backtest/engine.py` to confirm the previously uncovered lines (~533-536, ~665-668) are now exercised.

Constraints: keep tests deterministic (use `MockDataProvider`/synthetic data, no network); match existing test style in tests/test_backtest_engine.py (see `_engine_run` helper and `BuyThenSellStrategy`/`FirstDayBuyStrategy` at the top of the file).