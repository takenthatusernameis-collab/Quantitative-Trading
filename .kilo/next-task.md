# Next Task

## What changed (this session)

Task: make the annualization period configurable and internally consistent
across the risk/backtest metrics layer, and stop single-observation Sharpe
from returning NaN.

- `quant_trading/risk/metrics.py`
  - `calculate_volatility`, `calculate_sharpe_ratio`, `calculate_sortino_ratio`,
    `calculate_alpha`, `calculate_calmar_ratio` and `calculate_all_metrics` now
    accept an optional `periods_per_year: int = 252`. The value drives the
    `sqrt(periods_per_year)` annualization scaling **and** the conversion of
    the annual risk-free rate into a per-period rate
    (`risk_free_rate / periods_per_year`). The hardcoded `252` literals are
    gone.
  - `calculate_sharpe_ratio` no longer returns `NaN` for a single observation.
    The old guard `returns.std() == 0` is `False` for a 1-element series
    (`std` is `NaN`), so the ratio evaluated to `NaN` despite the docstring
    promising `0.0`. The guard is now `not np.isfinite(std) or std == 0`.
    `calculate_sortino_ratio` got the same `np.isfinite` guard for symmetry.
  - Defaults are unchanged (252), so all previously computed numbers are
    bit-for-bit identical.
- `quant_trading/backtest/metrics.py`: `calculate_backtest_metrics` already
  accepted `periods_per_year` but only used it for `annual_return` — every
  risk metric still used the hardcoded 252. It now forwards the value to
  volatility/Sharpe/Sortino/Calmar.
- `quant_trading/risk/manager.py`: `RiskManager.calculate_metrics` accepts
  and forwards `periods_per_year`.
- `quant_trading/config/settings.py`: `BacktestConfig` gained a
  `periods_per_year: int = 252` field (round-trips through YAML via the
  existing `__dict__` / `_filter_fields` plumbing).
- `quant_trading/backtest/engine.py`: `BacktestEngine.run` forwards
  `config.periods_per_year`; `run_backtest()` gained a `periods_per_year`
  parameter.
- `quant_trading/optimization/{base,grid_search,random_search,bayesian,walk_forward}.py`:
  `periods_per_year` threaded through `BaseOptimizer` (and the three
  subclasses) and `WalkForwardOptimizer` into every backtest they run and
  into the combined out-of-sample metrics.
- `quant_trading/monte_carlo/simulator.py`: `MonteCarloSimulator` and
  `run_monte_carlo` accept `periods_per_year` and forward it to the metrics
  computed for each resampled equity curve.
- `examples/cli.py`: new `--periods-per-year` flag and a
  `resolve_periods_per_year(interval, override)` helper that maps
  `1d -> 252`, `1wk -> 52`, `1mo -> 12` and intraday `Nm -> 252 * 390 / N`
  (390 = minutes in a 6.5h US equity session); unknown intervals fall back to
  252. The value is written to `config.backtest.periods_per_year` and passed
  to the backtest, the optimizers, the walk-forward optimizer and the Monte
  Carlo analysis. The synthetic provider always emits daily bars (its
  `fetch` documents the interval as ignored), so offline runs are pinned to
  252 unless `--periods-per-year` is given explicitly.
- `README.md`: new "Annualization Periods" section, the `periods_per_year`
  key in the example `config.yaml`, and a CLI usage example.
- Tests added (33 new): `tests/test_risk_metrics.py` (10),
  `tests/test_backtest_metrics.py` (4), `tests/test_cli.py` (13),
  `tests/test_config.py` (1), `tests/test_backtest_engine.py` (2),
  `tests/test_optimization.py` (1), `tests/test_monte_carlo.py` (2).
- Committed as `50c56e5` and pushed to `origin/main`. The commit was
  **rebased** on top of `dd99f1b` (a remote commit from another session that
  added `examples/run_momentum.py` and its README entry); the rebase was
  conflict-free and both sets of changes are present.

## What was actually verified (this session)

- `python -m pytest` → **1157 passed, 1 skipped** (baseline before this
  session: 1123 passed, 1 skipped; +33 new tests, +1 from the rebased
  remote commit's momentum example). Run took ~139 s.
- `python -m pytest --cov=quant_trading --cov-report=term-missing` → 100%
  line and branch coverage on **every module touched by this change**
  (`risk/metrics.py`, `backtest/metrics.py`, `backtest/engine.py`,
  `config/settings.py`, `risk/manager.py`, `optimization/*`,
  `monte_carlo/simulator.py`).
- `python -m ruff check .` → All checks passed.
- `python -m black --check .` → 79 files would be left unchanged.
- `python -m mypy quant_trading examples/cli.py` → Success: no issues found
  in 37 source files.
- Baseline confirmation for the pre-existing coverage gap: on the
  **unmodified** tree (`git stash`), the same run reported
  `quant_trading/strategies/examples.py 720 1 268 2 99% 2165->2124, 2401`
  and `TOTAL 99%` — i.e. that one uncovered line/branch pair is pre-existing
  and unrelated to this change.
- Manual CLI checks (offline, synthetic data):
  - `PYTHONPATH=. python examples/cli.py --offline --strategy ma --symbols AAPL --days 120`
    → Sharpe -129.79 (252-period annualization).
  - `... --periods-per-year 52` → Sharpe -288.65.
  - `... --interval 1wk` → Sharpe -288.65 (identical to the explicit
    `--periods-per-year 52` run, confirming the interval derivation).
- NaN regression confirmed fixed:
  `calculate_sharpe_ratio(pd.Series([0.01]))` returned `nan` before the
  change and returns `0.0` now; `calculate_backtest_metrics` on a two-point
  equity curve no longer puts `NaN` into `metrics.sharpe_ratio`.

## What remains unresolved

- **Pre-existing coverage gap (not from this session):**
  `quant_trading/strategies/examples.py` line 2401 and the `2165->2124`
  branch are uncovered. `2401` is inside `MomentumStrategy.generate_signals`
  (the `prev_price == 0` / NaN guard) and `2165->2124` is a
  long-to-short reversal branch in `ParabolicSARStrategy`. Reproduced on the
  unmodified tree, so it is not a regression. A bounded follow-up would be to
  add targeted tests for those two branches.
- **External CI workflow blocker (unchanged from prior handoffs):** the
  GitHub App token lacks the `workflows` permission, so workflow files
  cannot be pushed. `.github/workflows/` contains `kilo-workflow-audit.yml`
  and `main.yml` but no `ci.yml`. This requires maintainer action and cannot
  be fixed with a code change. Do not retry the identical workflow push.
- **README drift (not from this session):** the "Strategy Registry" section
  still documents only 4 of the 14 registered strategies (`ma`, `rsi`, `bb`,
  `macd`). The registry in `quant_trading/strategies/__init__.py` registers
  `ema`, `supertrend`, `donchian`, `aroon`, `keltner`, `stoch`, `ichimoku`,
  `sar`, `vwap` and `momentum` as well. The "Built-in Strategies" bullet in
  the Features list is stale for the same reason.

## Approaches already failed

- **Pushing `ci.yml` / retrying the identical CI push** → blocked by the
  missing `workflows` permission on the GitHub App token. Do not repeat.
- **A first attempt at the `run_backtest` docstring/signature edit in
  `quant_trading/backtest/engine.py` duplicated the function body** (the
  edit's `newString` re-emitted the docstring and the `BacktestConfig(...)`
  block while the original text remained). Detected immediately by
  `python -m ruff check` reporting `invalid-syntax` at `engine.py:609`; fixed
  by removing the duplicated block. Lesson: when replacing a whole function
  in this repo, make the `oldString` cover the *entire* function through its
  final line, or verify with `ruff` immediately.
- **First draft of the optimizer annualization test used MA
  `(fast=5, slow=20)`** on the mock data and asserted the two annualization
  periods produced different scores. The score was `0.0` for both because
  the mock data's MA crossover fires on the *last* bar of the window, so the
  equity curve is flat (`std == 0`) and the Sharpe is `0.0` regardless of
  the annualization period. Fixed by switching to `(fast=2, slow=3)`, which
  produces 10 trades inside the window and a non-zero Sharpe. The same data
  artifact is why `tests/test_optimization.py` scores are frequently `0.0`.

## One precise next task

**Close the pre-existing coverage gap in `quant_trading/strategies/examples.py`
(line 2401 and the `2165->2124` branch) with targeted unit tests.**

- `2401` is in `MomentumStrategy.generate_signals`: the
  `if pd.isna(current_price) or pd.isna(prev_price) or prev_price == 0:
  continue` guard. A test needs a price frame whose last two closes contain
  a NaN or a zero.
- `2165->2124` is the long-to-short reversal branch of
  `ParabolicSARStrategy.generate_signals` (the `current_trend == -1 and
  prev_trend == 1` path), which needs a hand-built SAR state sequence that
  flips from long to short.

Constraints and evidence:
- Do **not** change `quant_trading/strategies/examples.py` itself — the
  goal is to cover the existing branches, not to alter strategy logic.
- The target is `python -m pytest --cov=quant_trading --cov-report=term-missing`
  reporting `quant_trading/strategies/examples.py 720 0 268 0 100%` and
  `TOTAL 100%`. That same command on the unmodified tree reports
  `2165->2124, 2401` and `TOTAL 99%`, so these two spots are the only
  remaining gaps in the whole package.
- Keep the existing suite green: `1157 passed, 1 skipped`, plus
  `ruff check .`, `black --check .` and `mypy quant_trading` all clean.
- Add the new tests to `tests/test_strategies_examples.py`, which already
  contains `TestParabolicSARStrategy` and `TestMomentumStrategy` classes
  for exactly these two strategies.
