# Next Task

## What changed

`BacktestMetrics` and `TradeAnalysis` now count the same trades. The trade log rules that decide
which rows of the raw trade log are trades moved into one place,
`quant_trading/backtest/trade_log.py`, and both public APIs use it.

1. **New module `quant_trading/backtest/trade_log.py`** (46 statements, 100% covered)

   `split_trade_log(trades) -> TradeLog` splits a trade log into `entries` (every row, with the PnL
   of a short entry folded into the cover that closes it) and `round_trips` (one row per completed
   round trip). It carries the short pairing that used to live inline in `analyze_trades()`:
   short entries and covers are matched FIFO per symbol, the entry's PnL is folded into the cover,
   and the short entry row is dropped.

2. **`quant_trading/backtest/trade_analysis.py`** — `analyze_trades()` now calls `split_trade_log()`
   instead of pairing the shorts inline. No behaviour change; the logic moved verbatim.

3. **`quant_trading/backtest/metrics.py`** — `calculate_backtest_metrics()` now computes
   `num_trades`, `num_winning_trades`, `num_losing_trades`, `win_rate`, `avg_win`, `avg_loss`,
   `largest_win`, `largest_loss` and `profit_factor` from `split_trade_log(trades).round_trips`
   instead of from `trades[trades["pnl"] != 0]`. **This changes published numbers for every backtest
   that shorts**: a short entry used to be counted as its own losing trade. The docstrings of
   `num_trades`, `num_winning_trades`, `num_losing_trades`, `win_rate` and of
   `calculate_backtest_metrics()` were updated to say "completed round trip".

4. **`quant_trading/risk/metrics.py`** — two type annotations only (`cleaned: pd.Series`,
   `aligned: pd.DataFrame`). They fix two `no-any-return` errors that mypy 2.4.0 reports in this
   environment; the errors are pre-existing (they reproduce on a pristine `HEAD` checkout), and the
   change is annotation-only, so the behaviour is unchanged.

## What was actually verified

- Full suite: `python3 -m pytest --cov=quant_trading --cov-report=json:/tmp/cov.json -q`
  -> **1860 passed, 1 skipped** (was 1842 passed, 1 skipped; 18 new tests).
- Coverage from the same run: **100.0%** (5040/5040 statements, 0 missing branches, no module below
  100%). The new module is at 100% too.
- `python3 -m ruff check quant_trading tests examples` -> All checks passed.
- `python3 -m black --check quant_trading tests examples` -> 91 files unchanged.
- `python3 -m mypy quant_trading` -> Success: no issues found in 37 source files (36 before).
- The agreement itself was reproduced with the real engine (scripted long and short round trips):
  before the change a winning short round trip reported `metrics.num_trades = 2` /
  `win_rate = 0.5` against `analysis.total_trades = 1` / `win_rate = 1.0`; after the change both
  report `1` and `1.0`. The numbers are in `tests/test_trade_log.py`.

## What remains unresolved

- **A round trip that closes at exactly zero PnL is still not a trade.** Both APIs drop it, because
  the round trips are still identified by "the row's PnL is not zero" rather than by pairing an
  entry with the close that ends it. See the next task below.
- `TradeAnalysis.total_pnl` is the sum over the completed round trips only. An **open short at the
  end of a run books its entry fee in the trade log but the analysis drops it**, so
  `analysis.total_pnl` (0.0) disagrees with `sum(result.trades["pnl"])` (-15.0) for a run that ends
  with an open short. Reproduce with the snippet in the next task.
- `BacktestMetrics.avg_loss` is the (negative) mean PnL of the losing trades, while
  `TradeAnalysis.avg_loss` is the same value as a positive magnitude. The two APIs therefore report
  opposite signs for the same number. It is documented in both places, so it was left alone here.
- `quant_trading/data/providers.py` and `quant_trading/data/synthetic.py` are at 100% only because
  the offline provider tests are in the suite. The network-gated branches are untestable offline.

## Approaches that already failed

- `python -m pytest --cov=quant_trading.data.providers` (a narrow `--cov` target) fails with
  `ImportError: cannot load module more than once per process` from numpy/pandas under coverage's
  import hook. **Do not retry the narrow `--cov` target.** Measure coverage with the package-wide
  `--cov=quant_trading` instead. (`python -m coverage run -m pytest ...` fails the same way.)
- The environment ships no dependencies: `pandas`, `numpy`, `pytest`, `pytest-cov`, `black`, `ruff`,
  `mypy`, `pandas-stubs`, `yfinance` and `scikit-optimize` have to be installed before the suite
  runs. Without `yfinance` and `scikit-optimize`, 31 tests fail on import errors.
- Running `mypy<2` in a fresh virtualenv fails with `Type statement is only supported in Python 3.12
  and greater` from the numpy stubs, because `pyproject.toml` pins `python_version = "3.10"`. Use
  the installed `mypy` (2.4.0) instead.

## Next task

Identify the round trips by pairing the entries with the closes that end them, instead of by
"the PnL of the row is not zero", so that a round trip that closes at exactly zero PnL is counted
as a trade.

Evidence (reproduce with the snippet below):

    breakeven round trip -> metrics.num_trades = 0  win_rate = 0

    trades = pd.DataFrame({
        "symbol": ["AAPL", "AAPL"],
        "action": ["buy", "sell"],
        "quantity": [10.0, 10.0],
        "price": [100.0, 100.0],
        "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        "pnl": [0.0, 0.0],
    })
    equity = pd.Series([100000.0, 100000.0], index=pd.to_datetime(["2024-01-01", "2024-01-02"]))
    calculate_backtest_metrics(equity, trades).num_trades   # -> 0, should be 1

A backtest that opened a position and closed it at the same price reports **zero trades**. The
symptom is the same on both sides: `split_trade_log()` in `quant_trading/backtest/trade_log.py`
keeps `round_trips = frame[frame["pnl"] != 0]`, so the round trip is only recognised by its PnL
happening to be non-zero. The mirror image of the same rule is that a closing row that closes
nothing (a sell without an open entry, pnl 55.0) counts as a trade today.

The fix belongs in `split_trade_log()`: pair the long entries with the sells that close them, FIFO
per symbol, the way `_calculate_holding_periods()` in `quant_trading/backtest/trade_analysis.py`
already does. A closing row that closes part of an open entry is a round trip (its PnL is already
the PnL of the closed portion); a closing row that closes nothing is not. The long entry rows are
then dropped by construction, and the `pnl != 0` filter can go.

Constraints:

- Keep the change inside `quant_trading/backtest/trade_log.py` plus its tests; both public APIs
  pick it up through `split_trade_log()` and must keep agreeing.
- This changes published numbers again: round trips that closed at exactly zero PnL are counted
  from now on, and a breakeven round trip is neither winning nor losing, so it raises
  `num_trades` without raising `num_winning_trades` (the win rate of a single breakeven trade is
  0.0). Check the existing expectations in `tests/test_backtest_metrics.py`,
  `tests/test_trade_analysis.py` and `tests/test_backtest_engine.py` before changing anything and
  update them deliberately.
- A partial close (a sell that closes part of a position) counts as one trade today and must keep
  counting as one.
- Keep the package at 100% statement and branch coverage, and re-run `pytest --cov=quant_trading`
  (package-wide target only), ruff, black and mypy.
