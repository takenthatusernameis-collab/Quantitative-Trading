# Next Task

## What changed

**Trade analysis now counts short round trips as one trade, with correct holding
periods.** This was the task assigned by the previous handoff; it is finished and
verified below.

The remaining defect after the previous session's short/cover pairing was in
`quant_trading/backtest/trade_analysis.py`: `analyze_trades` folds a short
entry's fee PnL into its cover and then *drops* the short entry row, but
`_calculate_holding_periods(trades)` was called *after* that drop, so every
short round trip had no entry to match against and reported a 0-day holding
period. Holding periods are now computed *before* the short entry rows are
dropped (long entries are never dropped, so long behaviour is unchanged).

`quant_trading/backtest/trade_analysis.py`:
- `analyze_trades` computes `holding_periods` before `trades.drop(...)`
  (`trade_analysis.py:511`), so short entry rows still carry their entry
  timestamp when `_calculate_holding_periods` matches them FIFO against their
  covers (`trade_analysis.py:201-218`).
- `_calculate_consecutive_streaks` and `_calculate_symbol_stats` already
  operate on the post-pairing `pnl_trades` frame (one row per closed round
  trip), so they are round-trip aware for shorts with no further change.
  Decision documented: both remain per-row (per cover for partial covers) on
  `pnl_trades`, matching the existing long-side convention; symbol stats count
  every row of `pnl_trades` (same asymmetry as longs, inherited explicitly).

`tests/test_trade_analysis.py`: added
`test_short_round_trip_that_wins_counts_as_one_trade`,
`test_short_round_trip_that_loses_counts_as_one_trade`,
`test_partially_covered_short_records_one_holding_period_per_cover`,
`test_short_never_covered_is_not_counted`.

## Verified

- `pytest -q` (full run, includes `quant_trading/` doctests):
  **1713 passed, 1 skipped, 0 failed**.
  Baseline before this session: 1709 passed, 1 skipped. Delta = **+4 new
  tests** (all short round-trip cases).
- `ruff check .`: clean.
- `black --check quant_trading/ tests/`: clean, 69 files.
- `mypy quant_trading/`: clean, 36 source files.
- Probe (`/home/runner/work/_temp/kilo-tmp/kilo/probe_trade_analysis_shorts.py`):
  short round trip (entry 50.0, exit 40.0) now reports total_trades=1,
  winning=1, losing=0, win_rate=1.0, total_pnl=1973.0, holding period 2.0 days;
  long round trip unchanged (total_trades=1, losing=1, total_pnl=-2027.0,
  holding period 2.0 days).
- Reconciliation invariant `final_value - initial_capital == sum(trades["pnl"])`
  holds on the engine's raw trade log for both directions (trade log untouched;
  fix is in the analysis only).

## Remaining unresolved (in priority order)

1. **`RiskManager.portfolio_risk.leverage` is still net**
   (`quant_trading/risk/manager.py:183`: `positions_value / total_value`) while
   `PortfolioLimit.leverage()` is gross
   (`quant_trading/risk/limits.py:230`, `gross_exposure` = `abs(market_value)`,
   `limits.py:21-37`). With shorts this is actively misleading: a fully shorted
   portfolio reports *negative* leverage. The risk gates use the gross figure,
   so no limit is wrong — only the reported number is. Small, contained fix in
   `manager.py:183` (gross = sum of `abs(position.market_value)` / total value),
   consistent with `limits.py:247`; pin with a test in `tests/test_risk_manager.py`.

2. **The shipped example strategies still cannot open a short.** They emit
   `"sell"` for a bearish entry (`quant_trading/strategies/examples.py:1053`
   and others), which the engine rejects on purpose; their short exit
   (`"buy"`) works as a cover. Turning a shipped strategy into a short strategy
   means changing the actions it emits, which breaks its pinned tests and is a
   deliberate decision.

3. **`max_positions` is still not enforced before a trade.** Only detected
   after the bar by the report-only `check_portfolio()`, halting only when
   `halt_on_portfolio_violation=True` (default `False`). Would reverse an
   earlier recorded decision and change
   `test_halt_on_portfolio_violation_stops_backtest` and
   `test_config_driven_max_positions_halts_backtest`.

4. **The portfolio risk budget and the leverage limit are only advisory
   outside the signal gate**: `check_portfolio()` reports, and the backtest
   only stops when `halt_on_portfolio_violation=True` (default `False`).

5. **A position that is at its target can never be topped up.** The signal gate
   adds the *full* target size on top of the current position
   (`quant_trading/risk/manager.py:330`), so a position opened smaller than the
   target is rejected on the next signal even though the engine would only
   trade the missing part. Applies to shorts as well.

6. `quant_trading/strategies/__init__.py` exposes `get_available_strategies()`
   and `available_strategies()` as two names for the same thing. Redundant API
   surface, exported and tested.

## Approaches already tried and rejected (for trade analysis)

- **Computing holding periods after dropping short entries.** Rejected: that
  was the bug — shorts had no entry to match, yielding 0-day holding periods.
- **Wiring short exits into the engine as automatic stop-loss/take-profit.**
  Rejected: out of scope; the engine has no automatic exit.

## Next task (precise)

**Make `RiskManager.portfolio_risk.leverage` gross instead of net.**

`quant_trading/risk/manager.py:183` reports
`leverage = positions_value / total_value` (signed, net). With a short,
`positions_value < 0`, so a fully shorted portfolio reports negative leverage.
`PortfolioLimit.leverage()` in `quant_trading/risk/limits.py:230` computes the
*gross* figure as `sum(abs(position.market_value)) / portfolio_value` and is
what the risk gates actually enforce. The reported `PortfolioRisk.leverage`
should match so the number is not misleading.

Change `manager.py:183` to the gross figure
(`sum(abs(p.market_value) for p in positions.values()) / total_value`,
guarded by `total_value > 0`), and add a test in
`tests/test_risk_manager.py` asserting that a short position reports positive
gross leverage equal to `abs(market_value) / total_value` while long behaviour
(and the risk-gate figures) is unchanged. Long behaviour must stay unchanged;
pin with the existing `tests/test_risk_manager.py` cases.

Constraints:
- Do not change `PortfolioLimit.leverage()` or the risk gates (they already
  use gross); only the reported `PortfolioRisk.leverage` number changes.
- Keep `positions_value` (signed) reported separately; only `leverage` flips to
  gross.
- Reconcile: run `pytest -q`, `ruff check .`, `black --check`, `mypy
  quant_trading/`.
