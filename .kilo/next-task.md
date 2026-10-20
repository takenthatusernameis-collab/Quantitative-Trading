# Next Task

## What changed

**The assigned task (make the portfolio risk budget and leverage limit gate new
buys in `RiskManager.check_signal()`) was already implemented in HEAD**
(commit `d287e00`, which added the gating block; commit `b053112` only removed
an unused `gross_exposure` import). The gating block at
`quant_trading/risk/manager.py:258-275` rejects a buy when the post-trade
portfolio risk (`current_risk + buy_value * stop_loss_pct / value`) would
exceed `max_portfolio_risk`, or when post-trade gross leverage
(`current_gross + buy_value / value`) would exceed `max_leverage`.

**This session verified the assigned task and added signal-path tests.**

- `tests/test_risk_manager.py::TestCheckSignal::test_buy_exceeds_portfolio_risk_budget`
  and `::test_buy_exceeds_leverage_limit`: confirm `check_signal` rejects a buy
  that would breach the portfolio risk budget / leverage limit.
- Confirmed non-vacuous: both tests **fail** when the gating block is
  temporarily removed and **pass** with it restored.
- `PositionLimit.check()` / `PortfolioLimit.check()` already measure gross
  exposure (commit `7a81504`), so shorts are limited like longs.

## Verified

- `pytest` (default run, includes `quant_trading/` doctests):
  **1629 passed, 1 skipped, 0 failed** (baseline before this session: 1627
  passed, 1 skipped; delta = the 2 new unit tests).
- `ruff check .`: clean.
- `mypy quant_trading/`: clean (36 source files).
- `black --check quant_trading/ tests/`: clean (69 files).

## Remaining unresolved

- **The YAML `risk:` block is inert.** `Config.risk` (`RiskConfig`) is loaded
  from `config.yaml` and documented in the README, but nothing applies it:
  `BacktestEngine.__init__` builds `RiskManager(initial_capital=...)`
  with hardcoded defaults
  (`quant_trading/backtest/engine.py:319`), so `max_position_size: 0.2` in
  `config.yaml` has no effect on a backtest. `config.portfolio.max_positions`
  is likewise ignored. This is the next task (below).
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
  backtest only stops when `halt_on_portfolio_violation=True` (default `False`).

## Approaches already tried and rejected

- Changing the default `max_portfolio_risk` (0.02) or `max_leverage` (1.0) to
  make the limits "less binding": rejected. The values were already the
  documented defaults, and a probe of ordinary long-only backtests showed
  0 violations, so the defaults are not causing false alarms.
- Enforcing the portfolio risk budget by *shrinking* orders inside
  `PortfolioLimit.check()`: rejected. `check()` is a pure reporting API
  (`-> list[str]`); sizing belongs in the order path.

## Next task (precise)

**Wire `config.risk` (`RiskConfig`) and `config.portfolio.max_positions` into
the `RiskManager` built by `BacktestEngine.__init__`
(`quant_trading/backtest/engine.py:319-321`), so YAML-configured risk limits
take effect in backtests.**

Evidence/constraints carried forward:

- `BacktestEngine.__init__` currently constructs
  `RiskManager(initial_capital=self.config.initial_capital)` only, ignoring
  `self.config.risk.max_position_size`, `.max_portfolio_risk`, `.max_leverage`,
  `.stop_loss_pct`, `.max_drawdown` and `self.config.portfolio.max_positions`.
- Pass them through: `RiskManager(initial_capital=..., max_position_size=...,
  max_portfolio_risk=..., max_leverage=..., stop_loss_pct=..., max_drawdown=...,
  max_positions=...)`. `RiskManager.__init__` already forwards these to
  `PositionLimit`/`PortfolioLimit` and `check_signal()` now gates on
  `max_portfolio_risk` and `max_leverage`, so the limits will actually bind.
- Add a test proving a config with tight risk limits changes backtest behaviour
  (e.g. a low `max_portfolio_risk`/`max_leverage` causes `check_signal` to
  reject buys that default limits allow) and that default config is unchanged.
- Keep `risk_manager` constructor override supported (caller-supplied
  `RiskManager` still wins).
- `pytest` collects the `quant_trading/` doctests, so any new docstring
  example must be executable. Run `pytest` (no path argument), then
  `ruff check .`, `mypy quant_trading/` and `black --check quant_trading/
  tests/`.
