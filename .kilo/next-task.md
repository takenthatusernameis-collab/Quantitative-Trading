# Next Task

## What changed (this session)

Executed the prior handoff's assigned task: make the rebalancer's generated
actions affordable. Investigation showed the affordability machinery
(`_RebalancePlan`, `_plan_buy`, `_plan_sell`) was already implemented in
`generate_rebalance_actions` and works correctly — verified with the measured
scenario (`cash=100000`, `target_allocation={"AAPL": 0.5, "MSFT": 0.5}`,
`prices={"AAPL": 100.0, "MSFT": 200.0}`, `commission=0.001`, `slippage=0.0005`):
cash ends at ~0 (positive), not -150. The remaining gap was test coverage for
this affordability behavior and a few provably unreachable branches.

- **Restructured `if quantity > 0 and price > 0:`** to nested
  `if quantity > 0:` / `if price > 0:` at `rebalancer.py:349-351` (target
  allocation buy) and `rebalancer.py:388-390` (signal buy). `quantity > 0`
  implies `price > 0` (both come from the same `_resolve_plan_price` call), so
  the `price > 0` check when `quantity > 0` is provably unreachable and is
  marked `# pragma: no cover`.
- **Added `# pragma: no cover`** to `_plan_sell`'s `price <= 0` early return
  (`rebalancer.py:656`) — price is always > 0 when `_plan_sell` is called from
  `generate_rebalance_actions` because `_resolve_sell_quantity` requires a
  positive holding price and `_resolve_execution_price` resolves from the same
  source.
- **Added 10 new tests** to `tests/test_rebalancer_execution.py`:
  - `test_generated_actions_are_affordable` (5 fixed seeds): generates actions
    for random target allocations, executes with random commission/slippage,
    asserts `portfolio.cash >= 0`, `cash + market value == total value`, total
    value moved by exactly the fees, and every executed buy is affordable.
  - `test_generated_actions_affordable_with_high_fees`: 50% fee rate, cash
    stays non-negative.
  - `test_generated_actions_sell_funds_later_buy`: a sell earlier in the batch
    releases cash a later buy can use.
  - `test_plan_sell_size_zero_after_prior_sell`: `_plan_sell` early return
    when `size <= 0` (position already sold by an earlier action in the batch).
  - `test_plan_sell_against_short_position_costs_cash`: `_plan_sell` else
    branch for short positions (position < 0 costs cash).
  - `test_signal_buy_unaffordable_when_cash_exhausted`: `_plan_buy` returns 0
    when cash is exhausted, so no signal buy action is emitted.

## What was actually verified (this session)

- `python -m pytest tests/ -q` → **1436 passed, 1 skipped** (baseline at the
  start of this session: 1426 passed, 1 skipped; the +10 are the new tests).
- `python -m coverage run --branch -m pytest tests/ -q` +
  `python -m coverage report -m` → **100% statement and branch coverage** for
  the whole package (4601 statements, 1470 branches, 0 missed).
  `quant_trading/portfolio/rebalancer.py` is at 194/194 statements and 84/84
  branches.
- `python -m ruff check .` → All checks passed.
- `python -m black --check quant_trading tests` → clean (68 files unchanged).
- `python -m mypy quant_trading` → Success: no issues found in 36 source files.

## What remains unresolved

- **`Portfolio.get_allocation()` returns negative weights for shorts** (a
  short's market value is negative), so `summary()["allocation"]` can contain
  negative fractions. Left unchanged: consistent with the sign of the market
  value, but not a usable allocation for a short book.
- **Shorts are still unreachable in production.** The engine only ever buys
  (`quant_trading/backtest/engine.py:548`) and only sells an existing long
  (`engine.py:581`), and `execute_actions` deliberately only *reduces*
  exposure, so no production code path opens a short. The short branches are
  exercised by the tests only.
- **The `Rebalancer` is not wired to the `RiskManager`.** Buy sizes are not
  checked against the position limit, the daily loss limit or the available
  cash. `BacktestEngine` does use the risk manager, but the rebalancer does
  not.
- **No CI workflow runs the test suite**, so the new invariants only execute
  when an agent runs pytest locally. The Kilo controller stages with
  `':(exclude).github/workflows/**'` (`.github/scripts/kilo-controller.sh:327`),
  so a workflow file added by an agent would never be committed by the
  controller — do not spend a session on it.
- `tests/test_portfolio_rebalancer.py` is still the only file `black` would
  reformat (pre-existing, deliberately left untouched to avoid unrelated
  modifications).
- 100% line/branch coverage is not behavioural verification. The new
  invariants cover long and short books with random commissions and slippage,
  but they still assume cash-only settlement (no margin, no borrow cost, no
  dividends).

## Approaches already failed

- The previous two sessions both ended with "add regime detector tests"; the
  second attempt re-applied an already-applied patch and broke the package
  import (commit `01eb720`). That line of work was closed because
  `tests/test_regime.py` already gives `quant_trading/regime/detector.py` 100%
  branch coverage.
- The previous session's handoff described a code state the controller had
  already committed. **Read the code and the git log before acting on a
  handoff.** (Re-checked this session: the handoff was accurate about
  `execute_actions` being present, but the affordability defect it described
  had already been fixed by the `_RebalancePlan`/`_plan_buy`/`_plan_sell`
  machinery — the remaining work was test coverage, not implementation.)
- The prior handoff's bullet relation for `unrealized_pnl` was wrong for
  shorts; the correct, verified relation is
  `unrealized_pnl == abs(quantity) * abs(avg_cost) * unrealized_pnl_pct`.

## One precise next task

**Wire the `Rebalancer` to the `RiskManager` so buy sizes are checked against
the position limit, daily loss limit, and available cash before actions are
generated.**

Evidence and rationale:

- The rebalancer is the portfolio management layer but ignores the risk
  manager entirely (`quant_trading/portfolio/rebalancer.py` has no reference to
  `RiskManager`). `BacktestEngine` uses the risk manager, but the rebalancer
  does not, so generated actions can violate risk limits.
- This is bounded (add a `risk_manager` parameter to `Rebalancer.__init__`,
  check limits in `generate_rebalance_actions` before emitting buy actions,
  add tests), deterministic, network-free.
- The `RiskManager` already exists at `quant_trading/risk/manager.py` with
  methods for position limits and daily loss limits.

Steps:

1. Add an optional `risk_manager: RiskManager | None = None` parameter to
   `Rebalancer.__init__`.
2. In `generate_rebalance_actions`, before emitting a buy action, check the
   risk manager's position limit and daily loss limit; skip or size down the
   buy if it would violate a limit.
3. Add tests to `tests/test_portfolio_rebalancer.py` covering risk-limit-aware
   action generation.
4. Verify with `python -m pytest tests/ -q` (baseline: **1436 passed, 1
   skipped**), `python -m coverage run --branch -m pytest tests/ -q` &&
   `python -m coverage report -m` (must stay at 100%), `python -m ruff check
   .`, `python -m black --check quant_trading tests` and `python -m mypy
   quant_trading`.

Constraints:

- **Do not run `git commit`.** The Kilo controller stages and commits the
  working tree itself (`.github/scripts/kilo-controller.sh:327`, `:401`) and
  treats a session without a non-empty staged diff as *no project progress*
  (`:390-395`, `:570`). Leave the changes in the working tree and in
  `.kilo/next_task.md` / `.kilo/next-task.md` (keep the two files identical).
- Deterministic: fixed seeds only, no network, no unseeded randomness.
- If an invariant fails, **do not weaken the assertion to make it pass**:
  determine whether the implementation or the invariant is wrong, keep the
  evidence in the handoff, and keep `tests/test_portfolio.py`,
  `tests/test_portfolio_invariants.py`, `tests/test_cost_accounting_invariants.py`,
  `tests/test_holding_pnl_invariants.py` and `tests/test_rebalancer_execution.py`
  green for any implementation change.
- Repo conventions: tests live in `tests/`, use `pytest.approx`, black line
  length 100, `# pragma: no cover` only for provably unreachable branches.
