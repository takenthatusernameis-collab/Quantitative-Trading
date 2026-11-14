## What changed (this session)
- Completed the targeted mypy-strictness migration for `tests/test_regime.py` (the repo has no `tests/test_regime_detector.py`; `test_regime.py` is the regime-detector test module).
  - Added `-> None` return annotations to all 51 previously untyped test functions (`def test_*:` lines); `_make_series` was already typed. No runtime behavior changed.
  - Added a per-module `[[tool.mypy.overrides]]` for `tests.test_regime` with `disallow_untyped_defs = true` in `pyproject.toml` (global remains `false`).
  - Resolved 6 remaining strict-mode errors without runtime changes: annotated 5 `labels` locals as `list[Regime | None]` (passed to private `_merge_segments`) and added `# type: ignore[arg-type]` on the intentional non-Series input to `detect_regimes` (tests/test_regime.py:300).

## What was actually verified (evidence)
- `python3 -m pytest -q tests/test_regime.py -p no:cacheprovider` -> `51 passed in 0.59s`.
- `python3 -m mypy quant_trading/ tests/test_regime.py --show-error-codes` -> `Success: no issues found in 39 source files` (mypy `note: unused section(s)` for the three override modules is pre-existing/known, not a type error).
- `python3 -m ruff check .` -> `All checks passed!`.
- `python3 -m black --check tests/test_regime.py` -> unchanged (well-formed).
- `git diff --check` -> clean.
- `git diff --stat`: `pyproject.toml | 4 ++`, `tests/test_regime.py | 114 ++----` (61 insertions, 57 deletions).

## What remains unresolved
- Full test suite remains too slow for the 300-second command window; focused suites and targeted checks pass.
- Repository-wide `disallow_untyped_defs = true` remains impractical without a larger migration.
- Pre-existing mypy errors in `tests/test_optimization.py` (line 1542) and `tests/test_readme_cli_commands.py` (lines 53/64/117) remain outstanding (unrelated).
- `pyproject.toml` fails `black --check` parse at line 10 (`authors` TOML) — pre-existing, unrelated to this change.

## Failed or corrected approaches
- Do not enable global `disallow_untyped_defs` without addressing project-wide untyped definitions. Continue file-by-file targeted overrides.
- Initial attempt to append ` -> None` produced `(): -> None:` syntax errors on all 51 defs; fixed by replacing `(): -> None:` with `() -> None:` via replaceAll.
- Trailing `# type: ignore[arg-type]` on `detector._merge_segments(...)` call lines exceeds the 100-char limit; instead annotated the `labels` locals as `list[Regime | None]`.

## One precise next task
- Extend the targeted mypy-strictness migration to another small test module (first candidate: `tests/test_limits.py`; alternatives `tests/test_risk_manager.py`, `tests/test_portfolio_rebalancer.py`) by auditing untyped defs and adding a per-module `[[tool.mypy.overrides]]` with `disallow_untyped_defs = true`.
  - Evidence/constraints: confirm scope is bounded first (`python3 -m mypy tests/test_limits.py --disallow-untyped-defs --show-error-codes`, or grep for `def test`/helpers lacking annotations). Only proceed if untyped-def count is small (<= ~60).
  - Annotate helpers/tests with appropriate types (usually `-> None` for tests; specific types for fixtures/helpers) without changing runtime behavior; use `# type: ignore[arg-type]` or local annotations for intentional mismatches, keeping lines <= 100 chars.
  - Keep `pytest -q tests/test_limits.py -p no:cacheprovider`, `mypy quant_trading/ tests/test_limits.py`, `ruff check .`, `black --check tests/test_limits.py`, and `git diff --check` clean. Do not flip the global mypy setting.
