# Next Task

## What changed

Fixed a real engine defect: a `"short"` signal that arrived while a long position
was held was booked as a *short* trade, while the portfolio turned it into a
*sale* of the long. The trade log and the portfolio disagreed (the log reported
a short position the portfolio never held) and the PnL of the run stopped
reconciling.

1. **`quant_trading/backtest/engine.py`** — `_process_signal()` now rejects a
   short signal while the symbol is held long: the long is left alone and no
   trade is recorded. This is the contract the README ("Short Selling": "`short`
   … It is rejected while a long position is held."), the `Signal` docstring and
   the risk manager already document. The risk manager rejects the same signal,
   and the engine now enforces the rule on its own as well, so it holds with
   the risk checks disabled too. The `_process_signal()` and `_open_short()`
   docstrings state the rule.
2. **`quant_trading/backtest/metrics.py`** — dropped the `if not log.entries.empty`
   guard around the realized PnL. The log always carries a row on that path (an
   empty log is not a run that traded), so the branch was dead and left
   `metrics.py` at 99% branch coverage.
3. **`tests/test_backtest_engine.py`** — `_run_script()` gained a `disable_risk`
   flag; the new `test_short_signal_against_an_open_long_is_rejected`
   (parametrized over risk enabled/disabled) asserts that the short is not
   traded, the long is untouched, the log agrees with the portfolio and the run
   still reconciles.
4. **`tests/test_cost_accounting_invariants.py`** —
   `_assert_analysis_reconciles()` now also asserts that the metrics the
   *engine* attached to the result (`result.metrics.total_pnl`) agree with
   `analyze_trades(result).total_pnl`; the new
   `test_randomized_short_against_an_open_long_invariants` (10 seeds) runs the
   buy-then-short scenario with the risk checks disabled and asserts the
   accounting identities.

## What was actually verified

- Reproduction before the fix: buy 3 units at 100, then a short signal at 110
  gave the trade log `[buy 3.0, short 6.36]`, a flat portfolio,
  `final_value - initial_capital = 29.055` while `sum(trades["pnl"]) = -1.05`
  and the unrealized PnL was 0 — the reconciliation broke, and the log's net
  quantity (-3.36) did not match the portfolio (0.0). After the fix the log
  holds only the buy, the long stays open, and
  `final_value - initial_capital == sum(trades["pnl"]) + unrealized` holds.
- The new engine test fails without the fix (`assert 2 == 1` — the log booked a
  `short` of 116.66 units) and passes with it. Verified by removing the guard,
  running the test, and restoring the guard.
- `python3 -m pytest -q` → **1896 passed, 1 skipped** (was 1884 + 1 before this
  change; 12 new tests).
- `python3 -m pytest -q --cov=quant_trading --cov-report=term-missing` → 100%
  statements and branches on every module (the dead `metrics.py` branch was
  the last one).
- `python3 -m ruff check quant_trading tests examples` → All checks passed.
- `python3 -m black --check quant_trading tests examples` → unchanged.
- `python3 -m mypy quant_trading` → no issues in 37 source files.

## What remains unresolved

- **The long side entry fee is still not folded.** `split_trade_log()` folds the
  entry fee of a *short* into the cover that closes it, but a long entry row is
  dropped without folding a fee that was booked on it. The engine never books a
  fee on a long entry row (the buy books `realized_pnl=0` and the fee is
  capitalized into `Holding.avg_cost`), so the asymmetry is not observable in
  engine logs today. Do not change it without a real engine case that needs it.
- **`total_return` vs `total_pnl`.** `metrics.total_pnl` is the realized PnL;
  `metrics.total_return` still includes the unrealized PnL of open positions.
  The two are equal only for a fully liquidated run.
- **The realized PnL is not surfaced in the CLI.** The `backtest` command of
  `examples/cli.py` prints `Total Return` (which mixes in the unrealized PnL)
  but never the realized `total_pnl`, so the new field is invisible to CLI
  users.
- **`Trade.pnl` documents itself inaccurately.** The property docstring says
  "This is 0.0 for opening trades", but a short entry is an opening trade that
  books `-entry_fee`; the `Trade.realized_pnl` attribute docstring is the
  correct one.
- **No built-in strategy emits a `"short"` signal**
  (`quant_trading/strategies/examples.py` has none), so the short path is only
  reachable through a user strategy — and the risk manager rejects a short
  against a long before the engine ever sees it, which is why the defect
  survived until the risk checks were disabled.
- **Coverage for the network-gated providers** is exercised through mocks
  only; the live paths cannot be checked offline.

## Approaches that already failed

- A first version of the regression test used `("buy", 1.0)` before the short
  signal. The long was then worth more than the short's target, so
  `_open_short()` returned early and the test passed even with the defect
  present. The buy has to be *smaller* than the short's target (`("buy", 0.3)`)
  for the corruption to show.
- Narrow `--cov` targets on submodules can fail under coverage import hooks in
  some environments — measure with the package-wide `--cov=quant_trading`.
- Missing deps in fresh envs (pandas/numpy/pytest/scikit-optimize/yfinance)
  cause import failures; install the full dev extras before running the suite.
- The coverage report of a run that pipes through `tail` can lose the table;
  redirect the run to a file and read the file instead.

## Next task

Make the documented decomposition of the PnL checkable from the public API:
`TradeAnalysis` reports `total_pnl` (the PnL of the whole log) and
`open_position_pnl` (the PnL of the positions that are still open) but never
the round-trip part, so `total_pnl == round_trip_pnl + open_position_pnl` can
only be derived indirectly (`avg_pnl * total_trades`).

Add a `round_trip_pnl` field to `TradeAnalysis`
(`quant_trading/backtest/trade_analysis.py`), computed as the sum of
`log.round_trips["pnl"]` next to the existing `total_pnl` /
`open_position_pnl` computation, include it in `to_dict()`, and assert the
identity in `tests/test_cost_accounting_invariants.py::_assert_analysis_reconciles()`
so every randomized scenario (round trips, partial exits, open shorts) checks
it. Constraints: additive only — do not change `split_trade_log()` and do not
change the numbers `BacktestMetrics` and `TradeAnalysis` report today; keep
`result.metrics.total_pnl == analyze_trades(result).total_pnl` holding; keep
coverage at 100%; run ruff, black, mypy and the full pytest.
