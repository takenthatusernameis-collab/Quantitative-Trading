# Next Task

## What changed

**The signal gate now stops a portfolio that is in a drawdown breach from
opening new positions.**

`max_drawdown` was the one limit of the four that the signal gate did not
enforce: the position size, the portfolio risk budget, the leverage limit and
the number of open positions were all gated in `RiskManager.check_signal()`,
but a portfolio that had fallen 20% below its peak could still open new
positions. The framework already had the rule in one place — the
`Rebalancer` refuses to buy while the drawdown limit is breached
(`quant_trading/portfolio/rebalancer.py:686`) — and the engine's gate now
agrees with it.

`quant_trading/risk/manager.py`:
- New `_reject_signal_if_in_drawdown_breach()`
  (`quant_trading/risk/manager.py:332`) rejects a signal that would add
  exposure while the portfolio is in a breach of
  `portfolio_limit.max_drawdown`. It uses
  `self.portfolio_risk.current_drawdown` and
  `self.portfolio_limit.max_drawdown`, exactly like the rebalancer does
  (`current_drawdown <= -limit`).
- `check_signal()` calls it in the `"buy"` branch and in the `"short"`
  branch (`quant_trading/risk/manager.py:459` and
  `quant_trading/risk/manager.py:487`). A `"buy"` that covers an open short
  returns before the check (the cover reduces the gross exposure), and a
  `"sell"` reduces a long, so neither is gated.
- A `max_drawdown` of `0.0` disables the limit, exactly as it disables it in
  the rebalancer.
- The violation message follows the style of the other messages of the gate:
  `"Buy signal rejected: portfolio drawdown -25.00% exceeds max 20.00%"`.
- The docstring of `check_signal()` documents the new gate and the one-bar
  lag: the drawdown the gate reads is the one of the risk manager's current
  view, which the engine refreshes with `update_portfolio_value()` at the end
  of every bar, so a breach that happens on a bar is seen by the gate on the
  next bar. That is the same lag the position-count gate has.

`quant_trading/backtest/engine.py`: unchanged. The engine sizes and executes
the trades; the gate rejects the ones that are not allowed, exactly like the
other limits.

`quant_trading/risk/limits.py`:
- The `max_drawdown` attribute docstring and the inline comment now say
  "before new positions are stopped" instead of "before halt", because the
  limit does not stop the run: the run only stops when
  `halt_on_portfolio_violation` is set (default `False`).

`tests/test_risk_manager.py`:
- New class `TestDrawdownGate` with 9 tests:
  - `test_a_buy_that_would_add_exposure_is_rejected_in_a_drawdown_breach`
  - `test_a_short_that_would_add_exposure_is_rejected_in_a_drawdown_breach`
  - `test_a_buy_that_tops_up_an_open_long_is_rejected_in_a_drawdown_breach`
  - `test_a_buy_that_covers_an_open_short_is_allowed_in_a_drawdown_breach`
  - `test_a_sell_is_not_gated_by_a_drawdown_breach`
  - `test_a_buy_is_allowed_inside_the_drawdown_limit`
  - `test_a_max_drawdown_of_zero_disables_the_check`
  - `test_the_gate_reads_the_drawdown_of_the_current_view`
  - `test_the_violation_reports_the_drawdown_and_the_limit`

`tests/test_backtest_engine.py`:
- New class `TestDrawdownGateEndToEnd` with 3 tests:
  - `test_a_run_in_a_drawdown_breach_opens_no_new_position` — a run that
    buys `A`, buys `B`, watches `A` lose 60% of its value (the portfolio ends
    24% below its peak), tries to buy `C` and then sells `A`. The `C` buy is
    rejected, the `A` sell is executed: the trades are `A buy`, `B buy`,
    `A sell`.
  - `test_the_drawdown_breach_is_reported_by_the_portfolio_check`
  - `test_a_run_without_a_drawdown_limit_opens_the_position` — the control:
    the same run with `max_drawdown=0.0` buys `C` as well.

`README.md`:
- The risk limit table now says "Drawdown from the peak that stops new
  positions" instead of "Drawdown from the peak that halts trading".
- "Risk Limits" names the drawdown among the limits the signal gate
  enforces, says that a portfolio in a breach opens no new positions while it
  can still close them, that a `max_drawdown` of `0.0` disables the limit,
  and that the drawdown the gate reads is one bar old.
- A new paragraph says that a breach stops the run only when
  `halt_on_portfolio_violation` is set, with the YAML switch.
- The YAML example of the "Configuration" section lists
  `halt_on_portfolio_violation: false`.

## Verified

- `pytest -q` (full run, includes the `quant_trading/` doctests):
  **1785 passed, 1 skipped, 0 failed**.
  The baseline at the start of this session was **1773 passed, 1 skipped**
  (green). Delta = **+12 tests** (9 in `tests/test_risk_manager.py`, 3 in
  `tests/test_backtest_engine.py`), 0 failures.
- The new tests fail against the previous implementation:
  - `git stash push quant_trading/risk/manager.py` and re-running
    `tests/test_risk_manager.py -k DrawdownGate` gives **5 failed, 4 passed**.
    The 4 that pass pin the behaviour that must *not* change (the cover that
    stays allowed, the sell that is not gated, the buy inside the limit, and
    the `max_drawdown=0.0` that disables the check).
  - the same stash and re-running
    `tests/test_backtest_engine.py -k DrawdownGateEndToEnd` gives
    **1 failed, 2 passed**; the failing one is the run that opens `C`, the
    2 that pass are the control (the limit disabled) and the portfolio
    check that reports the breach.
- `ruff check .`: clean.
- `black --check quant_trading/ tests/ examples/`: clean, 88 files.
- `mypy quant_trading/`: clean, 36 source files.
- Probe (`/home/runner/work/_temp/kilo-tmp/kilo/probe_drawdown_gate.py`):
  - the gate rejects a buy at a drawdown of -25% with
    `Buy signal rejected: portfolio drawdown -25.00% exceeds max 20.00%`;
  - the `Rebalancer` refuses the same buy (`_risk_adjust_buy` returns 0.0)
    on the same portfolio state, so the two agree;
  - the end-to-end run trades `A buy`, `B buy`, `A sell` (no `C`), the
    equity curve is `[100000, 100000, 76000, 76000, 76000, 76000]` and
    `portfolio_violations` reports `Drawdown -24.00% exceeds max 20.00%`.

## Remaining unresolved (in priority order)

1. **`DataConfig.default_interval` and `DataConfig.default_period` are never
   read by anything.** This is the next task below.
2. **The shipped example strategies still cannot open a short.** They emit
   `"sell"` for a bearish entry (`quant_trading/strategies/examples.py:1053`
   and others), which the engine rejects on purpose; their short exit
   (`"buy"`) works as a cover. The engine, the risk manager and the
   portfolio all support shorts (see the README's "Short Selling"), but no
   built-in strategy can use them, so a user of the built-in strategies
   cannot reach the feature. Turning a shipped strategy into a short
   strategy means changing the actions it emits, which breaks its pinned
   tests and is a deliberate decision.
3. **`PortfolioConfig.rebalance_frequency` and
   `PortfolioConfig.min_position_size` are never read by anything.** The
   `Rebalancer` in `quant_trading/portfolio/rebalancer.py` is a complete,
   standalone component that the backtest never drives, so wiring these two
   fields into a run means driving the rebalancer from the engine. That is a
   much bigger change than the interval fix below and is left for a session
   that can own it.
4. **The portfolio risk budget and the leverage limit are only advisory
   outside the signal gate**: `check_portfolio()` reports them, and the
   backtest only stops when `halt_on_portfolio_violation=True` (default
   `False`). The signal gate does enforce them for new exposure, so this is
   now only about positions that drift over the limits through the market.
5. `quant_trading/strategies/__init__.py` exposes `get_available_strategies()`
   and `available_strategies()` as two names for the same thing. Redundant
   API surface, exported and tested.
6. `PositionLimit.max_value` is derived from the *initial* capital
   (`initial_capital * max_position_size`), so the absolute cap on a
   position does not grow with the portfolio. The percentage limit does
   grow with it, so the absolute cap is the binding one after a good run.
   Changing it would change the results of every existing backtest, so it
   was left alone.
7. The command line derives the annualization from a local `interval`
   variable (`examples/cli.py:1040`) that forces `"1d"` for the synthetic
   provider, while the calls themselves pass `interval=args.interval`. The
   two can disagree. The next task touches that code, so the next agent
   should keep them in sync.

## Approaches already tried and rejected

- **Gating the drawdown in `check_portfolio()` only.** Rejected: that check
  runs after the bar, so it reports a breach that has already been traded.
  The place where a risk limit belongs is the gate, which is what the other
  four limits already use.
- **Rejecting the whole signal, including the ones that reduce the
  exposure.** Rejected: a `"buy"` that covers an open short and a `"sell"`
  reduce the gross exposure of the portfolio, so they cannot make the
  drawdown worse. Blocking them would trap a position that is bleeding.
- **Gating only a signal that opens a *new* position** (the rule the
  position-count gate uses). Rejected: a `"buy"` that tops up an open long
  adds exposure as well, and the rebalancer refuses every buy during a
  breach, not only the first one of a symbol.
- **Using the `portfolio_value` argument of `check_signal()` to recompute the
  drawdown.** Rejected: the peak lives in the risk manager
  (`self.peak_value`), and the rebalancer reads the drawdown of the
  manager's current view. Recomputing it in the gate would give the gate a
  different number than the rebalancer and than the reported violation.
- **Flipping the default of `halt_on_portfolio_violation`.** Rejected: it
  would change the results of every existing backtest, and the gate is the
  place where a risk limit belongs.

## Next task (precise)

**Make `DataConfig.default_interval` configure the data layer of a run.**

`default_interval` is defined (`quant_trading/config/settings.py:66`),
documented (the README's YAML example) and read by **nothing**. The
interval that a run actually uses comes from a hard-coded default, so a
configuration that asks for weekly bars is silently ignored and the run
fetches (and annualizes) daily bars.

Evidence of the defect:
- `run_backtest()` has `interval: str = "1d"`
  (`quant_trading/backtest/engine.py:997`) and hands it to
  `engine.run(symbols, start, end, interval)`
  (`quant_trading/backtest/engine.py:1112`). The `data` section of the
  configuration is never consulted for it. `BacktestEngine.run()` has the
  same hard-coded default (`quant_trading/backtest/engine.py:390`).
- The command line has `--interval` with `default="1d"`
  (`examples/cli.py:263`) and passes `interval=args.interval` to every
  `run_backtest()` call (`examples/cli.py:1324`, `1342`, `1362`, `1489`,
  `1761`, `1891`). A hard-coded default overrides the file, exactly the
  defect that was fixed for `--initial-capital`, `--commission`,
  `--slippage` and `--risk-free-rate` in the previous session.
- `grep -rn "default_interval" --include="*.py"` finds only the definition
  in `quant_trading/config/settings.py` and the doctest next to it.

The fix follows the rule that is already in place everywhere else: **an
explicit value wins over the configured one, the configured one wins over
the built-in default**.

`quant_trading/backtest/engine.py`:
- `run_backtest()` takes `interval: str | None = None`, so "not given" can
  be told apart from "given the default value".
- A new `_resolve_data_interval()` (or an extra step in
  `_resolve_backtest_config()`) resolves it: the configured value is
  `config.data.default_interval` for a full `Config` and for a `DataConfig`
  alike, and the built-in default is `"1d"`. A `DataConfig` only describes
  the data layer, so it is the section that carries the interval.
- The configuration of the caller is never modified.

`examples/cli.py`:
- `--interval` defaults to `None` instead of `"1d"`, so the file wins
  unless the flag is given; the help text says so.
- `create_config()` applies the flag to `config.data.default_interval` when
  it is given, which keeps the rule in one place.
- The `periods_per_year` derivation and the `run_backtest()` calls must use
  the **resolved** interval, not `args.interval` and not two different
  variables. The synthetic provider always emits daily bars, so its
  interval stays `"1d"` (that special case is at
  `examples/cli.py:1040`; see remaining item 7).

`tests/test_backtest_engine.py`:
- New tests in the `TestRunBacktestAppliesConfig` class (or a new class):
  - the configured `default_interval` is the one the run fetches with;
  - an explicit `interval` wins over the configured one;
  - a `DataConfig` that names an interval configures the run;
  - the configuration of the caller is not modified.

`tests/test_cli.py`:
- `test_default_args` pins that `--interval` defaults to `None`.
- A new test that `create_config()` keeps the interval of the file and that
  the flag overrides it.
- An end-to-end test: a YAML that asks for a different interval is used by
  the run.

`README.md`:
- The "Configuration" section says that the `data` section configures the
  data layer, that the flag wins over the file, and that
  `periods_per_year` follows the resolved interval.

Constraints:
- Do not change the built-in default of `"1d"`, the resolution rule, the
  synthetic provider's daily bars, or the other configuration fields.
- Do not change the annualization rule: `periods_per_year` has to follow
  the interval the data was actually fetched with.
- Do not touch `default_period` in this task: turning a period string
  ("1y", "6mo") into a date range needs a period parser that the codebase
  does not have, and the date range of the command line is decided by
  `--days`, `--start` and `--end`. That is a separate, larger task; the
  remaining list records it.
- Reconcile: run `pytest -q`, `ruff check .`, `black --check quant_trading/
  tests/ examples/`, `mypy quant_trading/`.
