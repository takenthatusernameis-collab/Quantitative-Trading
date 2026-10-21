# Next Task

## What changed

The previous session's assignment (identify the round trips by pairing the entries with the
closes that end them) was already implemented in `ef83eaa` and is verified here. This session
finished the work that was still open on that change and closed the sign inconsistency that the
two public APIs had been carrying since the trade log moved into its own module.

1. **`quant_trading/backtest/trade_analysis.py`** — one sign convention for the loss figures.
   `TradeAnalysis.avg_loss` is now the **signed** mean PnL of the losing trades (negative), like
   `TradeAnalysis.largest_loss` and like `BacktestMetrics.avg_loss`. It used to be the same
   number as a positive magnitude, so the same quantity was reported with two signs in three
   places: `BacktestMetrics.avg_loss` was negative, `TradeAnalysis.avg_loss` was positive, and
   `TradeAnalysis.symbol_stats[<symbol>]["avg_loss"]` was negative again. The printed report
   showed "Avg Loss: $50.00" at the top and "Avg Loss $-50.00" in the per-symbol table of the
   same run. The expectancy formula follows the sign: it is now
   `win_rate * avg_win + (1 - win_rate) * avg_loss` instead of
   `win_rate * avg_win - (1 - win_rate) * avg_loss`, which leaves the expectancy value unchanged
   (25.0 in the example below) and makes it the plain win-rate weighted average of the trade
   PnLs. The docstrings of `TradeAnalysis.avg_loss`, `analyze_trades()` and
   `_calculate_symbol_stats()` state the convention.

2. **`quant_trading/backtest/metrics.py`** — docstring only: `avg_loss` now says that it is
   negative. The value was already signed; it was the analysis that disagreed with it.

3. **`quant_trading/backtest/trade_log.py`** — the `short_rows` set that the pairing change
   left behind is gone (it was written but never read, the short rows are dropped by
   construction now), and the docstrings of `TradeLog.round_trips` and `split_trade_log()` say
   that a round trip is recognized by the row that closes it and not by the PnL that row booked.

4. **`tests/test_trade_log.py`** — two new tests: the two public APIs must report the same
   `avg_win` and `avg_loss` (they did not before), and the loss figures must be signed in the
   top level, the per-symbol stats and the metrics at the same time. A third test asserts that
   the per-symbol figures of a one-symbol run agree with the top level figures.

## What was actually verified

- Full suite: `python3 -m pytest --cov=quant_trading --cov-report=json:/tmp/cov.json -q`
  -> **1865 passed, 1 skipped** (was 1863 passed, 1 skipped; 2 new tests).
- Coverage from the same run: **100.0%** (5060/5060 statements, 1702/1702 branches, no module
  below 100%).
- `python3 -m ruff check quant_trading tests examples` -> All checks passed.
- `python3 -m black --check quant_trading tests examples` -> 91 files unchanged.
- `python3 -m mypy quant_trading` -> Success: no issues found in 37 source files.
- The agreement itself was reproduced with the real code (one winning and one losing long round
  trip):

      metrics.avg_loss  = -50.0 | analysis.avg_loss = -50.0 | symbol avg_loss = -50.0
      largest_loss: -50.0 -50.0 -50.0
      expectancy: 25.0 (win_rate*avg_win + (1-win_rate)*avg_loss = 25.0)

  and the report now shows "Avg Loss: $-50.00" next to "Largest Loss: $-50.00" and the
  per-symbol "Avg Loss $-50.00".

## What remains unresolved

- **`TradeAnalysis.total_pnl` does not reconcile with the PnL the engine booked.** This is the
  next task below.
- **`split_trade_log()` counts the fee of a short entry twice inside `entries`.** The fold of
  the entry fee into the cover is applied to the `entries` frame, and the short row keeps its
  own fee, so `log.entries["pnl"].sum()` is not the sum of the log. This is part of the next
  task as well, because the fix for `total_pnl` needs the raw sum.
- `quant_trading/data/providers.py` and `quant_trading/data/synthetic.py` are at 100% only
  because the offline provider tests are in the suite. The network-gated branches are untestable
  offline.
- The trade log still assumes that a long entry books no PnL. The engine books the fee of a
  long in the cash balance and not on the buy row, so this holds for every log the engine
  writes, but a log that books a fee on the buy row would lose it: the long side does not fold
  the entry PnL into the closing row the way the short side does.

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

Make `TradeAnalysis.total_pnl` the PnL the run actually booked, so that it reconciles with the
engine and with the equity curve.

Evidence (reproduce with the snippet below):

    a run that ends with an open short
    sum(result.trades["pnl"])  = -15.0     <- the fee the engine booked
    analysis.total_pnl          =   0.0     <- what the analysis reports
    analysis.total_trades       =   0      <- and the whole analysis is empty

    from datetime import datetime
    import pandas as pd
    from quant_trading.backtest.engine import BacktestResult
    from quant_trading.backtest.metrics import BacktestMetrics
    from quant_trading.backtest.trade_analysis import analyze_trades

    trades = pd.DataFrame({
        "symbol": ["AAPL"], "action": ["short"], "quantity": [10.0], "price": [100.0],
        "timestamp": pd.to_datetime(["2024-01-01"]), "pnl": [-15.0]})
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    equity = pd.Series([100000.0 + step * 10.0 for step in range(10)], index=dates)
    result = BacktestResult(
        equity_curve=equity, trades=trades, positions={}, metrics=BacktestMetrics(),
        start_date=datetime(2024, 1, 1), end_date=datetime(2024, 1, 10),
        initial_capital=100000.0, final_value=100090.0, total_return=90.0, total_return_pct=0.09)
    print(float(result.trades["pnl"].sum()), analyze_trades(result).total_pnl)

The engine books the entry fee of a short on the short row itself
(`quant_trading/backtest/engine.py`, `_open_short`), and its own accounting invariant is
`final_value - initial_capital == sum(trades["pnl"]) + unrealized_pnl`
(`tests/test_cost_accounting_invariants.py`). `analyze_trades()` sums the PnL of the completed
round trips only, so the PnL that is booked on a position that is still open at the end of the
run is dropped: the analysis reports "Total PnL: $0.00" for a run that lost $15. The docstring
of `total_pnl` ("Sum of all trade PnL") is not true today either.

The fix has two halves, and the second one is what the PnL of an open position needs:

1. **The fold of the short fee must leave the `entries` frame alone.** `split_trade_log()` folds
   the entry fee into the cover row *in `entries`*, while the short row keeps its own fee, so
   the fee is counted twice in the entries sum:

       raw log pnl sum = 85.0
       entries pnl      = [-15.0, 85.0]  sum = 70.0
       round_trips pnl  = [85.0]          sum = 85.0

   Fold the fee into the round trips only, so that `entries` stays the raw log and
   `log.entries["pnl"].sum() == result.trades["pnl"].sum()`. `tests/test_trade_log.py` asserts
   the folded PnL in `entries` in two places (`test_short_entry_is_folded_into_the_cover_that_closes_it`
   and `test_partial_cover_folds_the_matching_share_of_the_entry_fee`); update them deliberately.

2. **`analyze_trades()` must report the PnL of the positions that are still open.** The PnL of
   an open position is the entry fee of a short that was never covered (a long entry books no
   PnL). It has to be attributed somewhere, so that the per-symbol figures keep summing up to
   the top level figure. The recommended shape: `total_pnl` becomes the PnL of the whole log
   (the run's realized PnL, equal to `sum(result.trades["pnl"])`), the per-symbol
   `total_pnl` values sum up to it, and the per-trade statistics (counts, win rate, averages,
   streaks, per-symbol trade counts) stay over the completed round trips. A separate field for
   the PnL of the positions that are still open (a new `TradeAnalysis` field with the default
   `0.0`, and an entry in `to_dict()`) makes the difference visible instead of hiding it.
   `analyze_trades()` must also stop returning an all-zero analysis when the log books PnL but
   has no completed round trip.

Constraints:

- Keep the change inside `quant_trading/backtest/trade_log.py` and
  `quant_trading/backtest/trade_analysis.py` plus their tests. `BacktestMetrics` does not
  carry a `total_pnl`, so it is not affected.
- The target invariant is executable and should be tested: for every backtest result,
  `analysis.total_pnl == float(result.trades["pnl"].sum())`, and the per-symbol `total_pnl`
  values sum up to `analysis.total_pnl`. The trade level statistics must not change: the number
  of trades, the win rate and the per-trade averages stay over the completed round trips.
- Check the existing expectations in `tests/test_trade_analysis.py` (the `total_pnl`
  assertions at the top of the file and around lines 988-1078) before changing anything, and
  update them deliberately.
- A run that is fully liquidated must keep reporting exactly the PnL it reports today, and the
  engine invariant `final_value - initial_capital == sum(trades["pnl"])` must keep holding for
  those runs.
- Keep the package at 100% statement and branch coverage, and re-run `pytest --cov=quant_trading`
  (package-wide target only), ruff, black and mypy.
