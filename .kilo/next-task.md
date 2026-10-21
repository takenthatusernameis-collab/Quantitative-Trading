# Next Task

## What changed

**Trailing-stop machinery is now implemented end to end.** The previous
handoff assigned "make `RiskManager.portfolio_risk.leverage` gross", but that
was already done in the committed code (`quant_trading/risk/manager.py:190-194`
computes `sum(abs(p.market_value)) / total_value`; the test
`test_short_position_reports_gross_leverage` already existed). Only a stale
docstring remained, which was fixed. The real, blocking defect found on
inspection was that `get_position_stop_loss` called a nonexistent
`self.get_trailing_stop(symbol)`, which raised `AttributeError` and broke 7
tests.

`quant_trading/risk/manager.py`:
- `sync_position` now drops the trailing-stop state when a position is closed
  (`manager.py:246-249`), so a reopened symbol starts clean.
- `update_trailing_stop(symbol, current_price)` tracks the running high (long)
  or low (short), arms the stop only once the price has moved past
  `trailing_stop_activation_pct` from entry, and stores it as
  `high * (1 - trailing_stop_pct)` for a long or `low * (1 + trailing_stop_pct)`
  for a short. It is a no-op when `trailing_stop_pct <= 0` or the position is
  flat/absent (`manager.py:252-299`).
- `get_trailing_stop(symbol)` returns the stored armed stop or None
  (`manager.py:301`).
- `reset()` clears the trailing-stop state (`manager.py:675-677`).

`quant_trading/backtest/engine.py`:
- After `update_portfolio_value`, the engine now calls
  `risk_manager.update_trailing_stop(symbol, price)` for every non-flat
  position, using the bar's close price (`engine.py:479-486`). With the default
  `trailing_stop_pct=0.0` this is a no-op, so existing behaviour is unchanged.

`tests/test_risk_manager.py`: added `TestTrailingStop` (10 tests) covering
disabled/no-position/flat, pre-activation, arming and monotonic tracking for
longs and shorts, tighter-than-fixed selection, closure dropping the state, and
reset clearing it.

## Verified

- `pytest -q` (full run, includes `quant_trading/` doctests): **1723 passed,
  1 skipped, 0 failed**. Baseline before this session: 1716 passed, 1 skipped
  (7 failing from the `get_trailing_stop` `AttributeError`). Delta = **+7 newly
  passing** + **10 new tests**.
- `ruff check .`: clean.
- `black --check quant_trading/ tests/`: clean, 69 files.
- `mypy quant_trading/`: clean, 36 source files.
- Focused re-run after the black reformat: `pytest tests/test_risk_manager.py
  tests/test_limits.py tests/test_backtest_engine.py ...` = 512 passed, 1
  skipped.

## Remaining unresolved (in priority order)

1. **`RiskManager.portfolio_risk.leverage` is gross** — done this session
   (docstring corrected; the computation was already gross). No further action.
2. **The shipped example strategies still cannot open a short.** They emit
   `"sell"` for a bearish entry, which the engine rejects on purpose; their
   short exit (`"buy"`) works as a cover. Changing the emitted actions breaks
   pinned tests and is a deliberate decision.
3. **`max_positions` is still not enforced before a trade.** Only detected
   after the bar by the report-only `check_portfolio()`, halting only when
   `halt_on_portfolio_violation=True` (default `False`).
4. **The portfolio risk budget and the leverage limit are only advisory
   outside the signal gate**: `check_portfolio()` reports, and the backtest
   only stops when `halt_on_portfolio_violation=True` (default `False`).
5. **A position that is at its target can never be topped up.** The signal gate
   adds the *full* target size on top of the current position, so a position
   opened smaller than the target is rejected on the next signal even though
   the engine would only trade the missing part.
6. `quant_trading/strategies/__init__.py` exposes `get_available_strategies()`
   and `available_strategies()` as two names for the same thing. Redundant API
   surface, exported and tested.

## Approaches already tried and rejected

- **Computing holding periods after dropping short entries** (trade analysis):
  rejected, that was the bug — shorts had no entry to match.
- **Wiring short exits into the engine as automatic stop-loss/take-profit**:
  rejected, out of scope; the engine has no automatic exit.
- **Making `get_position_stop_loss` swallow the missing method** (e.g. return
  the fixed stop only): rejected — the trailing-stop state was deliberately
  initialised in `__init__`, so the intended design is a real trailing stop,
  not a silent fallback.

## Next task (precise)

**Pick one of the remaining unresolved items and implement it.** Candidates
in priority order:

1. Enforce `max_positions` *before* a trade in the engine, gated behind
   `halt_on_portfolio_violation` so the default behaviour is unchanged. This
   reverses an earlier recorded decision and would change
   `test_halt_on_portfolio_violation_stops_backtest` and
   `test_config_driven_max_positions_halts_backtest`.
2. Make the portfolio risk budget and leverage limit halt the backtest by
   default (currently advisory outside the signal gate).
3. Let a position that is below its target be topped up instead of rejected.
4. Consolidate `get_available_strategies()` / `available_strategies()`.

Constraints for any change:
- Keep the signal gate and the risk gates on gross exposure; do not weaken
  them.
- Reconcile with `pytest -q`, `ruff check .`, `black --check`, `mypy
  quant_trading/`.