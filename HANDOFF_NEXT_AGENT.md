## Status

Completed the assigned numerical audit of `quant_trading/risk/metrics.py` and
`quant_trading/backtest/metrics.py`. The existing empty/constant/single/zero
guards were mostly sound; direct probing found real remaining failures when
NaN/inf observations were present.

Reproduced defects that are now fixed:

1. Non-finite return observations produced NaN volatility/VaR/CVaR/Omega
   results.
2. A non-finite portfolio return could produce NaN beta/alpha/Treynor results.
3. Non-finite rows in allocation inputs produced NaN volatility contributions
   or non-finite/non-normalized ERC/risk-budget weights.
4. NaN/inf equity endpoints leaked into `BacktestMetrics.total_return` and
   `total_return_pct`.
5. NaN/inf trade PnL contaminated `total_pnl`, average win/loss, extrema, and
   profit factor.

## What Changed

### `quant_trading/risk/metrics.py`
- Added private `_drop_non_finite` and `_drop_non_finite_rows` helpers.
- Return/equity-based metrics now ignore NaN and infinite observations before
  calculating:
  - `calculate_volatility`, `calculate_max_drawdown`, `calculate_sharpe_ratio`,
    `calculate_sortino_ratio`, `calculate_var`, `calculate_cvar`,
    `calculate_omega_ratio`, `calculate_calmar_ratio`, `calculate_ulcer_index`.
- DataFrame allocation metrics now drop rows containing non-finite values:
  `calculate_marginal_var`, `calculate_volatility_contributions`,
  `calculate_equal_risk_contribution_weights`, and
  `calculate_risk_budget_weights`.
- `calculate_beta` and `calculate_information_ratio` return their neutral
  `0.0` result when either input contains an infinity, preserving the existing
  contract while avoiding undefined covariance/tracking-error arithmetic.
- `calculate_beta` also guards a non-finite computed beta.

### `quant_trading/backtest/metrics.py`
- `calculate_backtest_metrics` drops NaN/inf equity and benchmark observations
  before computing returns and market-relative metrics.
- Trade totals and derived trade statistics exclude non-finite PnL values.
  Structural trade counts remain unchanged.

### Repository-integrity fixes
- Added missing Args/Returns/Examples docs for the new risk helpers and the
  existing `quant_trading/optimization/base.py::_finite_or_zero` helper.
- Updated `tests/test_optimization.py` to set its intentionally dynamic
  `win_rate_pct` attribute through `vars(result)`, satisfying mypy without
  violating Ruff.

### Tests added
- `tests/test_risk_metrics.py`: non-finite scalar returns, market-relative
  metrics, and `calculate_all_metrics`.
- `tests/test_backtest_metrics.py`: non-finite equity endpoints, benchmark
  returns, trade PnL, and a finiteness invariant over all numeric fields.
- `tests/test_risk_attribution.py`: non-finite allocation inputs for
  volatility contributions, ERC weights, and risk-budget weights.

## What Was Verified

- Targeted suites plus changed-module doctests:
  `python -m pytest -q tests/test_risk_metrics.py tests/test_backtest_metrics.py tests/test_risk_attribution.py quant_trading/risk/metrics.py quant_trading/optimization/base.py quant_trading/backtest/metrics.py`
  — **329 passed**.
- Full suite: `python -m pytest -q` — **4,312 passed, 151 deselected** in
  341.21s.
- `python -m mypy quant_trading tests/test_optimization.py` — clean.
- `python -m ruff check` on all changed Python files — clean.
- `python -m black --check` on all changed Python files — clean.
- `git diff --check` — clean.
- Working tree was not committed or pushed.

## Unresolved / Notes

- Non-finite observations are now treated as missing data and excluded from
  calculations. This is intentional and matches the existing NaN-dropping
  behavior, but callers that need to distinguish dirty data from valid zeros
  must validate upstream.
- Non-finite trade PnL is excluded from derived trade statistics while
  `num_trades` still reflects completed round-trip rows. This preserves the
  existing trade-count contract.
- `calculate_beta`/`calculate_information_ratio` return `0.0` when either input
  contains an infinity. This preserves the repository's existing beta contract;
  do not silently change it to positional cleaning without updating tests.
- No Hypothesis dependency was added; focused parametrized manual edge cases
  cover the reproduced failures.

## Failed Approach / Evidence

An initial fix sanitized infinities inside `_align_series`. This broke the
existing contract that a benchmark containing `inf` must produce beta `0.0`
(`TestCalculateBeta.test_beta_non_finite_market_variance` changed from 0.0 to
2.0). The change was reverted; the narrower final fix keeps NaN dropping in
`_align_series` and guards infinity in the public beta/information-ratio
functions.

The first full-suite run also exposed repository-integrity failures that were
already present or caused by the new helpers: missing docstring sections on
`_finite_or_zero` and the two new risk helpers, plus a test-only mypy error from
assigning a dynamic attribute. These were fixed directly; no alternate approach
was abandoned for them.

## One Precise Next Task

The trade-analysis/trade-log audit is complete (this session). `analyze_trades`
and `_calculate_symbol_stats` now treat non-finite PnL as missing data so every
numeric field stays finite and trade/round-trip counts stay consistent with
`calculate_backtest_metrics`. Verified with:

- `python -m pytest -q tests/test_trade_analysis.py tests/test_backtest_metrics.py tests/test_trade_log.py` — 156 passed.
- Module doctests `quant_trading/backtest/trade_analysis.py trade_log.py metrics.py` — 8 passed.
- `python -m mypy quant_trading/backtest/trade_analysis.py` — clean.
- `python -m ruff check` and `python -m black --check` on the two changed files — clean.
- Working tree not committed or pushed.

Next bounded task: audit `quant_trading/portfolio/` and the rebalancer
(`quant_trading/rebalancer/`) for the same degenerate/non-finite-input defects
(empty positions, NaN/+inf/-inf prices, weights, or cash). Assert every numeric
output stays finite and that any trade/position counts stay consistent across
the portfolio and rebalancer APIs. Do not change count semantics without a
failing focused test. Keep the fix minimal and rerun:

```bash
python -m pytest -q tests/test_portfolio.py tests/test_rebalancer.py tests/test_portfolio_invariants.py tests/test_rebalancer_risk_integration.py
```
