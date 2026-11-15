## What changed (this session)
Completed the type-annotation migration of `tests/test_backtest_engine.py`:
- Added return annotations to all 134 defs that were missing them (all 159 defs now typed).
  Test functions / `__init__` -> `-> None`; helpers -> concrete types
  (`_run`/`_engine_run`/`_make_result` -> `BacktestResult`, `to_dict` -> `dict`,
  nested `generate_signals` -> `list[Signal]`).
- Added parameter annotations for 15 previously-untyped params: `tmp_path: Path`,
  `monkeypatch: pytest.MonkeyPatch`, helper args (`strategy`, `data`, `traded`,
  `benchmark`, `script`), widened `_run(config: Config | DataConfig [| None])`,
  and `**kwargs: Any`.
- Added imports `from pathlib import Path` and `from typing import Any, cast`.
- Fixed 18 latent mypy errors that surfaced only once the function bodies became
  type-checked: `cast(Any, ...)` for deliberately out-of-contract test values
  (fake regime analysis, `metrics=None`, `Dummy` metrics), `assert x is not None`
  guards before reading Optional attributes, and local `MagicMock` managers in the
  fetch-error tests.
- Added `[[tool.mypy.overrides]] module = "tests.test_backtest_engine"` /
  `disallow_untyped_defs = true` immediately before `[tool.coverage.run]`
  (now 55 overrides, 0 duplicates).
- Ran `black` on the file (it only re-wrapped the over-length signatures I added).

## What was actually verified (evidence)
- `python3 -m pytest tests/test_backtest_engine.py -p no:cacheprovider -q` -> `118 passed`
- `python3 -m mypy quant_trading/ tests/ --show-error-codes --no-incremental` -> only
  1 pre-existing error: `tests/test_optimization.py:1542` (list-item). `test_backtest_engine`
  is NOT in the error list. The override is active: enabling it made mypy check the
  previously-unchecked bodies, which is how the 18 latent errors were found and fixed.
- `python3 -m ruff check tests/test_backtest_engine.py pyproject.toml` -> `All checks passed!`
- `python3 -m black --check tests/test_backtest_engine.py` -> unchanged
- `git diff --check` -> clean
- AST audit (ast-based analyzer, not regex): 159 defs, 0 missing return, 0 missing params.

## What remains unresolved (pre-existing / environment, DO NOT "fix" by editing test code)
- Missing optional dependency `matplotlib`; `pandas-stubs>=3.0.0` declared but not
  installed -> known env noise.
- `black --check pyproject.toml` parse failure (do not run black on the TOML).
- Pre-existing `tests/test_optimization.py:1542` list-item type error (file SKIPPED for migration).
- `quant_trading/strategies/base.py:290` only under global `--disallow-untyped-defs`.

## Remaining migration candidates (verified counts via AST)
- `test_integration.py`: 5/5 missing return, 0 params (smallest -> recommended next)
- `test_alphavantage_provider.py`: 305 missing return, 313 params
- `test_cli.py`: 324 missing return, 157 params
- `test_strategies_examples.py`: 555 missing return, 12 params
- `test_optimization.py`: 211 missing return, 76 params (SKIP: pre-existing 1542 error)

## One precise next task
Migrate `tests/test_integration.py` (5 defs; currently 5 passed, no mypy override).
1. Baseline: `python3 -m pytest tests/test_integration.py -p no:cacheprovider -q`
   (expect 5 passed) and `python3 -m mypy quant_trading/ tests/ --show-error-codes --no-incremental`
   (confirm only the 1 pre-existing `test_optimization.py:1542` error).
2. Add `-> None` to the 5 test functions at approx lines 22, 84, 107, 142, 158.
   No params are missing. Check for any nested `if __name__ == "__main__":` hiding defs.
3. Append `[[tool.mypy.overrides]] module = "tests.test_integration"` /
   `disallow_untyped_defs = true` immediately before `[tool.coverage.run]`
   (expect 56 overrides, 0 duplicates).
4. Verify: `mypy quant_trading/ tests/` -> only the 1 pre-existing error; `pytest
   tests/test_integration.py` -> 5 passed; `ruff check tests/test_integration.py pyproject.toml`;
   `black --check tests/test_integration.py`; `git diff --check`.
Constraints: preserve the working baseline; no unrelated refactors; prefer real
annotations over `# type: ignore`; lines <= 100 chars; leave changes uncommitted.

## Failed or corrected approaches this session
- Initial `grep`/regex attempts to locate missing return annotations were unreliable
  (they matched every def and missed multi-line signatures). Switched to an AST-based
  analyzer (walk `FunctionDef`/`AsyncFunctionDef`, check `node.returns` and arg
  annotations) for an accurate list.
- Enabling the mypy override revealed 18 latent body errors (expected consequence of
  newly checking typed bodies). Fixed them with `cast`/`assert` rather than blanket
  `# type: ignore`, per the "prefer real annotations" constraint.