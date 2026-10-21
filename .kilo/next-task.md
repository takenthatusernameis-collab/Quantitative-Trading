# Next Task

## What changed

**A configuration that is handed to a run now configures that run.**
`run_backtest()` used to read the `data` section of a `Config` and to drop
its `backtest`, `risk` and `portfolio` sections on the floor, so a
configuration that limited a run to one position, or that set a position
size of 1% of the portfolio, was silently ignored: the run used the
built-in defaults instead. The command line had the same problem from the
other side: `--initial-capital`, `--commission`, `--slippage` and
`--risk-free-rate` carried hard-coded defaults, so they overrode the values
of the YAML file even when the flag was not given.

`quant_trading/backtest/engine.py`:
- `run_backtest()` (`quant_trading/backtest/engine.py:989`) takes
  `initial_capital`, `commission`, `slippage` and `periods_per_year` as
  `None` when they are not given, so an explicit value can be told apart
  from "not given".
- New `_resolve_backtest_config()`
  (`quant_trading/backtest/engine.py:947`) resolves the backtest settings:
  **an explicit value wins over the configured one, the configured one wins
  over the built-in default**. The `backtest` section of a full `Config` is
  the only source of a configured value; a `DataConfig` only describes the
  data layer and leaves the backtest settings at their defaults.
- When a full `Config` is given, the engine is built with it (a copy, via
  `dataclasses.replace`), so the `risk` section drives the limits of the
  risk manager and the `portfolio` section drives the limit on the number
  of open positions. The `backtest` section provides the starting capital,
  the costs, the annualization period, `halt_on_portfolio_violation` and
  `enable_stop_exits`. The configuration of the caller is never modified.
- The docstring of the `config` argument said that the config "takes
  precedence over data_manager"; the code does the opposite (a data manager
  is only built from the config when no data manager is given). The
  docstring now matches the code.

`examples/cli.py`:
- `--initial-capital`, `--commission`, `--slippage` and `--risk-free-rate`
  now default to `None` instead of a hard-coded value, so the YAML file
  wins unless the flag is given. The help text says so.
- `create_config()` applies those flags to the `backtest` section of the
  configuration when they are given, which keeps the "a flag that is given
  wins over the file" rule in one place.
- The optimizer, the walk-forward and the backtest calls read the resolved
  values from `config.backtest` instead of the raw arguments, because the
  optimizers need a number and not "not given".
- The `periods_per_year` of the file is still replaced by the value that
  matches the interval of the run. That is deliberate: the annualization
  has to match the data that was fetched. It is now documented.

`tests/test_backtest_engine.py`:
- New class `TestRunBacktestAppliesConfig` with 9 tests:
  - `test_the_risk_section_of_the_config_sizes_the_positions`
  - `test_the_portfolio_section_of_the_config_limits_the_number_of_positions`
  - `test_the_portfolio_section_allows_the_positions_it_permits`
  - `test_the_backtest_section_of_the_config_switches_the_stop_exits_on`
  - `test_the_configured_initial_capital_is_used`
  - `test_an_explicit_value_wins_over_the_configured_one`
  - `test_the_configured_periods_per_year_is_used`
  - `test_the_config_is_not_modified_by_the_run`
  - `test_a_data_config_leaves_the_backtest_settings_at_their_defaults`

`tests/test_cli.py`:
- `test_default_args` now pins that the four cost flags default to `None`
  (it pinned the hard-coded values before, which was the bug).
- New `test_cost_flags_are_parsed`.
- New `test_create_config_keeps_the_values_of_the_config_file` and
  `test_create_config_lets_the_flags_override_the_config_file`.
- New class `TestConfigFileEndToEnd` with
  `test_main_with_a_config_file_uses_the_capital_of_the_file` and
  `test_main_with_a_config_file_uses_the_limit_of_the_file`.

`README.md`:
- "Command Line Interface" → "Configuration" describes that every section
  of the file configures the run, that a flag wins over the file, and that
  `periods_per_year` follows the interval.
- "Configuration" describes that a `Config` handed to `run_backtest()`
  configures the run, with the precedence rule and the note that a
  `DataConfig` only describes the data layer.

## Verified

- `pytest -q` (full run, includes the `quant_trading/` doctests):
  **1773 passed, 1 skipped, 0 failed**.
  The baseline at the start of this session was **1759 passed, 1 skipped**
  (green). Delta = **+14 tests**, 0 failures.
- The new tests fail against the previous implementation:
  - `git stash push quant_trading/backtest/engine.py` and re-running
    `tests/test_backtest_engine.py -k RunBacktestAppliesConfig` gives
    **5 failed, 4 passed**. The 4 that pass pin the behaviour that must
    *not* change (the control that allows both positions, the explicit
    value winning, the untouched configuration, the defaults of a
    `DataConfig`).
  - `git stash push examples/cli.py` and re-running the CLI tests gives
    **3 failed**: the two end-to-end tests of `TestConfigFileEndToEnd` and
    `test_create_config_lets_the_flags_override_the_config_file`.
- `ruff check .`: clean.
- `black --check quant_trading/ tests/ examples/`: clean, 88 files.
- `mypy quant_trading/`: clean, 36 source files.
- Probe (`/home/runner/work/_temp/kilo-tmp/kilo/probe_config_ignored.py`):
  a 2-symbol run with `portfolio.max_positions = 1` and
  `risk.max_position_size = 0.01`.
  - before: 2 positions, 8.47% and 12.85% of the portfolio;
  - after: 1 position, 0.85% of the portfolio.
- Probe (`/home/runner/work/_temp/kilo-tmp/kilo/probe_cli_config.py`): the
  CLI path with a YAML that sets `initial_capital: 25000`,
  `max_position_size: 0.05` and `max_positions: 1` now runs with 25000.0
  and holds a single position.
- The CLI itself (`python examples/cli.py --config <yaml>`) prints
  `Initial Capital: $25,000.00` for a file that asks for 25000.0, where it
  printed $100,000.00 before.

## Remaining unresolved (in priority order)

1. **The `max_drawdown` limit does not stop the engine from opening new
   positions.** This is the next task below.
2. **The shipped example strategies still cannot open a short.** They emit
   `"sell"` for a bearish entry (`quant_trading/strategies/examples.py:1053`
   and others), which the engine rejects on purpose; their short exit
   (`"buy"`) works as a cover. The engine, the risk manager and the
   portfolio all support shorts (see the README's "Short Selling"), but no
   built-in strategy can use them, so a user of the built-in strategies
   cannot reach the feature. Turning a shipped strategy into a short
   strategy means changing the actions it emits, which breaks its pinned
   tests and is a deliberate decision.
3. **The portfolio risk budget and the leverage limit are only advisory
   outside the signal gate**: `check_portfolio()` reports them, and the
   backtest only stops when `halt_on_portfolio_violation=True` (default
   `False`). The signal gate does enforce them for new exposure, so this is
   now only about positions that drift over the limits through the market.
4. **Four configuration fields are never read by anything**:
   `PortfolioConfig.rebalance_frequency` and
   `PortfolioConfig.min_position_size` (the `Rebalancer` in
   `quant_trading/portfolio/rebalancer.py` is a complete, standalone
   component that the backtest never drives), and
   `DataConfig.default_interval` and `DataConfig.default_period` (the
   providers take the interval as an argument, and the CLI has its own
   `--interval`).
5. `quant_trading/strategies/__init__.py` exposes `get_available_strategies()`
   and `available_strategies()` as two names for the same thing. Redundant
   API surface, exported and tested.
6. `PositionLimit.max_value` is derived from the *initial* capital
   (`initial_capital * max_position_size`), so the absolute cap on a
   position does not grow with the portfolio. The percentage limit does
   grow with it, so the absolute cap is the binding one after a good run.
   Changing it would change the results of every existing backtest, so it
   was left alone.

## Approaches already tried and rejected

- **Resolving the configuration in `BacktestEngine` only.** Rejected: the
  engine already honours a full `Config` (`BacktestEngine.__init__` builds
  the risk manager from `config.risk` and `config.portfolio`). The defect
  was in `run_backtest()`, which threw the `risk` and `portfolio` sections
  away before it got there.
- **Keeping the hard-coded defaults of `run_backtest()` and treating the
  configuration as an override that always wins.** Rejected: an explicit
  argument has to be able to win over the configuration, otherwise a caller
  cannot override a file without building a new configuration. The `None`
  sentinel is what makes "not given" distinguishable from "given the
  default value".
- **Letting the configuration win over an explicit argument.** Rejected:
  the opposite of the rule the CLI already follows ("override with CLI
  args, only when explicitly provided", `examples/cli.py:1007`).
- **Mutating the configuration of the caller.** Rejected: the run would
  change the object the caller holds. `dataclasses.replace` makes a copy.
- **Copying the whole `Config` including the `data` section.** Not
  needed: only the `backtest` section is changed, so the copy shares the
  `data`, `risk` and `portfolio` objects with the original. The engine
  only reads them.

## Next task (precise)

**Make the signal gate reject a signal that would add exposure while the
portfolio is in a `max_drawdown` breach.**

`max_drawdown` is the one limit of the four that the signal gate does not
enforce: the position size, the portfolio risk budget, the leverage limit
and (since the previous session) the number of open positions are all
gated in `RiskManager.check_signal()`, but a portfolio that is 25% below its
peak can still open new positions. The README's risk limit table calls the
limit "Drawdown from the peak that halts trading", and nothing halts it
unless `halt_on_portfolio_violation=True` (default `False`).

The framework already has the behaviour in one place: the `Rebalancer`
refuses to buy while the drawdown limit is breached
(`quant_trading/portfolio/rebalancer.py:686`):

```python
drawdown_limit = self.risk_manager.portfolio_limit.max_drawdown
if (
    drawdown_limit > 0
    and self.risk_manager.portfolio_risk.current_drawdown <= -drawdown_limit
):
    return 0.0
```

The engine's gate should agree with it.

`quant_trading/risk/manager.py`:
- In `check_signal()`, a `"buy"` or a `"short"` signal that would **add**
  exposure must be rejected when the portfolio is in a drawdown breach.
  The check uses `self.portfolio_risk.current_drawdown` and
  `self.portfolio_limit.max_drawdown`, exactly like the rebalancer does.
- A `"buy"` that covers an open short reduces the exposure, so it must
  stay allowed: the early return for a cover happens before the new check
  (it is already the first thing the buy branch does).
- A `"sell"` is not gated (it reduces a long).
- The violation message should follow the style of the other messages of
  the gate, e.g.
  `f"Buy signal rejected: portfolio drawdown {drawdown:.2%} exceeds max {limit:.2%}"`.
- A `max_drawdown` of `0.0` disables the limit (the rebalancer treats it
  the same way).
- The drawdown the gate sees is the one of the risk manager's current
  view, which the engine refreshes with `update_portfolio_value()` at the
  end of every bar. A breach that happens on a bar is therefore seen by
  the gate on the next bar. That is the same one-bar lag the position
  count gate has, and it should be documented rather than worked around.

`quant_trading/backtest/engine.py`:
- No change is needed. The engine sizes and executes the trades; the gate
  rejects the ones that are not allowed, exactly like the other limits.

`tests/test_risk_manager.py`:
- A new test class (e.g. `TestDrawdownGate`) that pins:
  - a buy that would add exposure is rejected while the portfolio is in a
    drawdown breach;
  - a short that would add exposure is rejected while the portfolio is in
    a drawdown breach;
  - a buy that covers an open short is allowed while the portfolio is in a
    drawdown breach;
  - a buy is allowed while the portfolio is inside the drawdown limit;
  - a `max_drawdown` of `0.0` disables the check;
  - the check uses the drawdown of the risk manager's current view (a
    `sync_position`/`update_portfolio_value` refresh moves it).

`tests/test_backtest_engine.py`:
- An end-to-end test: a backtest whose portfolio falls into a drawdown
  breach stops opening new positions, while the positions that are already
  open are still closed by their own exit signals.

`README.md`:
- The "Risk Limits" section names the limits the signal gate enforces;
  add the drawdown to that list and say that a portfolio in a drawdown
  breach does not open new positions, while it can still close them.
- The risk limit table says "Drawdown from the peak that halts trading":
  say that the whole backtest only stops when
  `halt_on_portfolio_violation` is set.

Constraints:
- Do not change the other limits, the levels, the signal gate's post-trade
  arithmetic or the engine's sizing.
- Do not change the default of `halt_on_portfolio_violation`: flipping it
  would change the results of every existing backtest, and the gate is the
  place where a risk limit belongs.
- Reconcile: run `pytest -q`, `ruff check .`, `black --check quant_trading/
  tests/ examples/`, `mypy quant_trading/`.
