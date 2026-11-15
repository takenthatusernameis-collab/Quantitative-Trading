## What changed (this session)
Migrated `tests/test_monte_carlo.py` to mypy `disallow_untyped_defs` strictness (annotations only, no behavior change):
- `tests/test_monte_carlo.py`:
  - Added `-> None` to all 37 module-level test functions and 5 methods in `TestMonteCarloResultSerialization`.
  - Annotated the 3 `@pytest.mark.parametrize` parameters: `n_simulations: int`, `confidence_level: float`, `periods_per_year: int` (matches convention in `tests/test_config.py`).
  - No `# type: ignore` needed — the file had no pre-existing assignment/attr/index errors under `--disallow-untyped-defs`.
- `pyproject.toml`: added `[[tool.mypy.overrides]] module = "tests.test_monte_carlo"` / `disallow_untyped_defs = true` inside the mypy override block, immediately before `[tool.coverage.run]`.

Earlier sessions (already committed, do not redo): `tests/test_strategy_choppiness.py`, `test_strategy_ma.py`, `test_strategy_parabolic_sar.py`, `test_strategy_bollinger_percentb.py`, `test_strategy_registry_coverage.py`, `test_strategy_rsi.py`, `test_strategy_aroon.py`, `tests/test_strategy_factory.py`, `tests/test_yfinance_provider.py`.

## What was actually verified (evidence)
- `python3 -m pytest tests/test_monte_carlo.py -p no:cacheprovider -q` -> `47 passed in 1.42s`.
- `python3 -m mypy tests/test_monte_carlo.py --disallow-untyped-defs --show-error-codes --no-incremental` -> only pre-existing `quant_trading/strategies/base.py:290` remains (41 `no-untyped-def` errors resolved).
- `python3 -m mypy tests/test_monte_carlo.py --show-error-codes --no-incremental` -> `Success: no issues found in 1 source file` (override applies `disallow_untyped_defs`).
- `python3 -m mypy quant_trading/ tests/test_monte_carlo.py --show-error-codes --no-incremental` -> `Success: no issues found in 39 source files`.
- `python3 -m ruff check tests/test_monte_carlo.py pyproject.toml` -> `All checks passed!`.
- `python3 -m black --check tests/test_monte_carlo.py` -> unchanged.
- `git diff --check` -> clean.
- Override audit via tomllib: 48 overrides, 0 duplicates, `tests.test_monte_carlo` present and placed immediately before `[tool.coverage.run]`.
- Per-module override audit (`mypy <file> --disallow-untyped-defs`, errors filtered to that file, excluding `base.py:290`): running in background, results in `/tmp/audit.log`.

## What remains unresolved (pre-existing, DO NOT touch)
- Missing optional dependency `matplotlib` -> reporting/CLI test failures (pre-existing).
- Pre-existing mypy issue `quant_trading/strategies/base.py:290` (only reported when `--disallow-untyped-defs` is forced globally; not triggered by per-module overrides).
- Pre-existing `tests/test_optimization.py:1542` list-item `arg-type` error.
- Pre-existing `black --check pyproject.toml` parse failure. Do not run black on the TOML.
- Changes are UNCOMMITTED in the working tree (`tests/test_monte_carlo.py` + `pyproject.toml`). Commit only if the user/harness asks.

## Remaining candidates for the same migration
(in-file error counts measured with `mypy <file> --disallow-untyped-defs --show-error-codes`, excluding `base.py:290`; counts from the prior session may be slightly stale — re-baseline each file):
`test_trade_analysis` 49, `test_backtest_report` 56, `test_yfinance_fetch_many` 88, `test_portfolio_rebalancer` 110, `test_risk_metrics` 115, `test_backtest_engine` 133, `test_integration` 138, `test_risk_manager` 156, `test_optimization` 211 (SKIP, pre-existing error), `test_alphavantage_provider` 305, `test_cli` 324, `test_strategies_examples` 555.

## One precise next task
Continue the same migration with `tests/test_trade_analysis.py` (expect ~49 `no-untyped-def` errors). Concrete plan:
1. Baseline: `python3 -m pytest tests/test_trade_analysis.py -p no:cacheprovider -q` (should pass) and `python3 -m mypy tests/test_trade_analysis.py --disallow-untyped-defs --show-error-codes --no-incremental` (expect `no-untyped-def` errors in that file plus `base.py:290`; note any pre-existing assignment/attr/index errors like those in `test_yfinance_provider.py`).
2. Inspect the file; add `-> None` / concrete parameter annotations (conventions used this session: `tmp_path: Path` via `from pathlib import Path`, `datetime | None` for optional datetimes, `int`/`float` for parametrize params). If annotation newly exposes real mypy errors in bodies, prefer fixing the annotation; use narrow `# type: ignore[<code>]` only where needed (matching existing convention in the file).
3. Append `[[tool.mypy.overrides]] module = "tests.test_trade_analysis"` / `disallow_untyped_defs = true` **inside the mypy override block, immediately before `[tool.coverage.run]`** (do not append at end of file).
4. Verify: `python3 -m mypy tests/test_trade_analysis.py --show-error-codes` -> 0 errors; `mypy quant_trading/ tests/test_trade_analysis.py`; `pytest tests/test_trade_analysis.py`; `ruff check tests/test_trade_analysis.py pyproject.toml`; `black --check tests/test_trade_analysis.py`; `git diff --check`.
5. Re-run the per-module override audit (all overridden modules clean, 0 duplicates, expect 49 overrides) before handing off.

Constraints: preserve the working baseline; no unrelated refactors; do not touch `tests/test_optimization.py:1542` or `quant_trading/strategies/base.py:290`; do not attempt to fix the pre-existing `matplotlib` failures; keep annotations minimal and lines <= 100 chars; changes stay uncommitted unless asked.

## Failed or corrected approaches this session
- None. `test_monte_carlo.py` migrated cleanly with annotation-only changes; no `# type: ignore` required and no behavioral edits.

(End of file)