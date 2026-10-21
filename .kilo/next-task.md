# Next Task

## What changed

Fixed the walk-forward optimizer: the out-of-sample (test) periods of two windows
overlapped, so the combined out-of-sample result double-counted periods and was
not a valid time series.

1. **`quant_trading/optimization/walk_forward.py`**
   - `_generate_windows()` now divides `[start, end]` into `n_windows`
     sub-intervals of `window_days` days. Each sub-interval is split into a
     training span and a test span; the test span stops where the next
     window's training span begins, so **two consecutive out-of-sample
     periods never overlap**. Anchored mode keeps the training start fixed and
     expands the training end; rolling mode slides the training span forward.
   - `step_size` now defaults to `1.0` (was `train_size / n_windows` for
     anchored and `1 - train_size` for rolling). With one step per window the
     sub-intervals tile the requested period, so the walk-forward no longer
     leaves most of `[start, end]` untested. An explicit `step_size` is still
     honoured and is clamped by the same non-overlap rule.
   - `_combine_test_results()` now emits a **strictly increasing, duplicate-free**
     equity curve (a point that is not later than the last emitted one is
     skipped), and scales each window's trade-log `pnl` into the combined
     account's dollars with the same factor used for that window's equity
     curve, so `combined.metrics.total_pnl` is the chained realized PnL of the
     windows and agrees with `combined.final_value`.
2. **`tests/test_optimization.py`** — 7 new regression tests (6 test functions,
   two of them parametrized over anchored/rolling): out-of-sample periods do not
   overlap, the combined equity curve is a valid time series with every window
   bar present exactly once, the combined PnL is the chained realized PnL, the
   combined result can be analyzed by `analyze_trades`, and overlapping windows
   handed to `_combine_test_results` still produce a valid curve.
   `create_test_data()` gained an optional `end` argument so the new tests use
   fixed dates (default behaviour unchanged).

## What was actually verified

- Reproduction before the fix (`quant_trading/optimization/walk_forward.py`,
  5 windows, `train_size=0.7`, anchored): the out-of-sample periods of
  consecutive windows overlapped by 5 days, the walk-forward covered only
  2024-01-25..2024-02-21 of a 2024-01-01..2024-06-28 request, and the combined
  equity curve had a non-monotonic index with 4 backwards time steps and 32
  duplicate timestamps.
- After the fix: out-of-sample periods are disjoint and chronological, the
  combined equity curve is monotonic and unique, and the combined PnL equals
  the independently recomputed chained realized PnL.
- All 6 new test functions fail against the pre-fix implementation
  (`git checkout -- quant_trading/optimization/walk_forward.py`, 5 failed /
  1 failed) and pass with the fix.
- `python3 -m pytest -q` (full suite) -> **1893 passed, 1 skipped** (was 1886
  passed, 1 skipped before this change).
- `python3 -m ruff check quant_trading tests examples` -> All checks passed.
- `python3 -m black --check quant_trading tests examples` -> 91 files unchanged.
- `python3 -m mypy quant_trading` -> no issues found in 37 source files.
- End-to-end CLI run: `PYTHONPATH=. python3 examples/cli.py --walk-forward
  --offline --strategy ma --symbols AAPL --start 2023-01-01 --end 2024-01-01
  --wf-windows 3` now produces train/test spans that tile the requested year
  (test 2023-03-26..2023-05-02, 2023-07-25..2023-08-31, 2023-11-23..2023-12-30).

## What remains unresolved

- **Long side entry fee folding** (carried over): `split_trade_log()` folds a
  short entry fee into the covering row but not a long entry fee. The engine
  capitalizes long entry fees into `Holding.avg_cost` and books `0.0` realized
  PnL on a long entry, so the asymmetry is unreachable through the engine; it
  only shows up for hand-built trade logs. Not changed (no evidence of a real
  engine case).
- **`total_pnl` is realized, `total_return` includes unrealized PnL**: the
  engine invariant `final_value - initial_capital == sum(trades["pnl"]) +
  unrealized_pnl` still holds. `BacktestResult` exposes no explicit
  realized/unrealized split field; it is reachable through
  `result.metrics.total_pnl` and `result.positions`.
- **Network-gated providers** remain hard to cover offline.
- **The combined walk-forward trade log mixes units by design**: its `pnl`
  column is in the combined account's dollars, while `fee`/`cost` columns and
  `BacktestResult.total_costs` stay in each window's own capital base. This is
  documented in `_combine_test_results()`; scaling the cost columns as well
  would break the existing `test_walk_forward_combine_sums_window_costs`
  expectation (19.75) and was left alone deliberately.

## Approaches that already failed

- Narrow `--cov` targets on submodules can fail under coverage import hooks in
  some environments — measure with package-wide `--cov=quant_trading`.
- Missing deps in fresh envs (pandas/numpy/pytest/scikit-optimize/yfinance)
  cause import failures; the full dev deps are needed.
- `examples/cli.py` cannot be run as `python3 examples/cli.py`; it needs
  `PYTHONPATH=.` from the repository root.
- An earlier attempt asserted that consecutive out-of-sample periods are
  *contiguous* (`test_start == previous test_end`). That is wrong for a
  walk-forward: the in-sample span of a later fold sits between two
  out-of-sample spans. The correct invariant is "disjoint and chronological".

## Next task

**Thread `periods_per_year` through the regime entry points.**

Evidence: `RegimeDetector.__init__` accepts `periods_per_year`
(`quant_trading/regime/detector.py:304`) and uses it to annualize the rolling
volatility and rolling mean return
(`quant_trading/regime/detector.py:366-367`), but the module-level wrapper
`detect_regimes()` (`quant_trading/regime/detector.py:579`) does not expose
the parameter, and neither do `analyze_regimes()`
(`quant_trading/backtest/analysis.py:324`) nor `regime_for_backtest()`
(`quant_trading/backtest/analysis.py:386`). Every regime label is therefore
annualized at 252 periods, while the rest of the framework
(`BacktestConfig.periods_per_year` in `quant_trading/config/settings.py:139`,
backtest metrics, Monte Carlo, optimization) honours the configured frequency.
On weekly or hourly data the regime thresholds and the reported regime
volatility are wrong by the square root of the frequency ratio.

Bounded scope: add an optional `periods_per_year: int = 252` argument to
`detect_regimes()`, `analyze_regimes()` and `regime_for_backtest()`, pass it
through to `RegimeDetector`, keep the current defaults so existing callers and
tests are unaffected, and add tests that assert a non-daily `periods_per_year`
changes the annualized regime volatility/return thresholds (and that the
detector's labels follow).

Constraints: keep the existing public defaults; do not change the regime
labelling rules; run `python3 -m pytest -q`, `ruff`, `black --check` and
`mypy quant_trading` before handing off.
