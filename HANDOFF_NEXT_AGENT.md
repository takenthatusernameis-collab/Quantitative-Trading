## Status

Audited `quant_trading/risk/manager.py` (the `RiskManager`) for
degenerate/non-finite-input defects: NaN/+inf/-inf signal prices, portfolio
values, position values, drawdown, and limit config, plus empty/flat positions.
Fixes applied to `quant_trading/risk/manager.py` following the same
sanitize-to-zero/drop-non-finite pattern used in `quant_trading/portfolio/`,
`quant_trading/risk/metrics.py`, and `quant_trading/risk/limits.py`; 28
regression tests added to `tests/test_risk_manager.py`.

## What Changed (this session)

`quant_trading/risk/manager.py`:

- `__init__`: reject non-finite `risk_free_rate` (limit config).
- `update_portfolio_value`: store positions via a new `_sanitize_position`
  helper (non-finite `quantity`/`avg_price`/`current_price` zeroed to 0.0) and
  coerce non-finite `cash` to 0.0, so `total_market_value`,
  `positions_value`, leverage, drawdown, and `peak_value` stay finite.
- `sync_position`: store sanitized positions.
- `check_signal`: reject non-finite `portfolio_value` (nan/inf/-inf, like
  `<= 0`); treat non-finite `signal.price` as "no price"; reject non-finite
  `signal.strength` ("invalid strength").
- `update_trailing_stop`: reject non-finite prices.
- `get_position_stop_loss`/`get_position_take_profit`: return None for
  non-finite `avg_price`.
- `_position_weights`: raise on non-finite total market value.
- `calculate_metrics`: validate `periods_per_year` and reject non-finite
  `risk_free_rate`.
- `check_portfolio`: reject non-finite internal portfolio state.

`tests/test_risk_manager.py`: new `TestNonFiniteInputs` class with 28
regression tests covering every leak below.

## What Was Verified

- `python -m pytest -q tests/test_risk_manager.py` — **263 passed**
  (235 pre-existing + 28 new).
- Risk family:
  `tests/test_limits.py tests/test_risk_metrics.py tests/test_risk_attribution.py
  tests/test_cost_accounting_invariants.py tests/test_holding_pnl_invariants.py`
  — **688 passed**.
- Neighbor suites:
  `tests/test_backtest_engine.py tests/test_integration.py
  tests/test_backtest_metrics.py tests/test_portfolio.py tests/test_rebalancer.py`
  — **326 passed**.
- Module doctests: `quant_trading/risk/manager.py` — **25 passed**.
- `python -m mypy quant_trading/risk/manager.py tests/test_risk_manager.py` — clean.
- `python -m ruff check quant_trading/risk/manager.py tests/test_risk_manager.py` — clean.
- `python -m black --check quant_trading/risk/manager.py tests/test_risk_manager.py` — clean.
- Degenerate-input probe (22 checks): NaN/inf/-inf cash, capital, prices,
  quantities, signal prices/strengths; non-finite metrics args; nan state —
  all rejected or sanitized, **0 leaks remain**.

## Unresolved / Notes

- Pre-existing repo-integrity failures unrelated to this change (also fail on
  baseline `cd89df5`; left untouched):
  - `test_repository_is_black_formatted`: `quant_trading/backtest/trade_log.py`
    is not black-formatted.
  - `test_documented_examples_are_valid`:
    `quant_trading/portfolio/rebalancer.py:98` and `:306` have empty Examples
    sections.

## Failed Approach / Evidence

None this session; the probe confirmed each leak and every fix resolved its
leak (re-run probe shows 0 LEAKS).

## One Precise Next Task

Audit `quant_trading/backtest/engine.py` (the `run_backtest`/`BacktestEngine`
path) for the same degenerate/non-finite-input defects: non-finite
`initial_capital`, prices, position sizes, and equity curve values must not
produce non-finite metrics or silent bad decisions. Reuse the
sanitize-to-zero/drop-non-finite pattern and the `RiskManager`/`limits.py`
validation conventions. Verify with:

```bash
python -m pytest -q tests/test_backtest_engine.py
python -m pytest --doctest-modules -q quant_trading/backtest/engine.py
python -m mypy quant_trading/backtest/engine.py
python -m ruff check quant_trading/backtest/engine.py
python -m black --check quant_trading/backtest/engine.py
```

Relevant evidence: the README documents non-finite guards at the CLI for
`--initial-capital`, `--risk-free-rate`, and `--periods-per-year`; the engine
consumes those values directly, so the library boundary should reject or
sanitize them the same way.
