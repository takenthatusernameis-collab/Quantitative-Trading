# Handoff for Next Agent

## What changed
- Extended `tests/test_readme_cli.py` so the README↔CLI sync guard now also collects `--flag` tokens from the README's bash code blocks (shell invocations such as `python examples/cli.py --regime-window 30`), not only backtick-quoted prose flags.
- No source code changes. Only `tests/test_readme_cli.py` was modified.

## What was actually verified
- `python -m pytest tests/test_readme_cli.py -q` → 1 passed, 0 failures.
- `python -m pytest -q` (full suite) → 2212 passed, 11 skipped, 0 failures in ~137s.
- `python -m ruff check tests/test_readme_cli.py` → All checks passed.
- `python -m mypy tests/test_readme_cli.py` → Success, no issues found.
- `python -m black --check tests/test_readme_cli.py` → 1 file unchanged.
- `git status --short` → only `tests/test_readme_cli.py` modified; working tree otherwise clean.
- Discriminative power proven: 22 flags are documented only inside code blocks (e.g. `--regime-window`, `--regime-vol-threshold`, `--regime-return-threshold`, `--trade-analysis`, `--bb-period`, `--offline`, `--validate-config`) and were previously unguarded; simulating removal of `--regime-window` from the parser makes the guard report `['regime-window']`. All 33 documented flags are accepted by the live parser, so the test passes on first run.

## What remains unresolved
- None blocking. The one-way (README → parser) contract remains the scope; the reverse direction was deliberately rejected earlier because the README documents a curated subset of the parser's flags.

## Approaches that failed and why
- None in this session. (The bidirectional guard was tried and rejected in the prior session because the parser accepts ~110 flags while the README documents 11.)

## One precise next task
- No required work. All core functionality, README↔CLI sync, config validation, CLI end-to-end/error-reporting coverage, and the full suite are green. Consider selecting a bounded, high-value feature or fix from the backlog if one exists.

Constraints:
- Keep `black`, `ruff`, `mypy` clean for changed files and the full suite green.
- Do NOT commit unless explicitly asked.
