# Next Task

## What changed (this session)

The handoff from the previous session asked for two things: (1) create
`tests/test_portfolio_invariants.py` with seeded, randomized portfolio-level
property tests, and (2) make `Portfolio.add_holding` handle a reduction of a
long consistently with `Portfolio.remove_holding`.

**Part (2) was already applied and committed by the Kilo controller** as
`8d0f2c9` ("Fix duplicate-definition SyntaxError and restore full test
coverage" was the previous commit; `8d0f2c9` is the controller's checkpoint of
the previous agent's working tree). The handoff file was written *before* that
change, so it described a state that no longer existed. Part (1) was never
done — the file did not exist.

This session therefore:

- **Created `tests/test_portfolio_invariants.py`** (297 lines, 94 seeded,
  randomized property tests). It drives a `Portfolio` through random sequences
  of `add_holding` (buys, sells, short opens, short covers), `remove_holding`
  and `update_prices` over three symbols, and asserts after **every** step:
  1. `portfolio.cash + sum(h.market_value) == portfolio.total_value`
  2. **a trade executed at the market price changes the total value by the fees
     and nothing else** — `total_before - executed * price * (commission + slippage)`.
     This is the property that catches phantom cash.
  3. the position moved by exactly the executed quantity, and a trade against
     an open position is capped at the size of that position
  4. a reduction never changes the cost basis of the remaining position
  5. `add_holding(-q)` and `remove_holding(q)` leave the same position, the
     same basis, the same cash and the same total value
  6. a fully offset position disappears; no zero-quantity leftovers survive
  7. `summary()["num_positions"]` equals the number of open positions
  Scenarios: randomized multi-symbol trade sequences (20 seeds); randomized
  reductions that must not move the basis (20 seeds); randomized
  `add_holding`/`remove_holding` equivalence for longs, including over-sized
  reductions that must be capped (20 seeds); the same equivalence for short
  covers (20 seeds); growing an existing short (10 seeds); plus five targeted
  cases (fully offset long, fully covered short, zero-quantity trade, capped
  reduction).

- **Fixed three more phantom-cash bugs in `Portfolio.add_holding`
  (`quant_trading/portfolio/portfolio.py:187`).** They were found by an
  executable probe, not by reading the code, and all three are the same class of
  bug the previous session fixed in the engine (a trade booked for more units
  than were actually held):
  - **Over-sized reduction.** `add_holding("AAPL", -150, 110.0)` on a 100-unit
    long credited cash for **150** units sold while only 100 were held: cash
    ended at 106500.0 instead of 101000.0, i.e. **5500.0 of phantom cash**.
    `remove_holding` already capped the removal at the position size; the
    reduction branch of `add_holding` did not. Now both cap.
  - **Adding to an existing short replaced the position.** `add_holding` with a
    negative quantity on a symbol that already held a short fell into the
    `else` branch and *overwrote* the holding: a -100 short plus `-50` became
    a -50 short (and credited 5000.0 of phantom cash). The short is now grown
    to -150 and its basis is averaged at the raw execution price, consistent
    with the documented "short positions keep the execution price as their
    basis".
  - **Buying back a short flipped the position sign.** `add_holding` with a
    positive quantity on a short fell into the same `else` branch and replaced
    the -100 short with a **+40 long** (and debited cash for a buy that never
    happened). The short is now covered down to -60.
  A fourth, smaller leak: `add_holding(symbol, 0, price)` created a
  zero-quantity holding, which inflated `summary()["num_positions"]` and the
  risk manager's `max_positions` count (`PortfolioLimit.check` counts
  `len(positions)`). A zero quantity is now a no-op.

- **Fixed `Portfolio.remove_holding` on short positions
  (`quant_trading/portfolio/portfolio.py:279`).** It computed
  `actual_qty = min(quantity, holding.quantity)`, which for a -100 short and a
  50-unit request gives `min(50, -100) = -100`: the position was deleted and
  cash was debited for 100 units instead of 50 being covered. `remove_holding`
  is now always a capped reduction: it sells a long (credits cash) or covers a
  short (debits cash), deletes a fully closed position, and returns the net
  cash effect (negative when covering a short).

- **The cash rule is now uniform across both methods**: a buy debits cash at
  `price * (1 + commission + slippage)`, a sell credits cash at
  `price * (1 - commission - slippage)`, applied to the *executed* quantity.
  This is what makes invariant 2 above hold for every trade.

- **Updated `tests/test_portfolio.py`** with seven targeted unit tests for the
  new behaviour (capped reduction, growing a short, reducing a short, zero
  quantity, covering a short, fully covering a short) and fixed the stale
  docstring of `test_add_holding_net_zero` (it claimed the position "resets
  avg_cost to 0"; the position is removed).

## What was actually verified (this session)

- `python -m pytest tests/ -q` → **1383 passed, 1 skipped**. Baseline at the
  start of this session: **1283 passed, 1 skipped** (the +100 are the new
  invariant cases and the new unit tests).
- `python -m coverage run --branch -m pytest tests/ -q` +
  `coverage report -m` → **100% statement and branch coverage** for the whole
  package (4520 statements, 1450 branches, 0 missed).
- `python -m ruff check .` → All checks passed.
  `python -m black --check quant_trading tests` → clean except
  `tests/test_portfolio_rebalancer.py` (pre-existing drift, untouched — it is
  not in `git status`).
  `python -m mypy quant_trading` → Success: no issues found in 36 source files.
- **The new tests were proven to catch the bugs they target**, by running
  `tests/test_portfolio_invariants.py` against the old implementations:
  - against `HEAD` (`8d0f2c9`, i.e. only the previous session's fix) →
    **57 failed, 37 passed**;
  - against `8d0f2c9^` (the re-averaging implementation) →
    **93 failed, 1 passed**;
  - against the fixed implementation → **94 passed**.
- The bugs themselves were measured with a throwaway probe kept outside the
  repository in `/home/runner/work/_temp/kilo-tmp/kilo/probe_portfolio.py`;
  the scenario-level reproduction is in
  `/home/runner/work/_temp/kilo-tmp/kilo/repro_invariant.py`.

## What remains unresolved

- **`Holding.unrealized_pnl_pct` disagrees with `Holding.unrealized_pnl` for
  short positions.** Measured: a -100 short with `avg_cost 100` and
  `current_price 90` reports `unrealized_pnl == 1000.0` (a profit) but
  `unrealized_pnl_pct == -0.1` (a loss). The percentage is the *price* move,
  not the position's PnL, so the two properties have opposite signs for a
  short. It also returns a non-zero value for a zero-quantity holding, while
  `unrealized_pnl` returns `0.0` for it. Nothing in `quant_trading/` consumes
  `unrealized_pnl_pct` (only its own docstring example does). This is the next
  task.
- **`Portfolio.get_allocation()` returns negative weights for shorts** (a
  short's market value is negative), so `summary()["allocation"]` can contain
  negative fractions. Left unchanged; it is consistent with the sign of the
  market value but is not a usable allocation for a short book.
- **The short-side fixes are currently test-only.** The engine only ever buys
  (`quant_trading/backtest/engine.py:548`) and only sells an existing long
  (`engine.py:567`), so no production code path reaches the short branches.
  Nothing in `quant_trading/` calls `add_holding` with a negative quantity
  outside of tests.
- **The `Rebalancer` emits `RebalanceAction` objects but never executes them**
  (`quant_trading/portfolio/rebalancer.py:278`), so the corrected reduction
  semantics are not exercised by the rebalancing path either.
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
- Stale contradictory tests cannot be "reconciled" by editing assertions; the
  superseded variant was deleted instead.
- The previous session's handoff described a code state that the controller had
  already committed. **Read the code and the git log before acting on a
  handoff**; `git show HEAD` showed the reduction fix was already in place and
  only the test file was missing.
- The previous session's handoff also said the invariant "`final_value -
  initial_capital == signed sum of `Trade.cost`" only holds when the book is
  flat. That is still true: with open positions the signed cost reconciles
  with the **cash balance**, not with the final value. The cash form is the
  correct one; do not "fix" it by changing the cash assertion back.
- **This session:** the first version of the randomized driver modelled
  `remove_holding` with `add_holding`'s contract (a trade in the direction of
  the position is executed in full). `remove_holding` is always a capped
  reduction, so 18 of the 20 randomized seeds failed. The fix was to give the
  two public methods their own helper (`_executed_quantity` vs
  `_removed_quantity`) rather than to weaken the assertion — the assertion was
  right and the model was wrong.
- The engine fix of the previous session was found by a randomized probe
  rather than by reading the code, so a second, independent randomized scenario
  (multi-symbol, add-to-existing, risk-enabled) was kept in
  `tests/test_cost_accounting_invariants.py` to guard against a fix that only
  holds for one path. The same principle was applied here: the portfolio
  invariant is a *derived* property (only the fees may move the total value),
  not a re-statement of the implementation, so it catches phantom cash
  regardless of which code path produced it.

## One precise next task

**Make `Holding.unrealized_pnl_pct` consistent with `Holding.unrealized_pnl`
for short and zero-quantity positions, and lock it in with seeded, randomized
property tests.**

Evidence and rationale:

- `quant_trading/portfolio/portfolio.py:79` defines
  `unrealized_pnl_pct` as `(current_price - avg_cost) / avg_cost`, i.e. the
  price move, while `unrealized_pnl` (`:71`) is
  `quantity * (current_price - avg_cost)`, i.e. the position's PnL. For a long
  the two agree in sign; for a short they do not.
- Measured: `Holding("AAPL", quantity=-100, avg_cost=100.0, current_price=90.0)`
  → `unrealized_pnl == 1000.0` but `unrealized_pnl_pct == -0.1`. The same
  holding with `quantity=+100` gives `unrealized_pnl == -1000.0` and
  `unrealized_pnl_pct == -0.1`.
- A zero-quantity holding reports `unrealized_pnl == 0.0` but
  `unrealized_pnl_pct == (current_price - avg_cost) / avg_cost`, which is
  generally non-zero.
- The relation that must hold for every holding is
  `unrealized_pnl == quantity * abs(avg_cost) * sign * unrealized_pnl_pct`,
  i.e. `unrealized_pnl_pct` must be the PnL as a fraction of the position's
  cost basis: `(current_price - avg_cost) / avg_cost` for a long and
  `-(current_price - avg_cost) / avg_cost` for a short. The current code has
  no `quantity` term at all, so it cannot satisfy that relation.
- `unrealized_pnl_pct` has no production consumer (`grep` finds only its own
  docstring example at `portfolio.py:56` and two tests in
  `tests/test_portfolio.py`), so the change is low risk.
- This is now the last known sign/definition inconsistency in the portfolio's
  PnL reporting, and the short book is only reachable through the API, so the
  property test has to drive `Portfolio` directly rather than the engine.

Steps:

1. Create `tests/test_holding_pnl_invariants.py` using a fixed-seed RNG
   (`numpy.random.default_rng(seed)`) that builds random `Holding` objects
   (random sign of the quantity, random `avg_cost`, random `current_price`)
   and asserts for every one of them:
   - `unrealized_pnl_pct == 0.0` when `quantity == 0` or `avg_cost == 0`;
   - `unrealized_pnl == quantity * abs(avg_cost) * unrealized_pnl_pct` (within
     `pytest.approx`) — the sign-consistency relation above;
   - `sign(unrealized_pnl) == sign(unrealized_pnl_pct)` whenever both are
     non-zero;
   - a long and a short with the same prices are mirror images: the short's
     `unrealized_pnl` is the negation of the long's and its
     `unrealized_pnl_pct` is too.
2. Implement the fix in `Holding.unrealized_pnl_pct`
   (`quant_trading/portfolio/portfolio.py:79`) so that it is the PnL over the
   position's cost basis, and update the existing test
   `tests/test_portfolio.py::test_unrealized_pnl_pct` (it asserts the current
   long-only formula) and the docstring example at `portfolio.py:56`. Keep the
   `avg_cost == 0` guard. Update the `Holding` class docstring to state the
   short convention explicitly, because the previous two sessions established
   that a documented contract is what the property tests pin down.
3. Verify with `python -m pytest tests/ -q` (baseline: **1383 passed,
   1 skipped**), `python -m coverage run --branch -m pytest tests/ -q &&
   python -m coverage report -m` (must stay at 100%), `python -m ruff check .`,
   `python -m black --check quant_trading tests` and `python -m mypy
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
  `tests/test_portfolio_invariants.py`, `tests/test_backtest_engine.py` and
  `tests/test_cost_accounting_invariants.py` green for any implementation
  change.
- Repo conventions: tests live in `tests/`, use `pytest.approx`, black line
  length 100, `# pragma: no cover` only for provably unreachable branches.
