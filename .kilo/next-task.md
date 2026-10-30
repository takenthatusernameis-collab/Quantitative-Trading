# Next Task

## Repository state

Checks: `python -m ruff check .` → clean. `python -m black --check quant_trading tests examples` → clean. `python -m mypy quant_trading` → clean, 0 errors across 37 source files. `python -m pytest --doctest-modules quant_trading` → 188 passed.

## What changed (this session)

Added 1 test (`test_prices_all_nan_after_first_bar_returns_empty_result`) to `tests/test_regime.py`, covering the `if len(returns) < 1: return RegimeResult()` guard at `quant_trading/regime/detector.py:364`. A two-bar series whose second bar is `NaN` has `len(prices) >= 2` (so the earlier guard at line 359 does not fire) but `pct_change().dropna()` yields zero returns, exercising the line 364 branch.

## What was actually verified

- `python -m ruff check .`: clean.
- `python -m black --check quant_trading tests examples`: 131 files clean.
- `python -m mypy quant_trading`: clean.
- `python -m pytest tests/test_regime.py -q`: 44 passed.
- Coverage: `quant_trading/regime/detector.py` now 100% (was 99%; line 364 covered by the new test). Verified with `COVERAGE_CORE=pytrace python -m coverage run -m pytest tests/test_regime.py` then `coverage report -m`.
- Broader subset: 833 passed across regime/backtest_engine/risk_metrics/config/portfolio/optimization/monte_carlo/strategies_examples.

## What remains unresolved

- No commit made (repo rule: only on explicit user request).
- `quant_trading/optimization/__init__.py` lines 19-20 (`except ImportError`) remain uncovered but the branch is structurally unreachable (skopt imports in `bayesian.py` are lazy). Not a meaningful gap.
- Several modules at 99% each have a single uncovered defensive branch: `config/settings.py:136`, `data/providers.py:493->495`, `optimization/walk_forward.py:53` & `796`, `portfolio/portfolio.py:517`, `backtest/engine.py:1030->1033`, `backtest/metrics.py:269->272`.
- Full `pytest -q` cannot complete in one run due to a pre-existing hanging network test in `tests/test_alphavantage_provider.py` (unrelated).

## Approaches that failed and why

- `quant_trading/optimization/__init__.py` `except ImportError` cannot be meaningfully covered: skopt imports are lazy, so the import always succeeds even when skopt is absent. Chasing it would test dead code.
- Coverage measurement: `pytest-cov` (7.1.0) in this environment breaks numpy import ("cannot load module more than once per process"). Workaround: use `COVERAGE_CORE=pytrace python -m coverage run -m pytest ...` then `python -m coverage report -m` (the pure-Python tracer avoids the C-extension re-entry conflict).

## One precise next task

- Add a deterministic test for one remaining single-branch coverage gap in a core module (best candidate: `quant_trading/backtest/engine.py:1030` `if quantity <= 0: return` in `_cover_short`, or `quant_trading/portfolio/portfolio.py:517`), then re-verify ruff/black/mypy/tests/coverage for that module using the `COVERAGE_CORE=pytrace` workaround above.
- Constraints: do NOT commit unless explicitly asked; preserve working baseline; exclude secrets/env/cache artifacts.

(End of file)