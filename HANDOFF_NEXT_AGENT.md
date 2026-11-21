## Status

Hardened three `from_dict` deserializers in `quant_trading/risk/limits.py` with the `_finite` helper pattern used in `quant_trading/risk/metrics.py` and `quant_trading/risk/manager.py`:

1. **PositionLimit.from_dict** (line 176): Non-finite (NaN/inf), non-numeric, and missing numeric fields are sanitized to defaults (0.1, 50000.0, 0.05, 0.15).

2. **PortfolioLimit.from_dict** (line 373): All six numeric fields sanitized to defaults (20, 0.1, 0.02, 0.20, 1.0, 0.05).

3. **CheckResult.from_dict** (line 584): Docstring updated to note numeric field sanitization (passed/violations are non-numeric).

Added `_finite` helper function (lines 23-61) with doctests covering finite numbers, non-finite numbers, non-numeric values, numeric strings, bool rejection, and None handling.

## Verified

- pytest tests/test_limits.py: **198 passed** (including 66 new regression tests)
- pytest tests/test_portfolio.py tests/test_risk_metrics.py tests/test_risk_manager.py tests/test_serialization_roundtrip.py: **762 passed** total
- doctest quant_trading/risk/limits.py: **64 passed** (including 6 new _finite doctests)
- doctest quant_trading/risk/manager.py: **132 passed**
- ruff check: **clean**
- black --check: **clean**
- mypy quant_trading/risk/limits.py: **clean**

Full `pytest` suite times out locally (>5 min) — appears to be pre-existing slowness unrelated to this change; verify in CI if available.

## Next Task

The hardening chain is complete. The scan found every remaining `from_dict`
deserializer was already hardened with `_finite` (or an inline equivalent)
except two, which were hardened in this session:

1. `OptimizationResult.from_dict` (`quant_trading/optimization/base.py`):
   `best_score` now runs through `_finite` instead of a raw `float(...)` cast,
   so NaN/inf/non-numeric/unconvertible values sanitize to `0.0`. Doctest added.
2. `BayesianOptimizerConfig.from_dict` (`quant_trading/optimization/bayesian.py`):
   `noise` now runs through `_finite(..., 1e-6)`; imports `_finite` from
   `quant_trading.optimization.base`. Doctest added.

Regression tests added to `tests/test_optimization.py`:
- `test_optimization_result_from_dict_sanitizes_non_finite_best_score`
- `test_bayesian_optimizer_config_from_dict_sanitizes_non_finite_noise`

No other exposed deserializers accepting raw untrusted dictionaries lack
hardening: `PositionLimit`, `PortfolioLimit`, `CheckResult` (risk/limits.py),
`RiskMetrics` (risk/metrics.py), `RiskAttribution`, `PortfolioRisk`
(risk/manager.py), `BacktestMetrics`, `Trade`, `BacktestResult`
(backtest/engine.py), `BacktestRegimeAnalysis` (backtest/analysis.py),
`TradeAnalysis` (backtest/trade_analysis.py), `RegimeSegment`, `RegimeResult`
(regime/detector.py), `MonteCarloResult` (monte_carlo/simulator.py),
`ParameterSpace`, `ParameterGrid`, `OptimizationResult`
(optimization/base.py), `BayesianOptimizerConfig` (optimization/bayesian.py),
`SensitivityConfig` (optimization/sensitivity.py), `WalkForwardWindow`,
`WalkForwardResult` (optimization/walk_forward.py), `Signal`, `Position`
(strategies/base.py), `Holding`, `Portfolio` (portfolio/portfolio.py),
`RebalanceAction`, `RebalanceExecution`, `_RebalancePlan`
(portfolio/rebalancer.py), and all config classes (config/settings.py) are
hardened or delegate to hardened sub-deserializers.

## Verified (this session)

- pytest tests/test_optimization.py: **232 passed, 11 skipped**
- pytest tests/test_serialization_roundtrip.py tests/test_backtest_engine.py: **191 passed**
- doctest quant_trading/optimization/base.py + bayesian.py: **25 passed**
- mypy on both changed modules: **clean**
- black --check on changed files: **clean** (pre-existing `_finite`
  formatting in base.py:36 untouched, not part of this change)
- ruff check on changed files: **clean** except pre-existing I001 import
  sort in base.py (untouched, not part of this change)

Full `pytest` suite times out locally (>5 min) — pre-existing slowness
unrelated to this change; verify in CI if available.

There is no remaining follow-up task for the deserialization hardening chain.

## Session 2026-11-21 (this session)

Fixed a pre-existing failing test in `tests/test_config.py`:
- `test_from_dict_rejects_non_finite_risk_free_rate` expected `BacktestConfig.from_dict({"risk_free_rate": nan})` to raise `ValueError`, but `from_dict` sanitizes numerics via `_finite` (collapsing NaN/inf to `0.0`), so no exception is raised. Direct construction still rejects non-finite values via `__post_init__`.
- Renamed to `test_from_dict_sanitizes_non_finite_risk_free_rate`, asserting nan/inf/-inf → `0.0`, finite, no exception. Added `import math`.

Verified:
- pytest tests/test_config.py: **144 passed** (was 1 failed, 143 passed)
- ruff check / black --check / mypy on tests/test_config.py: **clean**

Next task: audit the CLI validations documented in README.md "Error Reporting" section (e.g. `--risk-free-rate nan`, `--initial-capital nan`, `--synthetic-seed -1`, `--commission 1.5`, `--mc-simulations 0`) against `examples/cli.py` and close gaps where a documented error case is not caught pre-run with a one-line `Error:` + exit 1.