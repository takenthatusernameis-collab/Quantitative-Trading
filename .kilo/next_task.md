# Next Task

## What changed (this session)

**Completed the risk-managed rebalancer integration tests (already implemented).**
- Verified `TestRebalancerRiskIntegration` in `tests/test_portfolio_rebalancer.py` passes: `test_risk_managed_rebalance_preserves_solvency_across_rounds` and `test_risk_managed_rebalance_respects_drawdown_limit`.
- All rebalancer tests pass (56 passed). Full test suite: **1453 passed, 1 skipped**.

## What was actually verified (this session)

- `python -m pytest tests/test_portfolio_rebalancer.py -v` → 56 passed
- `python -m pytest tests/ -q` → 1453 passed, 1 skipped
- `git status` clean of uncommitted changes (working tree as-is)

## What remains unresolved

- **`Portfolio.get_allocation()` returns negative weights for shorts** (a short's market value is negative), so `summary()["allocation"]` can contain negative fractions. Left unchanged previously - not a usable allocation for a short book.
- **Shorts are still unreachable in production.** The engine only ever buys (`quant_trading/backtest/engine.py:548`) and only sells an existing long (`engine.py:581`), and `execute_actions` deliberately only *reduces* exposure, so no production code path opens a short.
- **No CI workflow runs the test suite** (Kilo controller excludes `.github/workflows/**`), so invariants only execute when run locally.
- Previous failed attempts: regime detector tests already fully covered; handoff text can be stale - always read code/git log before acting.

## Approaches already failed

- N/A this session (task was already implemented).

## One precise next task

**Make `Portfolio.get_allocation()` produce usable allocations when shorts are present (or add a clear API for gross/net allocations).**

Evidence and rationale:
- Short positions have negative `market_value` (see `Holding.market_value`/`Holding.pnl` logic), so current `get_allocation()` returns negative weights. This breaks typical "sum to 1.0" assumptions and is awkward for reporting/rebalancing.
- Need to decide on semantics: either (1) return absolute weights normalized by total |market_value| or total equity, or (2) add `get_gross_allocation()`/`get_net_allocation()` and keep existing behavior documented, or (3) return allocations as fractions of total equity with shorts shown as negative (current) but ensure consumers handle it. Look up existing codebase expectations - tests don't expect shorts, but better to make it robust.
- Bounded change in `quant_trading/portfolio/portfolio.py`, possibly add tests in `tests/test_portfolio.py`.

Steps:
1. Inspect `Holding.market_value` for shorts (negative quantity gives negative market value) and current usage.
2. Choose a sensible, backward-compatible approach. Option A: add parameter `use_absolute: bool = False` - if True, use `abs(h.market_value)/sum(abs(...))` so shorts contribute positively to gross exposure; if False keep current behavior (negative weights). Option B: add separate methods. Prefer minimal API change.
3. Update `get_allocation()` and `summary()` accordingly; update docstring.
4. Add tests covering short positions - verify allocations are sensible and don't break invariants.
5. Verify with `python -m pytest tests/test_portfolio.py -v` and full suite. Ensure 100% coverage maintained.

Constraints:
- Deterministic, no network.
- Backward compatible where possible.
- Follow repo style (black line length 100).
- Do not run `git commit`. Leave changes in working tree.
- Keep all existing portfolio/invariant tests green.
