# Next Task

## What changed

**The stop loss and take profit helpers of the risk manager are now direction
aware.** This was the task assigned by the previous handoff; it is finished and
verified below.

The four helpers in `quant_trading/risk/manager.py` used to compute long-only
thresholds, which are wrong for exactly the short positions the previous
session added. They now read the direction of the position the manager tracks:

| Helper | Long (`quantity > 0`) | Short (`quantity < 0`) |
| --- | --- | --- |
| `get_position_stop_loss` (`manager.py:475`) | `avg_price * (1 - stop_loss_pct)` | `avg_price * (1 + stop_loss_pct)` |
| `get_position_take_profit` (`manager.py:498`) | `avg_price * (1 + take_profit_pct)` | `avg_price * (1 - take_profit_pct)` |
| `should_stop_loss` (`manager.py:521`) | `current_price <= stop` | `current_price >= stop` |
| `should_take_profit` (`manager.py:543`) | `current_price >= tp` | `current_price <= tp` |

- **The direction comes from the sign of `position.quantity`**, which is the
  framework's existing convention (`quant_trading/strategies/base.py:83`:
  "Position quantity (positive for long, negative for short)"). A short
  produced by the engine has a negative quantity in both the result and the
  manager's own view — verified end to end (see below).
- **One new public method** was added: `RiskManager.is_short_position(symbol)`
  (`manager.py:448`). It answers the direction question once, so the four
  helpers cannot drift apart, and it is usable by a strategy that wants to
  close a position in the right direction. A symbol with no position, or with
  a flat one, is not a short.
- **The long behaviour is unchanged.** The level formulas and the comparison
  operators for a long are exactly the old ones, and the pinned tests
  (`tests/test_risk_manager.py::TestStopLossTakeProfit`) still pass untouched.
- **A flat position (`quantity == 0`) keeps the long behaviour** (it is not a
  short). The old code returned a long level for it, and nothing in the
  framework creates a flat position with a non-zero `avg_price` in the
  manager's view.
- **A missing position or an `avg_price <= 0` still returns `None`**, and the
  two `should_*` helpers still return `False` for it.
- **No backtest behaviour changed.** The engine never calls these four
  helpers (it has no automatic stop-loss exit), so the change is confined to
  `quant_trading/risk/manager.py` plus tests and documentation.
- **Docs**: the four docstrings now state which direction they apply to, and
  the README's "## Short Selling" section gained a short paragraph with a
  worked example (`README.md:793`).

## Verified

- `pytest -q` (full run, includes the `quant_trading/` doctests):
  **1709 passed, 1 skipped, 0 failed**.
  Baseline before this session: 1700 passed, 1 skipped. Delta = **9 new
  tests** (8 risk manager, 1 backtest engine).
- `ruff check .`: clean.
- `mypy quant_trading/`: clean, 36 source files.
- `black --check quant_trading/ tests/`: clean, 69 files.
- A probe script was written and run against the new behaviour
  (`/home/runner/work/_temp/kilo-tmp/kilo/probe_short_thresholds.py`): a short
  opened by the engine has `quantity = -100.0` and `avg_price = 100.0` in
  both `result.positions["TEST"]` and `engine.risk_manager.positions["TEST"]`;
  the stop is `105.0` (= `100 * 1.05`, above the entry) and the target `85.0`
  (= `100 * 0.85`, below the entry); a price at the stop triggers the stop and
  *not* the target, a price at the target triggers the target and *not* the
  stop.

New tests:

- `tests/test_risk_manager.py::TestStopLossTakeProfit` — the short's stop is
  above the entry price and its target below it; the mirrored levels are the
  exact mirror image of the long ones (`long + short == 2 * avg_price`); a
  short's stop and target never overlap; a short's stop is triggered by a
  rising price and its target by a falling price; the helpers follow a
  position that was synced with `sync_position` (the view the signal gate
  uses); `is_short_position` is True for a negative quantity and False for a
  long, a flat position and an unknown symbol.
- `tests/test_backtest_engine.py::test_engine_short_gets_mirrored_stop_loss_and_take_profit`
  — the end-to-end wiring: a short opened by the engine produces the mirrored
  thresholds in the manager's own position view.

## Remaining unresolved

- **The trade analysis ignores short round trips.** This is the biggest
  remaining gap and is the next task (see below).
- **`RiskManager.portfolio_risk.leverage` is still net**
  (`positions_value / total_value`, `quant_trading/risk/manager.py:183`) while
  `PortfolioLimit.leverage()` is gross
  (`quant_trading/limits.py:230`). With shorts this is now actively
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
  behaviour, unchanged by the previous session; it now applies to shorts as
  well.
- `quant_trading/strategies/__init__.py` exposes `get_available_strategies()`
  and `available_strategies()` as two names for the same thing. They are
  exported and tested, but the duplication is still redundant API surface.

## Approaches already tried and rejected

- **Keeping the old long-only helpers and adding direction-aware variants
  under new names** (e.g. `get_position_stop_loss_for_short`). Rejected: it
  leaves a public helper that silently returns the wrong threshold for a
  short, which is exactly what the previous handoff forbade, and it doubles
  the API surface for one formula.
- **Adding an explicit `direction` argument to the four helpers.** Rejected:
  the manager already knows the direction from the position it tracks, and an
  extra argument invites a caller to pass the wrong one — the failure mode
  being fixed in the first place.
- **Adding an `is_short` field/property to the `Position` dataclass.**
  Rejected as unnecessary: the sign of `quantity` is already the framework's
  documented convention (`strategies/base.py:83`), and the portfolio layer
  already derives the short's mirror-image behaviour from it
  (`portfolio/portfolio.py:89-113`). A new field would have to be kept in
  sync with the quantity for no gain.
- **Wiring the helpers into the engine as automatic stop-loss / take-profit
  exits.** Rejected: out of scope. The engine has no automatic exit, adding
  one changes backtest behaviour, and the assigned task was explicitly the
  helpers, not the engine.
- **A separate `is_short_position` helper vs. an inline `position.quantity < 0`
  check in each of the four helpers.** Chose the helper: it is used by both
  `should_*` methods and by the two level methods, so a single definition
  keeps the direction rules in one place.

## Next task (precise)

**Make the trade analysis round-trip aware for shorts.**

`quant_trading/backtest/trade_analysis.py` was written for long-only round
trips and now miscounts short round trips. Measured evidence (probe
`/home/runner/work/_temp/kilo-tmp/kilo/probe_trade_analysis_shorts.py`, one
round trip per run, entry at 50.0 and exit at 40.0, fees included):

| | long (`buy` → `sell`) | short (`short` → `cover`) |
| --- | --- | --- |
| trades counted | 1 | **2** |
| winning / losing | 0 / 1 | 1 / 1 |
| win rate | 0.0 | **0.5** |
| total PnL | -2027.0 | +1973.0 |
| holding period | 2.0 days | **0.0 days** |

The short round trip above was a **winner** (+1973.0), yet it is reported as
two trades with a 50% win rate and no holding period at all.

Two concrete causes:

1. **`_calculate_holding_periods` (`trade_analysis.py:149`)** matches `"buy"`
   entries against `"sell"` exits only, using a FIFO queue of open entries.
   A `"short"` / `"cover"` pair is never matched, so a short contributes no
   holding period. Nothing is corrupted — the short trades do not pollute the
   long FIFO queue — but the statistic is simply missing for short
   strategies.
2. **`analyze_trades` (`trade_analysis.py:460-466`)** counts wins and losses
   per trade row: `pnl_trades = trades[trades["pnl"] != 0]`, then
   `winning = pnl_trades[pnl_trades["pnl"] > 0]`. A long's entry has
   `pnl == 0.0` and is filtered out, so only the exit carries the round trip
   PnL → 1 trade. A short's entry books the entry fee as realized PnL
   (`quant_trading/backtest/engine.py:784`, `realized_pnl=-entry_fee`), so it
   is a non-zero **negative** PnL and is counted as a **losing** trade, while
   the cover books the price move → 2 trades for one round trip, one of which
   is always a loss.

Constraints and evidence:

- **The trade log must not change.** The reconciliation invariant
  `final_value - initial_capital == sum(trades["pnl"])` holds today for both
  directions (verified in the probe) and must keep holding. So the fix
  belongs in the *analysis*, not in the engine or in `Trade.pnl`.
- The natural shape of the fix is to pair a `"short"` with the `"cover"` that
  closes it (a FIFO queue per symbol, exactly like the long side) and to
  count one round trip instead of two trades — i.e. the short's entry fee and
  the cover's price move belong to the *same* round trip, the same way a
  long's entry fee and exit PnL belong to the same round trip.
- `_calculate_consecutive_streaks` (`trade_analysis.py:209`) and
  `_calculate_symbol_stats` (`trade_analysis.py:318`) take the same
  per-trade `pnl` frame and are affected in the same way; decide explicitly
  whether they are round-trip based too, and say which choice was made.
  Note that `_calculate_symbol_stats` counts **every** row of the symbol
  (including the zero-PnL entries), while `analyze_trades` filters the
  zero-PnL rows out first — that asymmetry already exists on the long side
  and is worth deciding on explicitly rather than silently inheriting.
- The existing long behaviour is pinned by `tests/test_trade_analysis.py`
  (and the invariants in `tests/test_cost_accounting_invariants.py`); it must
  not change.
- Add the mirrored cases: a short round trip that wins, one that loses, a
  partially covered short (several covers against one short), and a short that
  is never covered — the last one has no round trip and must not be counted
  as one (the long side has the same rule: an unclosed long contributes no
  holding period).
