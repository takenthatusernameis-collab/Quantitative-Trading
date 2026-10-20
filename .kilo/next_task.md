# Next Task

## What changed (this session)

Executed the prior handoff's assigned task: make `Holding.unrealized_pnl_pct`
consistent with `Holding.unrealized_pnl` for short and zero-quantity positions,
and lock it in with seeded, randomized property tests.

- **Fixed `Holding.unrealized_pnl_pct`** (`quant_trading/portfolio/portfolio.py:79`).
  It is now the position's PnL as a fraction of its cost basis and carries the
  sign of the PnL:
  ``copysign(1.0, quantity) * (current_price - avg_cost) / avg_cost``, returning
  ``0.0`` when ``quantity == 0`` or ``avg_cost == 0``. A long and a short with
  the same prices are now mirror images (their `unrealized_pnl` and
  `unrealized_pnl_pct` are negations), and the relation
  ``unrealized_pnl == abs(quantity) * abs(avg_cost) * unrealized_pnl_pct``
  holds for every holding. `copysign` was already imported at `portfolio.py:30`.
- **Updated the `Holding` class docstring** to state the short convention
  explicitly, with long / short / zero-quantity examples.
- **Updated `tests/test_portfolio.py`**: added
  `test_unrealized_pnl_pct_short` (short mirrors the long, negated) and
  `test_unrealized_pnl_pct_zero_quantity` (returns 0.0). The existing
  `test_unrealized_pnl_pct` (long = 0.5) still passes unchanged.
- **Created `tests/test_holding_pnl_invariants.py`** (15 tests: 5 fixed seeds
  × 3 properties) using `numpy.random.default_rng(seed)`:
  - `unrealized_pnl_pct == 0.0` when `quantity == 0` or `avg_cost == 0`;
  - `unrealized_pnl == abs(quantity) * abs(avg_cost) * unrealized_pnl_pct`
    (within `pytest.approx`);
  - `sign(unrealized_pnl) == sign(unrealized_pnl_pct)` when both non-zero;
  - a long and a short with the same prices are mirror images (negations).

## What was actually verified (this session)

- `python -m pytest tests/ -q` → **1400 passed, 1 skipped** (baseline at the
  start of this session: 1383 passed, 1 skipped; the +17 are the 15 new
  invariant tests and the 2 new unit tests).
- `python -m coverage run --branch -m pytest tests/ -q` +
  `python -m coverage report -m` → **100% statement and branch coverage** for
  the whole package (4520 statements, 1450 branches, 0 missed). Both branches
  of the `quantity == 0 or avg_cost == 0` guard and both `copysign` signs are
  exercised.
- `python -m ruff check .` → All checks passed.
- `python -m black --check quant_trading tests` → clean except
  `tests/test_portfolio_rebalancer.py` (pre-existing drift, untouched — it is
  not in `git status`).
- `python -m mypy quant_trading` → Success: no issues found in 36 source files.

## What remains unresolved

- **`Portfolio.get_allocation()` returns negative weights for shorts** (a
  short's market value is negative), so `summary()["allocation"]` can contain
  negative fractions. Left unchanged; consistent with the sign of the market
  value but not a usable allocation for a short book.
- **The short-side portfolio fixes are test-only.** The engine only ever buys
  (`quant_trading/backtest/engine.py:548`) and only sells an existing long
  (`engine.py:567`), so no production code path reaches the short branches.
- **The `Rebalancer` emits `RebalanceAction` objects but never executes them**
  (`quant_trading/portfolio/rebalancer.py:298`), so the corrected reduction
  semantics are not exercised by the rebalancing path. There is no method that
  applies a `RebalanceAction` to the `Portfolio`.
- `tests/test_portfolio_rebalancer.py` is still the only file `black` would
  reformat (pre-existing, deliberately left untouched to avoid unrelated
  modifications).
- **No CI workflow runs the test suite**, so the new invariants only execute
  when an agent runs pytest locally. The Kilo controller stages with
  `':(exclude).github/workflows/**'` (`.github/scripts/kilo-controller.sh:327`),
  so a workflow file added by an agent would never be committed by the
  controller — do not spend a session on it.
- 100% line/branch coverage is not behavioural verification. The portfolio
  invariants now cover long and short books with random commissions and
  slippage, but they still assume cash-only settlement (no margin, no borrow
  cost, no dividends).

## Approaches already failed

- The previous two sessions both ended with "add regime detector tests"; the
  second attempt re-applied an already-applied patch and broke the package
  import (commit `01eb720`). That line of work was closed because
  `tests/test_regime.py` already gives `quant_trading/regime/detector.py` 100%
  branch coverage.
- The previous session's handoff described a code state the controller had
  already committed. **Read the code and the git log before acting on a
  handoff.**
- **This session:** no failures — the implementation, the existing long-only
  test, and the new property tests all agree. The literal bullet relation in
  the prior handoff (`unrealized_pnl == quantity * abs(avg_cost) *
  unrealized_pnl_pct`) was wrong for shorts (missing a `sign`/`abs` on
  quantity); the correct, verified relation is
  `unrealized_pnl == abs(quantity) * abs(avg_cost) * unrealized_pnl_pct`, which
  matches the prose ("PnL as a fraction of cost basis", mirror images, sign
  consistency).

## One precise next task

**Add an `execute_actions` method to `Rebalancer` that applies each
`RebalanceAction` to the portfolio, and lock it in with seeded, randomized
property tests.**

Evidence and rationale:

- `Rebalancer.generate_rebalance_actions()` (`rebalancer.py:192`) builds
  `RebalanceAction` objects (`action` in `{"buy", "sell", "hold"}`,
  non-negative `quantity`, `reason`, `symbol`) but nothing in
  `quant_trading/` ever executes them (`rebalancer.py:298` just returns the
  list). The corrected `Portfolio.add_holding`/`remove_holding` reduction
  semantics (capped reductions, no flip, no phantom cash, basis preserved) are
  therefore dead code in production.
- A natural execution contract: a "buy" action calls
  `portfolio.add_holding(symbol, +quantity, price, ...)`, a "sell" action calls
  `portfolio.remove_holding(symbol, quantity, price, ...)` (or
  `add_holding(symbol, -quantity, price, ...)`), "hold" is a no-op. Price is
  resolved from an optional `prices` map, falling back to the holding's
  `current_price`. Executions are appended to `rebalance_history` and
  `last_rebalance` is updated. The method returns the executed actions (with
  the cash effect / executed quantity recorded).
- This is bounded (one method + tests), deterministic, network-free, and
  directly exercises the portfolio fixes just landed. It can be verified fully
  in one session.

Steps:

1. Add `Rebalancer.execute_actions(actions, prices=None)` to
   `quant_trading/portfolio/rebalancer.py` that applies each action to
   `self.portfolio` and records the execution.
2. Create `tests/test_rebalancer_execution.py` using a fixed-seed RNG that
   builds random portfolios and random action sequences and asserts after every
   step: cash + market value == total value; a trade moves the total value by
   exactly the fees; a sell is capped at the position size; a fully offset
   position is removed; a buy of a symbol already held averages the basis;
   `summary()["num_positions"]` matches open positions.
3. Verify with `python -m pytest tests/ -q` (baseline: **1400 passed, 1
   skipped**), `python -m coverage run --branch -m pytest tests/ -q &&
   python -m coverage report -m` (must stay at 100%), `python -m ruff check
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
  evidence in the handoff, and keep
  `tests/test_portfolio.py`, `tests/test_portfolio_invariants.py`,
  `tests/test_cost_accounting_invariants.py` and
  `tests/test_holding_pnl_invariants.py` green for any implementation change.
- Repo conventions: tests live in `tests/`, use `pytest.approx`, black line
  length 100, `# pragma: no cover` only for provably unreachable branches.
