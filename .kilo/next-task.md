# Next Task

## Repository state (verified this session)
- Branch `main` up to date with `origin/main`; working tree clean except for the changes below.
- `python -m ruff check .` → All checks passed.
- `python -m mypy quant_trading --ignore-missing-imports` → Success: no issues in 38 source files.

## Completed this session

**Added construction-time input validation to `MonteCarloSimulator`.**

`MonteCarloSimulator.__init__` accepted `n_simulations`, `confidence_level`, and
`periods_per_year` without validation, so invalid values silently produced
degenerate runs (e.g. `n_simulations=0` divides by zero in
`probability_of_profit`).

**Fix** (`quant_trading/monte_carlo/simulator.py`): `__init__` now raises
`ValueError` when `n_simulations < 1`, `confidence_level` not in `(0, 1)`, or
`periods_per_year < 1`, mirroring the existing `WalkForwardOptimizer` validation
style.

**Tests added** (`tests/test_monte_carlo.py`): rejection tests parametrized over
invalid `n_simulations`, `confidence_level`, and `periods_per_year`, plus a
boundary-acceptance test and a `run_monte_carlo` propagation test.

## Verified (this session, evidence)

- `tests/test_monte_carlo.py` → **47 passed** (0 failed).
- ruff on changed files → **All checks passed.**
- mypy on `quant_trading/monte_carlo/simulator.py` → **no issues.**
- doctest-modules on `simulator.py` → **6 passed.**

## Unresolved / not completed

- None identified.

## Failed approaches (do not repeat unchanged)

- None for this task.

## Verification commands (re-run before starting)

```bash
python -m pytest tests/test_monte_carlo.py -q -p no:cacheprovider
python -m ruff check quant_trading/monte_carlo/simulator.py tests/test_monte_carlo.py
python -m mypy quant_trading/monte_carlo/simulator.py --ignore-missing-imports
python -m pytest --doctest-modules quant_trading/monte_carlo/simulator.py -q -p no:cacheprovider
```

## Git state

- Branch `main` up to date with `origin/main`.
- Working tree has uncommitted changes: `quant_trading/monte_carlo/simulator.py`
  (+25), `tests/test_monte_carlo.py` (+53). Do NOT commit unless explicitly asked.

## One precise next task

Add library-level input validation to `RiskManager.__init__`
(`quant_trading/risk/manager.py:147-222`), mirroring the walk-forward and Monte
Carlo validation pattern. Reject at construction with `ValueError`:
`initial_capital <= 0`; `max_position_size` not in `(0, 1]`;
`max_portfolio_risk` not in `(0, 1]`; `max_drawdown` not in `[0, 1]` (`0.0`
disables the limit); `max_positions < 1`; `stop_loss_pct` not in `[0, 1]`;
`take_profit_pct` not in `[0, 1]`; `max_leverage < 1e-9`;
`trailing_stop_pct` not in `[0, 1]`; `trailing_stop_activation_pct` not in
`[0, 1]`. Add parametrized rejection tests + a boundary-acceptance test in
`tests/test_risk_manager.py`. Verify: `tests/test_risk_manager.py`,
`tests/test_limits.py`, `tests/test_portfolio_rebalancer.py`, ruff, mypy on
`quant_trading/risk/manager.py`.
