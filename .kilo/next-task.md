# Next Task

## What changed

**The task assigned by the previous session (enforce `max_portfolio_risk` and
`max_leverage` in `PortfolioLimit.check()`) was already implemented in HEAD**
(commit `859fb23`, which carried an empty commit message and did not refresh
this file). This session verified that implementation, found and fixed a
related hole in the same enforcement code, and refreshed the handoff.

### 1. Verified the assigned task (no change needed)

`quant_trading/risk/limits.py` now measures

- **portfolio risk** = `sum(|quantity| * entry_price * stop_loss_pct)` over all
  open positions, as a fraction of the portfolio value, and
- **leverage** = `sum(|market_value|)` (gross) / portfolio value,

and `PortfolioLimit.check()` reports `Portfolio risk X% exceeds max Y%` and
`Portfolio leverage X.XXx exceeds max Y.YYx` violations. `RiskManager` forwards
`max_leverage` and `stop_loss_pct` to the portfolio limit, and
`RiskConfig.max_leverage` exists in the YAML config.

### 2. Fixed: short positions bypassed every concentration limit

**Evidence (before the fix).** `PositionLimit.check()` and the per-position
check inside `PortfolioLimit.check()` divided the *signed* market value by the
portfolio value. A short position has a negative market value, so its share
was negative and could never exceed a limit:

```python
short = Position(symbol="AAPL", quantity=-6000, avg_price=150.0, current_price=150.0)
PositionLimit(max_size=0.1, max_value=50_000.0).check(short, 1_000_000.0)
# -> []            (a $900,000 short against a $1,000,000 portfolio)
PortfolioLimit(max_position_size=0.1, ...).check({"AAPL": short}, 1_000_000.0, 1_000_000.0)
# -> []            (the same exposure long is reported)
```

That contradicted the gross-exposure semantics the new leverage check uses
(and the README documents): a short of 90% of the portfolio passed the 10%
position limit, and the `max_value` dollar limit was skipped entirely
(negative > positive is false).

**The fix.** `quant_trading/risk/limits.py` gained a `gross_exposure(position)`
helper (`abs(market_value)`, exported from `quant_trading.risk`). Both
concentration checks now use it:

- `PositionLimit.check()` measures `position_value` and `position_pct` gross.
- `PortfolioLimit.check()` measures the per-position share gross.
- `PortfolioLimit.leverage()` reuses the same helper (it was already gross).

Nothing else changed: the rebalancer's `_risk_adjust_buy` sizing is already
consistent with gross semantics (`room = max_position_value - current_position
* price` is exactly the gross constraint for a buy), so the two now agree.

### 3. Tests (8 new) and doctests

- `tests/test_limits.py::TestPositionLimitGrossExposure` (5 tests) and
  `::TestPortfolioLimitGrossExposure` (3 tests): short size violation, short
  value violation, short within limits, long/short equivalence, an offsetting
  short not hiding the long, and the `gross_exposure` helper.
- New executable doctests in `quant_trading/risk/limits.py`: a short position
  reported by `PositionLimit.check()` and by `PortfolioLimit.check()`.
- The 5 behavioural tests were confirmed to **fail before** the fix and pass
  after it (verified by reverting the two lines, running the new tests, and
  restoring the fix).

### 4. README

`README.md` "Risk Limits": documented that `max_position_size` (and
`PositionLimit`'s `max_size`/`max_value`) are measured on gross exposure, that
the risk budget implies a maximum open exposure
(`max_portfolio_risk / stop_loss_pct` = 40% with the defaults), and that the
portfolio-level limits are reported on a check rather than resizing orders.

### 5. Formatting

`black --check quant_trading/ tests/` was already failing on two untouched
files (`quant_trading/strategies/examples.py`, `tests/test_portfolio.py`).
Both were reformatted (formatting only, no behaviour change) so the
repo-wide formatting check is green again.

## Verified

- `pytest` (default run, includes the `quant_trading/` doctests):
  **1627 passed, 1 skipped, 0 failed** (baseline before this session:
  1619 passed, 1 skipped; the delta is the 8 new unit tests).
- `pytest --doctest-modules quant_trading/risk/limits.py -v`: 3 passed
  (module, `PortfolioLimit`, `PositionLimit`).
- `python -m doctest -v quant_trading/risk/limits.py`: the new short-position
  examples execute and pass.
- `ruff check .`: clean.
- `mypy quant_trading/`: clean (36 source files).
- `black --check quant_trading/ tests/`: clean (69 files).
- Behavioural probe (synthetic data, 1/3/5/10 symbols, MA crossover, default
  `RiskManager`): 0 portfolio violations, i.e. the newly enforced limits do not
  fire in an ordinary long-only backtest, so the previous session's change did
  not silently alter default backtest behaviour.

## Remaining unresolved

- **The portfolio risk budget and the leverage limit are still advisory.** They
  are detected by `PortfolioLimit.check()` and surfaced by
  `RiskManager.check_portfolio()`, but they never influence an order:
  `RiskManager.check_signal()` (the gate the backtest engine uses at
  `quant_trading/backtest/engine.py:523`) only checks the *single position*
  limits, and `Rebalancer._risk_adjust_buy`
  (`quant_trading/portfolio/rebalancer.py:655`) only applies the position
  limit and the drawdown halt. A strategy can keep opening positions until the
  post-hoc check reports a breach, and the backtest only stops when
  `halt_on_portfolio_violation=True` (default `False`). This is the next task
  (below).
- **The YAML `risk:` block is inert.** `Config.risk` (`RiskConfig`) is loaded
  from `config.yaml` and documented in the README, but nothing applies it:
  `BacktestEngine.__init__` builds `RiskManager(initial_capital=...)` with
  default limits (`quant_trading/backtest/engine.py:319`), and `Rebalancer`
  takes a `RiskManager` the caller must build. `max_position_size: 0.2` in
  `config.yaml` therefore has no effect on a backtest. Separate task.
- **`RiskManager.portfolio_risk.leverage` is net** (`positions_value /
  total_value`) while `PortfolioLimit.leverage()` is gross. Both docstrings
  say which is which; the names collide, so a reader can easily confuse them.
  Not changed here because `PortfolioRisk.leverage` is public API with
  existing tests.
- **The backtest engine cannot open or close shorts.** `_process_signal` only
  buys (`quantity = available_value / price`) and the sell path returns early
  for `holding.quantity <= 0`, so a short can only appear via a hand-seeded
  portfolio. The gross-vs-signed fixes above are therefore only reachable
  through the rebalancer and direct limit checks today.

## Approaches already tried and rejected

- Changing the default `max_portfolio_risk` (0.02) or `max_leverage` (1.0) to
  make the limits "less binding": rejected. The values were already the
  documented defaults of `PortfolioLimit`/`RiskConfig` before the previous
  session started enforcing them, and a probe of ordinary long-only backtests
  showed 0 violations, so the defaults are not causing false alarms.
- Enforcing the portfolio risk budget by *shrinking* orders inside
  `PortfolioLimit.check()`: rejected. `check()` is a pure reporting API
  (`-> list[str]`) used by `check_portfolio()`; changing it into a mutating
  or sizing API would break the existing contract. The sizing belongs in the
  order path, which is the next task.

## Next task (precise)

**Make the portfolio risk budget and the leverage limit gate new buys, in
`RiskManager.check_signal()` (`quant_trading/risk/manager.py:238-256`).**

Evidence/constraints carried forward:

- `check_signal()` currently only rejects a buy that would breach
  `position_limit.max_size` / `max_value`. It does not look at
  `portfolio_limit.max_portfolio_risk` or `portfolio_limit.max_leverage`, so
  the limits the previous session added are detected only after the fact.
- The manager already has everything needed: `self.positions`,
  `self.portfolio_risk.total_market_value` and
  `self.portfolio_limit.portfolio_risk_pct()` / `.leverage()`. Compute the
  post-trade values (the buy adds `|quantity| * price * stop_loss_pct` of
  risk and `quantity * price` of gross exposure) and reject the signal when
  they would exceed the budget.
- Keep the existing report-only semantics of `PortfolioLimit.check()`; do not
  weaken the current position-limit enforcement; keep the "buy may not exceed
  the position limit" messages unchanged so existing tests keep passing.
- Follow-up inside the same area: `Rebalancer._risk_adjust_buy` should shrink
  a buy to fit the same budget (it already shrinks to fit the position limit
  and halts on drawdown) — do this only if the signal-path change is done and
  verified.
- `pytest` collects the `quant_trading/` doctests, so any new docstring
  example must be executable. Run `pytest` (no path argument), then
  `ruff check .`, `mypy quant_trading/` and `black --check quant_trading/
  tests/`.
