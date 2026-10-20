# Next Task

## What changed (this session)

Executed the prior handoff's assigned task: added `Rebalancer.execute_actions`
to apply `RebalanceAction` objects to the portfolio and locked it in with
seeded, randomized property tests.

- **Added `Rebalancer.execute_actions`** (`quant_trading/portfolio/rebalancer.py:360`).
  - "buy" calls `portfolio.add_holding` with a positive quantity; "sell"
    reduces long positions via `portfolio.remove_holding` (capped reductions,
    fully offset positions removed) or covers shorts via `add_holding`, and
    if there is no position it creates a short via the fallback `add_holding`.
  - "hold" and non-positive quantities are no-ops (actions still recorded).
  - Price is resolved from the `prices` map, falling back to the holding's
    `current_price`; actions are skipped if no valid price is available.
  - Commission/slippage are forwarded to portfolio methods. Executions are
    appended to `rebalance_history` with `executed: True` and
    `last_rebalance` is updated. The method returns the executed actions.
- **Created `tests/test_rebalancer_execution.py`** (23 tests) with fixed-seed
  RNGs: basic buy/sell/hold, capped sell removal, short cover and short-creation
  fallback, history updates, price fallbacks, and seeded randomized invariants
  (5 seeds × ~multiple steps) asserting cash + holdings == total value, no
  zero-quantity holdings, `summary()["num_positions"] == len(portfolio.holdings)`,
  and basis averaging on additional buys.

## What was actually verified (this session)

- `python -m pytest tests/ -q` → **1423 passed, 1 skipped** (baseline from
  prior handoff: **1400 passed, 1 skipped**; +23 new tests).
- `python -m coverage run --branch -m pytest tests/ -q` +
  `python -m coverage report -m` → **99% total** (4549 statements, 5 missed;
  1468 branches, 2 partial). `quant_trading/portfolio/rebalancer.py` is **99%**
  (142 statements, 0 missed, 82 branches, 1 partial branch `410->438` which is
  not reachable from current tests).
- `python -m ruff check .` → All checks passed.
- `python -m black --check quant_trading tests` → clean except
  `tests/test_portfolio_rebalancer.py` (pre-existing drift, untouched — not
  in git status).
- `python -m mypy quant_trading` → Success: no issues found in 36 source files.

## What remains unresolved

- **`tests/test_portfolio_rebalancer.py` is still the only file `black` would
  reformat** (pre-existing, deliberately left untouched).
- **The rebalancer execution path now exercises portfolio logic**, but there is
  still no higher-level orchestration wiring actions into a "rebalance and
  apply" flow beyond `execute_actions` itself. No production code calls
  `execute_actions` yet.
- **No CI workflow runs the test suite** (Kilo controller stages with
  `:(exclude).github/workflows/**`), so new tests only run locally.
- 100% line/branch coverage not required; remaining partial branch in
  `rebalancer.py` is not safely exercisable without changing behavior.

## Approaches already failed

- None this session. Implementation matched the portfolio semantics fixed in
  the prior handoff (capped reductions, no flips, basis preserved for longs,
  shorts handled via existing portfolio rules).

## One precise next task

**Add support for executing actions with a per-action price override and
record executed quantities/costs in `rebalance_history`, with seeded
invariant tests.**

Evidence and rationale:

- `RebalanceAction` only stores `symbol`, `action`, `quantity`, `reason`,
  `timestamp`. `execute_actions` currently records the action list and
  portfolio value but does not record per-action executed quantity, price,
  fees, or cash impact.
- The randomized invariants in `tests/test_rebalancer_execution.py` already
  assert portfolio-level invariants; adding execution details to history would
  make debugging and verification easier and would let tests assert fee
  accounting matches `Portfolio` behavior.
- Bounded change: extend `RebalanceAction` (optional fields) or store
  execution records in history; update `execute_actions` to capture
  `executed_quantity` and effective price; add fixed-seed tests asserting
  recorded values match the portfolio deltas.

Steps:

1. Extend `RebalanceAction` with optional `executed_quantity: float | None = None`
   and/or record execution details in `rebalance_history` entries (per-action
   dicts with symbol/action/quantity/executed_quantity/price/cash_effect).
2. Update `execute_actions` to compute and record these details (using prices
   resolved from map/holding).
3. Add `tests/test_rebalancer_execution_details.py` with fixed seeds asserting
   history records match observed cash/value changes and respect caps (sell
   more than held → executed_quantity capped).
4. Verify with `python -m pytest tests/ -q` (baseline: **1423 passed, 1
   skipped**), `python -m coverage run --branch -m pytest tests/ -q &&
   python -m coverage report -m`, `python -m ruff check .`,
   `python -m black --check quant_trading tests` and `python -m mypy
   quant_trading`.

Constraints:

- **Do not run `git commit`.** The Kilo controller stages and commits the
  working tree itself; leave changes in working tree and keep
  `.kilo/next-task.md` and `.kilo/next_task.md` identical.
- Deterministic: fixed seeds only, no network.
- Do not weaken assertions to make failures pass; if portfolio behavior
  conflicts with recorded details, keep evidence in handoff.
- Repo conventions as before.
