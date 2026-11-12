# Next Task

## Repository state (verified this session)
- Branch `main` up to date with `origin/main`; working tree clean.
- `python -m ruff check .` → All checks passed.
- `python -m mypy quant_trading --ignore-missing-imports` → Success: no issues in 38 source files.

## Completed this session

**Verified: `RiskManager.__init__` validation is already implemented and tested.**

The `RiskManager.__init__` method in `quant_trading/risk/manager.py:227-276` already validates all constructor parameters:
- `initial_capital <= 0` → `ValueError`
- `max_position_size` not in `(0, 1]` → `ValueError`
- `max_portfolio_risk` not in `(0, 1]` → `ValueError`
- `max_drawdown` not in `[0, 1]` → `ValueError`
- `max_positions < 1` → `ValueError`
- `stop_loss_pct` not in `[0, 1]` → `ValueError`
- `take_profit_pct` not in `[0, 1]` → `ValueError`
- `max_leverage < 1e-9` → `ValueError`
- `trailing_stop_pct` not in `[0, 1]` → `ValueError`
- `trailing_stop_activation_pct` not in `[0, 1]` → `ValueError`

**Tests** in `tests/test_risk_manager.py::TestRiskManagerInitValidation` cover all validation cases with parametrized rejection tests and boundary-acceptance tests (165 tests total in the file, all passing).

## Verified (this session, evidence)
- `tests/test_risk_manager.py` → **165 passed**
- `tests/test_limits.py` + `tests/test_portfolio_rebalancer.py` → **180 passed**
- `ruff check quant_trading/risk/manager.py tests/test_risk_manager.py` → **All checks passed**
- `mypy quant_trading/risk/manager.py --ignore-missing-imports` → **Success**

## Unresolved / not completed
- None for the previously assigned task.

## Failed approaches (do not repeat unchanged)
- None.

## Verification commands (re-run before starting)
```bash
python -m pytest tests/test_risk_manager.py tests/test_limits.py tests/test_portfolio_rebalancer.py -q -p no:cacheprovider
python -m ruff check quant_trading/risk/manager.py tests/test_risk_manager.py
python -m mypy quant_trading/risk/manager.py --ignore-missing-imports
```

## Git state
- Branch `main` up to date with `origin/main`.
- Working tree clean.

## One precise next task

**Add construction-time input validation to `PortfolioRebalancer.__init__`** (`quant_trading/portfolio/rebalancer.py:104-174`), mirroring the `RiskManager` and `MonteCarloSimulator` validation pattern.

The `PortfolioRebalancer.__init__` accepts parameters without validation:
- `target_weights` (dict[str, float]) — should validate: non-empty, all values > 0, sum ≈ 1.0
- `tolerance` (float) — should be in `(0, 1]`
- `min_trade_size` (float) — should be >= 0
- `max_turnover` (float | None) — if not None, should be in `(0, 1]`
- `risk_manager` (RiskManager | None) — no validation needed (duck-typed)
- `allow_short` (bool) — no validation needed
- `cash_buffer_pct` (float) — should be in `[0, 1]`
- `rebalance_on_drawdown_breach` (bool) — no validation needed

Add parametrized rejection tests + a boundary-acceptance test in `tests/test_portfolio_rebalancer.py` (or a new `TestPortfolioRebalancerInitValidation` class). Verify: `tests/test_portfolio_rebalancer.py`, `tests/test_rebalancer.py`, ruff, mypy on `quant_trading/portfolio/rebalancer.py`.