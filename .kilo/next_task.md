# Next Task

## What changed (this session)

**Wired the `Rebalancer` to the `RiskManager`** so buy sizes are checked against the position limit, the drawdown (loss) limit, and available cash before actions are generated.

- `Rebalancer.__init__` gained an optional `risk_manager: RiskManager | None = None` parameter (`quant_trading/portfolio/rebalancer.py:229`). Stored on `self.risk_manager`; defaults to `None`, in which case behavior is unchanged.
- `generate_rebalance_actions` now runs every buy (target-allocation and signal) through a new `_risk_adjust_buy` helper before `_plan_buy` (`rebalancer.py:360`, `rebalancer.py:401`). The helper:
  - returns the quantity unchanged when no risk manager is configured or it is disabled;
  - returns 0.0 (drops the buy) when the portfolio's drawdown is at or beyond `portfolio_limit.max_drawdown`;
  - otherwise caps the quantity so the resulting position value stays within `min(position_limit.max_size * total_value, position_limit.max_value)`, dropping the buy when no room remains.
  - Cash affordability continues to be enforced by `_plan_buy`, so emitted actions remain affordable.
- Added 13 tests to `tests/test_portfolio_rebalancer.py` (class `TestRebalancerRiskLimits` plus a multi-signal batch-skip test): risk manager stored/defaults to None, behavior unchanged without one, position-limit sizing down, tighter of fraction vs dollar cap wins, no room skips the buy, drawdown limit halts buys, drawdown within limit still buys, zero drawdown limit skips the loss check, disabled risk manager buys as usual, signal buy respects the position limit, risk-limited buy executes with non-negative cash, and a non-sizeable signal in a batch is skipped while later signals still trade.

## What was actually verified (this session)

- `python -m pytest tests/ -q` → **1449 passed, 1 skipped** (baseline: 1436 passed, 1 skipped; +13 new tests).
- `python -m coverage run --branch -m pytest tests/ -q` + `python -m coverage report -m` → **100% statement and branch coverage** (4620 statements, 1480 branches, 0 missed). `quant_trading/portfolio/rebalancer.py` at 213/213 statements and 94/94 branches.
- `python -m ruff check .` → all checks passed.
- `python -m black --check quant_trading tests` → clean (68 files unchanged).
- `python -m mypy quant_trading` → success, no issues in 36 source files.
- `git status` shows only the two intended files modified; no commit was made (the Kilo controller commits the working tree itself).

## What remains unresolved

- **`Portfolio.get_allocation()` returns negative weights for shorts** (a short's market value is negative), so `summary()["allocation"]` can contain negative fractions. Left unchanged: consistent with the sign of the market value, but not a usable allocation for a short book.
- **Shorts are still unreachable in production.** The engine only ever buys (`quant_trading/backtest/engine.py:548`) and only sells an existing long (`engine.py:581`), and `execute_actions` deliberately only *reduces* exposure, so no production code path opens a short. The short branches are exercised by the tests only.
- **No CI workflow runs the test suite**, so the invariants only execute when an agent runs pytest locally. The Kilo controller stages with `':(exclude).github/workflows/**'` (`.github/scripts/kilo-controller.sh:327`), so a workflow file added by an agent would never be committed by the controller — do not spend a session on it.

## Approaches already failed

- The previous two sessions both ended with "add regime detector tests"; the second attempt re-applied an already-applied patch and broke the package import (commit `01eb720`). That line of work was closed because `tests/test_regime.py` already gives `quant_trading/regime/detector.py` 100% branch coverage.
- The previous session's handoff described a code state the controller had already committed. **Read the code and the git log before acting on a handoff.** (Re-checked this session: the handoff was accurate about `execute_actions` being present, but the affordability defect it described had already been fixed by the `_RebalancePlan`/`_plan_buy`/`_plan_sell` machinery — the remaining work was test coverage, not implementation.)
- The prior handoff's bullet relation for `unrealized_pnl` was wrong for shorts; the correct, verified relation is `unrealized_pnl == abs(quantity) * abs(avg_cost) * unrealized_pnl_pct`.
- Marking the signal-site `if quantity > 0:` False branch with `# pragma: no cover` was considered and rejected: a negative `signal.price` is truthy, passes the `diff > 0 and signal.price` guard, then resolves to a non-positive plan price, so `_resolve_buy_quantity` can return 0.0. The branch is real and is covered by `test_zero_quantity_signal_in_batch_skipped` (negative first price in a two-signal batch).

## One precise next task

**Add end-to-end solvency tests proving a risk-managed `Rebalancer` followed by `execute_actions` keeps the portfolio cash non-negative and all positions within risk limits across multiple rebalance rounds.**

Evidence and rationale:

- `generate_rebalance_actions` now risk-sizes buys, but there is no test that repeatedly rebalances (new `generate_rebalance_actions` + `execute_actions` round) with a `RiskManager` in place and asserts invariants after every round: `portfolio.cash >= 0`, `cash + holdings value == total value`, every position value within `min(max_size * total_value, max_value)`, and every executed buy affordable.
- Bounded, deterministic, network-free: fixed seeds only, synthetic portfolios and prices, no network.
- Reuse `tests/test_portfolio_rebalancer.py` (or a new `test_rebalancer_risk_integration.py`) and the `_risk_manager`/`_empty_portfolio` helpers already present.

Steps:

1. Write a test that, across several fixed-seed rebalance rounds, generates risk-aware actions and executes them, asserting cash non-negativity, the cash+holdings-value identity, and per-position limit compliance after every round.
2. Include a round where the drawdown limit is breached and assert no buy actions are generated while sells still work.
3. Verify with `python -m pytest tests/ -q` (baseline: **1449 passed, 1 skipped**), `python -m coverage run --branch -m pytest tests/ -q` && `python -m coverage report -m` (must stay at 100%), `python -m ruff check .`, `python -m black --check quant_trading tests` and `python -m mypy quant_trading`.

Constraints:

- **Do not run `git commit`.** Leave the changes in the working tree and keep `.kilo/next_task.md` and `.kilo/next-task.md` identical.
- Deterministic: fixed seeds only, no network, no unseeded randomness.
- Keep `tests/test_portfolio.py`, `tests/test_portfolio_invariants.py`, `tests/test_cost_accounting_invariants.py`, `tests/test_holding_pnl_invariants.py` and `tests/test_rebalancer_execution.py` green.
- Repo conventions: tests live in `tests/`, use `pytest.approx`, black line length 100, `# pragma: no cover` only for provably unreachable branches.
