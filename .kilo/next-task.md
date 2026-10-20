# Next Task

## What changed (this session)

Executed the prior handoff's assigned task: add an `execute_actions` method to
`Rebalancer` that applies `RebalanceAction` objects to the managed portfolio,
and lock it in with seeded, randomized property tests.

- **Added `Rebalancer.execute_actions(actions, prices=None, commission=0.0,
  slippage=0.0)`** (`quant_trading/portfolio/rebalancer.py:356`). It applies
  each action to `self.portfolio`:
  - a `"buy"` buys `quantity` units (`Portfolio.add_holding`): it opens a long,
    adds to an open long, or covers an open short;
  - a `"sell"` sells `quantity` units (`Portfolio.remove_holding`): it reduces
    an open long or covers an open short;
  - a `"hold"` does nothing.

  The portfolio caps a trade against an open position at the size of that
  position, so an action can never open or flip a position, and a fully
  offset position is removed from the portfolio. The execution price comes from
  the `prices` map when it holds a positive price for the symbol, otherwise
  from the current price of the holding; an action with no resolvable price, a
  zero quantity, or a `"hold"` direction is skipped and reported with an
  executed quantity of 0.0. An unrecognized direction raises `ValueError`.
  The run is recorded in `rebalance_history` (with an extra `"executions"` key
  holding the per-action detail) and both `Rebalancer.last_rebalance` and
  `Portfolio.last_rebalance` are updated.
- **Added the `RebalanceExecution` dataclass**
  (`quant_trading/portfolio/rebalancer.py:79`): `symbol`, `action`,
  `requested_quantity`, `executed_quantity`, `price`, `cash_effect`, `reason`,
  `timestamp`. `execute_actions` returns one of these per input action, in
  order, so the caller can see what was *actually* traded (the quantity may be
  smaller than requested because the portfolio caps it).
- **Exported `RebalanceExecution`** from `quant_trading/portfolio/__init__.py`.
- **Created `tests/test_rebalancer_execution.py`** (26 tests): 2 seeded
  randomized property tests plus 24 unit tests.
  - `test_randomized_execution_invariants` (5 fixed seeds x 40 steps) drives
    random portfolios (longs *and* shorts) with random buy/sell/hold actions
    and asserts after every step: cash + market value == total value; only the
    fees moved the total value (`total_after == total_before - executed *
    price * (commission + slippage)`); a trade against an open position is
    capped at the size of that position; a fully offset position is removed; a
    buy of a symbol already held averages the cost basis; the reported
    position count matches the open positions; and no zero-quantity position
    is ever left behind.
  - `test_randomized_execution_never_leaves_zero_quantity_positions` (5 seeds
    x 40 steps) hammers the buy/sell path only.
  - Unit tests cover: buy opens a position, sell reduces a position and leaves
    the remaining basis untouched, hold is a no-op, a sell larger than the
    position is capped, the `prices` map wins over the holding price, the
    holding price is the fallback, an action with no price is skipped, an
    unknown direction raises `ValueError`, a sell of an unheld symbol is a
    no-op, a zero quantity is a no-op, a buy covers an open short instead of
    flipping it, commission and slippage are charged to cash and to the cost
    basis, one execution is returned per action in order, the run is recorded
    in `rebalance_history`, `last_rebalance` is stamped on the rebalancer and
    the portfolio, and the generated actions can be executed end to end (the
    allocation deviation shrinks).

## What was actually verified (this session)

- `python -m pytest tests/ -q` → **1426 passed, 1 skipped** (baseline at the
  start of this session: 1400 passed, 1 skipped; the +26 are the new tests).
- `python -m coverage run --branch -m pytest tests/ -q` +
  `python -m coverage report -m` → **100% statement and branch coverage** for
  the whole package (4562 statements, 1464 branches, 0 missed).
  `quant_trading/portfolio/rebalancer.py` is at 155/155 statements and 78/78
  branches.
- `python -m ruff check .` → All checks passed.
- `python -m black --check quant_trading tests` → clean except
  `tests/test_portfolio_rebalancer.py` (pre-existing drift, untouched — it is
  not in `git status`).
- `python -m mypy quant_trading` → Success: no issues found in 36 source files.
- The handoff's code-state claims were re-read from the source before acting:
  `Holding.unrealized_pnl_pct` is fixed at `portfolio.py:107` and the
  `Rebalancer` really had no execution path (`rebalancer.py:298` just returned
  the list). The prior handoff was accurate.

## What remains unresolved

- **The rebalancer's plan is not affordable: it can drive cash negative.**
  `generate_rebalance_actions` sizes a buy against the *whole* portfolio value
  (including the cash that the buy consumes) and ignores the fees, so
  executing the plan spends more cash than there is. Measured with the code as
  it is now (`cash=100000`, `target_allocation={"AAPL": 0.5, "MSFT": 0.5}`,
  `prices={"AAPL": 100.0, "MSFT": 200.0}`, `commission=0.001`,
  `slippage=0.0005`): the plan is 500 AAPL + 250 MSFT = $100,000 of buys
  against $100,000 of cash, the fees are $150, and `portfolio.cash` ends at
  **-149.99999999998545**. `Portfolio` has no margin, so a negative cash
  balance is a broken state, not a short. `execute_actions` deliberately
  executes what it is asked to execute (it does not silently resize a trade),
  so the defect is in the sizing, not in the execution. This is the next task.
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
  handoff.** (Re-checked this session: the handoff was accurate.)
- The prior handoff's bullet relation for `unrealized_pnl` was wrong for
  shorts; the correct, verified relation is
  `unrealized_pnl == abs(quantity) * abs(avg_cost) * unrealized_pnl_pct`.
- **This session:** one failure, in the *test*, not the implementation. The
  first draft of the "a fully offset position disappears" invariant fired on
  `"hold"` actions (a hold never touches a position, so the position is
  correctly still there). The invariant was corrected to apply only to
  actions that reduce a position (a sell, or a buy against a short). The
  implementation was never at fault and no assertion was weakened.

## One precise next task

**Make the rebalancer's generated actions affordable: size the buys against the
cash that is actually available (net of fees), and lock it in with seeded,
randomized property tests.**

Evidence and rationale:

- The defect is measured and reproducible (see "What remains unresolved"
  above): `generate_rebalance_actions` plans $100,000 of buys against
  $100,000 of cash and the fees push `portfolio.cash` to -150. The
  `execute_actions` method added this session is the first code path that
  spends the cash the rebalancer sized, so the defect is now reachable from
  the public API instead of being theoretical.
- `generate_rebalance_actions` computes `quantity = diff / price` where `diff`
  is a fraction of `portfolio.total_value` (`rebalancer.py:236`,
  `_resolve_buy_quantity` at `rebalancer.py:300`). `total_value` is
  `cash + holdings`, so the planned buys are allowed to spend the cash twice
  over, and neither the fees nor the cash already committed to an earlier
  action in the same batch is subtracted.
- A natural contract: the planned buys of one batch must be affordable, i.e.
  the sum of the buy notionals plus their fees must not exceed the available
  cash, and a buy that cannot be afforded is either skipped or sized down to
  what the cash can buy. The rebalancer already has the machinery for this:
  `_resolve_buy_quantity` returns 0.0 when no price is available, and
  `generate_rebalance_actions` skips an action whose quantity is 0.
- This is bounded (one method plus tests), deterministic, network-free, and it
  directly protects the cash invariant that `tests/test_portfolio_invariants.py`
  and `tests/test_cost_accounting_invariants.py` already assert elsewhere.

Steps:

1. Fix the sizing in `quant_trading/portfolio/rebalancer.py` so that the
   actions of one `generate_rebalance_actions` batch are affordable with the
   cash the portfolio has (net of commission and slippage), and so that the
   cash committed to the earlier actions of the same batch is taken into
   account. Keep `generate_rebalance_actions` returning the same shape
   (`RebalanceAction` objects) and keep the existing threshold semantics.
2. Extend `tests/test_rebalancer_execution.py` (or add a new file next to it)
   with a seeded, randomized test that generates actions for random target
   allocations, executes them with random commission and slippage, and
   asserts after the batch: `portfolio.cash >= 0`; `cash + market value ==
   total value`; the total value moved by exactly the fees of the trades that
   were executed; and every generated action that was executed is affordable
   on its own. Assert the invariants on the *implementation*, not on a
   weakened version of them.
3. Verify with `python -m pytest tests/ -q` (baseline: **1426 passed, 1
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
