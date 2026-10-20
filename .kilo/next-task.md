# Next Task

## What changed (this session)

Added tests covering the two pre-existing uncovered branches in `quant_trading/backtest/engine.py`:

- `tests/test_backtest_engine.py`:
  - `test_buy_returns_when_available_value_non_positive`: preloads a holding so that `target_value - current_value <= 0`, emits a buy signal via a strategy, runs backtest; asserts result is not None and the early return at engine.py:535-536 is exercised (no trade added for that signal when position already meets/exceeds target).
  - `test_run_backtest_with_config_and_no_data_manager`: calls `run_backtest(..., config=Config(data=DataConfig(provider="synthetic", offline=True)), data_manager=None)`, verifying the branch at engine.py:666-668 creates a data manager from config.

## What was actually verified (this session)

- `python -m pytest tests/test_backtest_engine.py -q` → 35 passed (added 2 new tests; previous 33).
- Full non-dependency subset: `python -m pytest tests/ --ignore=tests/test_cli.py --ignore=tests/test_optimization.py --ignore=tests/test_alphavantage_provider.py --ignore=tests/test_yfinance_fetch_many.py -q` → 669 passed, 1 skipped (baseline 667 passed, 1 skipped; delta is the 2 new engine tests).
- Both previously uncovered branches are now exercised by tests.

## What remains unresolved

- **Pre-existing environment constraints:** `yfinance` not installed (2 CLI test failures), `scikit-optimize` not installed (optimization tests); `ruff`, `black`, `mypy` not installed locally.
- **Coverage gaps (low):** `regime/detector.py` (28%), `backtest/trade_analysis.py` (18%), `monte_carlo/simulator.py` (0%), `data/yfinance_provider.py` (6%), `strategies/examples.py` (11%), plus other small gaps. Also `portfolio/rebalancer.py` has 4 unreachable defensive branches under valid inputs (documented in previous handoff).

## Approaches already failed

- None in this session.

## One precise next task

**Add tests to cover `quant_trading/regime/detector.py` core behaviors (bounded, high-value, deterministic, no network).**

1. Read `quant_trading/regime/detector.py` to understand classes/methods (e.g. `Regime`, `RegimeDetector`, `analyze_regimes`, regime segmentation logic, bull/bear/sideways and volatility classification, any helper functions).
2. Create/add tests in `tests/test_regime_detector.py` following existing test style (see `tests/test_regime.py`). Cover at least: regime classification of synthetic equity curves (bull/bear/sideways), low/high volatility segmentation, current regime detection, and threshold overrides if applicable.
3. Use only deterministic synthetic data/returns (no network). Keep tests isolated and fast.
4. Verify with `python -m pytest tests/test_regime_detector.py -v` and, if coverage is available, `python -m coverage run -m pytest tests/test_regime_detector.py && python -m coverage report --include=quant_trading/regime/detector.py`.
5. Keep changes minimal and localized to tests; only modify implementation if a trivial bug is found with clear evidence.

Constraints: follow repository test patterns, no external dependencies, deterministic synthetic inputs only.
