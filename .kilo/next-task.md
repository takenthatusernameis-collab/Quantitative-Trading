# Next Task

## What changed

**The broken trailing-stop commit `84063f8` was completed, and the repository
is green again.** That commit added the trailing-stop configuration and the
"tighter of the two stops" merge to `RiskManager.get_position_stop_loss()`, but
it never defined `get_trailing_stop()`, so every caller of the stop helpers
raised `AttributeError: 'RiskManager' object has no attribute
'get_trailing_stop'`. The repository was left with **8 failing tests** at the
start of this session. The feature is now implemented, wired to the
configuration, documented and tested.

`quant_trading/risk/manager.py`:
- `get_trailing_stop(symbol)` returns the trailing stop price currently
  tracked for a symbol (`None` when there is none).
- `update_trailing_stop(symbol, price)` feeds a market price into the
  tracker. It records the best price the position has reached (the highest
  price for a long, the lowest for a short) and places the stop
  `trailing_stop_pct` away from it. The stop only ratchets in the favourable
  direction: it never moves down for a long and never moves up for a short.
- The stop only starts to trail once the position has moved
  `trailing_stop_activation_pct` in its favour, measured from the average
  entry price. Before that the position keeps the stop it already has.
- `update_portfolio_value()` and `sync_position()` feed the price of every
  position they know about, so the trailing stop follows the market on its
  own. A caller that tracks prices elsewhere can call
  `update_trailing_stop()` directly.
- The trailing state of a symbol is dropped when the position is closed
  (`sync_position(symbol, None)`), when the position disappears from a
  portfolio update, when the position flips direction, and on `reset()`.
- `get_position_stop_loss()` now returns the tighter of the fixed stop and the
  trailing stop: the higher level for a long, the lower level for a short.
  (For a long a higher stop is tighter, because it triggers first.)
- `should_stop_loss()` and `should_take_profit()` return a real `bool`. They
  returned `numpy.bool_` when the price came from a pandas/numpy value, which
  broke `is True` assertions on the public API.

`quant_trading/config/settings.py`: `RiskConfig` gained `trailing_stop_pct`
and `trailing_stop_activation_pct` (both `0.0`, i.e. disabled).

`quant_trading/backtest/engine.py`: the risk configuration is forwarded to the
`RiskManager` the engine builds, so `trailing_stop_pct` in a config file
reaches the manager.

`README.md`: a "Trailing Stops" section, and the new keys in the YAML
example.

`tests/test_risk_manager.py`: a new `TestTrailingStop` class with 16 cases —
disabled by default, long and short ratchet, the stop never loosens, the
fixed stop stays in place until the trailing stop is tighter (both
directions), the activation threshold (both directions), the portfolio update
feeding prices, and the three ways the trailing state is cleared.

`tests/test_backtest_engine.py`: the trailing stop configuration reaches the
risk manager, and the engine's own price feed moves the trailing stop.

`tests/test_config.py`: the new `RiskConfig` fields.

## Verified

- `pytest -q` (full run, includes the `quant_trading/` doctests):
  **1733 passed, 1 skipped, 0 failed**.
  The baseline at the start of this session was **8 failed, 1706 passed,
  1 skipped** (the broken commit). Delta = **+19 tests** and **-8 failures**.
- `ruff check .`: clean.
- `black --check quant_trading/ tests/`: clean, 69 files.
- `mypy quant_trading/`: clean, 36 source files.
- Probe (`/home/runner/work/_temp/kilo-tmp/kilo/probe_trailing.py`): long stop
  95.0 → 114.0 at a high of 120.0, holds at 114.0 when the price falls back to
  110.0, rises to 123.5 at a high of 130.0; short stop 105.0 → 84.0 at a low
  of 80.0, holds at 84.0 when the price returns to 90.0, falls to 73.5 at a
  low of 70.0; with `trailing_stop_activation_pct=0.10` the stop is `None`
  until the price reaches 111.0, then 105.45; a closed position reports
  `None`; with trailing stops disabled the fixed stop is unchanged.
- The trailing stop is inert by default: with `trailing_stop_pct=0.0` no
  state is created and `get_position_stop_loss()` returns the fixed stop, so
  the pre-existing behaviour of the 1714 pre-existing tests is unchanged.

## Remaining unresolved (in priority order)

1. **A position that is at its target can never be topped up.** The signal
   gate adds the *full* target size on top of the current position
   (`quant_trading/risk/manager.py:340` for a buy, `:364` for a
   short), so a position opened smaller than the target is rejected on the
   next signal even though the engine would only trade the missing part
   (`quant_trading/backtest/engine.py:617-625` computes
   `available_value = target_value - current_value`). Applies to shorts as
   well.
2. **The engine has no automatic exits.** The fixed stop, the take profit and
   the new trailing stop are all advisory: the manager reports whether a
   level was hit, but the engine never closes a position because of it. This
   was explicitly out of scope for the previous sessions and is a deliberate
   design decision, not a defect.
3. **The shipped example strategies still cannot open a short.** They emit
   `"sell"` for a bearish entry (`quant_trading/strategies/examples.py:1053`
   and others), which the engine rejects on purpose; their short exit
   (`"buy"`) works as a cover. Turning a shipped strategy into a short
   strategy means changing the actions it emits, which breaks its pinned
   tests and is a deliberate decision.
4. **`max_positions` is still not enforced before a trade.** Only detected
   after the bar by the report-only `check_portfolio()`, halting only when
   `halt_on_portfolio_violation=True` (default `False`). Would reverse an
   earlier recorded decision and change
   `test_halt_on_portfolio_violation_stops_backtest` and
   `test_config_driven_max_positions_halts_backtest`.
5. **The portfolio risk budget and the leverage limit are only advisory
   outside the signal gate**: `check_portfolio()` reports, and the backtest
   only stops when `halt_on_portfolio_violation=True` (default `False`).
6. `quant_trading/strategies/__init__.py` exposes `get_available_strategies()`
   and `available_strategies()` as two names for the same thing. Redundant API
   surface, exported and tested.

Note on the previous handoff's item 1: `RiskManager.portfolio_risk.leverage`
was **already** gross in the code (`quant_trading/risk/manager.py:190-194`
computes `sum(abs(p.market_value)) / total_value`, pinned by
`tests/test_risk_manager.py::TestUpdatePortfolioValue::test_short_position_reports_gross_leverage`).
Only the docstring still described it as net; that docstring is now correct.

## Approaches already tried and rejected

- **Reverting commit `84063f8` instead of completing it.** Rejected: the
  partial work (the configuration, the state, the "tighter stop" merge) is a
  coherent design, and the missing part is small. Reverting would have
  discarded it and left the feature unimplemented.
- **Making the trailing stop the only stop.** Rejected: a trailing stop that
  is still wider than the fixed stop loss must not loosen the risk of a
  position, so the tighter of the two is used. This is why the merge is
  `max(fixed, trailing)` for a long and `min(fixed, trailing)` for a short.
- **Seeding the tracker with the entry price.** Rejected: the tracker starts
  from the first price it observes, which keeps the activation threshold
  meaningful.

## Next task (precise)

**Make the signal gate measure the target exposure instead of the target
size plus the current exposure.**

`quant_trading/risk/manager.py`:
- `check_signal()` for a `"buy"` (`:327-345`) and a `"short"` (`:352-369`)
  pass `trade_value=signal.strength * value * self.position_limit.max_size`
  (the *full* target) and `current_gross` (the exposure the symbol already
  carries) to `_check_exposure_increase()`.
- `_check_exposure_increase()` (`:371-429`) then computes
  `new_size = current_gross + trade_value` and adds the whole `trade_value`
  to the portfolio risk and the leverage.

That double counts the exposure the position already has. The engine, on the
other hand, only trades the *missing* part:
`available_value = target_value - current_value`
(`quant_trading/backtest/engine.py:617-620`). A position that was opened
smaller than its target (because the cash on hand trimmed it) is therefore
rejected by the gate on every later signal, even though the engine would
have brought it up to the target.

Change the gate so that the position-size checks are made on the exposure the
position would have *after* the trade (`max(current_gross, target)`), and so
that the portfolio risk and the leverage are increased by the *increment*
(`target - current_gross`, floored at zero) rather than by the whole target.
Keep `positions_value`/`current_gross` measured on gross exposure, so a short
is still limited like a long of the same size.

Add tests in `tests/test_risk_manager.py` that pin:
- a buy signal against a position that is already at its target still passes
  (it is a no-op for the engine);
- a buy signal against a position that is *below* its target passes and is
  sized to the missing part, i.e. it is not rejected by the position size
  limit;
- a short signal behaves the same way;
- the portfolio risk and the leverage limit are increased by the increment
  only, not by the whole target;
- the existing rejections (a signal that really would breach a limit) still
  fail.

Constraints:
- Do not change `PortfolioLimit`, the risk gates or the engine's sizing; only
  the arithmetic of the signal gate changes.
- The gross-exposure convention (a short counts like a long) must not change.
- Reconcile: run `pytest -q`, `ruff check .`, `black --check quant_trading/
  tests/`, `mypy quant_trading/`.
