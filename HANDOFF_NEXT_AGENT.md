## What changed (this session)
Migrated `tests/test_risk_metrics.py` to full type annotations and enabled its mypy override, plus fixed one real latent bug in `calculate_beta` that the migration surfaced.
- `tests/test_risk_metrics.py`:
  - Added `-> None` to 115 defs that were missing a return annotation.
  - Replaced `np.testing.assert_allclose(result.values, expected.values)` with `result.to_numpy()/expected.to_numpy()` to satisfy numpy stubs (`.values` is typed `ndarray | ExtensionArray`).
  - Structural fix: 10 test functions were accidentally nested *inside* the first `if __name__ == "__main__": pytest.main(...)` block (old lines 591-648), so they were never collected and had untyped `self`. Converted them into a real class `TestEdgeCaseCoverage` (preserves coverage; now collected). The EOF `if __name__` guard is now the only one.
- `pyproject.toml`: appended `[[tool.mypy.overrides]] module = "tests.test_risk_metrics"` / `disallow_untyped_defs = true`, immediately before `[tool.coverage.run]`. Now 53 overrides, 0 duplicates.
- `quant_trading/risk/metrics.py`: `calculate_beta` used exact `var == 0` to detect a constant market; a non-exactly-representable constant (e.g. `[0.05,0.05,0.05]`) yields float-noise variance `~7.2e-35`, so beta was a spurious `0.0833` instead of `0.0`. Added a `market.nunique() <= 1` guard (constant series has exactly one unique value, independent of float noise) and kept an `np.isfinite`/zero fallback. `calculate_alpha` delegates to `calculate_beta`, so it inherits the fix.

## What was actually verified (evidence)
- `python3 -m pytest tests/test_risk_metrics.py -p no:cacheprovider -q` -> `115 passed` (baseline was 105; +10 recovered tests).
- `python3 -m pytest tests/test_backtest_engine.py tests/test_backtest_metrics.py tests/test_risk_manager.py -p no:cacheprovider -q` -> `364 passed` (beta consumers unaffected).
- Full suite `python3 -m pytest tests/ -p no:cacheprovider -q` -> `3542 passed, 140 deselected in 352.91s` (0 failures; doctests run via `--doctest-modules`).
- `python3 -m mypy quant_trading/ tests/ --show-error-codes --no-incremental` -> `Found 6 errors in 5 files`, exactly the pre-existing set (4 `no-any-return` in `test_yfinance_provider`/`test_strategy_rsi`/`test_strategy_ma`/`test_readme_cli_commands` + `test_optimization.py:1542` [list-item]); `test_risk_metrics` NOT in the list.
- `python3 -m mypy tests/test_risk_metrics.py --show-error-codes --no-incremental` -> `Success` (direct mode).
- `python3 -m ruff check tests/test_risk_metrics.py quant_trading/risk/metrics.py pyproject.toml` -> `All checks passed!`.
- `python3 -m black --check tests/test_risk_metrics.py quant_trading/risk/metrics.py` -> unchanged.
- `git diff --check` -> clean.

## What remains unresolved (pre-existing / environment, DO NOT "fix" by editing test code)
- Missing optional dependency `matplotlib` (not hit this run; full suite passed).
- `pandas-stubs>=3.0.0` declared but not installed -> 4 pre-existing `no-any-return` modules (see above); treat as known env noise.
- Pre-existing `black --check pyproject.toml` parse failure. Do not run black on the TOML.
- Pre-existing `quant_trading/strategies/base.py:290` issue only under global `--disallow-untyped-defs`; not triggered by per-module overrides.

## Remaining candidates for the same migration (missing `->` counts)
`test_backtest_engine` 134, `test_integration` 5, `test_risk_manager` 156, `test_alphavantage_provider` 305, `test_cli` 324, `test_strategies_examples` 555. `test_optimization` 211 (SKIP, pre-existing `test_optimization.py:1542`).

## One precise next task
Continue the migration with `tests/test_risk_manager.py` (156 missing return annotations). Concrete plan:
1. Baseline: `python3 -m pytest tests/test_risk_manager.py -p no:cacheprovider -q` and `python3 -m mypy quant_trading/ tests/ --show-error-codes --no-incremental` (confirm only the 6 pre-existing errors).
2. Add `-> None` / concrete annotations to all defs missing a return annotation. Also check for any defs with untyped *parameters* (the override enforces both) and any accidentally-nested `if __name__ == "__main__":` blocks that hide untyped `self` (as happened in `test_risk_metrics.py`).
3. Append `[[tool.mypy.overrides]] module = "tests.test_risk_manager"` / `disallow_untyped_defs = true` immediately before `[tool.coverage.run]` (expect 54 overrides, 0 duplicates).
4. Verify: `mypy quant_trading/ tests/` -> only 6 pre-existing errors; `pytest tests/test_risk_manager.py` -> all pass; `ruff check tests/test_risk_manager.py pyproject.toml`; `black --check tests/test_risk_manager.py`; `git diff --check`.
Constraints: preserve the working baseline; no unrelated refactors; prefer fixing annotations over `# type: ignore`; lines <= 100 chars; do not touch `test_optimization.py:1542`, `quant_trading/strategies/base.py:290`, or the pre-existing matplotlib failures; changes stay uncommitted unless asked.

## Failed or corrected approaches this session
- Initial migration added only `-> None`; the newly-enabled override then surfaced 10 `[no-untyped-def]` "missing type annotation for one or more parameters" errors. Root cause was NOT missing returns but 10 functions trapped inside the first `if __name__ == "__main__":` block (untyped `self`, never collected). Fix: convert them into a proper class rather than typing `self` on orphan functions or deleting them.
- Recovering the hidden tests exposed a genuine `calculate_beta` bug (float-noise variance on constant float series). Resolved by an exact `nunique() <= 1` constant check, not by weakening the test.
- Confirmed (same as prior handoff): mypy `[[tool.mypy.overrides]]` sections are reported "unused" when a file is passed directly on the CLI; overrides only take effect for discovered/imported modules. Use directory mode (`mypy quant_trading/ tests/`) as the enforcement check; direct-file `mypy <file>` is only a secondary sanity check.

(End of file)