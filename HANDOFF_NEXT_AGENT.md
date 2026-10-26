# Handoff for Next Agent

## What changed
- Added `tests/test_readme_cli.py` (new file, not committed): a README↔CLI drift guard that mirrors the prior session's README↔provider method guard in `tests/test_readme.py`.

## What was actually verified
- `python -m pytest tests/test_readme_cli.py -q` → 1 passed, 0 failures.
- `python -m pytest -q` (full suite) → 2205 passed, 11 skipped, 0 failures in ~139s (was 2204; +1 new test).
- `python -m ruff check tests/test_readme_cli.py` → clean.
- `python -m mypy tests/test_readme_cli.py` → Success, no issues.
- `python -m black --check tests/test_readme_cli.py` → 1 file unchanged.
- `git status --short` → only `tests/test_readme_cli.py` untracked; working tree otherwise clean.

## What remains unresolved
- None blocking. All checks green for the changed file and the full suite.

## Approaches that failed and why
- First attempt wrote the guard bidirectionally (`test_no_undocumented_flags_are_advertised`), which was wrong: the README documents a curated subset of the 110 flags the parser accepts, so the reverse direction failed immediately. Removed that test and kept only the one-way README→parser direction, matching the contract the README actually states.
- `_documented_cli_flags()` initially kept the `--` prefix while `_parser_cli_flags()` stripped it, so every documented flag was reported missing. Fixed by calling `.lstrip("-")` on the parsed flag.
- `ruff` flagged `import examples.cli as cli` (PLR0402); moved to a top-level `from examples import cli` import and removed the inner import. No retries beyond these single corrections.

## One precise next task
- No required work. Consider a bounded feature or fix from the backlog; all core functionality verified and working.

Constraints:
- Follow the existing `_documented_entries()` / `_registry_section()` / `_documented_av_methods()` parsing style already used in `tests/test_readme.py`.
- Keep `black`, `ruff`, `mypy` clean for changed files and the full suite green.
- Do NOT commit unless explicitly asked.

(End of file - total 33 lines)