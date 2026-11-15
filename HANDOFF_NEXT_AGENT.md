## What changed (this session)
Migrated `tests/test_strategy_choppiness.py` to mypy `disallow_untyped_defs` strictness (annotations only, no behavior change):
- `tests/test_strategy_choppiness.py`: `def _valid_chop() -> ChoppinessIndexStrategy:` + 8 `-> None` test methods.
- `pyproject.toml`: added `[[tool.mypy.overrides]] module = "tests.test_strategy_choppiness"` / `disallow_untyped_defs = true` inside the mypy override block, before `[tool.coverage.run]`.

Earlier in this session, verified (no changes needed — already committed/annotated):
- `tests/test_strategy_parabolic_sar.py` (8 `-> None`, override present) and `tests/test_strategy_bollinger_percentb.py` (8 `-> None`, override present).
- `tests/test_strategy_ma.py` (committed in e07333f: 8 `-> None` + 1 param annotation, override present).

## What was actually verified (evidence)
- Audit of overridden modules (`mypy <file> --show-error-codes` per override): `failing overridden modules: none`.
- `python3 -m mypy quant_trading/ --show-error-codes` -> `Success: no issues found in 38 source files`.
- `python3 -m mypy quant_trading/ tests/test_strategy_choppiness.py --show-error-codes` -> `Success: no issues found in 39 source files`.
- `python3 -m pytest tests/test_strategy_choppiness.py -p no:cacheprovider -q` -> `8 passed in 0.07s`.
- `python3 -m pytest tests/test_strategy_parabolic_sar.py tests/test_strategy_bollinger_percentb.py -p no:cacheprovider -q` -> `14 passed in 0.16s`.
- `python3 -m ruff check tests/ pyproject.toml` -> `All checks passed!`.
- `python3 -m black --check <changed files>` -> unchanged; `git diff --check` -> clean.
- `tomllib` parse of `pyproject.toml`: 42 overrides, 0 duplicates.

## What remains unresolved
- Pre-existing mypy issue `quant_trading/strategies/base.py:290` (only reported when `--disallow-untyped-defs` is forced globally; not triggered by per-module overrides). Do not touch.
- Pre-existing `tests/test_optimization.py:1542` list-item `arg-type` error — do not touch.
- Pre-existing `black --check pyproject.toml` parse failure (`pyproject.toml:10:17 authors = [{name = "..."}]`). Unrelated; only surfaces if someone runs black on the TOML.
- Changes are UNCOMMITTED in the working tree (tests/test_strategy_choppiness.py + pyproject.toml). Commit only if the user/harness asks.

## Remaining candidates for the same migration
(in-file error counts measured with `mypy <file> --disallow-untyped-defs --show-error-codes`, excluding the `base.py:290` noise):
`test_strategy_registry_coverage` 9, `test_strategy_rsi` 9 (8 `-> None` + 1 param annotation), `test_strategy_aroon` 11,
`test_strategy_factory` 36, `test_yfinance_provider` 36, `test_monte_carlo` 40, `test_trade_analysis` 49,
`test_backtest_report` 56, `test_yfinance_fetch_many` 88, `test_portfolio_rebalancer` 110,
`test_risk_metrics` 115, `test_backtest_engine` 133, `test_integration` 138, `test_risk_manager` 156,
`test_optimization` 211 (SKIP, pre-existing error), `test_alphavantage_provider` 305, `test_cli` 324,
`test_strategies_examples` 555.

## Failed or corrected approaches
- No approach failures this session. All three named files (parabolic_sar, bollinger_percentb, choppiness) migrated cleanly on the first pass.
- Rejected: widening `run_backtest`/`BacktestEngine.run` `start`/`end` annotations to `datetime | None` (see prior session notes — targeted `type: ignore[arg-type]` is the minimal fix).

## One precise next task
Continue the same migration with `tests/test_strategy_registry_coverage.py` (9 errors, all
`Function is missing a return type annotation`; check whether it has a `_valid_*` helper needing a concrete return type).
Procedure (proven, ~10 min per file):
1. Baseline: `python3 -m pytest tests/test_strategy_registry_coverage.py -p no:cacheprovider -q` and
   `python3 -m mypy tests/test_strategy_registry_coverage.py --disallow-untyped-defs --show-error-codes` (expect only
   `no-untyped-def` errors in that file plus the `base.py:290` note).
2. Add `-> None` to parameterless `test_*` functions and a concrete return type to any `_valid_*` helper.
3. Append `[[tool.mypy.overrides]] module = "tests.test_strategy_registry_coverage"` / `disallow_untyped_defs = true`
   **inside the mypy override block, before `[tool.coverage.run]`** (do not append at end of file).
4. Verify: `python3 -m mypy tests/test_strategy_registry_coverage.py --show-error-codes` -> 0 errors;
   `mypy quant_trading/ tests/test_strategy_registry_coverage.py`; pytest on the file; `ruff check`; `black --check`;
   `git diff --check`.
5. Re-run the override audit (all modules must be clean, 0 duplicates) before handing off.

Constraints: preserve the working baseline (full suite must stay green); no unrelated refactors;
do not touch `tests/test_optimization.py:1542` or `quant_trading/strategies/base.py:290`;
keep annotations minimal and lines <= 100 chars.
