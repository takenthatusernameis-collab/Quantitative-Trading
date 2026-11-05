# Next Task

## Repository state (post-cleanup)

All checks clean:
- `pytest -q` → **2832 passed, 13 skipped, 131 deselected** (slow/network deselected by default).
- `python -m ruff check .` → All checks passed.
- `python -m black --check .` → 141 files unchanged.
- `python -m mypy quant_trading/` → Success: no issues found in 37 source files.
- Full coverage: **100%** across all 37 modules (6944 stmts, 0 miss, 2372 branches, 0 partial).

## What changed (this session)

Fixed a deterministic `black` formatting regression left by the prior `__all__` audit
session (commit da8d900 added `__all__` lists with **single-quoted** string literals to
24 modules but never ran `black --check`). Normalized all 18 affected modules to
double-quoted literals, matching the project convention used by the other 123 files
and every `__init__.py`.

Files touched (quote normalization only, 69+/69- symmetric):
- `quant_trading/backtest/metrics.py`
- `quant_trading/config/settings.py`
- `quant_trading/data/synthetic.py`
- `quant_trading/data/yfinance_provider.py`
- `quant_trading/monte_carlo/simulator.py`
- `quant_trading/optimization/base.py`, `bayesian.py`, `grid_search.py`, `random_search.py`, `walk_forward.py`
- `quant_trading/portfolio/portfolio.py`, `rebalancer.py`
- `quant_trading/regime/detector.py`
- `quant_trading/risk/limits.py`, `manager.py`, `metrics.py`
- `quant_trading/utils/formatting.py`, `logging.py`

No source, test, or config behavior changed. The change is left unstaged for the
controller to checkpoint (never commit unless explicitly asked).

## What was verified (this session)

- `python -m black --check .` → 141 files unchanged (was: 18 files would be reformatted).
- `python -m ruff check .` → All checks passed.
- `python -m mypy quant_trading/` → Success: no issues found in 37 source files.
- `python -m pytest --doctest-modules <18 changed modules>` → 109 passed, 2 skipped.
- `tests/test_repository_integrity.py`, `test_strategy_registry_coverage.py`,
  `test_config.py`, `test_readme.py`, `test_readme_cli.py` → 64 passed.
- Full `pytest -q` → 2832 passed, 13 skipped, 131 deselected in 290.33s
  (identical to the pre-existing green baseline; no behavior change).

## What remains unresolved

- Nothing functional. The tree is green on black, ruff, mypy, and the full test suite.
- The formatting fix is left unstaged for the controller to checkpoint.

## Approaches that failed and why

- Coverage-gap hunting is still a dead end: all 37 modules are at 100%.
- Adding a new `examples/run_*.py` script is unnecessary: all 46 primary registry keys
  already have a corresponding example script and README entry.
- The real gap this session was found by running the full CI-equivalent check set
  (`black --check .`) rather than trusting the prior session's claim that "all checks
  clean": black failed on 18 files, all of them `__all__` lists with single-quoted
  literals. Lesson: always run `black --check` after any edit that adds string
  literals, even a pure `__all__` audit.

## One precise next task

- If another session is requested, first re-run `pytest -q`, `python -m ruff check .`,
  `python -m black --check .`, and `python -m mypy quant_trading/` to confirm the tree
  is still green, then select a new bounded task.
- Candidate directions: document more of the remaining undocumented but user-facing
  CLI flags (e.g. `--rsi-period`, `--macd-fast`, `--stoch-k-period`, `--mc-method`,
  `--mc-confidence`, `--mc-seed`), each verified to run end-to-end under the
  mocked-network harness; or extend CLI/README coverage for an under-documented feature.
- Constraints: Do not modify tests to make them pass. Keep changes minimal and
  reversible. The `tests/test_readme_cli.py` and `tests/test_readme_cli_commands.py`
  guards enforce bidirectional consistency between the README CLI section and the live
  parser; any newly documented flag must be a real parser flag and its command must
  exit 0 (or 1 for documented error cases) with no traceback.

(End of file - total 68 lines)