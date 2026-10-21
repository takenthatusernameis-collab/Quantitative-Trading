# Next Task

## What changed

**The backtest engine now closes a position when the risk manager reports
that its stop loss, its take profit or its trailing stop was hit.** Until
now the levels the risk manager computes were advisory: nothing in the engine
acted on them, so a backtest could lose far more than the configured
`stop_loss_pct` on a position and nothing in the trade log or the risk report
said so.

The exits are **off by default**, so every existing backtest keeps its current
results and the whole existing test suite keeps passing unchanged.

`quant_trading/config/settings.py`:
- `BacktestConfig` gets `enable_stop_exits: bool = False` (next to
  `halt_on_portfolio_violation`, the other engine-behaviour flag). The YAML
  round trip picks it up automatically (`Config.from_yaml()` filters on the
  dataclass fields), verified by hand: a config written with
  `enable_stop_exits: true` loads back as `True`.

`quant_trading/backtest/engine.py`:
- The bar loop of `run()` (`quant_trading/backtest/engine.py:447`) now closes
  the bar in this order: mark the portfolio to the bar's close → refresh the
  risk manager → **close the positions whose stop was hit** → append the
  equity curve → check the portfolio limits.
- The exit step runs **after** `self.risk_manager.update_portfolio_value(...)`
  because that call is what feeds the bar's close into the trailing stop
  tracker, so the trailing stop is up to date before it is checked.
- The equity curve append moved below the risk manager refresh and the exit
  step, so the last point of the curve is the post-exit portfolio value and
  still equals `result.final_value`. The refresh itself does not change the
  portfolio, so the curve is unchanged for a run without exits.
- New `BacktestEngine._process_stop_exits()`
  (`quant_trading/backtest/engine.py:605`): for every open position it
  compares the bar's close with the levels the risk manager computes and
  closes the position at that close:
  - a long is closed with `_reduce_long(...)` (a `"sell"` signal of strength
    1.0) and a short is covered with `_cover_short(...)` (a `"buy"` signal of
    strength 1.0). Both already cap the removal at the size of the position,
    refresh the risk manager's position view (`sync_position`) and book the
    realized PnL, so the trade log and the accounting stay consistent. There
    is no separate exit path.
  - the stop loss is evaluated before the take profit, and the position is
    closed **once**, at the bar's close, whichever level was reached.
  - a symbol without a price on the bar is skipped.
- The exit is recorded in `trades_list` like any other trade, so
  `final_value - initial_capital == sum(trades["pnl"])` keeps holding for a
  run that is liquidated this way.
- The risk manager is unchanged: `should_stop_loss()` and
  `should_take_profit()` already return a real `bool` and already follow the
  direction of the position. The levels, the risk limits, the signal gate and
  the engine's sizing are all untouched.

`tests/test_backtest_engine.py`:
- New "Stop exits" section with 8 tests:
  - `test_stop_loss_closes_a_long_at_the_bar_close`
  - `test_take_profit_closes_a_long_at_the_bar_close`
  - `test_stop_loss_covers_a_short_at_the_bar_close`
  - `test_take_profit_covers_a_short_at_the_bar_close`
  - `test_trailing_stop_closes_a_long_on_a_later_bar` (the exit happens on
    the bar **after** the one that ratcheted the stop, and the exit price is
    that later bar's close)
  - `test_stop_exit_keeps_the_accounting_invariant` (cash, PnL and the equity
    curve still reconcile after an exit)
  - `test_stop_exits_are_off_by_default` (the default behaviour is unchanged:
    the position that breaches its stop stays open)
  - `test_a_bar_that_hits_both_levels_closes_the_position_once`
- `_run_script()` grew an optional `risk_manager` argument so a test can
  drive the engine with a risk manager that has overlapping levels.

`README.md`:
- The YAML example in "Configuration" gained `enable_stop_exits: false`.
- A new "Stop Exits" section (after "Trailing Stops") describes the switch,
  what is closed at which level, the reconciliation, the close-based
  semantics, and that the exits are off by default.
- "Risk Limits" now points at the new section: the levels the risk manager
  computes are advisory until the exits are switched on.

## Verified

- `pytest -q` (full run, includes the `quant_trading/` doctests):
  **1751 passed, 1 skipped, 0 failed**.
  The baseline at the start of this session was **1743 passed, 1 skipped**
  (green). Delta = **+8 tests**, 0 failures.
- The 7 new behaviour tests **fail against the previous implementation** and
  pass against the new one. Evidence: `git stash push
  quant_trading/backtest/engine.py` and re-running
  `tests/test_backtest_engine.py` gives `4 failed, 5 passed` for
  `-k "stop"` (the take-profit and the both-levels tests are not matched by
  `-k stop`, they fail too: `assert 1 == 2` — only the entry was traded).
  `test_stop_exits_are_off_by_default` passes against **both**
  implementations, as intended: it pins that the default behaviour is
  unchanged.
- `ruff check .`: clean.
- `black --check quant_trading/ tests/`: clean, 69 files.
- `mypy quant_trading/`: clean, 36 source files.
- Probe (`/home/runner/work/_temp/kilo-tmp/kilo/probe_stop_exits.py`): a
  200-bar, 2-symbol synthetic run with a 5% stop, a 15% target and a 5%
  trailing stop.
  - exits off: 8 trades (buys only), one position still open, max drawdown
    **-3.38%**;
  - exits on: 17 trades (11 buys, 6 exits), flat at the end, max drawdown
    **-1.83%**;
  - the accounting holds for the liquidated run:
    `final_value - initial_capital == sum(trades["pnl"])` (361.39600119263923
    on both sides), the signed trade costs reconcile to the same number, and
    `equity_curve.iloc[-1] == final_value`.
  - the largest exit was $11,742, above the $10,000 position limit, because
    the limit is on the size at entry and the position had grown. That is the
    expected behaviour.

## Remaining unresolved (in priority order)

1. **`max_positions` is still not enforced before a trade.** The other three
   limits (position size, risk budget, leverage) are gated at signal time;
   the number of positions is only detected after the bar by the report-only
   `check_portfolio()`, and the backtest only halts when
   `halt_on_portfolio_violation=True` (default `False`). With the default
   limits this is latent (10% positions and 1.0x leverage cap the portfolio
   at 10 positions, below the default `max_positions=20`), but a config with
   a smaller position size or a higher leverage limit can open more
   positions than allowed. This is the next task below.
2. **The shipped example strategies still cannot open a short.** They emit
   `"sell"` for a bearish entry (`quant_trading/strategies/examples.py:1053`
   and others), which the engine rejects on purpose; their short exit
   (`"buy"`) works as a cover. Turning a shipped strategy into a short
   strategy means changing the actions it emits, which breaks its pinned
   tests and is a deliberate decision.
3. **The portfolio risk budget and the leverage limit are only advisory
   outside the signal gate**: `check_portfolio()` reports them, and the
   backtest only stops when `halt_on_portfolio_violation=True` (default
   `False`). The signal gate does enforce them for new exposure, so this is
   now only about positions that drift over the limits through the market.
4. `quant_trading/strategies/__init__.py` exposes `get_available_strategies()`
   and `available_strategies()` as two names for the same thing. Redundant API
   surface, exported and tested.
5. `PortfolioConfig.rebalance_frequency` is never read by the engine: the
   `Rebalancer` in `quant_trading/portfolio/rebalancer.py` is a complete,
   standalone component that the backtest never drives.
6. The stop exits are not reachable from `run_backtest()`: it builds its own
   `BacktestConfig` and has no parameter for the new flag. A user has to use
   `BacktestEngine` with a `Config` to switch them on. Adding a parameter is
   a small API change that was left out on purpose (it is not needed for the
   feature and every new keyword argument is public API).

## Approaches already tried and rejected

- **Exiting before `update_portfolio_value()`.** Rejected: that call is what
  feeds the bar's close into the trailing stop tracker
  (`RiskManager.update_portfolio_value()` → `update_trailing_stop()`), so the
  trailing stop would be a bar stale and would trigger a bar late.
- **A separate exit path (a new method that closes the holding and books the
  PnL itself).** Rejected: `_reduce_long()` and `_cover_short()` already cap
  the removal at the size of the position, refresh the risk manager's
  position view (`sync_position`) and book the realized PnL the way the
  strategy trades do, so a second path would be a second set of accounting
  rules. The exit reuses them.
- **Checking the take profit first.** Rejected: the stop is the level that
  protects the position, so it is evaluated first. The observable result is
  the same either way (one close, at the bar's close), which is why the
  precedence is pinned by `test_a_bar_that_hits_both_levels_closes_the_position_once`
  (the position is closed exactly once) and not by a price assertion.
- **Enabling the exits by default.** Rejected: it would change the results
  of every existing backtest and break the existing suite. The flag is off
  by default and the existing behaviour is pinned by
  `test_stop_exits_are_off_by_default`.
- **An intrabar exit (a level that was crossed inside the bar triggers the
  exit at the level).** Rejected: the engine only knows the close of a bar,
  and the OHLC high/low would need a path assumption the framework does not
  make. The exit is at the close, which is the price the engine knows.
- **Making a trailing stop trigger on the bar that ratcheted it.** Rejected:
  the stop is always placed below the best price a long has reached (above
  it, for a short), so the bar that ratchets it can never be below the stop.
  That is the intended close-based behaviour.

## Next task (precise)

**Enforce `max_positions` in the signal gate, so a signal that would open a
position beyond the limit is rejected before the trade.**

`max_positions` is the only one of the four limits that is not checked
before a trade: the position size, the risk budget and the leverage limit are
all gated in `RiskManager.check_signal()`, but the number of open positions
is only detected after the bar by the report-only `check_portfolio()`.

`quant_trading/risk/manager.py`:
- In `check_signal()`, a `"buy"` or a `"short"` signal that would open a
  **new** position (the symbol has no position, or a flat one) must be
  rejected when the portfolio already holds `portfolio_limit.max_positions`
  positions. A signal that tops up a position that is already open does not
  add a position and must stay allowed.
- A `"buy"` that covers an open short does not add a position either, and it
  already returns early ("Covering reduces the gross exposure"), so it must
  stay allowed.
- The violation message should follow the style of the other messages of the
  gate, e.g. `f"Buy signal would exceed max positions: {count} >= {limit}"`.
- `PortfolioLimit` and the risk limits themselves are untouched: the limit
  stays what it is, the gate is what reads it.

`quant_trading/backtest/engine.py`:
- No change is needed. The engine sizes and executes the trades; the gate
  rejects the ones that are not allowed, exactly like the other limits.

`tests/test_risk_manager.py`:
- A new test class (e.g. `TestMaxPositionsGate`) that pins:
  - a buy that would open a position beyond the limit is rejected;
  - a short that would open a position beyond the limit is rejected;
  - a buy that tops up a position that is already open is allowed at the
    limit;
  - a buy that covers an open short is allowed at the limit;
  - a buy that opens a position while the portfolio is below the limit is
    allowed.

`tests/test_backtest_engine.py`:
- **Three existing tests have to change**, because they use `max_positions=0`
  as a convenient way to force a portfolio violation, and with the gate in
  place no position is opened at all:
  - `test_portfolio_violations_collected_without_halt`
    (`tests/test_backtest_engine.py:423`) uses
    `RiskManager(initial_capital=100000.0, max_positions=0)`;
  - `test_halt_on_portfolio_violation_stops_backtest`
    (`tests/test_backtest_engine.py:452`) uses the same trick;
  - `test_config_driven_max_positions_halts_backtest`
    (`tests/test_backtest_engine.py:485`) uses
    `PortfolioConfig(max_positions=1)` with two symbols.
  Force the violation a different way (a `max_drawdown` breach, or a
  position-size breach) so that the tests keep testing what they are about
  (the collection of violations and the halt), and add a new end-to-end test
  that a portfolio at its position limit does not open a new position.

`README.md`:
- The "Risk Limits" section says that the signal gate rejects an individual
  order that would breach a limit; extend it to name `max_positions` as one
  of the limits the gate enforces, and note that a signal that tops up a
  position that is already open is still allowed.

Constraints:
- Do not change the other three limits, the levels, the signal gate's
  post-trade arithmetic or the engine's sizing.
- The gate must count the positions the risk manager currently knows about
  (`self.positions`), which is refreshed by `update_portfolio_value()` and
  kept current by `sync_position()`.
- Reconcile: run `pytest -q`, `ruff check .`, `black --check quant_trading/
  tests/`, `mypy quant_trading/`.
