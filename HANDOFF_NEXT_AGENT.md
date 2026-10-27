# Handoff for Next Agent

## What changed
- Added a generalized README↔code drift guard in `tests/test_readme.py` (+64 lines, only file modified):
  - New helper `_documented_quant_trading_imports()` parses every `from quant_trading.* import ...` statement in the README (single-line, multi-name, and parenthesised multi-line blocks) and maps each module to its imported names.
  - New test class `TestReadmeQuantTradingImports.test_documented_quant_trading_imports_resolve()` imports each referenced module and asserts every documented name is exported by it (one-way: README → module; modules export more than the README documents, matching the existing CLI-guard philosophy).
- Existing `tests/test_readme.py` tests (`TestReadmeDataImports`, etc.) left untouched.

## What was actually verified
- All README-documented `quant_trading.*` imports currently resolve (manually checked before writing the guard; no existing drift to fix).
- `python -m pytest tests/test_readme.py -q` → 11 passed (was 10; +1 new test).
- `python -m pytest -q` (full suite) → 2206 passed, 11 skipped, 0 failures in ~139s (was 2205; +1 new test).
- `python -m ruff check tests/test_readme.py` → clean.
- `python -m mypy tests/test_readme.py` → Success, no issues.
- `python -m black --check tests/test_readme.py` → 1 file unchanged (after applying `black` once).
- `git status --short` → only `tests/test_readme.py` modified; working tree otherwise clean.

## What remains unresolved
- None blocking. All checks green for the changed file and the full suite.

## Approaches that failed and why
- None for this task.

## One precise next task
- No required work. Consider a bounded feature or fix from the backlog; all core functionality verified and working.

Constraints:
- Follow the existing `_documented_entries()` / `_registry_section()` / `_documented_av_methods()` parsing style already used in `tests/test_readme.py`.
- Keep `black`, `ruff`, `mypy` clean for changed files and the full suite green.
- Do NOT commit unless explicitly asked.

(End of file)