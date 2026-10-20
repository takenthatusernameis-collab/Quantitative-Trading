# Next Task

## What changed

**1. The risk manager now sees the trades executed earlier in the same bar**
(the bug found and fixed in this session).

The backtest engine refreshed the risk manager's portfolio snapshot once per
bar (`update_portfolio_value` at the end of the bar loop), but it can execute
several trades inside one bar. Every risk check performed between those trades
therefore used the position set of the *previous* bar, so:

- a second buy in the same bar was measured against an exposure that did not
  include the first buy, and the `max_leverage` / `max_portfolio_risk` gates
  could be walked straight through;
- a sell signal for a position opened in the same bar was rejected with
  "Sell signal for position with no holdings", which stranded the position.

Reproduced before the fix (script kept at
`/home/runner/work/_temp/kilo-tmp/kilo/probe_stale_positions.py`):

- `risk.max_leverage=0.5`, `max_position_size=0.5`, two symbols bought on the
  same bar -> **1.00x gross exposure** (limit 0.50x), 2 trades executed.
- buy + sell of the same symbol inside one bar -> only the buy was executed,
  the position stayed open.

After the fix: the second buy is rejected (0.48x gross, 1 trade) and the
same-bar round trip executes both legs and ends flat.

Changes:

- `quant_trading/risk/manager.py:201` — new `RiskManager.sync_position(symbol,
  position)` refreshes a single position in the manager's position view. It
  does **not** touch the equity curve, the history or the `portfolio_risk`
  totals; `update_portfolio_value` remains the full refresh.
- `quant_trading/portfolio/portfolio.py:189` — new `Portfolio.get_position(symbol)`
  returns the `Position` of a single holding (or `None`).
- `quant_trading/backtest/engine.py:593` and `:634` — the engine calls
  `risk_manager.sync_position(symbol, portfolio.get_position(symbol))` after
  every executed buy and sell, so the next signal in the same bar is measured
  against the exposure that is already on the book.

**2. Two pre-existing quality-gate blockers introduced by the two commits that
landed after the previous handoff were fixed** (both were broken at `HEAD`
before this session, so the previous "ruff/mypy clean" note no longer held):

- `tests/test_backtest_engine.py` — commit `ad34963` had added unused
  `Config` / `PortfolioConfig` to a local import (ruff `F401`). The redundant
  local import was removed; the module-level import already provides them.
- `quant_trading/strategies/__init__.py` — commit `0343871` added
  `get_available_strategies()` / `available_strategies()` annotated as
  `-> list[str]` while they return `list_strategies()`, i.e. a
  `dict[str, type[Strategy]]` (mypy `return-value` error, 2 errors). The
  annotations now match the returned mapping, the three helpers are exported
  in `__all__`, and they are covered by a test.

**3. The task assigned by the previous agent is finished and verified.**
`config.portfolio.max_positions` halting was already implemented in the
engine (`quant_trading/backtest/engine.py:464-468`, `check_portfolio()` +
`halt_on_portfolio_violation`) and the previous agent's test
`test_config_driven_max_positions_halts_backtest`
(`tests/test_backtest_engine.py`) passes. The decision it settled on is:
**a `max_positions` breach is detected after the bar and stops the run only
when `halt_on_portfolio_violation=True`** (default `False`); the run
otherwise records the breach in `result.portfolio_violations` and continues.

## Verified

- `pytest -q` (full run, includes the `quant_trading/` doctests):
  **1646 passed, 1 skipped, 0 failed**.
  Baseline before this session: 1633 passed, 1 skipped. Delta = 13 new tests
  (2 portfolio, 6 risk manager, 2 backtest engine, 3 strategy factory).
- `ruff check .`: clean (was 2 errors at `HEAD`).
- `mypy quant_trading/`: clean, 36 source files (was 2 errors at `HEAD`).
- `black --check quant_trading/ tests/`: clean, 69 files.
- The probe above was re-run after the change and reproduces the fixed
  behaviour (rejection of the second same-bar buy, same-bar round trip).

New tests:

- `tests/test_risk_manager.py::TestSyncPosition` — the position view is
  added / replaced / removed, no equity point is recorded, a synced position
  counts towards the leverage limit, and a synced position can be sold.
- `tests/test_backtest_engine.py::test_same_bar_buys_are_measured_against_the_exposure_they_add`
  — a config-driven `max_leverage=0.5` rejects the second same-bar buy.
- `tests/test_backtest_engine.py::test_position_opened_in_the_same_bar_can_be_sold_again`
  — a buy and a sell inside one bar both execute and end flat.
- `tests/test_portfolio.py` — `get_position` for a held and a missing symbol.
- `tests/test_strategy_factory.py::TestStrategyConvenienceHelpers` — the three
  strategy convenience helpers.

## Remaining unresolved

- **`RiskManager.portfolio_risk.leverage` is net**
  (`positions_value / total_value`, `quant_trading/risk/manager.py:183`) while
  `PortfolioLimit.leverage()` is gross
  (`quant_trading/risk/limits.py:230`). With a long and a short of the same
  size the net figure is `0.0` while the gross exposure is `2.0x`. Both
  docstrings say which is which, but the names collide. `PortfolioRisk.leverage`
  is public API with existing tests, so changing it is a deliberate decision,
  not a drive-by fix.
- **The backtest engine still cannot open or close shorts.** `_process_signal`
  (`quant_trading/backtest/engine.py:525`) only buys, and the sell path
  returns early for `holding.quantity <= 0`. Everything *below* the engine
  already supports shorts: `Portfolio.add_holding` accepts a negative
  quantity and credits the sale proceeds, `Portfolio.remove_holding` covers a
  short, `PortfolioLimit` measures concentration on gross exposure, and the
  rebalancer can already open a short from a target allocation.
- **`max_positions` is still not enforced before a trade.** It is only
  detected after the bar by the report-only `check_portfolio()`, and it stops
  the run only when `halt_on_portfolio_violation=True`. A pre-trade gate is
  now easy to add (`sync_position` keeps the position count current), but it
  would reverse the decision recorded above and would change the meaning of
  `test_halt_on_portfolio_violation_stops_backtest` and
  `test_config_driven_max_positions_halts_backtest` (both use
  `max_positions=0` to force a breach).
- **The portfolio risk budget and the leverage limit are still only advisory
  outside the signal gate**: `check_portfolio()` reports, and the backtest
  only stops when `halt_on_portfolio_violation=True` (default `False`).
- **A position that is at its target can never be topped up.** `check_signal`
  adds the full target size on top of the current position, so a position
  that was opened smaller than the target (e.g. because cash ran out) is
  rejected on the next buy signal even though the engine would only buy the
  missing part. This is pre-existing behaviour, unchanged by this session.
- `quant_trading/strategies/__init__.py` exposes `get_available_strategies()`
  and `available_strategies()` as two names for the same thing. They are now
  exported and tested, but the duplication is still redundant API surface.

## Approaches already tried and rejected

- **Passing the live positions into `check_signal` as an extra argument**
  (`check_signal(signal, portfolio_value, positions=...)`): rejected. It is
  correct but costs one `Position` allocation per holding *per signal*, i.e.
  O(symbols^2) per bar for a cross-sectional strategy. `sync_position` is
  O(1) per executed trade.
- **Calling `update_portfolio_value` after every trade**: rejected. It
  appends to the risk manager's equity curve and history, so the curve would
  contain one point per trade instead of one per bar and the metrics computed
  from it would be wrong.
- **Enforcing `max_positions` inside `check_signal`**: rejected *for now*.
  It contradicts the decision the previous session made (detect after the
  bar, halt when configured) and would change two existing tests. The
  decision has to be made deliberately, not as a side effect of a
  stale-state fix.
- **Reversing the previous session's `max_positions` halting decision**:
  rejected. The wiring exists, it is tested, and it is the documented
  behaviour of `halt_on_portfolio_violation`.

## Next task (precise)

**Let the backtest engine open and close short positions.**

The portfolio, the risk limits and the rebalancer already support shorts; the
backtest engine is the only layer that cannot express a short strategy, which
makes every mean-reversion / pair-trading strategy unusable through
`BacktestEngine.run`.

Evidence and constraints carried forward:

- `Signal.action` is documented as `"buy"`, `"sell"` or `"hold"`
  (`quant_trading/strategies/base.py:17` and `:39`). A new action is needed
  (e.g. `"short"` to open and `"cover"` to close, or `"short"` plus
  `"buy"`-to-cover); pick one and document it in the `Signal` docstring.
- `RiskManager.check_signal` (`quant_trading/risk/manager.py:238`) only
  handles `"buy"` and `"sell"`. A short must be gated the same way a buy is
  (position size, portfolio risk budget, leverage) and a cover must be
  allowed against an open short — the current sell branch rejects any
  position with `quantity <= 0`, so covering a short is refused today.
- `Portfolio.add_holding` with a negative quantity already opens a short and
  credits the proceeds to cash; `Portfolio.remove_holding` already covers a
  short. The engine must not re-implement that accounting.
- **The realized PnL formula in `_process_signal` is long-only**:
  `quantity * price * (1 - fees) - avg_cost * quantity`
  (`quant_trading/backtest/engine.py:627-630`). Covering a short has the opposite
  sign. Getting this wrong silently corrupts the equity curve, so the tests
  must pin the cash change against the booked PnL, the way
  `tests/test_backtest_engine.py::test_total_costs_reconciles_with_pnl_and_final_value`
  does for the long case.
- Keep the risk manager's view current for short trades too: call
  `risk_manager.sync_position(symbol, portfolio.get_position(symbol))` after
  the short is opened and after it is covered, exactly as the buy and sell
  paths do now (`quant_trading/backtest/engine.py:593` and `:634`).
- Expected deliverables: the engine opens a short from a short signal, sizes
  it from the position limit, books the entry fee, covers it, and ends flat
  with the PnL, the cash and the equity curve reconciled; plus the risk
  gates reject an oversized short; plus a regression test that a long/short
  pair is measured on gross exposure.

Cheaper alternative if short support is judged too large for one session:
make `PortfolioRisk.leverage` gross so it agrees with
`PortfolioLimit.leverage()` (the first "Remaining unresolved" item), and
state the behavioural change in the `PortfolioRisk` docstring.
