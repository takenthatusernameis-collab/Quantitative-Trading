## Status

The two pre-existing repo-integrity failures noted in the prior handoff are
**already complete** (committed in HEAD `41415b9`, before this session):

- `quant_trading/backtest/trade_log.py` — black formatting fixed (single collapsed
  line at the `open_pnl` sum; no logic change).
- `quant_trading/portfolio/rebalancer.py:98` and `:306` — valid doctests added to
  `RebalanceAction.__post_init__` and `_RebalancePlan.__post_init__`.

`tests/test_repository_integrity.py` is fully green (51 passed). `HANDOFF_NEXT_AGENT.md`
was stale (it listed those as remaining); this session's real work is below.

## What Changed (this session)

Hardened the **dict/JSON deserialization boundary** for risk metrics, following
the same sanitize-to-zero `_finite` pattern already used in
`quant_trading/backtest/engine.py` (`Trade.from_dict`, `BacktestResult.from_dict`)
and `quant_trading/risk/manager.py` / `quant_trading/portfolio/`.

`quant_trading/risk/metrics.py`:

- Added `import math` and `Any` to imports.
- `RiskMetrics.from_dict`: every numeric field
  (`sharpe_ratio`, `sortino_ratio`, `max_drawdown`, `volatility`, `var_95`,
  `var_99`, `cvar_95`, `cvar_99`, `beta`, `alpha`, `calmar_ratio`,
  `treynor_ratio`, `information_ratio`, `omega_ratio`, `ulcer_index`) is now run
  through a `_finite` helper that preserves finite values and replaces
  NaN/inf (and uncoercible values) with `0.0`. Previously non-finite values
  passed straight through into downstream reporting.

`tests/test_risk_metrics.py`: new `TestRiskMetricsFromDictNonFinite` class with
5 regression tests (nan/inf/-inf per field, mixed non-finite, uncoercible
values, finite round-trip preservation).

## What Was Verified

- `python -m pytest -q tests/test_risk_metrics.py` — **179 passed**.
- `python -m pytest --doctest-modules -q quant_trading/risk/metrics.py` — **25 passed**
  (new `from_dict` doctest green).
- Neighbor suites: `tests/test_serialization_roundtrip.py tests/test_repository_integrity.py
  tests/test_risk_manager.py tests/test_risk_metrics.py` — **534 passed**.
- `python -m ruff check quant_trading/risk/metrics.py tests/test_risk_metrics.py` — clean.
- `python -m black --check quant_trading/risk/metrics.py tests/test_risk_metrics.py` — clean.
- `python -m mypy quant_trading/risk/metrics.py tests/test_risk_metrics.py` — clean.

## Unresolved / Notes

Other `from_dict` deserialization boundaries still pass NaN/inf straight through.
High-value remaining targets (thematic continuation of this session):

- `quant_trading/risk/manager.py:211` `RiskAttribution.from_dict`
- `quant_trading/risk/manager.py:388` `PortfolioRisk.from_dict`
- `quant_trading/portfolio/portfolio.py:178` `Holding.from_dict` / `:573` `Portfolio.from_dict`
- `quant_trading/optimization/base.py:726` `OptimizationResult.from_dict`
- `quant_trading/monte_carlo/simulator.py:394` `MonteCarloResult.from_dict`
- `quant_trading/regime/detector.py:228` `RegimeResult.from_dict`

None of these were probed this session; pick the risk-module ones first since
they feed the same reporting path as `RiskMetrics`.

## One Precise Next Task

Harden `RiskAttribution.from_dict` (risk/manager.py:211) and
`PortfolioRisk.from_dict` (risk/manager.py:388) so non-finite values are
sanitized to `0.0` via a `_finite` helper mirroring
`quant_trading/risk/metrics.py:from_dict` and
`quant_trading/backtest/engine.py`. Add a regression test class
`TestRiskManagerFromDictNonFinite` in `tests/test_risk_manager.py` covering
nan/inf/-inf per numeric field plus a finite round-trip sanity check.

Verify with:

```bash
python -m pytest -q tests/test_risk_manager.py tests/test_risk_metrics.py
python -m pytest --doctest-modules -q quant_trading/risk/manager.py quant_trading/risk/metrics.py
python -m ruff check quant_trading/risk/manager.py quant_trading/risk/metrics.py tests/test_risk_manager.py tests/test_risk_metrics.py
python -m black --check quant_trading/risk/manager.py quant_trading/risk/metrics.py tests/test_risk_manager.py tests/test_risk_metrics.py
python -m mypy quant_trading/risk/manager.py quant_trading/risk/metrics.py tests/test_risk_manager.py tests/test_risk_metrics.py
```

## Failed Approach / Evidence

None this session. Each change resolved its leak (doctest + regression tests
pass; the `from_dict` boundary no longer emits NaN/inf).
