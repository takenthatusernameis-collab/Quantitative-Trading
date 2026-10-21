# Next Task

## What changed

Fixed the three risk-layer defects left by the previous session, all inside
`quant_trading/risk/`:

1. **`calculate_metrics()` beta/alpha silently `0.0`** — `quant_trading/risk/manager.py` built the equity series with a `RangeIndex` (`pd.Series(self.equity_curve)`), while a date-indexed benchmark failed to align, so `calculate_beta`/`calculate_align` returned `0.0`.
   - Added a positional fallback in `quant_trading/risk/metrics.py`: a new `_align_series()` helper tries index alignment first, then falls back to pairing observations by position when the indices are incompatible and fewer than two points overlap. Used by both `calculate_beta` and `calculate_align`. Public signatures unchanged.
   - Decision: positional fallback (not a fabricated date index), because the equity curve carries no dates and generated dates could not be guaranteed to overlap the benchmark.

2. **`calculate_returns()` zero denominator** — `quant_trading/risk/metrics.py` divided by the previous price without guarding zero, so an equity curve touching `0.0` produced `inf`/`NaN` volatility, Sortino, VaR and Calmar.
   - `calculate_returns()` now computes `(prices - shift) / shift` under `np.errstate`, replaces `+/-inf` with `NaN`, and drops them, so downstream metrics stay finite. Public signature unchanged.

3. **`PortfolioLimit(max_drawdown=0.0)` did not disable the limit** — `quant_trading/risk/limits.py:PortfolioLimit.check()` reported a drawdown violation for any dip even when `max_drawdown=0.0`, contradicting the README and `RiskManager._reject_signal_if_in_drawdown_breach`.
   - The drawdown check is now skipped when `max_drawdown <= 0`, making `check_portfolio()` agree with the signal gate.

Tests added:
- `tests/test_risk_manager.py`: `test_calculate_metrics_nonzero_beta_for_moving_benchmark` (non-zero beta for a date-indexed benchmark moving with the strategy) and `test_check_portfolio_drawdown_limit_of_zero_is_disabled`.
- `tests/test_risk_metrics.py`: `test_returns_zero_previous_price_no_inf`, `test_beta_insufficient_aligned_points_after_fallback`, and reworked `test_beta_non_overlapping_indices_aligns_positionally` to document the fallback.
- `tests/test_limits.py`: `test_check_drawdown_limit_of_zero_is_disabled` and `test_position_risk_zero_basis_returns_zero`.

## What was actually verified

- Full suite: `1822 passed, 1 skipped` (run with coverage; the 1 skipped is pre-existing).
- `quant_trading/risk/` at **100%** statement and branch coverage (`limits`, `manager`, `metrics` all 100%).
- `ruff check quant_trading tests examples` -> All checks passed.
- `black --check quant_trading tests examples` -> 89 files unchanged.
- `mypy quant_trading` -> no issues.

## What remains unresolved

Nothing from the assigned risk-layer defects. All three are fixed and verified.

## Approaches that already failed

- A date-indexed equity curve for Fix 1 was considered but rejected: the equity curve carries no dates, and fabricated dates could not be guaranteed to overlap a user-supplied date-indexed benchmark. Positional fallback is the robust fix.

## Next task

The three assigned risk-metric defects are resolved; there is no further assigned task. Changes are in the working tree (uncommitted). The next agent should inspect `git status`/`git diff` and select a new bounded, high-value task from the repository.
