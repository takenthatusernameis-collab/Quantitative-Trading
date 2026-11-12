# Next Task

## Repository state (verified this session)
- Branch `main` up to date with `origin/main`; working tree has uncommitted changes (rebalancer validation regression fixes).
- `Rebalancer.__init__` construction-time validation (HEAD `c157804`) is implemented and verified:
  - `frequency` must be one of daily/weekly/monthly/quarterly → `ValueError`
  - `target_allocation` weights must be finite numbers → `ValueError`
  - `rebalance_threshold` must be in `[0, 1]` → `ValueError`
- `python -m ruff check quant_trading/portfolio/rebalancer.py tests/test_portfolio_rebalancer.py tests/test_rebalancer.py` → All checks passed.
- `python -m mypy quant_trading/portfolio/rebalancer.py --ignore-missing-imports` → Success.
- Rebalancer test files → **222 passed**; full suite → **3484 passed** with only pre-existing optional-dependency gaps (scikit-optimize/matplotlib), no new failures.

## Completed this session

Fixed 4 regressions caused by the `Rebalancer.__init__` validation:
- `tests/test_portfolio_rebalancer.py::test_unrecognized_frequency` — now asserts `ValueError` for `frequency="yearly"`.
- `tests/test_portfolio_rebalancer.py::test_target_buy_exact_target_no_action` — `rebalance_threshold=-0.001` → `0.05`.
- `tests/test_rebalancer.py::test_should_rebalance_unknown_frequency` — now asserts `ValueError` for `frequency="yearly"`.
- `tests/test_rebalancer.py::test_generate_rebalance_actions_exact_diff_negative_threshold` — `rebalance_threshold=-0.1` → `0.05`.
Also fixed ruff `PLR0124` in `quant_trading/portfolio/rebalancer.py:440` (self-comparison `weight == weight` → `isfinite(weight)`).

## Unresolved / not completed

- The previously listed task ("Add construction-time input validation to `PortfolioRebalancer.__init__` with `target_weights`, `tolerance`, `min_trade_size`, `max_turnover`, `cash_buffer_pct`, `allow_short`, `rebalance_on_drawdown_breach`") **cannot be executed as written**: no `PortfolioRebalancer` class and none of those parameters exist in the codebase. The real class is `Rebalancer`, and its `__init__` validation is already complete and verified. This task should be retired, not re-implemented as a fabricated parallel class.
- 3 full-suite failures are pre-existing optional-dependency gaps (`scikit-optimize` bayesian; `matplotlib` reporting). Install `quant-trading[reporting bayesian]` to clear them.

## Failed approaches (do not repeat unchanged)
- None. Do not weaken the `Rebalancer.__init__` validation to satisfy the old lenient tests; update those tests to the new contract (done).

## Verification commands (re-run before starting)
```bash
python -m pytest tests/test_portfolio_rebalancer.py tests/test_rebalancer.py -q -p no:cacheprovider
python -m ruff check quant_trading/portfolio/rebalancer.py tests/test_portfolio_rebalancer.py tests/test_rebalancer.py
python -m mypy quant_trading/portfolio/rebalancer.py --ignore-missing-imports
python -m pytest -q -p no:cacheprovider
```

## Git state
- Branch `main` up to date with `origin/main`.
- Working tree has uncommitted changes (`quant_trading/portfolio/rebalancer.py`, `tests/test_portfolio_rebalancer.py`, `tests/test_rebalancer.py`). Do NOT commit unless explicitly asked.

## One precise next task

Retire this stale next-task entry (the `PortfolioRebalancer.__init__` validation task references nonexistent code; `Rebalancer.__init__` validation is done), then clear the remaining optional-dependency test failures: `pip install quant-trading[reporting bayesian]` and re-run `python -m pytest -q -p no:cacheprovider` to confirm the full suite is green. If pip/network is unavailable, document that as a blocker.
