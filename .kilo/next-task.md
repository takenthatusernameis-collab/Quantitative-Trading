# Next Task

## This session

The previous handoff left no assigned task, so one was selected from a
read-only audit of the backtest accounting: **a `short` signal executed
against an open long position corrupted the trade log**, and the run no longer
reconciled with the portfolio value. That is fixed, and the invariant is now
pinned by an executable check.

1. **`quant_trading/backtest/engine.py` — a short against an open long now
   reduces the long.**
   - `_process_signal()` (the dispatcher) sends a `short` signal to
     `_reduce_long()` when the symbol already carries a long position, and to
     `_open_short()` otherwise. This is the mirror image of the `buy`-covers-
     `short` branch that was already there, and it keeps the framework's rule
     that a signal never flips a position.
   - The trade is recorded as the `sell` it actually is, with the executed
     quantity (capped at the size of the position) and the realized PnL of
     the sale. Before the fix the log recorded a `short` of the *requested*
     quantity with the short's entry fee as its PnL, while the portfolio had
     actually sold part of the long.
   - `_open_short()` gained a guard: it returns without trading when the
     symbol carries an open long, so the accounting hole cannot be reopened
     by another caller.
2. **`tests/test_cost_accounting_invariants.py` — a new invariant and a new
   randomized scenario.**
   - `_assert_a_short_only_ever_opens_a_short()` (new) walks the trade log and
     fails when a `short` row is executed while the symbol is long. It is
     called from `_assert_cost_accounting_invariants()`, so every scenario in
     the file now checks it.
   - `test_randomized_long_short_transition_invariants` (new, 20 seeds) drives
     the engine with a random mix of `buy` / `sell` / `short` / `hold` signals
     and the risk checks switched off, so every signal reaches the engine.
   - `test_a_short_against_an_open_long_sells_the_long` (new) pins the
     behaviour deterministically.
3. **`tests/test_backtest_engine.py`** — three deterministic regression tests
   (`..._reduces_the_long`, `..._reduces_only_its_share`,
   `..._opens_a_real_short`) plus the `_risk_free_manager()` helper.
4. **`quant_trading/backtest/metrics.py`** — the blind `except Exception` in
   `calculate_backtest_metrics()` was narrowed to `except (TypeError,
   ValueError)`. This was **pre-existing**, not caused by this session: it
   was the only `ruff check .` error on the pristine tree (ruff 0.17.1 reports
   `BLE001`). The behaviour is unchanged for valid input, and a programming
   error is no longer swallowed.
5. **`tests/test_backtest_metrics.py`** — the previously untested `positions=`
   argument of `calculate_backtest_metrics()` is now covered (two tests).
6. **`README.md`** and **`quant_trading/strategies/base.py`** — the `short`
   action and the "a signal never flips a position" rule are documented.

## What was actually verified

- **Baseline before any change**: `python3 -m pytest -q` -> `1920 passed,
  1 skipped`. The tree was green.
- **After the change**: `python3 -m pytest -q` -> **`1946 passed, 1 skipped,
  0 failed`** (26 new tests).
- `python3 -m ruff check .` -> **All checks passed** (it failed with one
  pre-existing `BLE001` before the change).
- `python3 -m black --check .` -> 91 files unchanged.
- `python3 -m mypy quant_trading examples` -> no issues found in 56 source
  files.
- **The bug was reproduced before the fix.** A script with the risk checks
  switched off (`risk_manager.disable()`), 10,000 of capital and the closes
  `[100, 150, 150]` produced:
  ```
  action  quantity   price      fee       pnl
  buy     5.000000  100.0  0.750000  0.000000
  short   3.332833  150.0  0.749888 -0.749888
  holdings: {'AAA': (1.667166, 100.15, 150.0)}   <- still LONG, no short exists
  final_value - initial_capital : 248.50
  sum(trades['pnl']) + unrealized: 82.36   -> MISMATCH of 166.14
  ```
  After the fix the same scenario records `buy` + `sell`, the position is
  flat, and the identity holds exactly.
- **The new tests fail on the pre-fix code.** The engine change was reverted
  (`git checkout quant_trading/backtest/engine.py`) and the two test files
  were run: **9 failed**. The change was restored and the same files passed
  (200 passed).
- **A 400-case randomized sweep** (random scripts over `buy` / `sell` /
  `short` / `hold`, one or two symbols, random fees, risk checks off) was
  run against three invariants — the portfolio-value reconciliation, the cash
  reconciliation and the "a short only ever opens a short" rule:
  - before the fix: **82 of 400 scenarios failed**;
  - after the fix: **0 of 400 scenarios failed**.
  The sweep lives in `/home/runner/work/_temp/kilo-tmp/work/sweep.py`
  (outside the repository).

## What remains unresolved

The following were found by the same audit and are **verified but not
fixed**. They are listed with their evidence so the next session does not
have to rediscover them.

- **The per-position dollar cap is static, so a strategy cannot re-enter
  after the account grew.** The engine sizes a new position at
  `portfolio.total_value * max_position_size`
  (`quant_trading/backtest/engine.py:741` and `:886`), but the signal gate
  compares that target against `position_limit.max_value`, which the risk
  manager fixes to `initial_capital * max_position_size`
  (`quant_trading/risk/manager.py:139`, checked at `:540`). Once the
  account is above its starting value the target exceeds the cap and every
  new entry is rejected. Measured with 100,000 of capital, a 10% position
  limit and the closes `[100, 200, 200, 200, 200]`:
  ```
  final value: 109955.0   initial: 100000.0
  risk manager max_value: 10000.0
  engine target for a full-size entry: 10995.5
  check_signal on the 4th entry: False
      ['Buy signal would exceed max position value: $10,995.50 > $10,000.00']
  ```
  The README calls `max_position_size` "the largest single position, as a
  fraction of the portfolio", and the percentage check in the same function
  is already relative to the *current* portfolio value, so the static dollar
  cap is the odd one out. It is not obvious from the code alone whether the
  dollar cap should be absolute (`PositionLimit.max_value` is a public field
  with a default of `50000.0`) or derived from the current portfolio value.
- **A signal without a price is filled at the *previous* bar's close.**
  `quant_trading/backtest/engine.py:620` falls back to
  `holding.current_price` when `signal.price` is `None`, but
  `update_prices()` only runs after the trades of the bar
  (`quant_trading/backtest/engine.py:494`), so that price is the previous
  bar's close. Measured with the closes `[100, 200, 200]` and a `sell` signal
  with `price=None`: the trade was filled at `100.0` while the bar it ran on
  closed at `200.0`, booking `0.0` of PnL instead of `+100,000`. The
  `_process_signal` docstring says a signal with insufficient price
  information is ignored; it is not. Only `sell` reaches this path (`buy` and
  `short` are rejected earlier by the risk gate for having no price).
- **The engine fills a signal at the close of the bar that produced it**
  (`quant_trading/backtest/engine.py:481-486` and `:620`). A live order
  cannot be filled at a close that is only known when the bar has closed.
  This is a design decision rather than a typo: every fixture in the test
  suite passes the bar's close as the signal price, and
  `tests/test_backtest_engine.py:1661` asserts the bar-close fill for stop
  exits. Changing it moves every backtest result.
- **`calculate_max_drawdown()` can return `-inf`**
  (`quant_trading/risk/metrics.py:160-163`): the guard is
  `running_max.eq(0).all()`, so an equity curve that starts at or below zero
  divides by a zero running maximum and the `-inf` propagates into
  `max_drawdown`, `max_drawdown_pct` and `calmar_ratio`.
- **`split_trade_log()` counts one round trip per closing row**
  (`quant_trading/backtest/trade_log.py:158-173`), so one sell that closes
  several FIFO lots is one "trade", while `analyze_trades()` reports one
  holding period per lot. The two public APIs disagree on the population.
- **The monthly return series drops the first month**
  (`quant_trading/backtest/trade_analysis.py:305-310`): `resample("ME").last()`
  followed by `pct_change().dropna()` throws away the first month's return.
- **The per-trade return divides by the equity *after* the trade**
  (`quant_trading/backtest/trade_analysis.py:420`), while the docstring says
  it divides by the capital the trade was taken with.
- **The engine does not enforce the requested `[start, end]` window**
  (`quant_trading/backtest/engine.py:465-473`): it trusts the provider to
  clip. The shipped providers do clip, so the impact is provider-dependent.
- **`analyze_trades(periods_per_year=...)` is still not wired to the run.**
  The trade-level Sharpe and Sortino are computed on the per-trade return
  series, so the parameter means "trades per year", not "bars per year".
  Forwarding the bar frequency from the config would conflate the two.
- **Network-gated providers** (Yahoo Finance, Alpha Vantage) remain hard to
  cover offline.

## Approaches that already failed

- **Fixing the trade log after the fact** (e.g. rewriting the `short` row
  into a `sell` row once the run is over) was rejected: the quantity, the
  fee and the realized PnL of the row were all wrong, and the cash
  reconciliation (`portfolio.cash - initial_capital == signed trade costs`)
  was wrong as well. The signal has to be executed as the sale it is, at the
  moment it is executed.
- **Letting `_open_short()` open the short anyway** (the current behaviour
  before this session) is what broke the accounting: `Portfolio.add_holding()`
  reduces an open long, but the engine logged the requested quantity, the
  `short` action and the short's entry fee. Two independently computed
  versions of the same trade is exactly the kind of drift the framework
  tries to avoid.
- **Rejecting the `short` signal outright** (the mirror of what the risk
  manager does) would also have fixed the accounting, but it drops the
  strategy's intent silently. The engine already treats a `buy` against an
  open short as a cover rather than as a rejection, so the reduction is the
  behaviour that matches the rest of the framework.
- **Relying on the risk manager to keep the accounting correct** does not
  work: `RiskManager.disable()` is a public API and the invariant tests
  already use it, so the engine has to be correct on its own.
- **The environment had no dependencies installed.** `pandas`, `numpy`,
  `pytest`, `black`, `ruff`, `mypy` and then `yfinance` and
  `scikit-optimize` were installed with `pip` before the baseline could be
  measured; without `yfinance` and `scikit-optimize` the suite reports 31
  failures that have nothing to do with the code.

## Next task

**Make the per-position dollar limit consistent with the position sizing, so
that a strategy can re-enter after the account grew.**

The engine sizes a new position against the *current* portfolio value
(`portfolio.total_value * max_position_size`) while the signal gate caps the
same position against the *initial* capital
(`position_limit.max_value == initial_capital * max_position_size`). Once the
account is above its starting value the two disagree and every new entry is
rejected with "Buy signal would exceed max position value: $10,995.50 >
$10,000.00", so a strategy that made 10% can never trade again.

The task is to make the two agree and to document which one is right:

1. Decide whether the per-position dollar cap is an absolute limit or a
   limit relative to the current portfolio value. The README already calls
   `max_position_size` "the largest single position, as a fraction of the
   portfolio", and the percentage check in the same function
   (`_check_exposure_increase`) is already relative to the current value, so
   the dynamic reading is the one the documentation supports.
2. Implement it in `quant_trading/risk/manager.py` without weakening the
   other caps: the leverage limit, the portfolio-risk budget, the position
   count and the drawdown gate must keep rejecting what they reject today.
   `PositionLimit.max_value` is a public field with its own default
   (`50000.0`) and `PositionLimit.check()` uses it, so it must keep meaning
   something for a caller that builds a `PositionLimit` directly.
3. Add the regression test: a run that gains money and then opens a new
   position has to be able to trade again, and a position that is too large
   for the *current* portfolio value still has to be rejected. The
   randomized harness in `tests/test_cost_accounting_invariants.py` and the
   scripted helper `_run_script` in `tests/test_backtest_engine.py` are the
   natural places for it.
4. Re-run `python3 -m pytest -q`, `python3 -m ruff check .`,
   `python3 -m black --check .` and `python3 -m mypy quant_trading examples`,
   and update the "Risk Limits" section of the README.
