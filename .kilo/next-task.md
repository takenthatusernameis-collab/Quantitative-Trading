# Next Task

## What changed

**The backtest engine can now open and close short positions.** This was the
task assigned by the previous handoff; it is finished and verified below.

The design that was chosen, and the reasoning behind it:

- **Signal actions** (`quant_trading/strategies/base.py:12`, documented in the
  `Signal` docstring): `"buy"`, `"sell"`, `"short"`, `"hold"`.
  - `"short"` opens or adds to a short position.
  - `"buy"` opens or adds to a long position, and **against an open short it
    covers that short** (up to the size of the short; a buy never flips a
    position). This is the broker convention, and it is the convention the
    shipped example strategies already use to exit a short
    (`quant_trading/strategies/examples.py:1125` and `:1147` emit `"buy"` for
    a short exit).
  - `"sell"` still only reduces or closes a long position, and is still
    rejected when no long position is held. The framework does not short a
    symbol through a plain sell; shorting goes through the explicit, separately
    gated `"short"` action.
- **Trade log actions** (`quant_trading/backtest/engine.py:126`): `"buy"`,
  `"sell"`, `"short"`, `"cover"`. The log says what each trade did to the
  position: a buy that covers a short is recorded as a `"cover"`, not as a
  `"buy"`, so the log stays unambiguous. `Trade.cost`
  (`quant_trading/backtest/engine.py:153`) charges `"buy"` and `"cover"` and
  credits `"sell"` and `"short"`, i.e. the cash sign follows the action.
- **Realized PnL for a short.** A short keeps the raw execution price as its
  cost basis (that is the framework's existing, tested portfolio convention —
  `tests/test_portfolio.py:162` and `tests/test_portfolio_invariants.py:249`),
  so the entry fee that is deducted from the sale proceeds is booked as
  realized PnL on the `short` trade itself, and the `cover` books the price
  move and the cover fee. The sum of the two is exactly the change in the
  portfolio value, for a fully liquidated short round trip and for a short
  that is still open (realized + unrealized = the value change).
- **The risk gate** (`quant_trading/risk/manager.py:238`): a `"short"` signal
  is gated exactly like a `"buy"` signal — position size, portfolio risk budget
  and the leverage limit — and all of them are measured on **gross** exposure,
  so a long and a short of the same size do not cancel each other out. The
  shared logic moved into `RiskManager._check_exposure_increase`
  (`quant_trading/risk/manager.py:330`) so the buy and the short cannot drift
  apart. A `"buy"` that covers a short is allowed (covering reduces the
  exposure, so no limit can be breached by it); a `"sell"` against an open
  short is rejected with "Sell signal for position with an open short"; a
  `"short"` against an open long is rejected with "Short signal for position
  with long holdings".
- **The engine** (`quant_trading/backtest/engine.py:537`): `_process_signal`
  dispatches to four helpers — `_open_long` (`:589`), `_reduce_long` (`:656`),
  `_open_short` (`:721`) and `_cover_short` (`:788`). A short is sized like a
  long (signal strength times the position limit, less the gross exposure the
  symbol already carries); its sale credits the proceeds to cash, so there is
  no cash constraint on a short. A cover is trimmed to the cash on hand. All
  four paths call `risk_manager.sync_position(symbol, portfolio.get_position(symbol))`
  after the trade, so the risk manager's view of the portfolio stays current
  within the bar.
- **Docs**: a new "## Short Selling" section in `README.md:754` and the
  reconciliation notes of `BacktestResult` (`quant_trading/backtest/engine.py:233`).

The portfolio layer was deliberately **not** touched: `Portfolio.add_holding`
with a negative quantity already opens a short and credits the proceeds,
`Portfolio.remove_holding` already covers a short, and the engine now uses
both instead of re-implementing the accounting.

## Verified

- `pytest -q` (full run, includes the `quant_trading/` doctests):
  **1700 passed, 1 skipped, 0 failed**.
  Baseline before this session: 1646 passed, 1 skipped. Delta = **54 new
  tests** (15 backtest engine, 9 risk manager, 30 cost accounting invariants).
- `ruff check .`: clean.
- `mypy quant_trading/`: clean, 36 source files.
- `black --check quant_trading/ tests/`: clean, 69 files.
- A probe script was written and run against the new behaviour
  (`/home/runner/work/_temp/kilo-tmp/kilo/probe_shorts.py`, 7 probes, all
  green): a short round trip reconciles the cash, the booked PnL and the
  equity curve; an open short satisfies
  `realized + unrealized == final_value - initial_capital`; an oversized
  short is rejected at the signal gate (the same buy is rejected the same
  way); a long and a short of the same size are rejected by the leverage
  limit although their net exposure is zero; a sell and a short in the same
  bar both execute and end short; a short and its cover in the same bar end
  flat.

New tests:

- `tests/test_backtest_engine.py` — the short is sized from the position
  limit and the entry fee is booked; a short round trip reconciles cash, PnL
  and equity and ends flat; a buy covers an open short; a partial cover
  closes only that part; an oversized short and a short that would breach
  the leverage limit are rejected; a long and a short pair is measured on
  gross exposure; a second short in the same bar is measured against the
  first; a sell does not add to an open short; a short is rejected while a
  long is open; a short and its cover in the same bar end flat; the
  `_process_signal` unit level cases for a short and for a buy-to-cover.
- `tests/test_risk_manager.py::TestShortSignals` — the short gate: within the
  limits, no price, position size, portfolio risk budget, leverage limit, a
  short against a long, adding to an open short, a buy that covers a short,
  a sell against an open short.
- `tests/test_cost_accounting_invariants.py` — the two helpers that map a
  trade to its effect on cash and on the position now know the `"short"` and
  `"cover"` actions, plus two new randomized scenarios: a short covered in
  random partial steps (20 seeds) and a short that is never covered
  (10 seeds). Both run the full invariant battery.

## Remaining unresolved

- **The stop loss and take profit helpers are long-only.**
  `RiskManager.get_position_stop_loss` (`quant_trading/risk/manager.py:448`)
  returns `avg_price * (1 - stop_loss_pct)` and
  `get_position_take_profit` (`:463`) returns `avg_price * (1 + take_profit_pct)`,
  and `should_stop_loss` (`:478`) / `should_take_profit` (`:492`) compare the
  price against them in the long direction. For a short position the stop is
  **above** the entry price and the target is **below** it, so all four
  helpers are now wrong for exactly the positions this session added. The
  engine does not call them (it has no automatic stop-loss exit), so nothing
  in the backtest is broken by it — but a strategy that uses them to close a
  short would close it at the wrong threshold.
- **The trade analysis ignores short round trips.**
  `quant_trading/backtest/trade_analysis.py:149` (`_calculate_holding_periods`)
  matches `"buy"` entries against `"sell"` exits only, so a short round trip
  contributes **no** holding period. Nothing is corrupted (the `"short"` and
  `"cover"` trades are skipped, they do not pollute the long FIFO queue), but
  the statistic is missing for short strategies. Related: the win rate counts
  the `short` entry as a losing trade, because it books the entry fee as
  realized PnL (the fee really is a realised cost, but it makes the trade
  count asymmetric with a long, whose entry books 0.0).
- **`RiskManager.portfolio_risk.leverage` is still net**
  (`positions_value / total_value`, `quant_trading/risk/manager.py:183`) while
  `PortfolioLimit.leverage()` is gross
  (`quant_trading/risk/limits.py:230`). With shorts this is now actively
  misleading: a fully shorted portfolio reports a *negative* leverage. The
  risk gates themselves use the gross figure, so no limit is wrong — only the
  reported number is.
- **The shipped example strategies still cannot open a short.** They emit
  `"sell"` for a bearish entry (`quant_trading/strategies/examples.py:1053`
  and others), which the engine rejects on purpose, and their short *exit*
  (`"buy"`) now works as a cover. Turning a shipped strategy into a short
  strategy means changing the actions it emits, which breaks its pinned tests
  and is a deliberate decision, not a side effect of this change.
- **`max_positions` is still not enforced before a trade.** It is only
  detected after the bar by the report-only `check_portfolio()`, and it stops
  the run only when `halt_on_portfolio_violation=True` (default `False`).
  `sync_position` keeps the position count current, so a pre-trade gate is
  now easy to add, but it would reverse the decision recorded in an earlier
  handoff and would change `test_halt_on_portfolio_violation_stops_backtest`
  and `test_config_driven_max_positions_halts_backtest` (both use
  `max_positions=0` to force a breach).
- **The portfolio risk budget and the leverage limit are only advisory
  outside the signal gate**: `check_portfolio()` reports, and the backtest
  only stops when `halt_on_portfolio_violation=True` (default `False`).
- **A position that is at its target can never be topped up.** The signal gate
  adds the *full* target size on top of the current position
  (`quant_trading/risk/manager.py:330`), so a position that was opened
  smaller than the target (e.g. because cash ran out) is rejected on the next
  signal even though the engine would only trade the missing part. Pre-existing
  behaviour, unchanged by this session; it now applies to shorts as well.
- `quant_trading/strategies/__init__.py` exposes `get_available_strategies()`
  and `available_strategies()` as two names for the same thing. They are
  exported and tested, but the duplication is still redundant API surface.

## Approaches already tried and rejected

- **Changing the portfolio's short cost basis to the net proceeds**
  (`avg_cost = price * (1 - fees)`, the mirror of a long's fee-inclusive
  basis). Rejected: it breaks the documented and tested portfolio convention
  (`tests/test_portfolio.py:162`,
  `tests/test_portfolio_invariants.py:249`) and the handoff explicitly said
  that the engine must not re-implement the portfolio accounting. The price
  paid is the convention above — the entry fee of a short is booked as
  realized PnL instead of being capitalised into the basis.
- **A separate `"cover"` *signal* action.** Rejected: the shipped example
  strategies already exit a short with a `"buy"`, so a second action would be
  redundant API surface for the same effect. The trade *log* still uses a
  distinct `"cover"` action, which is where the distinction is actually
  needed.
- **Letting a `"sell"` open a short** (the fully directional buy/sell
  convention). Rejected: "sell without holdings" is a deliberate safety
  control in the risk manager, and a short is a risk decision that deserves
  its own action and its own gate.
- **Letting a `"short"` signal flip an open long.** Rejected: a strategy can
  emit `"sell"` and `"short"` in the same bar, and `sync_position` keeps the
  risk view current, so the reversal already works without a new code path
  (covered by `test_short_and_cover_in_the_same_bar_end_flat` and the probe).
- **The gross-exposure test with a single symbol.** Rejected after the first
  run: a `"buy"` against an open short is a *cover*, not a long, so the test
  has to use two symbols for a long and a short.

## Next task (precise)

**Make the stop loss and take profit helpers direction-aware.**

`RiskManager.get_position_stop_loss`, `get_position_take_profit`,
`should_stop_loss` and `should_take_profit`
(`quant_trading/risk/manager.py:448-504`) compute long-only thresholds, so
they are wrong for the short positions this session added. A short's stop
loss sits **above** the entry price and its take profit **below** it:

- `get_position_stop_loss`: `avg_price * (1 - stop_loss_pct)` for a long,
  `avg_price * (1 + stop_loss_pct)` for a short.
- `get_position_take_profit`: `avg_price * (1 + take_profit_pct)` for a long,
  `avg_price * (1 - take_profit_pct)` for a short.
- `should_stop_loss`: `current_price <= stop` for a long,
  `current_price >= stop` for a short.
- `should_take_profit`: `current_price >= tp` for a long,
  `current_price <= tp` for a short.

The direction is `position.quantity`'s sign (`Position.quantity` is negative
for a short — see `quant_trading/strategies/base.py` and the short positions
the engine now produces, e.g. `result.positions["TEST"].quantity < 0`).

Constraints and evidence:

- The existing long behaviour is pinned by
  `tests/test_risk_manager.py::TestStopLossTakeProfit` (lines 624-671); it
  must not change.
- The engine does not call these helpers, so the change is confined to
  `quant_trading/risk/manager.py` plus tests; no backtest behaviour changes.
- The position view the helpers read is `RiskManager.positions`, which is
  kept current by `sync_position` — the same view the signal gate uses.
- Add the mirrored cases to `TestStopLossTakeProfit`: a short position with a
  negative quantity, and a short whose price crosses the mirrored thresholds.
- Update the four docstrings to say which direction they apply to.
- If the helpers are considered too narrow for the risk layer, the acceptable
  alternative is to add direction-aware variants (e.g.
  `get_position_stop_loss` returning the mirrored level) and keep the old
  long-only behaviour under a new, explicit name — but do not leave a public
  helper that silently returns the wrong threshold for a short.
