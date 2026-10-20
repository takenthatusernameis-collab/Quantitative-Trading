# Next Task

## What changed

**The assigned task (wire `config.risk` and `config.portfolio.max_positions`
into the `RiskManager` built by `BacktestEngine.__init__`) is implemented.**

- `BacktestEngine.__init__` now accepts `BacktestConfig | Config | None`.
  When a full `Config` is supplied, its `risk` and `portfolio` sub-configs
  drive the default `RiskManager`; when only a `BacktestConfig` is supplied,
  the `RiskManager` defaults are used (backward compatible).
- `self.config` is normalized to a `BacktestConfig` so every existing
  `self.config.*` access (commission, slippage, risk_free_rate, etc.)
  keeps working unchanged.
- `quant_trading/backtest/engine.py:303-353` constructs
  `RiskManager(initial_capital=..., max_position_size=..., max_portfolio_risk=...,
  max_leverage=..., stop_loss_pct=..., take_profit_pct=..., max_drawdown=...,
  max_positions=...)` from the config, so the YAML `risk:` block is no longer
  inert. `check_signal()` already gates on `max_portfolio_risk` and
  `max_leverage`, so the limits actually bind.

## Verified

- `pytest` (default run, includes `quant_trading/` doctests):
  **1632 passed, 1 skipped, 0 failed** (baseline before this session: 1629
  passed, 1 skipped; delta = the 3 new tests below).
- `ruff check .`: clean.
- `mypy quant_trading/`: clean (36 source files).
- `black --check quant_trading/ tests/`: clean (69 files).

New tests in `tests/test_integration.py`:

- `test_full_config_drives_risk_manager`: a `Config` with a tight
  `max_portfolio_risk=0.001` rejects every buy (0 trades opened), proving the
  YAML risk block is not inert.
- `test_backtest_config_only_uses_risk_defaults`: a bare `BacktestConfig`
  still builds a `RiskManager` with the default limits (0.02 risk, 1.0x
  leverage, 20 positions).
- `test_caller_supplied_risk_manager_wins_over_config`: an explicit
  `risk_manager=` argument overrides the config-driven default.

## Remaining unresolved

- **`RiskManager.portfolio_risk.leverage` is net** (`positions_value /
  total_value`) while `PortfolioLimit.leverage()` is gross. Both docstrings
  say which is which; the names collide, so a reader can easily confuse them.
  Not changed here because `PortfolioRisk.leverage` is public API with
  existing tests.
- **The backtest engine cannot open or close shorts.** `_process_signal` only
  buys (`quantity = available_value / price`) and the sell path returns early
  for `holding.quantity <= 0`, so a short can only appear via a hand-seeded
  portfolio.
- The portfolio risk budget / leverage limit gate new buys in `check_signal()`
  but remain advisory elsewhere: `check_portfolio()` is report-only and the
  backtest only stops when `halt_on_portfolio_violation=True` (default
  `False`).
- `config.portfolio.max_positions` is now wired into the `RiskManager`, but
  the engine does not halt when the limit is breached; it is only enforced
  through `check_signal()` (which does not count positions) and the
  report-only `check_portfolio()`.

## Approaches already tried and rejected

- Changing the default `max_portfolio_risk` (0.02) or `max_leverage` (1.0) to
  make the limits "less binding": rejected. The values were already the
  documented defaults, and a probe of ordinary long-only backtests showed
  0 violations, so the defaults are not causing false alarms.
- Enforcing the portfolio risk budget by *shrinking* orders inside
  `PortfolioLimit.check()`: rejected. `check()` is a pure reporting API
  (`-> list[str]`); sizing belongs in the order path.
- Normalizing `self.config` to a full `Config` instead of a `BacktestConfig`:
  rejected. It would break every existing caller that passes a bare
  `BacktestConfig` (all examples and most tests) and add no value over
  keeping `self.config` as a `BacktestConfig` and deriving the risk/portfolio
  sub-configs separately in `__init__`.

## Next task (precise)

**Decide whether `config.portfolio.max_positions` should halt the backtest
when breached, and if so, wire that into the run loop.**

Evidence/constraints carried forward:

- `max_positions` is now loaded from YAML and forwarded to the
  `RiskManager` via `BacktestEngine.__init__`, but the engine only enforces it
  through the report-only `check_portfolio()` call at
  `quant_trading/backtest/engine.py:437-440`. With
  `halt_on_portfolio_violation=False` (the default), a breach is recorded in
  `result.portfolio_violations` but the run continues.
- The existing `test_halt_on_portfolio_violation_stops_backtest` test uses a
  caller-supplied `RiskManager(max_positions=0)` and `halt_on_portfolio_violation=True`
  to prove halting works; a config-driven equivalent would be the natural
  follow-up.
- If halting is added, keep `risk_manager` constructor override supported
  (caller-supplied `RiskManager` still wins) and add a test proving a YAML
  `portfolio.max_positions: 1` halts a multi-symbol backtest.