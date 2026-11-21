## Status

Completed the assigned non-finite-input audit of `quant_trading/portfolio/`
and `quant_trading/portfolio/rebalancer/`. Degenerate inputs (empty positions,
NaN/+inf/-inf prices, weights, cash) no longer produce non-finite numeric
outputs, and trade/position counts stay consistent with `calculate_backtest_metrics`.

## What Changed

### `quant_trading/portfolio/portfolio.py`
- Added `_finite_or_default` helper: non-finite / non-numeric values are
  restored as `0.0` (missing data), matching the existing `__post_init__` /
  `reset` sanitization contract.
- `Portfolio.from_dict` now sanitizes `cash`, `initial_capital`, and
  `total_value` (non-finite total value falls back to restored cash), so
  `summary()` fields (`total_value`, `cash`, `holdings_value`, `pnl`,
  `pnl_pct`) always stay finite.
- `Holding.from_dict` now sanitizes `quantity`, `avg_cost`, `current_price`,
  `market_value`, so a restored holding never carries a non-finite quantity
  (which previously inflated `num_positions` while reporting zero value).

### `quant_trading/portfolio/rebalancer.py`
- `calculate_target_values` returns `{}` when the portfolio value is
  non-finite instead of leaking `inf`/`nan` targets.
- `generate_rebalance_actions` returns `[]` (and records an empty run) when
  the portfolio value is non-finite, since no trade can be sized against it.
- The signal-sell branch skips a holding with a non-finite quantity (no
  `nan`-quantity action, no corrupted `_plan_sell` state).
- `execute_actions` treats a non-finite action quantity as `0.0`: the action
  is skipped and reported with `executed_quantity` / `requested_quantity` of
  `0.0`.

### Tests added
- `tests/test_portfolio.py`: `from_dict` sanitization of non-finite cash,
  total value, initial capital, and holding fields; `summary()` finiteness
  invariant after a non-finite restore; `Holding.from_dict` sanitization.
- `tests/test_rebalancer.py`: non-finite portfolio value yields no targets
  and no actions; signal sell skips non-finite quantity; infinite prices
  produce only finite action quantities; `execute_actions` skips non-finite
  action quantities.

## What Was Verified

- Targeted suites plus changed-module doctests:
  `python -m pytest -q tests/test_portfolio.py tests/test_portfolio_invariants.py tests/test_rebalancer.py tests/test_rebalancer_risk_integration.py tests/test_rebalancer_execution.py tests/test_rebalancer_extra_coverage.py tests/test_rebalancer_sizing_invariants.py tests/test_rebalancer_risk_parity.py quant_trading/portfolio/` — **323 passed**.
- `python -m mypy quant_trading/portfolio/` — clean.
- `python -m ruff check` on all changed files — clean.
- `python -m black --check` on all changed files — clean.
- `git diff --check` — clean.
- Working tree not committed or pushed.

Full suite: **4,240 passed, 89 skipped, 151 deselected**; the only 4 failures
were in `tests/test_repository_integrity.py` and are all resolved by this
session except one (see Unresolved).

## Unresolved / Notes

- `test_repository_is_black_formatted` still fails on
  `quant_trading/backtest/trade_log.py`, which is **pre-existing** (the file
  is untouched by this session and fails `black --check` at `HEAD`). Out of
  scope for this audit; leave it or fix it as a separate formatting task.
- Non-finite observations are treated as missing data and excluded/sanitized;
  callers that need to distinguish dirty data from valid zeros must validate
  upstream.
- Count semantics were not changed: zero/non-finite trades never create
  positions, and structural trade/position counts stay consistent with
  `calculate_backtest_metrics`.

## Failed Approach / Evidence

None for this task: every defect was first reproduced with a focused probe
(`float("nan")`/`float("inf")` via `from_dict`, injected non-finite holding
quantities, infinite prices, nan-quantity actions) before the matching minimal
guard was added. The earlier `risk/metrics.py` and `trade_analysis` sessions
already established the "non-finite = missing data" convention followed here.

## One Precise Next Task

Continue the same degenerate/non-finite-input audit on
`quant_trading/risk/limits.py` and `quant_trading/config/settings.py` (the
portfolio risk limits and config values the rebalancer and backtest consume at
construction). Assert every numeric output stays finite and that count/limit
semantics are unchanged. Keep fixes minimal; add focused tests mirroring the
`from_dict`/input-sanitization style of this session, then rerun:

```bash
python -m pytest -q tests/test_risk_manager.py tests/test_config.py tests/test_limits.py tests/test_portfolio.py tests/test_rebalancer.py quant_trading/risk/limits.py quant_trading/config/settings.py
python -m mypy quant_trading/risk/ quant_trading/config/
python -m ruff check quant_trading/risk/limits.py quant_trading/config/settings.py tests/test_risk_manager.py tests/test_config.py tests/test_limits.py
python -m black --check quant_trading/risk/limits.py quant_trading/config/settings.py tests/test_risk_manager.py tests/test_config.py tests/test_limits.py
```
