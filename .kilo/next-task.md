# Next Task

## Repository state

Checks: `python -m pytest -q` (2205 passed, 11 skipped, 0 failures), `python -m ruff check .` (clean for changed files; 3 pre-existing `FURB167` errors in `tests/test_repository_integrity.py` and `tests/test_readme.py:146` on the clean baseline), `python -m mypy quant_trading tests examples` (clean), `python -m black --check quant_trading tests examples` (clean for changed files; `tests/test_repository_integrity.py` would be reformatted but is unchanged on the clean baseline). Baseline is green across tests, lint, type checks, and formatting.

## What changed (this session)

Bounded task: extend the README↔CLI sync contract for the flags documented in the README's "Command Line Interface" section, mirroring the interval guard already in `tests/test_readme.py`.

- Added `tests/test_readme_cli.py` (new file) with:
  - `_cli_section()` — returns the README body under `## Command Line Interface`, using the same `text.index(...) + remainder.find("\n## ")` pattern as `_registry_section()` in `tests/test_readme.py`.
  - `_documented_cli_flags()` — collects every backtick-quoted `--flag` token in that section (e.g. `--strategy`, `--ma-fast-range`), stripping the leading dashes so names match the parser's attribute names.
  - `_parser_cli_flags()` — builds the flag set from the live `parse_args()` namespace rather than scanning `add_argument` calls, so a flag that shares its destination with another (e.g. `--wf-rolling` sets `wf_anchored`, same as `--wf-anchored`) is counted exactly once.
  - `TestReadmeCliFlags.test_every_documented_flag_is_accepted_by_the_parser` — every flag advertised in the README must be accepted by the parser. Direction is one-way (README → parser) because the README intentionally documents a curated subset of the 110 flags the parser accepts; a bidirectional guard was tried and rejected for that reason.
- All 11 README-documented CLI flags already exist on the parser (verified via the test itself and manual diff), so the test passes on first run; its value is catching future drift when a flag is removed from the parser while the README still references it.

Files changed: `tests/test_readme_cli.py` (new). No source code changes.

## What was actually verified

- `python -m pytest tests/test_readme_cli.py -q` → 1 passed, 0 failures.
- `python -m pytest -q` (full suite) → 2205 passed, 11 skipped, 0 failures in ~139s (was 2204; +1 new test).
- Drift detection proven: removing `strategy` from the parser namespace makes the test report `['strategy']`, so the guard has real discriminative power.
- `python -m ruff check tests/test_readme_cli.py` → clean.
- `python -m mypy tests/test_readme_cli.py` → Success, no issues in 1 source file.
- `python -m black --check tests/test_readme_cli.py` → 1 file unchanged (applied black once during authoring; reformats nothing now).
- `git status --short` → only `tests/test_readme_cli.py` untracked; working tree otherwise clean.

## What remains unresolved

- None blocking. All checks green for the changed file and the full suite.

## Approaches that failed and why

- Bidirectional guard (`test_no_undocumented_flags_are_advertised`) failed immediately: the README documents 11 flags while the parser accepts 110, so the reverse direction is the wrong contract. Removed it; kept only the README→parser direction.
- `_documented_cli_flags()` kept the `--` prefix while `_parser_cli_flags()` stripped it, so every documented flag was reported missing. Fixed with `.lstrip("-")`.
- `ruff` flagged `import examples.cli as cli` (PLR0402); moved to a top-level `from examples import cli` import. No retries beyond these single corrections.

## One precise next task

- No required work. Consider selecting a bounded, high-value feature or fix from the issue tracker/backlog. All core functionality verified and working.

Constraints:
- Follow the existing `_documented_entries()` / `_registry_section()` / `_documented_av_methods()` parsing style already used in `tests/test_readme.py`.
- Keep `black`, `ruff`, `mypy` clean for changed files and the full suite green.
- Do NOT commit unless explicitly asked.

(End of file - total 59 lines)