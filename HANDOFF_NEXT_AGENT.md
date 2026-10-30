# Handoff for Next Agent

## 1. What changed
- Working tree has ONE uncommitted change in `quant_trading/strategies/examples.py` (RSIStrategy). Committed HEAD (2a6a0df) already added incremental state to `MovingAverageCrossover.generate_signals` and `RSIStrategy.generate_signals`; working tree is otherwise clean.
- Fixed `RSIStrategy.generate_signals` incremental path: the previous version used Wilder's recursion `(avg*(period-1)+x)/period`, which DIVERGED from `_calculate_rsi`'s rolling mean (22 trades vs 55, $104,600 vs $109,826 on the offline example). State now stores the last `period` gains/losses with running sums (`gain_hist`, `loss_hist`, `gain_sum`, `loss_sum`), producing results identical to full recomputation.
- `_calculate_rsi` is retained (still used by the full-recompute/initialization branch and by StochRSIStrategy's own copy).

## 2. What was actually verified
- `python -m pytest -q`: 2470 passed, 55 skipped (unchanged baseline; includes test_backtest_engine.py 98 passed, test_strategies_examples.py).
- `examples/run_backtest_offline.py` output is byte-identical to the pre-optimization (parent commit, pure full-recompute) version for all three strategies + combined run (diffed /tmp/out_parent.txt vs /tmp/out_fixed.txt — IDENTICAL). MA was already identical; RSI now is too.
- cProfile before/after on `examples/run_backtest_offline.py` (4 engines x 365 days x 5 symbols):
  - Parent: 12.195s, 18.96M calls; RSI 5.37s cum, MA 1.42s cum.
  - Fixed: 5.727s, 9.13M calls; RSI 0.33s cum, MA 0.46s cum. (~2.1x wall speedup.)

## 3. What remains unresolved
- `BollingerBandsStrategy.generate_signals` still does full per-bar recomputation: 2.75s cum / ~2.8s in profile, unchanged by this session. Out of scope per "one strategy at a time" rule; it is the next dominant cost after MA and RSI.
- ~46 other strategies in examples.py still recompute indicators from scratch each bar (not profiled individually; none dominated the profile besides MA/RSI/BB).

## 4. Approaches that failed and why
- Wilder's recursion for incremental RSI: produces different RSI values than `_calculate_rsi`'s `rolling(window).mean()` (SMA of gains/losses), so backtest signals diverge. Replaced with exact rolling-window running sums over a retained history of the last `period` gains/losses.
- Per-symbol slice caching in the engine (extend `df.loc[:current_date]` by one row): rejected — measured slice cost ~0.07s total; no win.

## 5. One precise next task
- Make `BollingerBandsStrategy.generate_signals` (quant_trading/strategies/examples.py, class at line ~421) incremental: track per-symbol rolling sum and rolling sum of squares of `close` over `period` bars (Welford/count-based or running sums + deque of last `period` values) so mean and std are O(1) per bar, with full-recompute fallback when state is missing/stale (same pattern as MA/RSI).
- Verification requirements: (a) `examples/run_backtest_offline.py` output byte-identical to the pre-change version; (b) `python -m pytest -q` stays at 2470 passed / 55 skipped; (c) cProfile before/after showing BB cumtime drop and total wall time below 5.7s.
- Commit decision: leave uncommitted unless the user explicitly asks (repo rule: no commits without explicit request). The working tree currently contains the RSI fix uncommitted.
