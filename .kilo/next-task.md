# Next Task

## What changed

The assignment from the previous session was to make `TradeAnalysis.total_pnl` the PnL the run
actually booked, so that it reconciles with the engine and with the equity curve. Both halves of
it are done, and the invariant is now executable and checked against real engine runs.

1. **`quant_trading/backtest/trade_log.py`** — the entries are the raw log again.
   `TradeLog.entries` used to carry the PnL of a short entry folded into the cover that closed it
   *and* the fee on the short row itself, so the fee was counted twice inside the entries
   (`entries["pnl"].sum()` was 70.0 where the log booked 85.0). The fold now happens in the round
   trips only: `entries` is the log the run wrote, `round_trips` carries the PnL of the whole
   round trip, and `log.entries["pnl"].sum() == float(trades["pnl"].sum())` holds.

   `TradeLog` grew a third field, `open_pnl` (default `0.0`): the PnL the positions that are
   still open at the end of the run booked. It is the entry fee of the shorts that were never
   (fully) covered — a long entry books no PnL, so a long contributes 0.0. A partially covered
   short contributes the share of its fee that was never covered (6 of 10 shares of a -15.0 fee
   is -9.0).

2. **`quant_trading/backtest/trade_analysis.py`** — `total_pnl` is the PnL of the whole log.
   It used to be the sum of the PnL of the completed round trips, so a run that ended with an
   open short reported "Total PnL: $0.00" for a run that lost money. It is now
   `float(log.entries["pnl"].sum())`, which is exactly `sum(result.trades["pnl"])` and therefore
   the PnL the engine booked. The trade level statistics (the counts, the win rate, the averages,
   the streaks) are unchanged: they are still computed over the completed round trips only.

   The new field `TradeAnalysis.open_position_pnl` (default `0.0`, also in `to_dict()`) makes the
   difference visible instead of hiding it: `total_pnl` is the PnL of the run, `open_position_pnl`
   is the part of it that belongs to a position that is still open. `print_trade_analysis()` prints
   it as "Open Position PnL".

   `analyze_trades()` no longer returns an all-zero analysis when the log books PnL but has no
   completed round trip; it reports the PnL of the run, the PnL of the open positions and the per
   symbol figures. `_calculate_symbol_stats()` takes the round trips *and* the entries now: the
   trade level figures of a symbol come from its round trips, its PnL comes from the whole log, so
   the per symbol PnL adds up to the PnL of the run. A log without a `symbol` column no longer
   raises a `KeyError` there; it reports no per symbol figures.

3. **Tests** — `tests/test_trade_log.py` asserts the new trade log behaviour (the entries are the
   raw log, the open PnL of a short that was never covered, the open share of a partially covered
   short) and adds a `TestAnalysisReconcilesWithTheRun` class with the invariant
   `analysis.total_pnl == float(result.trades["pnl"].sum())` and the per symbol sum.
   `tests/test_trade_analysis.py` updates the expectations that the change makes wrong
   (`test_short_never_covered_is_not_counted` now expects `total_pnl == -5.0` and
   `open_position_pnl == -5.0`) and the changed signature of `_calculate_symbol_stats()`.
   `tests/test_cost_accounting_invariants.py` runs the reconciliation against **real engine runs**:
   every seeded scenario (full round trips, partial exits, added positions, several symbols, a
   short that is never covered) now asserts that the analysis reports the PnL the run booked and
   that the PnL of the symbols adds up to it.

## What was actually verified

- Full suite: `python3 -m pytest --cov=quant_trading --cov-report=json:/tmp/cov.json -q`
  -> **1876 passed, 1 skipped** (was 1865 passed, 1 skipped; 11 new test cases).
- Coverage from the same run: **100.0%** (5066/5066 statements, 1700/1700 branches, no module
  below 100%).
- `python3 -m ruff check quant_trading tests examples` -> All checks passed.
- `python3 -m black --check quant_trading tests examples` -> 91 files unchanged.
- `python3 -m mypy quant_trading` -> Success: no issues found in 37 source files.
- The reconciliation reproduced with the real engine (a scripted run of the mock provider in
  `tests/test_cost_accounting_invariants.py`):

      open short run:   sum(trades["pnl"]) = -1.5   analysis.total_pnl = -1.5
                        open_position_pnl  = -1.5   per symbol       = -1.5
                        final - initial    = -849.52 = -1.5 realized + -848.02 unrealized
      liquidated run:   sum(trades["pnl"]) = -301.77 = analysis.total_pnl = final - initial
                        open_position_pnl  = 0.0

  and the trade log itself now adds up: for a short of 10 shares with a -15.0 fee that is covered
  for 4 shares, `entries` = [-15.0, 100.0] (sum 85.0), `round_trips` = [94.0] and `open_pnl` =
  -9.0, so 94.0 - 9.0 = 85.0.

## What remains unresolved

- **The long side does not fold the entry PnL into the closing row.** The engine books the fee of
  a long in the cash balance and not on the buy row, so every log the engine writes is fine, and
  the top level `total_pnl` is now right in any case (it is the raw log sum). But a log that
  books a fee on the buy row would report a round trip PnL that misses that fee, so the trade
  level figures (avg win/loss, profit factor) would be off. The short side folds its entry PnL
  into the cover; the long side does not.
- **`BacktestMetrics` still carries no `total_pnl`**, so the two public APIs cannot be compared on
  the PnL of the run (they can be compared on the trade figures, which the previous session fixed).
- `quant_trading/data/providers.py` and `quant_trading/data/synthetic.py` are at 100% only
  because the offline provider tests are in the suite. The network-gated branches are untestable
  offline.
- `analyze_trades()` reports the realized PnL of the run. The unrealized PnL of the positions that
  are still open is not part of it (the engine books it in the portfolio value, not in the trade
  log), and the analysis has no access to the positions, so it cannot report it.

## Approaches that already failed

- `python -m pytest --cov=quant_trading.data.providers` (a narrow `--cov` target) fails with
  `ImportError: cannot load module more than once per process` from numpy/pandas under coverage's
  import hook. **Do not retry the narrow `--cov` target.** Measure coverage with the package-wide
  `--cov=quant_trading` instead. (`python -m coverage run -m pytest ...` fails the same way.)
- The environment ships no dependencies: `pandas`, `numpy`, `pytest`, `pytest-cov`, `black`,
  `ruff`, `mypy`, `pandas-stubs`, `yfinance` and `scikit-optimize` have to be installed before
  the suite runs. Without `yfinance` and `scikit-optimize`, 31 tests fail on import errors.
- Running `mypy<2` in a fresh virtualenv fails with `Type statement is only supported in Python 3.12
  and greater` from the numpy stubs, because `pyproject.toml` pins `python_version = "3.10"`. Use
  the installed `mypy` (2.4.0) instead.

## Next task

Give `BacktestMetrics` the PnL of the run, so that the two public APIs report the same realized
PnL and the reconciliation can be checked from either side.

Evidence (the two APIs disagree today because only one of them has the figure at all):

    from quant_trading.backtest.metrics import calculate_backtest_metrics
    from quant_trading.backtest.trade_analysis import analyze_trades

    metrics = calculate_backtest_metrics(result.equity_curve, result.trades)
    analysis = analyze_trades(result)

    float(result.trades["pnl"].sum())  = -15.0   <- the PnL the engine booked
    analysis.total_pnl                 = -15.0   <- the analysis knows it
    metrics.total_pnl                  = ???     <- the metrics have no such field

The shape to use, following the pattern the previous session established for `avg_win` and
`avg_loss` (the two APIs have to report the same number):

1. **`BacktestMetrics` gets a `total_pnl` field** (default `0.0`, plus an entry in
   `to_dict()`), holding the realized PnL of the run: the sum of the PnL of the trade log, which
   is `split_trade_log(trades).entries["pnl"].sum()`. It is the PnL of the run, so it is
   *not* the same as `total_return` (which is the change in portfolio value and therefore
   includes the unrealized PnL of the positions that are still open). The docstring has to say
   that.
2. **The two APIs have to agree.** `metrics.total_pnl == analysis.total_pnl` for every log, and
   the per symbol PnL has to add up to it. Assert that in the `TestMetricsAndAnalysisAgree`
   class in `tests/test_trade_log.py` (the same place the previous session asserted the
   agreement on `avg_win`/`avg_loss`), and in the seeded engine scenarios of
   `tests/test_cost_accounting_invariants.py`.
3. The trade level figures of `BacktestMetrics` stay as they are (the number of round trips, the
   win rate, the averages); only the PnL of the run is added.

Constraints:

- Keep the change inside `quant_trading/backtest/metrics.py` plus its tests. `TradeAnalysis` and
  `split_trade_log()` are already in the state this task needs, so they should not have to change
  (except for a docstring that mentions the new field).
- The engine invariant `final_value - initial_capital == sum(trades["pnl"]) + unrealized_pnl`
  (`tests/test_cost_accounting_invariants.py`) must keep holding, and
  `metrics.total_pnl` must be the realized part of it.
- A run that is fully liquidated must keep reporting the PnL it reports today, and
  `metrics.total_pnl` must then equal `metrics.total_return`.
- Keep the package at 100% statement and branch coverage, and re-run `pytest --cov=quant_trading`
  (package-wide target only), ruff, black and mypy.
