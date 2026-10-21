# Next Task

## What changed

**The signal gate no longer double counts the exposure a position already
carries.** A position that was opened smaller than its target (because the
cash on hand trimmed it, or because the signal that opened it was weaker
than a later one) was rejected by `RiskManager.check_signal()` on every
later signal, even though the engine would only have traded the missing part.
The gate now measures the exposure the position carries *after* the trade.

`quant_trading/risk/manager.py`:
- `_check_exposure_increase()` takes the **target** exposure of the signal
  (`target_value`) instead of the trade value, and derives two numbers from
  it and the exposure the symbol already carries (`current_gross`):
  - `post_trade_size = max(current_gross, target_value)` — the gross
    exposure the symbol carries once the trade is done. The position size
    limit (`max_value`) and the position size percentage
    (`max_size`) are checked on it.
  - `increment = max(0.0, target_value - current_gross)` — the exposure the
    trade actually adds. The portfolio risk budget and the leverage limit are
    increased by the increment alone, because the exposure the position
    already holds is already counted in the current portfolio risk and in the
    current gross leverage.
- The two call sites in `check_signal()` (the `"buy"` and the `"short"`
  branch) pass the target exposure:
  `signal.strength * value * self.position_limit.max_size`, which is exactly
  what the engine sizes the position to
  (`quant_trading/backtest/engine.py:617-620` and `:751-756`).
- The gross-exposure convention is unchanged: a short is measured on the
  absolute value of its position, so a short is limited exactly like a long
  of the same size.
- `PortfolioLimit`, the risk limits and the engine's sizing are untouched.

`tests/test_risk_manager.py`:
- `TestCheckSignal.test_buy_with_existing_position` became
  `test_buy_with_an_oversized_existing_position`: a position that is
  *already* above the position limit is still reported, because the
  post-trade exposure is at least the exposure the position already carries.
  (The old test used a position of 8000 against a target of 5000, which is
  not a breach under the new arithmetic: the engine would not trade it.)
- New `TestTargetExposureGate` class with 8 cases: a buy against a position
  at its target passes, a buy against a position below its target passes, a
  short against a position below its target passes, the leverage limit is
  increased by the increment only, the risk budget is increased by the
  increment only, and the three rejections that must still fire (a target
  above the position limit, a trade above the risk budget, a trade above the
  leverage limit).
- The comment in `test_short_can_add_to_an_open_short` was corrected: the
  open short is *above* the position limit, not "filling" it.

`tests/test_backtest_engine.py`:
- `test_buy_signal_tops_up_a_position_below_its_target` and
  `test_short_signal_tops_up_a_short_below_its_target`: an end-to-end proof
  that a position bought at half strength is topped up to its target by the
  next signal (2 trades, the position ends at 200 units), which is exactly
  what the old gate blocked.

`README.md`: a paragraph in "Risk Limits" that describes the signal gate and
the post-trade measurement, and a correction of the sentence that said the
risk and leverage limits "do not by themselves ... reject an individual
order" (the signal gate does).

## Verified

- `pytest -q` (full run, includes the `quant_trading/` doctests):
  **1743 passed, 1 skipped, 0 failed**.
  The baseline at the start of this session was **1733 passed, 1 skipped**
  (green). Delta = **+10 tests**, 0 failures.
- The 5 new "should pass" cases in `TestTargetExposureGate` and the 2 new
  engine top-up tests **fail against the previous implementation** and pass
  against the new one. Evidence: `git stash push quant_trading/risk/manager.py`
  then re-running them gives
  `5 failed, 3 passed` and `2 failed` respectively; the failures quote the
  old arithmetic ("would exceed max position value: $15,000.00 > $10,000.00"
  for a position of 5000 against a target of 10000, and `assert 1 == 2`
  trades in the engine).
- The 3 new "should still be rejected" cases pass against **both**
  implementations, as intended: they pin that a real breach is still caught.
- `ruff check .`: clean.
- `black --check quant_trading/ tests/`: clean, 69 files.
- `mypy quant_trading/`: clean, 36 source files.
- Probe (`/home/runner/work/_temp/kilo-tmp/kilo/probe_pnl.py`): the
  accounting invariants still hold after the change — a long round trip and a
  short round trip both reconcile
  (`final_value - initial_capital == sum(trades["pnl"])`, difference
  -1.8e-12), and a run that ends with an open position reports the
  unrealized value in `final_value` and `0.0` in the trade PnL.

## Remaining unresolved (in priority order)

1. **The engine has no automatic exits.** The fixed stop, the take profit and
   the trailing stop are all advisory: `RiskManager.should_stop_loss()` and
   `should_take_profit()` report whether a level was hit, but the engine
   never closes a position because of it (they are called nowhere outside
   `quant_trading/risk/manager.py`). This is the next task below.
2. **`max_positions` is still not enforced before a trade.** The other three
   limits (position size, risk budget, leverage) are gated at signal time;
   the number of positions is only detected after the bar by the report-only
   `check_portfolio()`, and the backtest only halts when
   `halt_on_portfolio_violation=True` (default `False`). With the default
   limits this is latent (10% positions and 1.0x leverage cap the portfolio
   at 10 positions, below the default `max_positions=20`), but a config with
   a smaller position size or a higher leverage limit can open more
   positions than allowed. Enforcing it in the gate would change
   `test_portfolio_violations_collected_without_halt`,
   `test_halt_on_portfolio_violation_stops_backtest` and
   `test_config_driven_max_positions_halts_backtest`, which use
   `max_positions=0` as a convenient way to force a violation.
3. **The shipped example strategies still cannot open a short.** They emit
   `"sell"` for a bearish entry (`quant_trading/strategies/examples.py:1053`
   and others), which the engine rejects on purpose; their short exit
   (`"buy"`) works as a cover. Turning a shipped strategy into a short
   strategy means changing the actions it emits, which breaks its pinned
   tests and is a deliberate decision.
4. **The portfolio risk budget and the leverage limit are only advisory
   outside the signal gate**: `check_portfolio()` reports them, and the
   backtest only stops when `halt_on_portfolio_violation=True` (default
   `False`). The signal gate does enforce them for new exposure, so this is
   now only about positions that drift over the limits through the market.
5. `quant_trading/strategies/__init__.py` exposes `get_available_strategies()`
   and `available_strategies()` as two names for the same thing. Redundant API
   surface, exported and tested.
6. `PortfolioConfig.rebalance_frequency` is never read by the engine: the
   `Rebalancer` in `quant_trading/portfolio/rebalancer.py` is a complete,
   standalone component that the backtest never drives.

## Approaches already tried and rejected

- **Keeping the old arithmetic and only relaxing the position size check.**
  Rejected: the portfolio risk budget and the leverage limit were charged
  the whole target as well, so a position at 50% of its target was still
  charged for 100% of it. The increment has to be used in both places; the
  exposure a position already carries is already in the current portfolio
  risk and in the current gross leverage.
- **Checking the position size on `current_gross + target` and skipping the
  checks when the position is already at its target.** Rejected: the
  post-trade exposure is `max(current_gross, target)`, which is the target
  when the position is below it *and* the exposure the position already
  carries when it is above it. A position that is already above the limit
  must still be reported, so the `max()` is needed.
- **Changing the engine to size the position from the signal strength
  instead of from the target.** Rejected: the engine already trades only the
  missing part (`available_value = target_value - current_value`), and the
  handoff explicitly required the engine's sizing to stay untouched.
- **Making the gate report a violation only when the trade really adds
  exposure.** Rejected: a signal against a position that is already over the
  limit is reported, exactly as before the change. The gate is a check on
  the state the portfolio would be in after the trade, not a check on the
  trade alone.

## Next task (precise)

**Make the engine close a position when the risk manager reports that its
stop loss, its take profit or its trailing stop was hit.**

The risk manager already computes the levels and the triggers
(`get_position_stop_loss()`, `get_position_take_profit()`,
`should_stop_loss()`, `should_take_profit()` in
`quant_trading/risk/manager.py`), but the engine never acts on them, so a
backtest can lose far more than the configured `stop_loss_pct` on a
position and nothing in the trade log or the risk report says so.

`quant_trading/config/settings.py`:
- Add `enable_stop_exits: bool = False` to `BacktestConfig` (next to
  `halt_on_portfolio_violation`, the other engine-behaviour flag). The
  default is **off**, so every existing backtest keeps its current results
  and the whole existing test suite keeps passing unchanged.

`quant_trading/backtest/engine.py`:
- In the bar loop of `run()` (the loop that calls `update_prices()` at
  `engine.py:468` and `update_portfolio_value()` at `engine.py:473`), add an
  exit step **after** `self.risk_manager.update_portfolio_value(...)`: that
  call is what feeds the bar's close into the trailing stop tracker, so the
  trailing stop is up to date before it is checked.
- For every open position, when `enable_stop_exits` is on:
  - `self.risk_manager.should_stop_loss(symbol, price)` or
    `self.risk_manager.should_take_profit(symbol, price)` → close the
    position at the bar's close price (`prices[symbol]`, the price the
    engine knows on that bar — no intrabar assumption, no look-ahead).
  - Close a long with `self._reduce_long(symbol, Signal(action="sell",
    strength=1.0, price=price), trades_list, current_date, price)` and
    cover a short with `self._cover_short(symbol, Signal(action="buy",
    strength=1.0, price=price), trades_list, current_date, price, holding)`.
    Both already cap the removal at the size of the position, refresh the
    risk manager's position view (`sync_position`) and book the realized
    PnL, so the trade log and the accounting stay consistent — do not write
    a separate exit path.
  - The trade is recorded in `trades_list` like any other trade, so
    `final_value - initial_capital == sum(trades["pnl"])` must keep holding
    for a run that exits.
- The stop loss wins over the take profit when both would trigger on the
  same bar (the stop is checked first).
- A trailing stop can only trigger on a bar *after* the one that ratcheted
  it, because the tracker records the best price the position reached and
  the stop is placed below it. That is the intended close-based behaviour;
  do not try to make a stop trigger on the bar that set it.

`README.md`: document the new `enable_stop_exits` key (in the YAML example
and in a short paragraph next to "Trailing Stops" or "Risk Limits") and say
that the exits are off by default.

Add tests in `tests/test_backtest_engine.py` that pin:
- a long whose close falls to (or below) its stop loss is closed at the
  bar's close, the trade is in the log, and the position is flat afterwards;
- a long whose close rises to (or above) its take profit is closed;
- a short whose close rises to (or above) its stop is covered, and a short
  whose close falls to (or below) its take profit is covered;
- a trailing stop closes a long on a later bar, after it has ratcheted;
- the accounting invariant still holds after an exit
  (`final_value - initial_capital == sum(trades["pnl"])`);
- with the default (`enable_stop_exits=False`) a position that breaches its
  stop is **not** closed, so the existing behaviour is unchanged.

Constraints:
- The default must stay off, so the 1743 existing tests keep passing
  unchanged.
- Do not change the levels the risk manager computes, the risk limits, the
  signal gate or the engine's sizing. The exit is a new, additive step.
- The risk manager needs no change: `should_stop_loss()` and
  `should_take_profit()` already return a real `bool` and already follow
  the direction of the position.
- Reconcile: run `pytest -q`, `ruff check .`, `black --check quant_trading/
  tests/`, `mypy quant_trading/`.
