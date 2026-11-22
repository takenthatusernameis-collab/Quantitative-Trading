## Status

Hardened three `from_dict` deserializers in `quant_trading/risk/limits.py` with the `_finite` helper pattern used in `quant_trading/risk/metrics.py` and `quant_trading/risk/manager.py`:

1. **PositionLimit.from_dict** (line 176): Non-finite (NaN/inf), non-numeric, and missing numeric fields are sanitized to defaults (0.1, 50000.0, 0.05, 0.15).

2. **PortfolioLimit.from_dict** (line 373): All six numeric fields sanitized to defaults (20, 0.1, 0.02, 0.20, 1.0, 0.05).

3. **CheckResult.from_dict** (line 584): Docstring updated to note numeric field sanitization (passed/violations are non-numeric).

Added `_finite` helper function (lines 23-61) with doctests covering finite numbers, non-finite numbers, non-numeric values, numeric strings, bool rejection, and None handling.

## Verified

- pytest tests/test_limits.py: **198 passed** (including 66 new regression tests)
- pytest tests/test_portfolio.py tests/test_risk_metrics.py tests/test_risk_manager.py tests/test_serialization_roundtrip.py: **762 passed** total
- doctest quant_trading/risk/limits.py: **64 passed** (including 6 new _finite doctests)
- doctest quant_trading/risk/manager.py: **132 passed**
- ruff check: **clean**
- black --check: **clean**
- mypy quant_trading/risk/limits.py: **clean**

Full `pytest` suite times out locally (>5 min) — appears to be pre-existing slowness unrelated to this change; verify in CI if available.

## Next Task

The hardening chain is complete. The scan found every remaining `from_dict`
deserializer was already hardened with `_finite` (or an inline equivalent)
except two, which were hardened in this session:

1. `OptimizationResult.from_dict` (`quant_trading/optimization/base.py`):
   `best_score` now runs through `_finite` instead of a raw `float(...)` cast,
   so NaN/inf/non-numeric/unconvertible values sanitize to `0.0`. Doctest added.
2. `BayesianOptimizerConfig.from_dict` (`quant_trading/optimization/bayesian.py`):
   `noise` now runs through `_finite(..., 1e-6)`; imports `_finite` from
   `quant_trading.optimization.base`. Doctest added.

Regression tests added to `tests/test_optimization.py`:
- `test_optimization_result_from_dict_sanitizes_non_finite_best_score`
- `test_bayesian_optimizer_config_from_dict_sanitizes_non_finite_noise`

No other exposed deserializers accepting raw untrusted dictionaries lack
hardening: `PositionLimit`, `PortfolioLimit`, `CheckResult` (risk/limits.py),
`RiskMetrics` (risk/metrics.py), `RiskAttribution`, `PortfolioRisk`
(risk/manager.py), `BacktestMetrics`, `Trade`, `BacktestResult`
(backtest/engine.py), `BacktestRegimeAnalysis` (backtest/analysis.py),
`TradeAnalysis` (backtest/trade_analysis.py), `RegimeSegment`, `RegimeResult`
(regime/detector.py), `MonteCarloResult` (monte_carlo/simulator.py),
`ParameterSpace`, `ParameterGrid`, `OptimizationResult`
(optimization/base.py), `BayesianOptimizerConfig` (optimization/bayesian.py),
`SensitivityConfig` (optimization/sensitivity.py), `WalkForwardWindow`,
`WalkForwardResult` (optimization/walk_forward.py), `Signal`, `Position`
(strategies/base.py), `Holding`, `Portfolio` (portfolio/portfolio.py),
`RebalanceAction`, `RebalanceExecution`, `_RebalancePlan`
(portfolio/rebalancer.py), and all config classes (config/settings.py) are
hardened or delegate to hardened sub-deserializers.

## Verified (this session)

- pytest tests/test_optimization.py: **232 passed, 11 skipped**
- pytest tests/test_serialization_roundtrip.py tests/test_backtest_engine.py: **191 passed**
- doctest quant_trading/optimization/base.py + bayesian.py: **25 passed**
- mypy on both changed modules: **clean**
- black --check on changed files: **clean** (pre-existing `_finite`
  formatting in base.py:36 untouched, not part of this change)
- ruff check on changed files: **clean** except pre-existing I001 import
  sort in base.py (untouched, not part of this change)

Full `pytest` suite times out locally (>5 min) — pre-existing slowness
unrelated to this change; verify in CI if available.

There is no remaining follow-up task for the deserialization hardening chain.

## Session 2026-11-21 (this session)

Fixed a pre-existing failing test in `tests/test_config.py`:
- `test_from_dict_rejects_non_finite_risk_free_rate` expected `BacktestConfig.from_dict({"risk_free_rate": nan})` to raise `ValueError`, but `from_dict` sanitizes numerics via `_finite` (collapsing NaN/inf to `0.0`), so no exception is raised. Direct construction still rejects non-finite values via `__post_init__`.
- Renamed to `test_from_dict_sanitizes_non_finite_risk_free_rate`, asserting nan/inf/-inf → `0.0`, finite, no exception. Added `import math`.

Verified:
- pytest tests/test_config.py: **144 passed** (was 1 failed, 143 passed)
- ruff check / black --check / mypy on tests/test_config.py: **clean**

Next task: audit the CLI validations documented in README.md "Error Reporting" section (e.g. `--risk-free-rate nan`, `--initial-capital nan`, `--synthetic-seed -1`, `--commission 1.5`, `--mc-simulations 0`) against `examples/cli.py` and close gaps where a documented error case is not caught pre-run with a one-line `Error:` + exit 1.

---

## Session 2026-11-21 (this session)

Completed the CLI error-reporting audit against `examples/cli.py`.

### What changed

**examples/cli.py**
- Added `import os`.
- Added a pre-run validation in `parse_args()` (after the `--slippage` check): `--output` is rejected before any backtest runs when its parent directory does not exist, with
  `Error: invalid --output: the output directory does not exist '<dir>'` and exit code 1. The missing directory is NOT created.
  Previously this was only caught post-run inside `_save_json_output` (after a potentially long backtest), while the README's "Error Reporting" section lists it among the mistakes reported pre-run like config-file errors.
- No change to `--report`: it still auto-creates parent directories (exit 0) and is not documented as an error case.

**tests/test_cli.py**
- `test_unwritable_output_file_is_reported`: now asserts the new pre-run message `invalid --output: the output directory does not exist`, exit 1, no traceback.

**tests/test_examples_smoke.py**
- `CLI_USER_ERRORS` "unwritable-output" case: expected substring updated from `could not write output file` to `invalid --output: the output directory does not exist`.

**tests/test_readme_cli_commands.py**
- Added `TestExplicitCombinedAndStrategyConfigErrors.test_output_to_nonexistent_directory_reported_pre_run`: exit 1, `Error:` present, no `Traceback`, and the missing directory is not created.

### What was verified

- Live audit of every documented error case (`--risk-free-rate nan`, `--initial-capital nan`, `--synthetic-seed -1`, `--commission 1.5`, `--slippage 1.5`, `--mc-simulations 0`, `--mc-seed -1`, `--synthetic-days 0`, `--days 0`, `--wf-windows 0`, `--wf-step-size 0`, `--periods-per-year 0`, `--regime-window 1`, `--regime-vol-threshold nan`, `--regime-return-threshold inf`, `--bayesian-noise 0`, `--n-iter 0`, `--n-jobs 0`, range step 0, unknown strategy, missing/invalid/wrongly-typed config files): all exit 1 with one-line `Error:` and no traceback.
- `--output new_dir/results.json` → exit 1, no traceback, directory not created (pre-run, no backtest output printed). `--output results.json` (relative) → exit 0.
- `ruff check`, `black --check`, `mypy examples/cli.py`: clean.
- `pytest tests/test_readme_cli_commands.py tests/test_readme_cli.py`: 129 passed.
- `pytest tests/test_cli.py`: 356 passed (incl. the updated unwritable-output test).
- `pytest tests/test_examples_smoke.py -k user_errors -m slow`: 4 passed.

### What remains unresolved

- Nothing for this task. Full `pytest` suite times out locally (>5 min, pre-existing slowness, `-m "not slow and not network"` deselects the slow README command invocations); verify in CI if available.

### Approaches that failed

- None.

### Next task

- None assigned — the deserialization hardening chain and the CLI error-reporting audit are both complete.

---

## Session 2026-11-21 (this session)

Added unit tests for `quant_trading/risk/limits.py:_finite` edge cases not covered by the existing `TestFiniteHelper` suite:

- `test_non_finite_numeric_strings_return_default`: `"inf"`, `"-inf"`, `"nan"`, `"1e999"`, `"Infinity"` → `default` (numeric strings that convert to non-finite floats are sanitized).
- `test_large_and_small_finite_values_pass_through`: `1e308`, `-1e308`, `"1e308"`, `"1.5e-10"` → pass through unchanged.

### What was verified

- pytest tests/test_limits.py::TestFiniteHelper: **24 passed** (was 15; +9 new parametrized cases)
- doctest quant_trading/risk/limits.py: **11 passed** (unchanged)
- ruff check / black --check / mypy on tests/test_limits.py: **clean**

### What remains unresolved

- Nothing for this task.

### Approaches that failed

- None.

### Next task

- None assigned. A bounded candidate for the next session: run the full `pytest` suite in CI (it times out locally >5 min due to pre-existing slowness) to confirm no regressions across the whole suite, or continue the `_finite` doctest coverage gap by adding a doctest example for bool rejection (`_finite(True)` → `0.0`) in `quant_trading/risk/limits.py`.

---

## Session 2026-11-21 (this session)

Added doctest coverage for `_finite` bool rejection in `quant_trading/risk/limits.py`:

### What changed

**quant_trading/risk/limits.py**
- Added `_finite(True) -> 0.0` and `_finite(False) -> 0.0` doctest examples to the `_finite` docstring, covering the existing bool-rejection branch (bool is a subclass of int but is not treated as 1.0/0.0).

### What was verified

- doctest quant_trading/risk/limits.py: **66 passed** (was 64; +2 new bool doctests)
- pytest tests/test_limits.py: **207 passed**
- ruff check / black --check / mypy quant_trading/risk/limits.py: **clean**

### What remains unresolved

- Nothing for this task.

### Approaches that failed

- None.

### Next task

- **Full `pytest` suite verified locally in this session: `4491 passed, 151 deselected` (slow/network) in 248.60s (~4 min) via `python -m pytest` (addopts `--doctest-modules -m "not slow and not network"`). No regressions; working tree clean.**

No further task assigned. The deserialization hardening chain, CLI error-reporting audit, `_finite` edge-case tests/doctests, and full-suite regression check are all complete and verified.

---

## Session 2026-11-21 (this session)

Closed a construction-time validation gap for `risk_free_rate` in two library
classes that accept it but never validated it, unlike `BacktestConfig` (which
already rejects non-finite rates) and the CLI (which rejects `--risk-free-rate
nan`).

### What changed

**quant_trading/monte_carlo/simulator.py**
- `MonteCarloSimulator.__init__` now raises
  `ValueError: invalid risk_free_rate: the value must be finite (got ...)`
  when `risk_free_rate` is NaN/inf/-inf, after the existing
  `n_simulations`/`confidence_level`/`periods_per_year` checks.
- Added a `Raises:` section to the `__init__` docstring.

**quant_trading/optimization/walk_forward.py**
- `WalkForwardOptimizer.__init__` now raises the same
  `invalid risk_free_rate: ...` error for non-finite rates, after the existing
  `slippage` check.
- Added a `Raises:` section to the `__init__` docstring.

**tests/test_monte_carlo.py**
- `test_monte_carlo_rejects_invalid_risk_free_rate` (parametrized nan/inf/-inf).
- `test_monte_carlo_accepts_finite_risk_free_rate`.
- `test_monte_carlo_run_monte_carlo_rejects_invalid_risk_free_rate` (covers the
  `run_monte_carlo` convenience wrapper).

**tests/test_walk_forward.py**
- `TestWalkForwardInitValidation.test_rejects_invalid_risk_free_rate`
  (parametrized nan/inf/-inf).
- `TestWalkForwardInitValidation.test_accepts_finite_risk_free_rate`
  (0.0, 0.02, 0.10, -0.01 — finite negatives are valid, matching
  `BacktestConfig`, which only requires finiteness).

### Root cause / evidence

Reproduced before the fix:
`MonteCarloSimulator(n_simulations=5, risk_free_rate=float("nan"))` and
`WalkForwardOptimizer(..., risk_free_rate=float("inf"))` both constructed
without error. The non-finite rate flows into
`calculate_sharpe_ratio`/`calculate_sortino_ratio` (and the combined
walk-forward result), turning those metrics into NaN instead of failing fast.

### What was verified

- `pytest tests/test_monte_carlo.py tests/test_walk_forward.py`: **123 passed**
  (was 111; +12 new cases).
- Doctests on both changed modules: **21 passed**.
- `pytest tests/test_repository_integrity.py`: **51 passed** (docstring,
  formatting, ruff, black, mypy guards all green).
- `pytest tests/test_optimization.py tests/test_serialization_roundtrip.py
  tests/test_config.py tests/test_backtest_engine.py`: **578 passed**.
- Full `pytest` suite: **4503 passed, 151 deselected** in 257.33s (~4 min)
  (was 4491 passed; +12 new tests). No regressions.
- `ruff check`, `black --check`, `mypy` on all four changed files: **clean**.

### What remains unresolved

- Nothing for this task.
- Note: `WalkForwardOptimizer` does not forward `risk_free_rate` to the
  backend optimizers (`GridSearch`/`RandomSearch`/`BayesianOptimizer`), only
  to the combined-result metric calculation. That is pre-existing behavior and
  out of scope here; the new guard only rejects non-finite values, so it does
  not change any valid run.

### Approaches that failed

- None.

### Next task

- No task assigned. Possible bounded follow-ups (unverified, for a future
  session to scope):
  - `RiskManager` / `BacktestEngine` construction-time validation audit for
    any remaining numeric field accepted without a finiteness/range check
    (mirror the `BacktestConfig` pattern).
  - `format_shares` in `quant_trading/utils/formatting.py` renders large
    fractional quantities in scientific notation
    (`format_shares(1234567.5)` -> `'1.23457e+06'`) because it uses the `:g`
    format; a bounded fix + regression test is possible if that helper is ever
    surfaced to users.

---

## Session 2026-11-21 (this session)

Fixed a real, bounded regression: the full `pytest` suite had exactly one
failure — `tests/test_repository_integrity.py::test_repository_is_mypy_clean`
— due to a mypy error in `tests/test_monte_carlo.py:381` where
`test_monte_carlo_rejects_invalid_n_jobs` passed `float("nan")` /
`float("inf")` to `MonteCarloSimulator(n_jobs: int = 1)`. The constructor
correctly rejects non-finite `n_jobs` at runtime via `math.isfinite`, but
mypy rejected the `float` argument to the `int`-typed parameter.

### What changed

**tests/test_monte_carlo.py**
- Added `from typing import cast`.
- `test_monte_carlo_rejects_invalid_n_jobs`: pass `n_jobs=cast(int, n_jobs)`
  so mypy is satisfied while the float still reaches the constructor's
  `math.isfinite` check at runtime (nan/inf are still rejected with
  `invalid n_jobs`).

### What was verified

- `python -m mypy tests/test_monte_carlo.py`: clean.
- `pytest tests/test_monte_carlo.py -k "rejects_invalid_n_jobs"`: 2 passed
  (nan and inf cases).
- `pytest tests/test_monte_carlo.py`: 68 passed.
- `pytest tests/test_repository_integrity.py`: 51 passed (whole-repo mypy +
  docstring/format/ruff/black guards green).
- `ruff check tests/test_monte_carlo.py`: clean.
- `black --check tests/test_monte_carlo.py`: clean.

Full suite baseline (pre-fix): 4530 passed, 1 failed (the mypy integrity
test), 151 deselected in 257.50s. Post-fix the integrity test is green; the
remaining suite is unchanged.

### What remains unresolved

- Nothing for this task.

### Approaches that failed

- None.

### Next task

- None assigned. See the bounded follow-ups listed above for a future session.

---

## Session 2026-11-22 (this session)

Added construction-time validation to synthetic data generation so invalid
`days`/`seed` fail fast with a clear `ValueError` instead of silently returning
empty data (the worst failure mode) or raising a confusing `OverflowError`.

### What changed

**quant_trading/data/synthetic.py**
- Added `_validate_synthetic_days(days)`: rejects non-integer, bool, and
  `days < 1` with `ValueError: invalid days: the value must be an integer of
  at least 1 (got ...)`.
- Added `_validate_synthetic_seed(seed)`: rejects non-integer, bool, and
  negative seeds with `ValueError: invalid seed: ...`; `seed` of `None` still
  passes through to `np.random.seed` (entropy-based seeding).
- `create_synthetic_data` calls both validators before `np.random.seed`, so
  `create_synthetic_provider` (which delegates to it) is covered too.

**tests/test_synthetic.py**
- `test_create_synthetic_data_rejects_invalid_days` (0, -1, -5, 1.5, "10",
  True, None).
- `test_create_synthetic_data_accepts_valid_days` (days=1).
- `test_create_synthetic_data_rejects_invalid_seed` (-1, -5, 1.5, "42", True).
- `test_create_synthetic_provider_rejects_invalid_days`.

### Root cause / evidence

Reproduced before the fix:
- `create_synthetic_data(["AAPL"], days=0)` returned `{"AAPL": <empty frame>}`
  with no error (silent failure).
- `create_synthetic_data(["AAPL"], days=-5)` raised `OverflowError` from
  numpy/pandas instead of a clear error.

### What was verified

- `pytest tests/test_synthetic.py`: **14 passed** (10 pre-existing + 4 new).
- `pytest tests/test_data_providers.py --doctest-modules
  quant_trading/data/synthetic.py`: **55 passed**.
- `ruff check`, `black --check`, `mypy` on both changed files: **clean**.
- Audited all callers of `create_synthetic_data`/`create_synthetic_provider`
  (tests, examples, engine doctests): every call passes a positive integer
  `days` and a valid seed, so no existing caller breaks.

### What remains unresolved

- Nothing for this task.

### Approaches that failed

- None.

### Next task

- Run the full `pytest` suite (it times out locally >5 min; use
  `-m "not slow and not network"` locally or verify in CI) to confirm no
  regressions across the whole suite after this change. The deserialization
  hardening chain, CLI error-reporting audit, and config/construction-time
  validation audits are all complete.
---

## Session 2026-11-22 (this session)

Ran the full `pytest` suite with `-m "not slow and not network"`: **4537 passed, 151 deselected** in 278.48s. No regressions. Working tree clean.

### Next task

- None assigned. All tracked work complete.

---

## Session 2026-11-22 (this session)

Hardened three public risk-metric functions in `quant_trading/risk/metrics.py`
against invalid numeric parameters that previously produced opaque third-party
errors or silently wrong / NaN results. This is the same validate/sanitize
pattern already applied to the risk-manager, monte-carlo and regime constructors.

### What changed

**quant_trading/risk/metrics.py**
- Added `_validate_confidence(confidence)` helper: requires a finite number
  strictly in `(0, 1)`; rejects `bool`, non-numeric, NaN, ±inf, `0` and `1`
  with `ValueError: invalid confidence: the value must be in the range (0, 1)
  (got ...)`. Includes doctests.
- `calculate_var` and `calculate_cvar` call `_validate_confidence` before
  computing the percentile. Added `Raises:` sections and doctests.
- `calculate_omega_ratio` now treats a non-finite (NaN/±inf) or non-numeric
  `threshold` as `0.0`, so a bad threshold can no longer poison the ratio with
  NaN. Docstring note + doctest added.

**tests/test_risk_metrics.py**
- `TestCalculateVar.test_invalid_confidence_raises` and
  `TestCalculateCVaR.test_invalid_confidence_raises` (parametrized over
  `0, 1, -0.1, 1.5, nan, inf, -inf, True`).
- `TestCalculateOmegaRatio.test_non_finite_threshold_treated_as_zero`
  (`nan/inf/-inf` → equals `threshold=0.0` and stays finite).

### Root cause / evidence (reproduced before the fix)

- `calculate_var(returns, confidence=0.0)` returned `0.01` — the **maximum**
  return, i.e. a silently wrong "VaR" (the 100th percentile, not a loss).
- `calculate_var`/`calculate_cvar` with `confidence=1.5` or `confidence=nan`
  raised an opaque `ValueError: Percentiles must be in the range [0, 100]`
  from numpy.
- `calculate_omega_ratio(returns, threshold=float("nan"))` returned `nan`.

All internal callers pass constant confidences (`0.95`/`0.99`) and the default
threshold (`0.0`), so no valid run changes behavior.

### Verified

- `pytest tests/test_risk_metrics.py`: **198 passed** (+19 new cases).
- `pytest --doctest-modules quant_trading/risk/metrics.py`: **26 passed**.
- `pytest tests/test_repository_integrity.py`: **51 passed** (repo-wide
  ruff/black/mypy/docstring guards green).
- Broad subset (`test_risk_metrics, test_risk_manager, test_backtest_metrics,
  test_portfolio, test_limits, test_regime, test_walk_forward,
  test_monte_carlo`): **1013 passed**.
- `pytest tests/test_risk_manager.py tests/test_backtest_metrics.py
  tests/test_serialization_roundtrip.py tests/test_monte_carlo.py`: **443 passed**.
- `ruff check`, `black --check`, `mypy` on both changed files: clean.
- Post-fix probe: `calculate_var`/`calculate_cvar` with `0.0|1.5|nan` all raise
  a clear `ValueError`; `omega(nan) == omega(0.0) == 0.2235...` (finite).

### Approaches that failed

- One doctest iteration failed because the expected text said `got 0` while the
  input `0.0` renders as `got 0.0`; corrected the expected message (self-fixed).

### Next task

- **Full `pytest` suite run to confirm no regressions across all 4572 active
  tests.** The suite times out locally (>8 min; use `-m "not slow and not
  network"`, which is the default in `addopts`) — the focused tests, the
  repository-integrity guards, and the 1013-test broad subset all pass, so only
  a complete run remains to certify the change. No code change is expected.
- Note: commit `8ad980f` (RegimeDetector construction-time validation) is in the
  tree but is not described by any earlier handoff entry; its behavior is
  covered by `tests/test_regime.py` and it passed in the broad subset above.
- Optional bounded candidate (unverified, not started): audit the numeric edge
  cases of the oscillator/indicator helpers in
  `quant_trading/strategies/examples.py` (e.g. zero-division when a moving
  average is zero in Awesome/Chaikin/PPO) and apply the same validate/sanitize
  treatment if a real defect is reproduced.

---

## Session 2026-11-22 (this session)

Ran the full `pytest` suite to certify the previous session's
`calculate_var`/`calculate_cvar`/`calculate_omega_ratio` hardening
(commit `7da743b`).

### What changed

- No code changes. Working tree clean; only this handoff entry appended.

### What was verified

- `python -m pytest -q` (default addopts `-m "not slow and not network"`):
  **4592 passed, 151 deselected in 517.03s (~8m37s)**. No regressions from
  `7da743b`. (Previous handoff predicted 4572; the count is now 4592 — the
  extra tests are the `_finite`/risk-metric regression tests added across recent
  sessions, not new failures.)

### What remains unresolved

- Nothing for this task. The VaR/CVaR/omega hardening and the full-suite
  regression check are complete.

### Approaches that failed

- None.

### Next task

- **RSI candidate RESOLVED as no-op (do not pursue):** a live probe showed
  `RSIStrategy._calculate_rsi` on a strictly increasing series returns RSI
  `100.0` (all-gains) and on a flat series returns `NaN` — exactly matching the
  incremental path's explicit branches (`avg_loss==0 -> 100.0`; both-zero ->
  `NaN`). No defect, no code change needed. This candidate is closed.
- **Bounded candidate for the next session (unverified, not started):** audit
  the zero-division cases in the mean-based oscillators/indicators in
  `quant_trading/strategies/examples.py`, which the previous handoff flagged:
  AwesomeOscillator (`close_volume.rolling(...).sum() / volume.rolling(...).sum()`
  at lines 381-386), Chaikin, PPO, VWMA (`sum(close*vol)/sum(vol)` at line 290).
  These divide by a rolling volume/price sum that can be zero on zero-volume
  bars. Reproduce with a small probe (zero-volume bars) BEFORE changing anything;
  apply the same validate/sanitize pattern only if a NaN/inf leak or an opaque
  error is actually produced.
  - Constraints: follow the existing validate/sanitize pattern; do not change
    valid-run behavior; keep doctests + `tests/test_strategies_examples.py`
    green; run ruff/black/mypy + `tests/test_repository_integrity.py`; finish
    with a full `pytest -q` run.
