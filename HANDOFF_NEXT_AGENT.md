## What changed (this session)
Annotated every `__init__` / `__init_subclass__` method in `quant_trading/` that lacked a `-> None`
return annotation (61 methods across 17 files) plus the previously-unannotated parameters of
`Strategy.__init_subclass__` (`cls: type[Any]`, `**kwargs: Any`) in quant_trading/strategies/base.py:290.
- All parameter types were already present; only `-> None` was missing. AST check confirms 0 missing
  parameter and 0 missing method return annotations across `quant_trading/`.
- No signature exceeded 100 columns after insertion; `black --check quant_trading/` is unchanged.
- Added a `[tool.mypy.overrides]` entry `module = "quant_trading.*"` / `disallow_untyped_defs = true`
  in pyproject.toml (placed right after `tests.test_optimization`, before `[tool.coverage.run]`).
  Did NOT flip the global `disallow_untyped_defs` because `examples/` has 67 pre-existing strict
  errors unrelated to this task.

## What was actually verified (evidence)
- `python3 -m mypy quant_trading/ examples/ tests/ --show-error-codes --no-incremental`
  -> `Success: no issues found in 156 source files` (0 errors).
- `python3 -m mypy quant_trading/ --disallow-untyped-defs --no-incremental`
  -> `Success: no issues found in 38 source files` (strict mode clean for quant_trading).
- `python3 -m ruff check quant_trading/` -> `All checks passed!`
- `python3 -m black --check quant_trading/` -> `38 files would be left unchanged.`
- `python3 -m pytest -q` -> `3726 passed, 53 skipped, 140 deselected, 19 failed` (213s).
  The 19 failures are ALL pre-existing environment issues, unrelated to this change:
  - 6x test_backtest_report.py: `ImportError: matplotlib is required for chart generation`
  - 2x test_backtest_report.py: `ModuleNotFoundError: No module named 'matplotlib'`
  - 8x test_cli.py::TestHtmlReportFlag: report/matplotlib failures
  - 3x test_readme_cli_commands.py: `--optimizer bayesian` (scikit-optimize not installed) and
    `--report` (matplotlib) commands
  None are caused by adding `-> None` annotations (zero runtime effect).

## What remains unresolved (pre-existing / environment, DO NOT "fix" by editing test/library code)
- Missing optional dev dependencies `matplotlib` and `scikit-optimize` (bayesian extra) and
  `pandas-stubs>=3.0.0` in the runtime environment (pandas treated as `Any` by mypy).
- `black --check pyproject.toml` parse failure (do not run black on TOML).
- `examples/` has 67 pre-existing `--disallow-untyped-defs` errors; out of scope for this task.

## Remaining candidates
- None identified for `quant_trading/`: all `__init__`/`__init_subclass__` methods annotated and
  `disallow_untyped_defs = true` active for `quant_trading.*`.

## One precise next task
No further typing work remains in `quant_trading/`. If the next session wishes to continue
type-strictness, the bounded task would be to install the missing dev dependencies
(`pip install -e ".[dev]"`) so the 19 environment-related test failures resolve and the suite is
green, then re-run `pytest -q` and `mypy quant_trading/ examples/ tests/`. Constraints: preserve
the working baseline; no unrelated refactors; leave changes uncommitted unless explicitly asked.

## Failed or corrected approaches this session
- Setting global `[tool.mypy] disallow_untyped_defs = true`: rejected because `examples/` has 67
  pre-existing strict errors; used a `quant_trading.*` override instead.
