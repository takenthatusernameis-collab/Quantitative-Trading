## What changed (this session)

Added library-level input validation to `RiskManager.__init__` so invalid
risk configuration is rejected at construction with a clear `ValueError`,
instead of silently producing misleading risk decisions.

**Root cause:** `RiskManager.__init__` accepted `initial_capital`,
`max_position_size`, `max_portfolio_risk`, `max_drawdown`, `max_positions`,
`stop_loss_pct`, `take_profit_pct`, `max_leverage`, `trailing_stop_pct`, and
`trailing_stop_activation_pct` without validation.

**Fix** (`quant_trading/risk/manager.py:223-269`): after the trailing-stop
attribute assignments, `__init__` now raises `ValueError` when:
- `initial_capital <= 0`
- `max_position_size` not in `(0, 1]`
- `max_portfolio_risk` not in `(0, 1]`
- `max_drawdown` not in `[0, 1]` (`0.0` disables the limit, so it is allowed)
- `max_positions < 1`
- `stop_loss_pct` not in `[0, 1]`
- `take_profit_pct` not in `[0, 1]`
- `max_leverage < 1e-9` (must be positive)
- `trailing_stop_pct` not in `[0, 1]`
- `trailing_stop_activation_pct` not in `[0, 1]`

The checks use the constructor parameters directly (mirroring the Monte Carlo
pattern in `quant_trading/monte_carlo/simulator.py:406-420`), since most of
these values are not stored as instance attributes.

**Tests added** (`tests/test_risk_manager.py`, class
`TestRiskManagerInitValidation`):
- parametrized rejection tests for each invalid family above
- boundary-acceptance tests for `max_drawdown`, `stop_loss_pct`,
  `take_profit_pct`, `trailing_stop_pct`, `trailing_stop_activation_pct`
  at `0.0`/`1.0`
- `test_accepts_minimal_positive_max_leverage` (`1e-9`)
- `test_accepts_all_boundary_valid_values`

**Existing tests updated** (`tests/test_backtest_engine.py`):
- `test_run_with_zero_initial_capital_does_not_divide_by_value` → renamed to
  `test_run_with_zero_initial_capital_is_rejected`, now asserts `ValueError`
  for `initial_capital=0.0`
- `test_a_bar_that_hits_both_levels_closes_the_position_once` → renamed to
  `test_negative_take_profit_pct_is_rejected`, now asserts `ValueError` for
  `take_profit_pct=-0.15` (that scenario required an inverted take profit,
  which is now invalid)

4 files changed: `quant_trading/risk/manager.py` (+43),
`tests/test_risk_manager.py` (+~110), `tests/test_backtest_engine.py` (2 tests
rewritten), `HANDOFF_NEXT_AGENT.md`.

## Verified (this session, evidence)

- `tests/test_risk_manager.py` → all pass
- `tests/test_limits.py` → all pass
- `tests/test_portfolio_rebalancer.py` → all pass
- `tests/test_backtest_engine.py`, `tests/test_integration.py`,
  `tests/test_rebalancer_extra_coverage.py`,
  `tests/test_rebalancer_sizing_invariants.py`,
  `tests/test_rebalancer_risk_integration.py` → all pass (496 passed total)
- `python -m ruff check quant_trading/risk/manager.py tests/test_risk_manager.py tests/test_backtest_engine.py` → **All checks passed.**
- `python -m mypy quant_trading/risk/manager.py --ignore-missing-imports` → **Success: no issues found.**
- `python -m pytest --doctest-modules quant_trading/risk/manager.py -q -p no:cacheprovider` → **12 passed.**

## Unresolved / not completed

- None for this task.

## Failed approaches (do not repeat unchanged)

- None for this task.

## Verification commands (re-run before starting)

```bash
python -m pytest tests/test_risk_manager.py tests/test_limits.py tests/test_portfolio_rebalancer.py tests/test_backtest_engine.py -q -p no:cacheprovider
python -m ruff check quant_trading/risk/manager.py tests/test_risk_manager.py tests/test_backtest_engine.py
python -m mypy quant_trading/risk/manager.py --ignore-missing-imports
python -m pytest --doctest-modules quant_trading/risk/manager.py -q -p no:cacheprovider
```

## Git state

- Branch `main` up to date with `origin/main`.
- Working tree clean before this session; changes not yet committed.
  Do NOT commit unless explicitly asked.

## One precise next task

- Add library-level input validation to `WalkForwardOptimizer.__init__`
  (`quant_trading/optimization/walk_forward.py:448-529`), mirroring the
  RiskManager / Monte Carlo validation pattern. The constructor accepts
  `n_windows`, `train_size`, `step_size`, `periods_per_year`,
  `initial_capital`, `commission`, and `slippage` without validation, so
  invalid values silently produce misleading walk-forward results. Reject at
  construction with `ValueError`:
  - `initial_capital <= 0`
  - `n_windows < 1`
  - `train_size` not in `(0, 1]`
  - `step_size <= 0` (must be positive; a zero step was already flagged in the
    CLI walk-forward path)
  - `periods_per_year < 1`
  - `commission` not in `[0, 1]`
  - `slippage` not in `[0, 1]`
- Add parametrized rejection tests + boundary-acceptance tests in
  `tests/test_walk_forward.py` (create if it does not exist).
- Verify: `tests/test_walk_forward.py`, `tests/test_optimization.py` if present,
  ruff on `quant_trading/optimization/walk_forward.py`, mypy on
  `quant_trading/optimization/walk_forward.py`, and the walk-forward doctest
  (`quant_trading/optimization/walk_forward.py:434-444` passes
  `strategy_cls=None`, so do not validate `strategy_cls`).
