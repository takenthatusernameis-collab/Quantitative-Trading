## What changed (this session)

Extended library-level input validation to `RiskConfig` and `PortfolioConfig` in
`quant_trading/config/settings.py`, mirroring the existing `RiskManager`
validation (`quant_trading/risk/manager.py:232-276`) and the prior
`BacktestConfig`/`BaseOptimizer` validation. `__post_init__` now raises
`ValueError` at construction (covers direct construction, `from_dict`, and
`from_yaml`):

`RiskConfig`:
- `max_position_size` in `(0, 1]` (`invalid max_position_size`)
- `max_portfolio_risk` in `(0, 1]` (`invalid max_portfolio_risk`)
- `max_drawdown`, `stop_loss_pct`, `take_profit_pct`, `trailing_stop_pct`,
  `trailing_stop_activation_pct` in `[0, 1]`
- `max_leverage` positive (`invalid max_leverage`)

`PortfolioConfig`:
- `max_positions >= 1` (`invalid max_positions`)
- `min_position_size` in `[0, 1]` (`invalid min_position_size`)

Error-message prefixes match `RiskManager` exactly so the existing
`pytest.raises(..., match=...)` style aligns.

**Tests added** (`tests/test_config.py`):
- `TestRiskConfig`: parametrized rejection tests for all 8 fields, boundary
  acceptance test, `test_from_dict_rejects_invalid_values`,
  `test_from_yaml_rejects_invalid_values`
- `TestPortfolioConfig`: rejection tests for `max_positions` and
  `min_position_size`, boundary acceptance test, `test_from_dict_rejects_invalid_values`,
  `test_from_yaml_rejects_invalid_values`

Also fixed one pre-existing broken test:
- `tests/test_backtest_engine.py::test_run_with_zero_initial_capital_is_rejected`
  constructed `BacktestConfig(initial_capital=0.0)` outside the
  `pytest.raises` block, which now raises at config construction (committed
  `BacktestConfig.__post_init__` validation). Moved the construction inside the
  `with` block so the rejection is actually asserted.

Files changed: `quant_trading/config/settings.py` (+68), `tests/test_config.py`
(+104), `tests/test_backtest_engine.py` (~4 lines moved).

## Verified (this session, evidence)

- `python -m pytest tests/test_config.py -q -p no:cacheprovider` → 88 passed
- Affected files (`test_config`, `test_backtest_engine`, `test_integration`,
  `test_serialization_roundtrip`, `test_rebalancer`, `test_risk_manager`,
  `test_limits`) → 532 passed
- Full suite `python -m pytest -q -p no:cacheprovider` → 3319 passed;
  17 failures are pre-existing environment gaps (missing `matplotlib` /
  `scikit-optimize` optional deps: report/HTML-report/bayesian CLI tests),
  none related to this change
- `python -m ruff check quant_trading/config/settings.py tests/test_config.py tests/test_backtest_engine.py` → All checks passed
- `python -m mypy quant_trading/config/settings.py --ignore-missing-imports` → Success: no issues found

## Unresolved / not completed

- None for the assigned task. The 17 full-suite failures are pre-existing
  optional-dependency gaps, not caused by this change.

## Failed approaches (do not repeat unchanged)

- None.

## Verification commands (re-run before starting)

```bash
python -m pytest tests/test_config.py tests/test_backtest_engine.py -q -p no:cacheprovider
python -m ruff check quant_trading/config/settings.py tests/test_config.py tests/test_backtest_engine.py
python -m mypy quant_trading/config/settings.py --ignore-missing-imports
```

## Git state

- Branch `main` up to date with `origin/main`.
- Working tree has uncommitted changes (settings.py, test_config.py,
  test_backtest_engine.py). Do NOT commit unless explicitly asked.

## One precise next task

A natural follow-up bounded task: extend the same `__post_init__` input
validation to `DataConfig` (`quant_trading/config/settings.py`), mirroring the
existing validation style. Sensible checks: `synthetic_days >= 1`,
`provider`/`default_interval`/`default_period` non-empty strings,
`synthetic_seed` any int (defaults already valid). Add parametrized rejection +
boundary tests plus `from_dict`/`from_yaml` rejection tests to
`tests/test_config.py` (class `TestDataConfig` exists), then run the
verification commands above plus the full suite. Scope constraint: keep changes
minimal (`__post_init__` only) and do not alter `Config.update()` unless a
separate issue motivates it.
