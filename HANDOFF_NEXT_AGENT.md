## What changed (this session)
Completed the type-annotation migration of `tests/test_cli.py` (329 defs):
- Added return annotations (`-> None` for all `test_*` methods/`__init__`/spy/`_raise_*`; specific return types for value-returning helpers: `_make_args`/`_args`/`_regime_args`/`_base_opt_args` -> `argparse.Namespace`, `_make_result`/`get_parameters`/`mock_create_strategy`/`summary`/`segments` -> `Any`, `_synthetic_config` -> `Config`, `_run` -> `tuple[int, str]`).
- Added parameter annotations for all previously-untyped params (`tmp_path: Path`, `capsys: CaptureFixture[Any]`, `monkeypatch: MonkeyPatch`, `filename`/`content`/`message: str`, `arguments: list[str]`, `days`/`seed`/`param_a`/`param_b: int`, `args`/`overrides: Any`, plus variadic `**overrides`/`*a, **k`/`*args, **kwargs` -> `Any`).
- No new imports needed (`argparse`, `Path`, `CaptureFixture`, `MonkeyPatch`, `Any`, `Config` already imported).
- Formatted with `black` (rewrapped over-long signatures).

Fixed 4 pre-existing call-site type errors that blocked a clean mypy run:
- `examples/cli.py:278` `_is_supported_interval(interval: str)` -> `(interval: str | None)` (body already handles `None` via `(interval or "")`).
- `tests/test_cli.py` three `strategy = kwargs.get("strategy")` sites in `side_effect` helpers -> added `assert strategy is not None` narrowing before `strategy.name` (lines ~2439, 2664, 2677).

Appended `[[tool.mypy.overrides]] module = "tests.test_cli"` / `disallow_untyped_defs = true` immediately before `[tool.coverage.run]` (now 58 overrides, 0 duplicates).

## What was actually verified (evidence)
- `python3 -m mypy quant_trading/ tests/ --show-error-codes --no-incremental` -> only 1 pre-existing error: `tests/test_optimization.py:1542` (list-item). `test_cli.py` produces no errors under the new override.
- `python3 -m pytest tests/test_cli.py -p no:cacheprovider -q` -> `9 failed, 286 passed, 3 deselected` (identical to baseline; the 9 failures are pre-existing `TestHtmlReportFlag` report/matplotlib issues, unrelated to annotations - no regressions).
- `python3 -m ruff check tests/test_cli.py examples/cli.py pyproject.toml` -> `All checks passed!`
- `python3 -m black --check tests/test_cli.py examples/cli.py` -> unchanged
- `git diff --check` -> clean

## What remains unresolved (pre-existing / environment, DO NOT "fix" by editing test code)
- Missing optional dependency `matplotlib`; `pandas-stubs>=3.0.0` declared but not installed -> known env noise (drives the `TestHtmlReportFlag` failures).
- `black --check pyproject.toml` parse failure (do not run black on the TOML).
- Pre-existing `tests/test_optimization.py:1542` list-item type error (file SKIP for migration).
- `quant_trading/strategies/base.py:290` only under global `--disallow-untyped-defs`.

## Remaining migration candidates (verified counts via AST)
- `test_strategies_examples.py`: 555 missing return, 12 params (recommended next)
- `test_optimization.py`: 211 missing return, 76 params (SKIP: pre-existing 1542 error)

## One precise next task
Migrate `tests/test_strategies_examples.py` (currently passing, no mypy override yet).
1. Baseline: `python3 -m pytest tests/test_strategies_examples.py -p no:cacheprovider -q` and `python3 -m mypy quant_trading/ tests/ --show-error-codes --no-incremental` (confirm only the 1 pre-existing `test_optimization.py:1542` error).
2. Add return annotations (`-> None` for test functions; specific types for value-returning helpers) and parameter annotations for missing params; check for nested `if __name__ == "__main__":` hiding defs and any def whose body returns a value (do not annotate those `-> None`).
3. Append `[[tool.mypy.overrides]] module = "tests.test_strategies_examples"` / `disallow_untyped_defs = true` immediately before `[tool.coverage.run]` (expect 59 overrides, 0 duplicates).
4. Verify: `mypy quant_trading/ tests/` -> only the 1 pre-existing error; `pytest tests/test_strategies_examples.py`; `ruff check tests/test_strategies_examples.py pyproject.toml`; `black --check tests/test_strategies_examples.py`; `git diff --check`.
Constraints: preserve the working baseline; no unrelated refactors; prefer real annotations over `# type: ignore`; lines <= 100 chars; leave changes uncommitted.

## Failed or corrected approaches this session
- `disallow_untyped_defs` requires annotations on `self` when combined with varargs: `def spy(self, *a: Any, **k: Any) -> None:` was flagged `no-untyped-def`; corrected to `def spy(self: Any, *a: Any, **k: Any) -> None:` (test double replacing `__init__`).
- mypy flagged unannotated variadic params (`**overrides`, `*args`/`**kwargs`, `*a`/`**k`); corrected all to `: Any`.
- mypy call-site errors `_is_supported_interval(None)` and `strategy.name` on `Any | None` pre-existed; fixed by widening the signature and adding `assert strategy is not None`, respectively.
