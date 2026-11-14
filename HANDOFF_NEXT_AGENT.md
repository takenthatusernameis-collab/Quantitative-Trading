## What changed (this session)
- Extended the targeted mypy-strictness migration to `tests/test_rebalancer_execution.py` (25 test defs, all `def test_xxx():` or `def test_xxx(seed: int):`).
  - Added ` -> None` return annotation to all 25 test defs; no runtime behavior changed.
  - No `type: ignore` needed: no test deliberately violates a type.
- Added a per-module `[[tool.mypy.overrides]]` for `tests.test_rebalancer_execution` with `disallow_untyped_defs = true` in `pyproject.toml` (global remains `false`).

## What was actually verified (evidence)
- `python3 -m pytest -q tests/test_rebalancer_execution.py -p no:cacheprovider` -> `37 passed in 0.17s` (identical to pre-change baseline).
- `python3 -m mypy quant_trading/ tests/test_rebalancer_execution.py --show-error-codes` -> `Success: no issues found in 39 source files` (the new override is now recognized — it no longer appears in the `unused section(s)` note).
- `python3 -m ruff check tests/test_rebalancer_execution.py` -> `All checks passed!`.
- `python3 -m black --check tests/test_rebalancer_execution.py` -> unchanged (well-formed).
- `git diff --check` -> clean.

## What remains unresolved
- Full test suite remains too slow for the 300-second command window; focused suites and targeted checks pass.
- Pre-existing mypy errors in `tests/test_optimization.py` (line 1542) and `tests/test_readme_cli_commands.py` (lines 53/64/117) remain outstanding (unrelated).
- `pyproject.toml` fails `black --check` parse at line 10 (`authors` TOML) — pre-existing, unrelated. `black --check` on the changed test file passes; only `pyproject.toml` itself fails to parse under black's TOML parser.
- `quant_trading/strategies/base.py:290` has a pre-existing untyped def; flagged only when `--disallow-untyped-defs` is passed on the CLI. Out of scope without flipping the global setting.
- `tests/test_risk_manager.py` (156 untyped defs) remains un-migrated — exceeds the <= ~60 bounded guideline; do not attempt without a materially different scope (e.g. a single bounded class) or flipping the global setting.

## Failed or corrected approaches
- `tests/test_risk_manager.py` as a target: audited via `mypy --disallow-untyped-defs` -> 157 errors / 156 untyped defs, above the ~60 guideline; abandoned. Do not retry as a whole-file migration.
- Bulk script appended ` -> None` after the existing colon (`...(self): -> None:`), producing syntax errors (seen in a prior session); fixed by matching `^(\s*def test_\w+\([^)]*)\):([ \t]*)$` directly and reconstructing the line. Not repeated here — the regex anchored on the closing paren + colon.
- Do not enable global `disallow_untyped_defs` without addressing project-wide untyped definitions (including `quant_trading/` source). Continue file-by-file targeted overrides.

## One precise next task
- Extend the targeted mypy-strictness migration to another small test module. Audited candidates (untyped-def counts): `tests/test_utils.py` (22 — smallest, recommended), `tests/test_rebalancer.py` (37), `tests/test_strategy_base.py` (55 — near the ~60 guideline ceiling).
  - Evidence/constraints: confirm scope is bounded first (`python3 -m mypy tests/<module>.py --disallow-untyped-defs --show-error-codes`; expect <= ~60 untyped defs). Only proceed if small and the module collects under pytest.
  - Annotate helpers/tests with appropriate types (usually `-> None` for tests; specific types for fixtures/helpers) without changing runtime behavior; keep lines <= 100 chars; run `black` on any line it flags; add intentional `type: ignore` only where a test deliberately violates a type.
  - Add a per-module `[[tool.mypy.overrides]]` for the module with `disallow_untyped_defs = true` in `pyproject.toml`. Do not flip the global mypy setting.
  - Keep `pytest -q tests/<module>.py -p no:cacheprovider`, `mypy quant_trading/ tests/<module>.py`, `ruff check tests/<module>.py`, `black --check tests/<module>.py`, and `git diff --check` clean.

(End of file)