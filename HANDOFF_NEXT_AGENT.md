## What changed (this session)
- `pyproject.toml`: added `[[tool.mypy.overrides]]` for `tests.test_examples_smoke` with `disallow_untyped_defs = true` (placed after `tests.test_example_scripts_run`).
- No test-file code changes required (`tests/test_examples_smoke.py` already fully annotated).

## What was actually verified (evidence)
- `python3 -m pytest tests/test_examples_smoke.py -p no:cacheprovider -q -m slow` -> `133 passed in 102.35s` (file is marked `pytest.mark.slow`, so default addopts deselect all; `-m slow` needed to run them).
- `python3 -m mypy tests/test_examples_smoke.py --disallow-untyped-defs --show-error-codes` -> `Success: no issues found in 1 source file` (only pre-existing unused-section notes).
- `python3 -m mypy quant_trading/ tests/test_examples_smoke.py --show-error-codes` -> not rerun after this edit, but prior full run was clean except pre-existing `quant_trading/strategies/base.py:290`.
- `python3 -m ruff check tests/test_examples_smoke.py pyproject.toml` -> `All checks passed!`
- `python3 -m black --check tests/test_examples_smoke.py` -> `1 file would be left unchanged` (pyproject.toml parse error at line 10 `authors` is pre-existing, unrelated to this change).
- `git diff --check` -> clean (exit 0).

## What remains unresolved
- Pre-existing mypy issue: `quant_trading/strategies/base.py:290` (untyped def, only flagged with `--disallow-untyped-defs`).
- Pre-existing mypy error: `tests/test_optimization.py:1542` list-item type incompatibility (do not touch).
- Pre-existing `pyproject.toml` `black --check` parse issue at line 10 (`authors` TOML); do not fix unless required.
- Pre-existing `pyproject.toml` mypy `unused section(s)` notes for many per-module overrides (benign for targeted checks).
- This session's change (pyproject.toml override) remains UNCOMMITTED (working tree not clean per git status after this edit; commit only if user asks).

## Failed or corrected approaches
- None. `tests.test_monte_carlo.py` was considered but rejected (~40 missing-return-annotation errors, not minimal); `tests/test_examples_smoke.py` chosen instead (already clean).

## One precise next task
- Continue targeted mypy-strictness migration to another test file lacking a `[[tool.mypy.overrides]]` entry. Bounded candidates already mypy-clean under `--disallow-untyped-defs` (verify each baseline first): pick one and confirm 0 errors, then add its override.
  - Candidate files without overrides: `tests/test_cli.py`, `tests/test_backtest_engine.py`, `tests/test_integration.py`, `tests/test_monte_carlo.py`, `tests/test_optimization.py` (SKIP — pre-existing :1542 error), `tests/test_risk_manager.py`, `tests/test_risk_metrics.py`, `tests/test_trade_analysis.py`, `tests/test_backtest_report.py`, `tests/test_yfinance_provider.py`, `tests/test_yfinance_fetch_many.py`, `tests/test_alphavantage_provider.py`, and the `tests/test_strategy_*.py` files not already overridden.
  - Verify baseline: `python3 -m pytest tests/<file>.py -p no:cacheprovider -q` (add `-m slow` if file uses `pytestmark = pytest.mark.slow`) and `python3 -m mypy tests/<file>.py --disallow-untyped-defs --show-error-codes` (tolerate only pre-existing `quant_trading/strategies/base.py:290`).
  - Add minimal, behavior-preserving annotations only where mypy requires; lines <= 100 chars; run `black` if needed.
  - Add `[[tool.mypy.overrides]]` for `tests.test_<file>` with `disallow_untyped_defs = true` in `pyproject.toml`.
  - Verify: pytest, mypy (`quant_trading/ tests/test_<file>.py --show-error-codes`), ruff, black, `git diff --check`.
  - Constraints: preserve working baseline; no unrelated refactors; do not touch `tests/test_optimization.py:1542` / `quant_trading/strategies/base.py:290` unless required with evidence; commit only if explicitly asked.
