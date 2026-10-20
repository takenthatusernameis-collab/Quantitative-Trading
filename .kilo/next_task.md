# Next Task

## What changed (this session)

- **Fixed a real accounting bug in `quant_trading/backtest/engine.py` (`BacktestEngine._process_signal`, sell branch, `engine.py:576`).**
  The sell quantity was computed as `holding.quantity * signal.strength` and used both for the portfolio removal and for the recorded trade. `Portfolio.remove_holding` (`quant_trading/portfolio/portfolio.py:282`) silently caps the removal at the position size, so a signal with `strength > 1` closed the whole position but the trade log recorded a **larger** quantity than the position held, and the realized PnL was computed on the uncapped quantity. The trade log therefore disagreed with the cash balance and with the portfolio.
  The fix caps the executed quantity: `quantity = min(holding.quantity * signal.strength, holding.quantity)`. For every contract-conformant signal (`0.0 <= strength <= 1.0`, the documented range in `quant_trading/strategies/base.py:18`, and every bundled strategy clamps with `min(1.0, ...)`) the expression is a no-op, so no existing behaviour changes. The `_process_signal` docstring was updated to say the sell is "capped at the size of the position".

- **Expanded `tests/test_cost_accounting_invariants.py` from 20 to 51 seeded, randomized invariant tests.**
  The file existed from the previous session but only covered one symbol, one buy and a single sequence of partial sells. It now covers four randomized scenarios (fixed seeds, no network, no unseeded randomness), each asserting six identities that must hold for every run:
  1. `result.total_costs == sum(trades["fee"])`
  2. `portfolio.cash - result.initial_capital == ` the signed trade costs (buys negative, sells positive)
  3. `portfolio.cash + sum(holding.market_value) == result.final_value`
  4. `result.final_value - result.initial_capital == realized PnL + unrealized PnL`
  5. a fully liquidated run books all of its PnL as realized
  6. the trade log's net quantity per symbol equals the portfolio holding
  Scenarios: full round trip with random partial exits (20 seeds); adding to an existing long, i.e. the weighted-average cost basis of `Portfolio.add_holding` (10 seeds); two symbols traded round-robin (10 seeds); runs where the risk manager rejects a signal (10 seeds). Plus `test_sell_signal_larger_than_position_records_executed_quantity`, the regression test for the engine fix.

- **The invariant set was derived from an executable probe, not from assumption.** A throwaway script (kept outside the repo in `/home/runner/work/_temp/kilo-tmp/kilo/`) ran the scenarios above plus variants and reported which identity broke; the `strength > 1` case was the only failing one, which is what led to the engine fix.

## What was actually verified (this session)

- `python -m pytest tests/ -q` → **1283 passed, 1 skipped** (baseline at the start of this session: 1252 passed, 1 skipped; the +31 are the new invariant cases).
- `python -m coverage run --branch -m pytest tests/ -q` + `coverage report -m` → **100% statement and branch coverage** for the whole package (4513 statements, 1444 branches, 0 missed).
- `python -m ruff check .` → All checks passed. `python -m black --check quant_trading tests` → clean except `tests/test_portfolio_rebalancer.py` (pre-existing drift, untouched). `python -m mypy quant_trading` → Success: no issues found in 36 source files.
- The regression test was proven effective: with `engine.py` reverted to `HEAD`, `python -m pytest tests/test_cost_accounting_invariants.py -q` → **1 failed, 50 passed**, with the exact diagnostic `assert np.float64(13.33214825348858) == 8.888098835659052` (recorded 13.33 units sold vs the 8.89 actually held); with the fix restored → **51 passed**.
- The full suite was run twice (once plain, once under coverage) after the fix; both were green.

## What remains unresolved

- **`Portfolio.add_holding` contradicts its own docstring when reducing a long** — this is the next task, see below. Measured: `add_holding("AAPL", -40, 110.0)` leaves 60 units at `avg_cost 93.33`, while `remove_holding("AAPL", 40, 110.0)` leaves 60 units at `avg_cost 100.0`; the cash is identical (94400.0) in both cases.
- `tests/test_portfolio_rebalancer.py` is still the only file `black` would reformat (pre-existing, deliberately left untouched to avoid unrelated modifications).
- **No CI workflow runs the test suite**, so the new invariants and the repository-integrity guard only execute when an agent runs pytest locally. Note that the Kilo controller stages with `':(exclude).github/workflows/**'` (`.github/scripts/kilo-controller.sh:327`), so a workflow file added by an agent would never be committed by the controller — do not spend a session on it.
- 100% line/branch coverage is not behavioural verification: the accounting identities are now exercised by 51 randomized runs, but the invariants still describe only long-only, cash-only, non-short books.

## Approaches already failed

- The previous two sessions both ended with "add regime detector tests"; the second attempt re-applied an already-applied patch and broke the package import (commit `01eb720`). That line of work was closed because `tests/test_regime.py` already gives `quant_trading/regime/detector.py` 100% branch coverage.
- Stale contradictory tests cannot be "reconciled" by editing assertions; the superseded variant was deleted instead.
- **This session:** the handoff's literal invariant "`final_value - initial_capital == signed sum of `Trade.cost`" only holds when the book is flat. With open positions the signed cost reconciles with the **cash balance**, not with the final value (which also contains the open positions' market value). The test therefore asserts the cash-based identity plus the market-value identity, and asserts the literal form only for a fully liquidated run. This is not a weakened assertion — the cash form is the correct one; do not "fix" this by changing the cash assertion back.
- The engine fix was found by a randomized probe rather than by reading the code, so a second, independent randomized scenario (multi-symbol, add-to-existing, risk-enabled) was kept in the file to guard against a fix that only holds for one path.

## One precise next task

**Make `Portfolio.add_holding` handle a reduction of a long consistently with `Portfolio.remove_holding`, and lock the behaviour in with seeded, randomized portfolio-level property tests.**

Evidence and rationale:

- `Portfolio.add_holding` documents: *"a new long position is costed at `price * (1 + commission + slippage)`, and lots added to an existing long are averaged at their fee-inclusive cost. **Reductions of a long leave the remaining basis untouched.**"* (`quant_trading/portfolio/portfolio.py:203-208`). The implementation does not do that: it re-averages the remaining basis with the raw execution value (`portfolio.py:230-240`, `new_avg_cost = (holding.avg_cost * holding.quantity + cost) / total_qty` at `portfolio.py:234`). Measured on `add_holding("AAPL", 100, 100.0)` followed by a 40-unit reduction at 110.0:
  - `add_holding("AAPL", -40, 110.0)` → 60 units, `avg_cost 93.33`, cash 94400.0
  - `remove_holding("AAPL", 40, 110.0)` → 60 units, `avg_cost 100.0`, cash 94400.0
  Two public APIs that perform the same sale disagree on the remaining basis (6.67/unit ≈ 400 on 60 units), which changes the realized PnL booked on the next exit.
- A full reduction through `add_holding` leaves a **zero-quantity holding** in `portfolio.holdings` (`portfolio.py:241-249`), whereas `remove_holding` deletes the position (`portfolio.py:286-287`). A zero-quantity leftover inflates `summary()["num_positions"]`, `get_positions()` and the risk manager's max-positions count.
- `tests/test_portfolio.py::test_add_holding_partial_reduction_keeps_weighted_basis` currently asserts the re-averaging behaviour and restates it in its own docstring, so it has to move together with any change.
- Nothing in `quant_trading/` calls `add_holding` with a negative quantity: the engine only buys (`quant_trading/backtest/engine.py:548`) and `Rebalancer` produces `RebalanceAction` objects without executing them (`quant_trading/portfolio/rebalancer.py:15` is a docstring example). The reduction path is currently test-only, so the change is low risk.

Steps:

1. Create `tests/test_portfolio_invariants.py` using a fixed-seed RNG (`numpy.random.default_rng(seed)`) that drives a `Portfolio` through random sequences of `add_holding` (positive and negative), `remove_holding` and `update_prices`, and assert:
   - `portfolio.cash + sum(h.market_value) == portfolio.total_value` after every step
   - reducing a long never changes `avg_cost` of the remaining position
   - `remove_holding` and the equivalent `add_holding` reduction leave the same remaining basis and the same cash
   - a fully offset position disappears from `portfolio.holdings` (no zero-quantity leftovers)
   - `portfolio.summary()["num_positions"]` equals the number of positions with `quantity > 0`
2. Implement the resolution: make the reduction branch of `add_holding` leave the basis untouched and drop the position when it is fully offset (matching its own docstring and `remove_holding`), and update `tests/test_portfolio.py::test_add_holding_partial_reduction_keeps_weighted_basis` (rename it accordingly). If the re-averaging behaviour is deliberately kept instead, correct the `add_holding` docstring and the test name to match — but state that decision explicitly in the next handoff.
   - Keep the **short** path working: a negative quantity on an unheld symbol opens a short in the `else` branch (`portfolio.py:241-249`) at the raw execution price, and `Holding.__post_init__` keeps a negative market value for shorts.
   - Watch the two `total_qty != 0` else-branches (`portfolio.py:219-225` and `portfolio.py:233-238`): one of them becomes unreachable once reductions keep the basis untouched. If so, remove it or mark it `# pragma: no cover` with a reason, following the convention already used at `portfolio.py:224` and `quant_trading/risk/metrics.py:339`.
3. Verify with `python -m pytest tests/ -q` (baseline: **1283 passed, 1 skipped**), `python -m coverage run --branch -m pytest tests/ -q && python -m coverage report -m` (must stay at 100%), `python -m ruff check .`, `python -m black --check quant_trading tests`, and `python -m mypy quant_trading`.

Constraints:

- **Do not run `git commit`.** The Kilo controller stages and commits the working tree itself (`.github/scripts/kilo-controller.sh:327`, `:401`) and treats a session without a non-empty staged diff as *no project progress* (`:390-395`, `:570`). Leave the changes in the working tree and in `.kilo/next_task.md` / `.kilo/next-task.md` (keep the two files identical).
- Deterministic: fixed seeds only, no network, no unseeded randomness.
- If an invariant fails, **do not weaken the assertion to make it pass**: determine whether the implementation or the invariant is wrong, keep the evidence in the handoff, and keep `tests/test_portfolio.py`, `tests/test_backtest_engine.py` and `tests/test_cost_accounting_invariants.py` green for any implementation change.
- Repo conventions: tests live in `tests/`, use `pytest.approx`, black line length 100, `# pragma: no cover` only for provably unreachable branches.
