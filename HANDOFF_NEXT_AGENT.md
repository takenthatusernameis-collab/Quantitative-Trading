## What changed (this session)

- Rejected non-finite `initial_capital` and `periods_per_year` at every
  validation surface that already range-checked them. Root cause: the existing
  guards used `<= 0` / `< 1`, and `nan <= 0`, `inf <= 0`, `nan < 1` are all
  `False`, so non-finite values slipped through and silently produced all-`nan`
  metrics with exit code 0.
  - `quant_trading/config/settings.py` — `BacktestConfig.__post_init__`:
    `if not math.isfinite(self.initial_capital) or self.initial_capital <= 0`
    and the same for `periods_per_year` (`< 1`).
  - `quant_trading/optimization/base.py` — `BaseOptimizer.__init__` (added
    `import math`), same finite guards for `initial_capital` /
    `periods_per_year`.
  - `quant_trading/optimization/walk_forward.py` — `WalkForwardOptimizer`
    (added `import math`), same finite guards.
  - `examples/cli.py` — `parse_args` now rejects non-finite `--initial-capital`
    (`nan`/`inf`/`-inf`), message
    `invalid --initial-capital: the value must be greater than 0 and finite`.
  - Error message wording for the two fields changed to "positive and finite" /
    "at least 1 and finite"; existing tests match the `invalid <field>` prefix,
    so they still pass.
- Tests:
  - `tests/test_config.py`: extended the `initial_capital` /
    `periods_per_year` reject parametrizations with `nan`, `inf`, `-inf`.
  - `tests/test_optimization.py` and `tests/test_walk_forward.py`: same
    extension for the two optimizer constructors.
  - `tests/test_cli.py`: new `test_initial_capital_non_finite_is_rejected`
    (uses `--flag=value` form because a bare `-inf` token is parsed as an
    option).
- `README.md`: documented the finite `--initial-capital` check and that the
  library config/optimizers enforce it too.
- **Files changed:** `quant_trading/config/settings.py`,
  `quant_trading/optimization/base.py`,
  `quant_trading/optimization/walk_forward.py`, `examples/cli.py`,
  `tests/test_config.py`, `tests/test_optimization.py`,
  `tests/test_walk_forward.py`, `tests/test_cli.py`, `README.md`.
- Changes are **not committed**; the working tree holds them (the previous
  session's commits used empty messages).

## Why this task (evidence)

- The previous handoff's "next task" (strategy float `std_dev`/`multiplier`
  finite guards) was **already implemented** in the code before this session.
  Verified by probe: `BollingerBandsStrategy(std_dev=nan)`,
  `AverageTrueRangeStrategy(atr_multiplier=nan|inf)` and
  `SuperTrendStrategy(multiplier=nan)` are all rejected. Do not redo it.
- The remaining hole of the same class was the backtest/optimizer capital and
  annualization fields. Reproduced before the fix:
  - `BacktestConfig(initial_capital=nan)` / `(initial_capital=inf)` /
    `(periods_per_year=nan)` → constructed OK.
  - `GridSearch(..., initial_capital=nan|inf)` and
    `WalkForwardOptimizer(..., initial_capital=nan)` → constructed OK.
  - `python examples/cli.py --offline --initial-capital nan --symbols AAPL
    --days 30` → printed `Initial Capital: $nan`, all metrics `nan`/`0`, exit 0.

## What was actually verified (evidence)

- Library probes after the fix: all of `nan`/`inf`/`-inf` for `initial_capital`
  and `periods_per_year` are now rejected by `BacktestConfig`, `GridSearch`
  (via `BaseOptimizer`) and `WalkForwardOptimizer`; finite positive values
  still construct.
- CLI probes after the fix:
  - `--initial-capital nan|inf` and `--initial-capital=-inf` → `Error: invalid
    --initial-capital: the value must be greater than 0 and finite (...)`, exit 1.
  - `--initial-capital 50000 --offline ...` → normal run, exit 0.
- `python -m pytest -q -p no:cacheprovider tests/test_config.py
  tests/test_walk_forward.py tests/test_optimization.py` → **356 passed, 37
  skipped**.
- `python -m pytest -q -p no:cacheprovider tests/test_cli.py::TestParseArgs`
  → **81 passed**.
- `python -m pytest -q -p no:cacheprovider tests/test_repository_integrity.py
  tests/test_readme.py tests/test_config.py tests/test_backtest_engine.py
  tests/test_risk_manager.py tests/test_monte_carlo.py` → **498 passed**.
- `python -m py_compile` on all changed files → OK.
- Full suite: **3465 passed, 17 failed, 131 skipped, 136 deselected**. All 17
  failures are pre-existing environmental ones: `TestHtmlReportFlag` +
  `test_backtest_report.py` require `matplotlib` (not installed), and the
  bayesian README-command tests require `scikit-optimize` (not installed;
  confirmed `ModuleNotFoundError`). None touch the changed code.

### Environment caveat (unchanged)

Minimal env (Python 3.14.4, pandas 3.1.1, numpy 2.5.4, pytest 9.2.0).
`ruff`, `mypy`, `matplotlib`, `scikit-optimize` are **NOT** installed, so
lint/type checks cannot run and the 17 tests above fail for environmental
reasons only.

## Unresolved / not completed

- None for this task. Change is minimal, isolated, verified.
- Lint/type checks not run (no ruff/mypy).
- Not committed (no explicit request).

## Failed approaches (do not repeat unchanged)

- Passing `-inf` as a separate argv token in tests/CLI: argparse consumes a
  bare `-inf` as an option. Use the `--flag=value` form for values starting
  with `-`.
- Re-attempting the previous handoff's strategy `std_dev`/`multiplier` finite
  guards: already implemented and verified; skip.

## Git state

- Branch `main`. Changes from this session are in the working tree, uncommitted.
- The repo's prior commits have empty messages; prefer a descriptive message
  when this work is committed.

## One precise next task

- **Risk/portfolio limit constructors still use `<= 0` and accept `nan`/`inf`.**
  Same class of silent-corruption bug, in a different module:
  - Evidence to gather first (not yet confirmed): `quant_trading/risk/manager.py`
    guards `initial_capital <= 0` (line ~227), `limit <= 0` (~476),
    `trailing_stop_pct <= 0` (~867); `quant_trading/risk/limits.py` guards
    `basis <= 0`, `portfolio_value <= 0`; `quant_trading/risk/metrics.py` may
    consume these. `nan`/`inf` slip past each `<= 0`.
  - Concrete step: add `not math.isfinite(x) or x <= 0` guards at the
    risk-manager / risk-limit constructor boundaries that already validate a
    numeric limit, mirroring this session's change. Verify with library probes
    (`RiskManager(initial_capital=nan)`, etc.) and add parametrized tests in
    `tests/test_risk_manager.py` / a risk-limits test file.
  - Constraints: minimal, localized; do not reject negative values beyond the
    existing rule; keep the `invalid <field>` message prefix so existing tests
    pass. Run `tests/test_risk_manager.py` plus the config/integrity suites.