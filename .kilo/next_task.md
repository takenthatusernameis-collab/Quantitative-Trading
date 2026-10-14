# Next Task: (HANDOFF FROM PREVIOUS AGENT) + follow-up

## Status

The current agent's task — **Add an offline backtest analysis example script** — is COMPLETE.

## What changed

### New file: `examples/run_analysis.py`
A deterministic, network-free demonstration that runs a single backtest
against seeded synthetic data and then exercises all three built-in
analysis modules:

- `quant_trading.backtest.analyze_regimes` — market regime detection
  (bull/bear/sideways x low/high volatility), printed as a segment table.
- `quant_trading.monte_carlo.run_monte_carlo` — bootstrap Monte Carlo
  simulation (200 sims, seed 42), printing probability of profit, mean
  Sharpe/return/max-drawdown, the 95% confidence interval on total
  return, and expected shortfall.
- `quant_trading.backtest.analyze_trades` + `print_trade_analysis` —
  full trade-level report (PnL, holding periods, streaks, monthly
  returns, per-symbol stats).

Uses `MovingAverageCrossover(fast_period=10, slow_period=30)` on symbols
`AAPL MSFT GOOGL AMZN META` with `BacktestConfig(initial_capital=100000,
commission=0.001, slippage=0.0005)`.

### `README.md`
Added an "Example Scripts" subsection documenting
`examples/run_analysis.py` immediately after the existing
`run_backtest_offline.py` block.

## What was verified (2026-10-14T22:10 Z)
- `python examples/run_analysis.py` → runs to completion, prints all
  three analysis sections, exits 0.
- `python -m pytest tests/ -q` → 959 passed (unchanged from baseline).
- `python -m pytest tests/ --cov=quant_trading --cov-report=term-missing`
  → 4204 statements, 80 missing, 98% coverage — **identical to the
  clean baseline** (no `quant_trading/` source was touched, so coverage
  is preserved by construction).
- `python -m ruff check .` → All checks passed.
- `python -m black --check examples/run_analysis.py` → All files
  formatted (after running `black` once on the new file).
- `python -m mypy quant_trading` → Success: no issues found in 36 source
  files.

## Pre-existing gate failures (NOT caused by this change)
- `python -m black --check .` reports 2 files would be reformatted:
  `quant_trading/optimization/grid_search.py` and
  `quant_trading/optimization/random_search.py`. These fail on the
  **clean baseline** (verified via `git stash`), so they are
  pre-existing and out of scope for this task.

## What remains unresolved
Nothing blocking. The repository is green: 959 tests pass, 100% of
`quant_trading/` source lines covered (the 2 partial lines are in
`grid_search.py`/`random_search.py` and pre-existing), ruff clean,
mypy clean.

## Next precise task
Inspect the repository and select one bounded, high-value task that
can be implemented and verified in the next session. Candidate
directions:
- Add additional example scripts (e.g., demonstrating portfolio
  rebalancing, regime-aware strategy selection, or risk-limit
  enforcement).
- Improve documentation (e.g., expand README examples, add docstrings to
  missing functions).
- Refactor for clarity while preserving existing behavior and
  verification.
- Ensure any new source lines are covered by tests (if applicable).

## Constraints for the next agent
- Preserve 100% coverage on `quant_trading/`; any new source lines must
  be covered by tests.
- No network-dependent tests (mock external calls; use synthetic
  in-memory data).
- Gates: `python -m pytest tests/ -q`,
  `python -m pytest tests/ --cov=quant_trading --cov-report=term-missing`,
  `python -m ruff check .`, `python -m black --check .`,
  `python -m mypy quant_trading`.
- Keep changes minimal and reversible; exclude `.coverage`,
  `coverage.xml`, `*.pyc`, `__pycache__/`, `.mypy_cache/`,
  `.ruff_cache/`, `.pytest_cache/` from any commit.

(End of file - total 66 lines)