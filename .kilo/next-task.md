# Next Task

## What changed (this session)

Executed the previous handoff: verified the two pre-existing uncovered branches in `quant_trading/backtest/engine.py` are already covered by tests and engine coverage is 100%.

- Confirmed `tests/test_backtest_engine.py::test_buy_signal_with_existing_position_at_target_does_not_trade` exercises `available_value <= 0` early return (engine.py:535-536).
- Confirmed `tests/test_backtest_engine.py::test_run_backtest_with_config_creates_data_manager` exercises `run_backtest` with `config` and `data_manager=None` (engine.py:666-668).
- Coverage verified: `python -m coverage run -m pytest tests/test_backtest_engine.py && python -m coverage report --include=quant_trading/backtest/engine.py` → 152 statements, 0 missed, 100% coverage.

## What was actually verified (this session)

- `python -m pytest tests/test_backtest_engine.py tests/test_portfolio.py tests/test_risk_manager.py tests/test_limits.py tests/test_backtest_metrics.py tests/test_backtest_analysis.py -q` → 153 passed.
- `python -m pytest tests/test_data_providers.py tests/test_strategy_factory.py tests/test_regime.py -q` → 91 passed.
- Full non-dependency subset: `python -m pytest tests/ --ignore=tests/test_cli.py --ignore=tests/test_optimization.py --ignore=tests/test_alphavantage_provider.py --ignore=tests/test_yfinance_fetch_many.py -q` → 626 passed, 1 skipped.

## What remains unresolved

- **Pre-existing environment constraints:** `yfinance` not installed (2 CLI test failures in full CLI suite), `scikit-optimize` not installed (optimization tests fail/skipped as expected).
- **Coverage gaps in other modules (low):** `portfolio/rebalancer.py` (12%), `regime/detector.py` (28%), `backtest/trade_analysis.py` (18%), `monte_carlo/simulator.py` (0%), `optimization/*` (0% without scikit-optimize deps), `data/yfinance_provider.py` (6%), `strategies/examples.py` (11%).

## Approaches already failed

- None in this session.

## One precise next task

**Add tests to cover `quant_trading/portfolio/rebalancer.py` core behaviors (bounded, high-value).**

1. Read `quant_trading/portfolio/rebalancer.py` to understand classes/methods (`Rebalancer`, `RebalanceResult`, etc.) and existing usage patterns.
2. Add tests in `tests/test_portfolio_rebalancer.py` (create if missing) following existing test style (pytest, no network). Cover at least: periodic rebalancing trigger logic, threshold-based rebalancing, drift calculation/allocation vs target, and `rebalance()` producing expected trades/cash effects with deterministic synthetic data.
3. Verify with `python -m pytest tests/test_portfolio_rebalancer.py -v` and check coverage: `python -m coverage run -m pytest tests/test_portfolio_rebalancer.py && python -m coverage report --include=quant_trading/portfolio/rebalancer.py`.
4. Keep changes minimal and localized to tests; only modify implementation if a trivial bug is found with clear evidence.

Constraints: use only in-memory/synthetic data, no external network calls, follow existing naming/conventions in tests/.
