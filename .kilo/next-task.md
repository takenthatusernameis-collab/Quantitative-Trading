# Next Task

## What changed

Closed the last three statement/branch coverage gaps in the package. `quant_trading` is now at
**100% statement and branch coverage overall** (5019/5019 statements, 0 missing branches) — it was
99.66% at the start of this session.

Three modules were closed, with one small behavioural fix and one small reordering:

1. `quant_trading/backtest/trade_analysis.py` (97% -> 100%)

   Five uncovered spots were closed, and one of them turned out to be a **latent crash**:

   - `_calculate_holding_periods()` read `trade["action"]` unguarded, so `analyze_trades()` raised
     `KeyError: 'action'` for a result whose trades frame has no `action` column. The helper now
     returns `[]` when the frame carries no `action` column (no entries/exits to pair -> no round
     trips -> no holding periods). This is the one source change in this file.
   - Added tests for: streaks counted on trades without a `timestamp` column (243->246), an
     unmatchable trade timestamp yielding NaN instead of raising (399-400), `_calculate_trade_returns`
     returning empty for trades without a timestamp (425), a short's entry fee being folded into the
     cover that closes it (505), and `analyze_trades()` on an `action`-less trades frame (515).

2. `quant_trading/regime/detector.py` (97.6% -> 100%) — two defensive branches of the private
   `_make_segment()`: a one-bar segment on the very first price bar (no predecessor -> 0.0% return)
   and a segment spanning no labeled bar (0.0% return). No source change.

3. `quant_trading/strategies/examples.py` (99% -> 100%) — the `MovingAverageCrossover` NaN-last-close
   guard could never fire: the moving-average NaN check always fired first, because a NaN in the last
   close propagates into both moving averages. The price check was moved **above** the moving-average
   computation, so the price the signal is emitted at is validated first. Behaviour is unchanged (the
   symbol is skipped either way). Tests were added for the moved guard, for the previous moving
   average being undefined, for a golden/death cross on a zero slow MA (the 0.5 strength fallback),
   for one-bar windows (the `len(fast_ma) < 2` guard), and for the RSI strategy on a flat series
   (undefined RSI).

## What was actually verified

- Full suite: `python -m pytest --cov=quant_trading --cov-report=json:/tmp/cov.json -q`
  -> **1842 passed, 1 skipped** (was 1829 passed, 1 skipped; 13 new tests).
- Coverage from the same run: **0 modules below 100%**, `TOTAL: 100.0` (5019 covered lines of 5019
  statements, 0 missing branches). Before this session: `trade_analysis.py` 97.44%,
  `regime/detector.py` 97.58%, `strategies/examples.py` 99.03%.
- `python -m ruff check quant_trading tests examples` -> All checks passed.
- `python -m black --check quant_trading tests examples` -> 89 files unchanged.
- `python -m mypy quant_trading` -> Success: no issues found in 36 source files.

## What remains unresolved

- `BacktestMetrics` and `TradeAnalysis` disagree about how many trades a backtest made (see the
  next task). This is a real, unfixed defect, not a coverage gap.
- `quant_trading/backtest/trade_analysis.py` still counts a *closing* trade with exactly zero PnL as
  "not a trade" (`pnl_trades = trades[trades["pnl"] != 0]`), so a breakeven round trip is dropped
  from `total_trades` and `win_rate`. Same filter in `calculate_backtest_metrics()`. Left alone here
  because fixing it changes published numbers.
- `quant_trading/data/providers.py` and `quant_trading/data/synthetic.py` are at 100% under the full
  suite, but only because the offline provider tests are in the suite. The network-gated branches
  are untestable offline.

## Approaches that already failed

- `python -m pytest --cov=quant_trading.data.providers` (a narrow `--cov` target) fails with
  `ImportError: cannot load module more than once per process` from numpy/pandas under coverage's
  import hook. **Do not retry the narrow `--cov` target.** Measure coverage with the package-wide
  `--cov=quant_trading` instead: that works and gives the same per-file numbers.
  (`python -m coverage run -m pytest ...` fails the same way, for the same reason.)

## Next task

Make `BacktestMetrics` count the same trades as `TradeAnalysis`, so the two public APIs stop
disagreeing about a backtest's trade count and win rate.

Evidence (reproduce with the snippet below): the engine records one row per executed trade
(`engine.py` builds `trades_df` from `trades_list`), so a round trip contributes a buy row with
`pnl == 0` and a sell row with the realised PnL. `calculate_backtest_metrics()` counts **every row**
(`metrics.num_trades = len(trades)`), while `analyze_trades()` counts only the rows with a non-zero
PnL (`trades[trades["pnl"] != 0]`). For a backtest with one winning and one losing round trip:

    calculate_backtest_metrics(...).num_trades -> 4     win_rate -> 0.25   # 2 opening rows counted
    analyze_trades(...).total_trades        -> 2     win_rate -> 0.5    # the correct answer

`num_trades`, `num_winning_trades`, `num_losing_trades` and `win_rate` in `BacktestMetrics` should be
computed from the same filtered trades `analyze_trades()` uses, so the two agree for the same result.

Constraints: keep the change small and reversible; `BacktestMetrics` is public API, so
`num_trades`/`win_rate` semantics change and the docstrings in `quant_trading/backtest/metrics.py`
(attributes `num_trades`, `win_rate`, and the `calculate_backtest_metrics` docstring) must be updated
to match. Check the existing expectations in `tests/test_backtest_metrics.py` and
`tests/test_integration.py` before changing anything — some of them may encode the current
count-every-row behaviour and will need to be updated deliberately, not silently. Add a regression
test that asserts the two APIs agree on the same trades frame, then re-run
`pytest --cov=quant_trading` (package-wide target only), ruff, black and mypy.
