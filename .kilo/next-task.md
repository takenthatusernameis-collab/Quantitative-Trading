# Next Task

## What changed

Fixed four deterministic correctness defects in the backtest result/analysis layer. Every one
of them was reproduced before the fix and is now covered by a regression test.

1. **`quant_trading/backtest/trade_analysis.py` — expectancy was `0.0` whenever no trade lost.**
   The line was
   `expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss) if avg_loss > 0 else 0`.
   With no losing trades `avg_loss` is 0, so the `else 0` branch discarded a correct result:
   a set of trades that won every time reported an expectancy of `$0`. The guard is gone; with
   no losses the formula naturally yields `win_rate * avg_win`. All-loss sets were already
   correct (`-35.0` for `[-50, -20]`).
2. **`quant_trading/backtest/trade_analysis.py` — `analyze_trades` ignored its documented
   `risk_free_rate` argument.** The trade-level Sharpe/Sortino were computed from raw dollar
   PnL with no risk-free adjustment, so `analyze_trades(result, risk_free_rate=0.0)` and
   `analyze_trades(result, risk_free_rate=0.10)` returned identical numbers (verified: both
   `4.810702354423639`). They are now computed on a per-trade return series — trade PnL divided
   by the portfolio equity at the trade's timestamp — and reuse the shared, already tested
   `quant_trading.risk.metrics.calculate_sharpe_ratio` / `calculate_sortino_ratio` helpers, so
   the annual rate is applied as a per-period rate.
3. **`quant_trading/backtest/trade_analysis.py` — consecutive win/loss streaks were counted in
   DataFrame order, not chronologically.** `_calculate_holding_periods` already sorted by
   timestamp; `_calculate_consecutive_streaks` did not, so the "current streak" was whatever the
   last row happened to be. It now does a stable sort by `timestamp` when that column exists.
4. **`quant_trading/backtest/engine.py` — `BacktestEngine.run` raised `ZeroDivisionError` when
   `initial_capital` was 0.** `BacktestConfig` does not validate the value, so
   `BacktestConfig(initial_capital=0.0)` crashed the run at
   `total_value / self.config.initial_capital`. `calculate_backtest_metrics` already guards this
   case (`metrics.py:182-185`); the engine now reports `total_return_pct == 0.0` the same way.

Two smaller hardening changes in the same area:

5. **`quant_trading/backtest/trade_analysis.py`** — `_calculate_monthly_returns` /
   `_calculate_weekly_returns` raised `TypeError` from `resample()` when the equity curve was not
   indexed by time. They now return `{}`.
6. **`quant_trading/portfolio/portfolio.py`** — `Holding.__post_init__` only derived `market_value`
   for long positions with a positive cost basis, so a short (`quantity < 0`) or a zero-cost
   holding reported `market_value == 0.0` instead of `quantity * current_price`. The invariant
   `market_value == quantity * current_price` (already asserted by
   `tests/test_portfolio_invariants.py:48`) is now enforced at construction.

Tests added (15):

- `tests/test_trade_analysis.py` — expectancy for all-win / all-loss / mixed sets; trade Sharpe
  and Sortino checked against the shared helpers; risk-free-rate sensitivity; unusable and
  non-time-indexed equity curves; chronological streaks (helper level and end to end).
- `tests/test_backtest_engine.py` — a zero-initial-capital run.
- `tests/test_portfolio.py` — `Holding.market_value` for long, short, zero-cost and zero-quantity.

## Verified

- `pytest tests/ -q`: **1497 passed, 1 skipped** (was 1482 passed, 1 skipped).
- `ruff check quant_trading/ tests/`: clean.
- `mypy quant_trading/`: clean (36 source files).
- `black --check` on the five touched source/test files: clean. `tests/test_portfolio.py` and
  `quant_trading/strategies/examples.py` were already not black-clean before this change; those
  pre-existing hunks were deliberately left alone.
- `python examples/run_backtest_offline.py`, `python examples/run_analysis.py` and
  `python examples/cli.py --offline --trade-analysis --symbols AAPL --days 120` all run clean.
  The CLI now prints a non-zero `Expectancy` for the all-winning case, which is the fix in (1).

## Behaviour changes to be aware of

- The trade-level Sharpe/Sortino now include the risk-free adjustment, so their values change.
  On `examples/run_analysis.py` the trade Sharpe went from `3.97` to `-51.79`. That is expected:
  the strategy earns about `$0.57` per trade on a `$100k` account while the per-period
  risk-free return on that account is about `$7.96`, so the risk-free-adjusted trade Sharpe is
  strongly negative. The magnitude is also inflated by the pre-existing convention of annualizing
  trade statistics by `sqrt(periods_per_year)` (252) even though that example only takes ~43
  trades a year. The equity-based Sharpe (`result.metrics.sharpe_ratio`) is unchanged.
- `TradeAnalysis.profit_factor` is still `0.0` when there are no losing trades. That matches the
  documented convention of `BacktestMetrics.profit_factor` ("0.0 if no losers", `metrics.py:58`)
  and was left alone on purpose — unlike the expectancy, it is a stated convention rather than a
  wrong formula.

## Next task

**Thread the configured risk-free rate through the paths that still hardcode `0.02`.**

Evidence (all four are literal `risk_free_rate=0.02` arguments):

- `quant_trading/risk/manager.py:294` — `RiskManager.calculate_metrics` hardcodes `0.02` and
  `RiskManager.__init__` takes no `risk_free_rate` at all, so the class cannot honour the
  configured rate.
- `quant_trading/optimization/walk_forward.py:713` — the walk-forward optimizer calls
  `calculate_backtest_metrics(..., risk_free_rate=0.02, ...)` even though `BacktestConfig` has a
  user-configurable `risk_free_rate` (documented in the README under `backtest:`).
- `quant_trading/monte_carlo/simulator.py:401` and `:451` — same hardcoded `0.02` in the
  Monte Carlo simulator.

`BacktestEngine.run` already passes `self.config.risk_free_rate` (`engine.py:471`), so the
inconsistency is that the optimizer, the simulator and the risk manager do not.

Constraints and suggested approach:

- Keep the change additive and backwards compatible: add an optional `risk_free_rate` parameter
  with the current `0.02` default to `RiskManager.__init__` / `RiskManager.calculate_metrics`,
  the walk-forward optimizer and the Monte Carlo simulator, and pass the configured value
  through. Defaults preserve today's behaviour for callers that do not pass one.
- Do not change the engine's existing wiring.
- Verify with `pytest tests/ -q`, `ruff check quant_trading/ tests/`, `mypy quant_trading/`, and
  a short `python examples/cli.py --offline ...` run. Add a test per module showing that a
  non-default rate reaches the computed Sharpe/Sortino.

Useful context for later, if time allows: `Rebalancer.generate_rebalance_actions` ignores sell
signals for symbols held short (`quant_trading/portfolio/rebalancer.py:420-432` requires
`holding.quantity > 0`), even though `execute_actions` → `Portfolio.remove_holding` can cover a
short. Verified: a portfolio holding `-50` AAPL and a sell signal for AAPL produces **no**
rebalance action, while the docstring says sell signals "liquidate the full holdings of the
signaled symbol".
