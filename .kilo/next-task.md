# Next Task

## Repository state

Checks: `python -m ruff check .` → clean. `python -m black --check quant_trading tests examples` → clean. `python -m mypy quant_trading` → clean, 0 errors across 37 source files. `python -m pytest -q` → 2416 passed, 148 skipped, 124 deselected; only failure is a pre-existing doctest in `quant_trading/optimization/bayesian.py` (`ImportError: BayesianOptimizer requires scikit-optimize`) — unrelated to recent work.

## What changed (this session)

Fixed two failing CLI tests that required the unavailable `yfinance` dependency:
- `tests/test_cli.py::TestSaveStrategyConfig::test_optimize_saves_best_params_config` and `...::test_walk_forward_saves_last_window_params_config` previously used the default `Config()` (provider=yfinance, online) and failed with `ImportError: yfinance is not installed`.
- Both tests now configure an offline/synthetic data provider before calling `run_optimization` / `run_walk_forward`:
  - `config.data.provider = "synthetic"`
  - `config.data.offline = True`
  - `config.data.synthetic_days = 120`
  - `config.data.synthetic_seed = 42`
- No library code changed; only the two tests were modified.

## What was actually verified

- `python -m pytest tests/test_cli.py::TestSaveStrategyConfig -q`: 3 passed.
- `python -m pytest tests/test_cli.py -q`: 170 passed (no regressions).
- `python -m pytest -q`: 2416 passed, 148 skipped, 124 deselected. Confirmed via `git stash` that the bayesian doctest failure predates this change.
- `python -m ruff check tests/test_cli.py`: All checks passed.
- `python -m black --check tests/test_cli.py`: 1 file unchanged.
- `python -m mypy tests/test_cli.py`: Success (no issues).
- Verified offline execution works: both `run_optimization` and `run_walk_forward` complete with `result == 0` and write the expected `--output-strategy-config` YAML (`type == "ma"`, `fast_period`/`slow_period` present).

## What remains unresolved

- `quant_trading/optimization/bayesian.py` doctest fails because `scikit-optimize` is not installed (`quant-trading[bayesian]` extra). Pre-existing; not caused by this session.
- `quant_trading/strategies/examples.py` still has ~108 uncovered statements (mostly low-value defensive branches).
- 5 third-party `Pandas4Warning` warnings from yfinance/pandas remain; cosmetic only.
- Network-gated README CLI command tests remain skipped in offline CI (148 skips).

## Approaches that failed and why

- Installing `yfinance` was rejected: unavailable in this environment, and the tests should not depend on live network/data availability.
- Marking the tests `@pytest.mark.skipif` was rejected in favor of making them self-contained offline, since the `--output-strategy-config` behavior is exactly what should be locked by a deterministic test.

## One precise next task

- The full suite is now green except the pre-existing scikit-optimize doctest. Recommended: either install/mock `scikit-optimize` so the `BayesianOptimizer` doctest passes, or add a `pytest.importorskip("skopt")` guard to the doctest module so the suite is fully green offline.
- Verification: `python -m pytest -q`; `python -m ruff check .`; `python -m black --check quant_trading tests examples`; `python -m mypy quant_trading`.
- Constraints: do NOT commit unless explicitly asked; preserve working baseline; do NOT change library code unless the task explicitly requires it; exclude secrets/env/cache artifacts.

(End of file - total 47 lines)