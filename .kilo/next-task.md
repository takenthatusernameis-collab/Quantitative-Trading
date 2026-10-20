# Next Task

## What changed (this session)

Executed the prior handoff: added `tests/test_portfolio_rebalancer.py` (41 tests) covering `quant_trading/portfolio/rebalancer.py` core behaviors, following existing test style (pytest, deterministic in-memory data, no network).

Coverage:
- `quant_trading/portfolio/rebalancer.py`: 0% → 94% (113 statements, 4 missed).
- The 4 remaining misses are unreachable defensive branches under valid inputs: `diff == 0` can't pass the positive-threshold guard (engine.py:234 equivalent), and sell-with-zero-price requires positive market value. Not worth contorting tests with invalid (negative) inputs.

## What was actually verified (this session)

- `python -m pytest tests/test_portfolio_rebalancer.py -q` → 41 passed.
- Full non-dependency subset: `python -m pytest tests/ --ignore=tests/test_cli.py --ignore=tests/test_optimization.py --ignore=tests/test_alphavantage_provider.py --ignore=tests/test_yfinance_fetch_many.py -q` → 667 passed, 1 skipped (baseline 626 passed, 1 skipped; delta is the 41 new rebalancer tests). No regressions.

## What remains unresolved

- **Pre-existing environment constraints:** `yfinance` not installed (2 CLI test failures), `scikit-optimize` not installed (optimization tests); `ruff`, `black`, `mypy` not installed locally.
- **Coverage gaps in other modules (low):** `regime/detector.py` (28%), `backtest/trade_analysis.py` (18%), `monte_carlo/simulator.py` (0%), `data/yfinance_provider.py` (6%), `strategies/examples.py` (11%), plus the 4 unreachable branches above.

## Approaches already failed

- None in this session.

## One precise next task

**Add tests to cover `quant_trading/regime/detector.py` core behaviors (bounded, high-value, deterministic, no network).**

1. Read `quant_trading/regime/detector.py` to understand classes/methods (e.g. `Regime`, `analyze_regimes`, regime segments, bull/bear/sideways x low/high volatility classification).
2. Add tests in `tests/test_regime_detector.py` (create if missing) following existing test style (see `tests/test_regime.py`). Cover at least: regime classification of synthetic equity curves (bull/bear/sideways), low/high volatility segmentation, `current_regime`, and threshold overrides.
3. Verify with `python -m pytest tests/test_regime_detector.py -v` and coverage: `python -m coverage run -m pytest tests/test_regime_detector.py && python -m coverage report --include=quant_trading/regime/detector.py`.
4. Keep changes minimal and localized to tests; only modify implementation if a trivial bug is found with clear evidence.

Constraints: use only deterministic synthetic equity curves/returns, no external network calls, follow existing naming/conventions in tests/.
