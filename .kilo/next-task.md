# Next Task

## What changed

Fixed three defects in the portfolio rebalancer
(`quant_trading/portfolio/rebalancer.py`) that made it plan trades at the
wrong size. The theme is *one price space*: the quantity of a trade, the
deviation it closes and the total value the target is derived from are now
all measured at the price the trade is planned at.

1. **A sell was sized at the holding's mark but executed at the prices map.**
   `_resolve_sell_quantity` derived the quantity from
   `holding.current_price` while `_plan_sell` booked the cash at
   `_resolve_execution_price`, so the trade released a different number of
   dollars than the deviation measured (a 2x error when the mark and the
   map disagreed). The quantity is now derived from the same price the trade
   is booked at, and the position is valued at that price as well, so the
   trade releases exactly the measured deviation and the position lands on
   its target.
2. **The targets and the threshold were measured in a different price space
   from the trades.** `calculate_target_values()` and the rebalance
   threshold used `portfolio.total_value` (marked with the holdings' stale
   marks) while the deviations were measured at the trade price. The total is
   now recomputed at the trade price (`_portfolio_value_at_prices`), and
   `calculate_target_values()` takes an optional `prices` argument for that.
3. **Two buy signals for the same symbol bought two slices.** The signal
   path read the symbol's current value from the portfolio, which the batch
   had not updated yet, so every signal added a fresh 5%-of-portfolio slice.
   The batch's own planned buys now count towards the current value, so a
   second signal tops the position up to its target instead. This matches
   what the backtest engine already does (`engine._open_long`).
4. **`set_target_allocation({...})` raised `ZeroDivisionError`** when the
   fractions summed to zero. It now raises a `ValueError` with a clear
   message; an empty allocation still clears the targets.

Also: `tests/test_rebalancer_sizing_invariants.py` (new, 22 tests) and two
fixtures in `tests/test_rebalancer.py` that were internally inconsistent
(they forced `portfolio.total_value` to a value the portfolio's cash and
positions did not add up to; they now set `portfolio.cash = 0.0` so the
portfolio is worth exactly $100,000).

## What was actually verified

- Full suite: `1817 passed, 1 skipped` (baseline before this change was
  `1795 passed, 1 skipped`).
- `quant_trading/portfolio/rebalancer.py` is back at **100%** statement and
  branch coverage; the package total is unchanged at 99%.
- `ruff check quant_trading tests examples` -> All checks passed.
  `black --check` -> 89 files unchanged. `mypy quant_trading` -> no issues.
- 14 of the 22 new tests fail against the pre-change rebalancer
  (verified by `git checkout -- quant_trading/portfolio/rebalancer.py` and
  re-running the new file), so they are genuine regression tests.
- The `scikit-optimize` dependency has to be installed for the Bayesian
  optimizer tests to pass (`pip install scikit-optimize`); it is an optional
  extra, and 11 tests fail with `ModuleNotFoundError` without it.

## What remains unresolved

These were found by an audit in this session, confirmed numerically, and
**not** fixed. They are in the risk layer, not the rebalancer:

- `RiskManager.calculate_metrics()` builds its equity series with a
  `RangeIndex` (`pd.Series(self.equity_curve)`) while a benchmark passed in
  is usually date-indexed. `calculate_all_metrics` aligns on the index, so
  `beta` and `alpha` come back as exactly `0.0` for every strategy. A
  positional fallback (or a date-indexed equity curve) would fix it.
- `calculate_returns()` divides by the previous value without guarding a
  zero: an equity curve that touches `0.0` produces `inf`/`NaN` volatility,
  Sortino, VaR and Calmar.
- `PortfolioLimit(max_drawdown=0.0)` is documented as "disables the limit"
  (README line 838) and `RiskManager._reject_signal_if_in_drawdown_breach`
  honours that, but `PortfolioLimit.check()` still reports a drawdown
  violation for any dip, so `RiskManager.check_portfolio()` disagrees with
  `check_signal()`.

## Approaches that already failed

- Auditing with a second, independent agent (backtest engine, metrics,
  analysis, trade analysis, Monte Carlo, regime detector, walk-forward)
  returned no findings at all. That line of work is not worth repeating as
  is; the risk manager / portfolio layer is where the confirmed defects
  were.
- A "recompute the total portfolio value inside the rebalancer" change was
  first tried with the mark-based `portfolio.total_value` kept for the
  targets. That mixes price spaces and broke
  `test_drawdown_breach_stops_buys_allows_sells`. Recomputing the total at
  the trade price is what makes the whole plan consistent.
- Making the whole batch land on its target in a randomised test is not a
  usable invariant: the buys are sized against the cash that is available
  at that point of the batch, so a buy that comes before its funding sell
  is legitimately reduced. The randomised tests assert the sizing invariant
  instead ("a trade never moves more than the deviation it closes").

## Next task

Fix the three open risk-metric defects above, in this order:

1. `quant_trading/risk/manager.py` `calculate_metrics()`: make the equity
   series and the benchmark comparable so `beta`/`alpha` are not silently
   `0.0`. Decide explicitly between a positional fallback and a
   date-indexed equity curve, document the choice, and add a regression test
   that asserts a non-zero beta for a benchmark that moves with the
   strategy.
2. `quant_trading/risk/metrics.py` `calculate_returns()`: guard a zero
   denominator so a wiped-out portfolio yields a finite metric set rather
   than `NaN`/`inf`.
3. `quant_trading/risk/limits.py` `PortfolioLimit.check()`: make
   `max_drawdown=0.0` disable the drawdown limit, matching the README and
   `RiskManager._reject_signal_if_in_drawdown_breach`.

Constraints: keep the change inside `quant_trading/risk/`, do not change the
public signatures of `calculate_all_metrics` or `calculate_returns`, keep
`quant_trading/risk/` at 100% coverage, and re-run the full suite plus
`ruff`, `black --check` and `mypy quant_trading` before committing.
