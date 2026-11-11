## What changed (this session)

Added library-level input validation to `MonteCarloSimulator.__init__` so invalid
simulation configuration is rejected at construction with a clear `ValueError`,
instead of silently producing a degenerate or misleading run.

**Root cause:** `MonteCarloSimulator.__init__` accepted `n_simulations`,
`confidence_level`, and `periods_per_year` without validation. A direct library
user could pass `n_simulations=0` (division by zero in
`probability_of_profit`), `confidence_level` outside `(0, 1)` (opaque numpy
percentile errors or degenerate intervals), or `periods_per_year < 1` (breaks
annualization), all of which silently failed or produced misleading output.

**Fix** (`quant_trading/monte_carlo/simulator.py:398-422`): after the `_rng`
defaulting, `__init__` now raises `ValueError` when:
- `n_simulations < 1`
- `confidence_level` not in `(0, 1)`
- `periods_per_year < 1`

**Tests added** (`tests/test_monte_carlo.py`):
- `test_monte_carlo_rejects_invalid_n_simulations` — parametrized over
  `n_simulations ∈ {0, -1, -5}`.
- `test_monte_carlo_rejects_invalid_confidence_level` — parametrized over
  `confidence_level ∈ {0.0, -0.5, 1.0, 1.5}`.
- `test_monte_carlo_rejects_invalid_periods_per_year` — parametrized over
  `periods_per_year ∈ {0, -1, -252}`.
- `test_monte_carlo_accepts_minimal_valid_values` — `n_simulations=1`,
  `confidence_level=0.5`, `periods_per_year=1` construct cleanly.
- `test_monte_carlo_run_monte_carlo_rejects_invalid_n_simulations` — the
  `run_monte_carlo` convenience function propagates the constructor validation.

4 files changed (incl. this handoff): `quant_trading/monte_carlo/simulator.py`
(+25), `tests/test_monte_carlo.py` (+53).

## Verified (this session, evidence)

- `tests/test_monte_carlo.py` → **47 passed** (0 failed).
- `python -m ruff check quant_trading/monte_carlo/simulator.py tests/test_monte_carlo.py` → **All checks passed.**
- `python -m mypy quant_trading/monte_carlo/simulator.py --ignore-missing-imports` → **Success: no issues found in 1 source file.**
- `python -m pytest --doctest-modules quant_trading/monte_carlo/simulator.py -q -p no:cacheprovider` → **6 passed.**
- Confirmed no existing caller passes invalid values (grep over `MonteCarloSimulator(` / `run_monte_carlo(` in tests, examples, and source).

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
- Working tree changes: `quant_trading/monte_carlo/simulator.py` (+25),
  `tests/test_monte_carlo.py` (+53). Do NOT commit unless explicitly asked.

## One precise next task

- Add library-level input validation to `RiskManager.__init__`
  (`quant_trading/risk/manager.py:147-222`), mirroring the walk-forward and
  Monte Carlo validation pattern. `max_position_size`, `max_portfolio_risk`,
  `max_drawdown`, `max_leverage`, `stop_loss_pct`, `take_profit_pct`,
  `trailing_stop_pct`, `trailing_stop_activation_pct`, `initial_capital`, and
  `max_positions` are accepted without validation, so invalid values silently
  produce misleading risk decisions. Reject at construction with `ValueError`:
  - `initial_capital <= 0`
  - `max_position_size` not in `(0, 1]`
  - `max_portfolio_risk` not in `(0, 1]`
  - `max_drawdown` not in `[0, 1]` (`0.0` disables the limit, so allow it)
  - `max_positions < 1`
  - `stop_loss_pct` not in `[0, 1]`
  - `take_profit_pct` not in `[0, 1]`
  - `max_leverage < 1e-9` (must be positive)
  - `trailing_stop_pct` not in `[0, 1]`
  - `trailing_stop_activation_pct` not in `[0, 1]`
- Add parametrized rejection tests + a boundary-acceptance test in
  `tests/test_risk_manager.py`.
- Verify: `tests/test_risk_manager.py`, `tests/test_limits.py`, `tests/test_portfolio_rebalancer.py`, ruff, mypy on `quant_trading/risk/manager.py`.

(End of file)
