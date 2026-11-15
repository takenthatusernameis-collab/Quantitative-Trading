## What changed (this session)
Completed the type-annotation migration of `tests/test_alphavantage_provider.py` (4339 lines, 305 defs):
- Added return annotations to all 305 defs (test functions `-> None`; the `json` mocks `-> Any`, the `provider`/`provider_no_cache` fixtures `-> AlphaVantageProvider`, `_ohlcv_record` `-> dict[str, str]`).
- Added parameter annotations for all 313 previously-untyped params (`provider`/`provider_no_cache` -> `AlphaVantageProvider`, `tmp_path` -> `Path`, `caplog` -> `pytest.LogCaptureFixture`, `status_code` -> `int`, `json_data` -> `Any`, `open_`/`high`/`low`/`close`/`volume` -> `str`, `method` -> `str`, `args` -> `tuple[str, ...]`).
- Added imports `from pathlib import Path` and `from typing import Any`.
- Appended `[[tool.mypy.overrides]] module = "tests.test_alphavantage_provider"` / `disallow_untyped_defs = true` immediately before `[tool.coverage.run]` (now 57 overrides, 0 duplicates).
- Fixed latent body errors surfaced once the override made mypy check the typed bodies: `assert md.metadata is not None` guards before `.get()` reads on `Optional[dict[str, Any]]` metadata (63 guards), `empty_response`/`empty_intraday` var annotations.
- Ran `black` on the file (re-wrapped over-long signatures / fixed spacing).

## What was actually verified (evidence)
- `python3 -m pytest tests/test_alphavantage_provider.py -p no:cacheprovider -q` -> `309 passed` (baseline was 309; unchanged).
- `python3 -m mypy quant_trading/ tests/ --show-error-codes --no-incremental` -> only 1 pre-existing error: `tests/test_optimization.py:1542` (list-item). `test_alphavantage_provider` is NOT in the error list.
- `python3 -m ruff check tests/test_alphavantage_provider.py pyproject.toml` -> `All checks passed!`
- `python3 -m black --check tests/test_alphavantage_provider.py` -> unchanged
- `git diff --check` -> clean

## What remains unresolved (pre-existing / environment, DO NOT "fix" by editing test code)
- Missing optional dependency `matplotlib`; `pandas-stubs>=3.0.0` declared but not installed -> known env noise.
- `black --check pyproject.toml` parse failure (do not run black on the TOML).
- Pre-existing `tests/test_optimization.py:1542` list-item type error (file SKIP for migration).
- `quant_trading/strategies/base.py:290` only under global `--disallow-untyped-defs`.

## Remaining migration candidates (verified counts via AST)
- `test_cli.py`: 324 missing return, 157 params (smallest -> recommended next)
- `test_strategies_examples.py`: 555 missing return, 12 params
- `test_optimization.py`: 211 missing return, 76 params (SKIP: pre-existing 1542 error)

## One precise next task
Migrate `tests/test_cli.py` (329 defs; currently passing, no mypy override yet).
1. Baseline: `python3 -m pytest tests/test_cli.py -p no:cacheprovider -q` and `python3 -m mypy quant_trading/ tests/ --show-error-codes --no-incremental` (confirm only the 1 pre-existing `test_optimization.py:1542` error).
2. Add return annotations (`-> None` for test functions) and parameter annotations for the 157 missing params; check for nested `if __name__ == "__main__":` hiding defs and any def whose body returns a value (do not annotate those `-> None`).
3. Append `[[tool.mypy.overrides]] module = "tests.test_cli"` / `disallow_untyped_defs = true` immediately before `[tool.coverage.run]` (expect 58 overrides, 0 duplicates).
4. Verify: `mypy quant_trading/ tests/` -> only the 1 pre-existing error; `pytest tests/test_cli.py`; `ruff check tests/test_cli.py pyproject.toml`; `black --check tests/test_cli.py`; `git diff --check`.
Constraints: preserve the working baseline; no unrelated refactors; prefer real annotations over `# type: ignore`; lines <= 100 chars; leave changes uncommitted.

## Failed or corrected approaches this session
- Initial single-regex pass annotated the fixture *method names* (`provider`, `provider_no_cache`) as if they were params, producing `def provider: AlphaVantageProvider(...)` syntax errors. Reverted and re-ran, applying param substitutions only inside the parens (after the first `(`).
- Blanket `-> None` on every def was wrong for `_ohlcv_record` (returns a dict) and the `json`/`provider` mocks (return values); corrected those return types individually.
