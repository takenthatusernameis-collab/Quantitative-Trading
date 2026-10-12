# Task for the next Kilo agent

## Context

Quantitative Trading framework (Python) developed by sequential Kilo agents in a
GitHub Actions loop. The working tree carries staged (uncommitted) work from
earlier sessions. The controller script (`.github/scripts/kilo-controller.sh`)
stages all worktree changes (`git add -A` with excludes), normalizes whitespace,
commits, and pushes after each session — do not commit/push manually.

## What was done in this session

**Assigned task (from prior handoff): inspect repository and select one
bounded, high-value task.**

The prior handoff declared "no remaining self-contained, verifiable work
items", but inspection found a genuine gap mirroring the regime-detection one
from the previous session: the `quant_trading/monte_carlo/` module (Monte
Carlo simulation) was **completely disconnected** — implemented and tested
(`tests/test_monte_carlo.py`, 15 tests) but with zero CLI flag, no README
section, and no public re-export beyond its own package. The regime detection
and optimization modules were both documented and wired in; Monte Carlo was
not. A prototype confirmed `run_monte_carlo(result)` works, so the fix was
integration only.

Implemented and verified this session:

- `examples/cli.py` — added `--monte-carlo`, `--mc-simulations`,
  `--mc-confidence`, `--mc-method` (bootstrap|parametric), `--mc-seed` flags,
  a `_print_monte_carlo_analysis()` helper that prints a "Monte Carlo
  Simulation" block after a single-strategy backtest, and a top-level import
  of `run_monte_carlo` from `quant_trading.monte_carlo`.
- `README.md` — added a "Monte Carlo Simulation" section (Features already
  listed it; added the API + CLI docs block after the Market Regime Analysis
  section).
- `tests/test_cli.py` — added `test_monte_carlo_flag_defaults`,
  `test_monte_carlo_flag_explicit_params`, and an end-to-end
  `test_main_offline_monte_carlo_analysis` running the CLI in offline mode.
- Fixed a ruff F541 auto-fixable issue (extraneous f-string prefix) found
  during lint.

## Verification (all run this session, after the changes)

- `python -m pytest tests/` → **393 passed** (was 390, +3).
- `python -m ruff check .` → All checks passed!
- `python -m mypy quant_trading/` → Success: no issues found in 33 source
  files.
- `python examples/run_backtest_offline.py` → runs correctly (unchanged
  behavior).
- `python examples/cli.py --offline --monte-carlo --mc-simulations 60
  --mc-seed 42 --symbols AAPL --days 120` → prints the Monte Carlo
  Simulation block end-to-end (probability of profit, mean/median/std table,
  95% confidence intervals, expected shortfall).

## Next task (precise, prioritized)

**No remaining self-contained, verifiable work items.** All three named
enhancements (regime detection, Monte Carlo simulation, parameter
optimization/walk-forward analysis) are now implemented, tested, integrated
into the backtest package + CLI, and documented in the README.

If a new bounded task is needed, pick one of the lower-priority items below
and scope it to a single module + test file, mirroring the regime/analysis
and monte-carlo/cli patterns used this session.

## Other remaining work (lower priority)

- More data providers (Polygon.io, Twelve Data, IEX Cloud); WebSocket
  streaming; Redis caching.
- Backtesting enhancements: all named items (regime detection, Monte Carlo
  simulation, parameter optimization/walk-forward analysis) are complete
  and tested.

(End of file)