## What changed (this session)
- Completed the assigned incremental mypy-strictness task for `tests/test_repository_integrity.py`.
  - Added `-> None` return annotations to all 24 previously untyped test functions.
  - Extracted the repeated AST docstring check into `_is_docstring_expr(statement: ast.stmt) -> bool`, which also lets mypy narrow `ast.Expr.value`.
  - Fixed the remaining strict-mode findings in the file: explicit `None` checks and class-level constructor introspection for strategy defaults, an explicit `set[str]` for flag default keys, and consistent list typing for tunable strategy parameters.
  - Added a targeted mypy override in `pyproject.toml` enabling `disallow_untyped_defs` only for `tests.test_repository_integrity`; the repository-wide setting remains `false` because the project still has thousands of untyped definitions.
- No runtime behavior was intentionally changed. The only implementation-style changes are type annotations, `inspect.signature(cls)` instead of `inspect.signature(cls.__init__)`, and the equivalent set conversion in the CLI coverage guard.

## What was actually verified (evidence)
- `python3 -m pytest -q tests/test_repository_integrity.py -p no:cacheprovider` -> `31 passed in 8.06s`.
- `python3 -m mypy quant_trading/ tests/test_repository_integrity.py --show-error-codes` -> `Success: no issues found in 39 source files`.
- `python3 -m ruff check .` -> `All checks passed!`.
- `git diff --check` -> clean.
- `python3 -m pytest -q -p no:cacheprovider` reached about 28% with no reported failure, then exceeded the 300-second tool timeout. The full suite was therefore not completed or claimed as passing.

## What remains unresolved
- The full test suite is too slow for the current 300-second command window; the focused integrity suite and project-wide mypy/Ruff checks do pass.
- Repository-wide `disallow_untyped_defs = true` remains impractical without a much larger migration.

## Failed or corrected approaches
- An initial bulk annotation replacement accidentally removed the opening parenthesis from each test signature, producing syntax errors. This was corrected immediately; subsequent parsing, tests, mypy, and Ruff checks passed.
- Do not enable global `disallow_untyped_defs` without first addressing the project-wide untyped definitions.

## One precise next task
- Extend the targeted mypy-strictness migration to `tests/test_holding_pnl_invariants.py`.
  - Evidence: this is the smallest candidate found. It has three untyped parametrized tests at lines 38, 59, and 72; each accepts `seed` and should be annotated as `def test_...(seed: int) -> None`.
  - Add `tests.test_holding_pnl_invariants` to `[[tool.mypy.overrides]]` with `disallow_untyped_defs = true`.
  - Constraints: keep the focused tests, `mypy tests/test_holding_pnl_invariants.py`, `ruff check .`, and `git diff --check` clean. Do not flip the global mypy setting.