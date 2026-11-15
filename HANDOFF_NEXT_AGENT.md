## What changed (this session)
Migrated `tests/test_strategy_registry_coverage.py` to mypy `disallow_untyped_defs` strictness
(annotations only, no behavior change):
- `tests/test_strategy_registry_coverage.py`: added `-> None` to 9 parameterless `test_*` functions
  (lines 70, 86, 92, 100, 120, 193, 201, 206, 226). Helpers `_example_strategy_classes`,
  `_example_test_classes`, `_synthetic_data` were already fully annotated.
- `pyproject.toml`: added `[[tool.mypy.overrides]] module = "tests.test_strategy_registry_coverage"` /
  `disallow_untyped_defs = true` inside the mypy override block, immediately before `[tool.coverage.run]`.

Earlier sessions (already committed/annotated, do not redo):
- `tests/test_strategy_choppiness.py` (d1c6e70), `tests/test_strategy_ma.py` (e07333f),
  `tests/test_strategy_parabolic_sar.py` + `tests/test_strategy_bollinger_percentb.py` (2bf24a7).

## What was actually verified (evidence)
- `python3 -m mypy tests/test_strategy_registry_coverage.py --show-error-codes` -> `Success: no issues found in 1 source file`.
- `python3 -m mypy tests/test_strategy_registry_coverage.py --disallow-untyped-defs --show-error-codes`
  -> 0 errors in the target file (only the known `quant_trading/strategies/base.py:290` note).
- `python3 -m mypy quant_trading/ tests/test_strategy_registry_coverage.py --show-error-codes`
  -> `Success: no issues found in 39 source files`.
- `python3 -m pytest tests/test_strategy_registry_coverage.py -p no:cacheprovider -q` -> `9 passed in 0.27s`.
- `python3 -m ruff check tests/test_strategy_registry_coverage.py pyproject.toml` -> `All checks passed!`.
- `python3 -m black --check tests/test_strategy_registry_coverage.py` -> unchanged.
- `git diff --check` -> clean.
- Override audit via `tomllib`: 43 overrides, 0 duplicates, target present.
- Per-module override audit (mypy per overridden module file, errors filtered to that file): `failing overridden modules: none`.
- Full suite: `3627 passed, 142 skipped, 140 deselected, 19 failed` — the 19 failures are ALL pre-existing
  environment failures caused by `matplotlib` not being installed
  (`ModuleNotFoundError: No module named 'matplotlib'` / `ImportError: matplotlib is required for chart generation`),
  located in `test_backtest_report.py`, `test_cli.py::TestHtmlReportFlag`, and
  `test_readme_cli_commands.py`. They do NOT touch the changed module and are unrelated to this annotation change.

## What remains unresolved (pre-existing, DO NOT touch)
- Missing optional dependency `matplotlib` -> the 19 reporting/CLI failures above. Not caused by these edits;
  do not attempt to "fix" them in this migration line of work.
- Pre-existing mypy issue `quant_trading/strategies/base.py:290` (only reported when `--disallow-untyped-defs`
  is forced globally; not triggered by per-module overrides). Do not touch.
- Pre-existing `tests/test_optimization.py:1542` list-item `arg-type` error — do not touch.
- Pre-existing `black --check pyproject.toml` parse failure (`pyproject.toml:10:17 authors = [{name = "..."}]`).
  Do not run black on the TOML.
- Changes are UNCOMMITTED in the working tree (tests/test_strategy_registry_coverage.py + pyproject.toml).
  Commit only if the user/harness asks.

## Remaining candidates for the same migration
(in-file error counts measured with `mypy <file> --disallow-untyped-defs --show-error-codes`, excluding `base.py:290`):
`test_strategy_rsi` 9 (8 `-> None` + `_df(prices: list[float]) -> pd.DataFrame` + `_valid_rsi() -> RSIStrategy`),
`test_strategy_aroon` 11,
`test_strategy_factory` 36, `test_yfinance_provider` 36, `test_monte_carlo` 40, `test_trade_analysis` 49,
`test_backtest_report` 56, `test_yfinance_fetch_many` 88, `test_portfolio_rebalancer` 110,
`test_risk_metrics` 115, `test_backtest_engine` 133, `test_integration` 138, `test_risk_manager` 156,
`test_optimization` 211 (SKIP, pre-existing error), `test_alphavantage_provider` 305, `test_cli` 324,
`test_strategies_examples` 555.

## Failed or corrected approaches
- No approach failures this session. `test_strategy_registry_coverage` migrated cleanly on the first pass.
- Note: the full suite is NOT fully green in this environment due to the missing `matplotlib` optional
  dependency (pre-existing). Do not treat those 19 failures as regressions from annotation work.

## One precise next task
Continue the same migration with `tests/test_strategy_rsi.py` (9 errors, all
`Function is missing a ... annotation`). Concrete plan:
1. `_df(prices)` at line 9 -> `_df(prices: list[float]) -> pd.DataFrame`
   (mirrors `tests/test_strategy_ma.py:11` exactly; `_df` is always called with a `list[float]`).
2. `_valid_rsi()` at line 23 -> `_valid_rsi() -> RSIStrategy` (`RSIStrategy` is already imported).
3. Add `-> None` to the 7 parameterless `test_*` functions at lines 27, 34, 41, 48, 54, 63, 84.
4. Append `[[tool.mypy.overrides]] module = "tests.test_strategy_rsi"` / `disallow_untyped_defs = true`
   **inside the mypy override block, immediately before `[tool.coverage.run]`** (do not append at end of file).
5. Verify: `python3 -m mypy tests/test_strategy_rsi.py --show-error-codes` -> 0 errors;
   `mypy quant_trading/ tests/test_strategy_rsi.py`; `pytest tests/test_strategy_rsi.py`; `ruff check`;
   `black --check tests/test_strategy_rsi.py`; `git diff --check`.
6. Re-run the per-module override audit (all overridden modules clean, 0 duplicates, expect 44 overrides) before handing off.

Procedure (proven, ~10 min per file):
1. Baseline: `python3 -m pytest <file> -p no:cacheprovider -q` and
   `python3 -m mypy <file> --disallow-untyped-defs --show-error-codes` (expect only `no-untyped-def`
   errors in that file plus the `base.py:290` note).
2. Add `-> None` to parameterless `test_*` functions and concrete types to any helper.
3. Append the override inside the mypy override block, before `[tool.coverage.run]`.
4. Run the verification commands above.
5. Re-run the override audit before handing off.

Constraints: preserve the working baseline; no unrelated refactors;
do not touch `tests/test_optimization.py:1542` or `quant_trading/strategies/base.py:290`;
do not attempt to fix the pre-existing `matplotlib` failures; keep annotations minimal and lines <= 100 chars.