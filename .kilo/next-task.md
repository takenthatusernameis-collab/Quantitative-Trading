# Next Task

## What changed

Threaded the configured risk-free rate through the three paths that still
hardcoded `0.02`. Every change is additive and backwards compatible: each new
parameter defaults to `0.02`, so callers that do not pass one keep today's
behaviour exactly. The engine's existing wiring was left untouched.

1. **`quant_trading/risk/manager.py`** — `RiskManager.__init__` now accepts
   `risk_free_rate: float = 0.02`, stores it on the instance, and
   `RiskManager.calculate_metrics(..., risk_free_rate: float | None = None)`
   passes it through to `calculate_all_metrics`. When the argument is `None`
   the configured rate is used; an explicit value overrides it.
2. **`quant_trading/optimization/walk_forward.py`** — `WalkForwardOptimizer`
   now accepts `risk_free_rate: float = 0.02` and passes it into
   `_combine_test_results` instead of the hardcoded literal.
3. **`quant_trading/monte_carlo/simulator.py`** — `MonteCarloSimulator` now
   accepts `risk_free_rate: float = 0.02`, stores it, and both `_run_bootstrap`
   and `_run_parametric` pass `self.risk_free_rate` to `calculate_backtest_metrics`.
   The `run_monte_carlo` convenience function forwards the same argument.

Tests added (7):

- `tests/test_risk_manager.py` — `TestRiskFreeRate`: default is 0.02, custom value
  is stored, a non-default rate reaches the computed Sharpe/Sortino, and an
  explicit argument overrides the configured rate.
- `tests/test_optimization.py` — `test_walk_forward_risk_free_rate_reaches_combined_metrics`:
  the configured rate reaches the combined walk-forward metrics.
- `tests/test_monte_carlo.py` — simulator stores the rate, default is 0.02,
  bootstrap and parametric methods both honour a non-default rate, and the
  same seed produces identical returns with only the risk-adjusted metrics
  differing.

## Verified

- `pytest tests/ -q`: **1506 passed, 1 skipped** (was 1497 passed, 1 skipped).
- `ruff check quant_trading/ tests/`: clean.
- `mypy quant_trading/`: clean (36 source files).
- `black --check` on the six touched source/test files: clean.
- `python examples/cli.py --offline --symbols AAPL --days 120` runs clean.
- `python examples/run_analysis.py` runs clean.

## Behaviour changes to be aware of

None for callers that do not pass a `risk_free_rate`: every default is `0.02`,
exactly what the previous hardcoded literals produced. The only observable
change is for callers that already pass a non-default rate — those now reach
the metrics they asked for instead of being silently overridden.

## Next task

**Fix `Rebalancer.generate_rebalance_actions` ignoring sell signals for short positions.**

Evidence: `quant_trading/portfolio/rebalancer.py:420-432` requires
`holding.quantity > 0` before emitting a sell action, so a portfolio holding
`-50` AAPL with a sell signal for AAPL produces **no** rebalance action, even
though `execute_actions` → `Portfolio.remove_holding` can cover a short. The
docstring says sell signals "liquidate the full holdings of the signaled
symbol".

Constraints and suggested approach:

- Make the sell branch act on `holding.quantity != 0` (or split into long and
  short cases), keeping the buy branch unchanged.
- A sell on a short position should buy-to-close, so check that
  `Portfolio.remove_holding` / `execute_actions` already handles negative
  quantities before relying on it.
- Add a regression test: a portfolio holding `-50` AAPL and a sell signal for
  AAPL must produce a rebalance action, and the action must reduce the short
  exposure rather than being dropped.

Useful context for later, if time allows: none outstanding.