# Handoff to next agent

## What changed
- `examples/cli.py` (`parse_args`): added CLI validation rejecting `--n-jobs < 1` (except the documented `-1` shorthand for all CPU cores) with a clear usage error naming the flag. This closes the gap flagged in the previous handoff: `--n-jobs 0` and `--n-jobs -2` were silently coerced to `1` by the library, unlike every sibling count flag (`--n-iter`, `--mc-simulations`, `--wf-windows`) which rejects `< 1`.
- `examples/cli.py` (`--n-jobs` help): documented the `-1` shorthand and the rejection of values below 1 other than `-1`.
- `tests/test_cli.py`: added 6 tests (4 in `TestParseArgs`, 2 in `TestUserErrorReporting`) mirroring the existing `--n-iter`/`--mc-simulations` parse/validation style.

## Verified (evidence)
- `--n-jobs 0` and `--n-jobs -2` now exit with `Error: invalid --n-jobs: the value must be at least 1, or -1 for all CPU cores (got 0)` / `(got -2)`.
- `--n-jobs -1` and `--n-jobs 4` still accepted.
- `python -m pytest tests/test_cli.py` → 205 passed (118s).
- `python -m pytest tests/test_readme_cli_commands.py` → 84 passed, 3 deselected (18s); README commands that inject `--n-jobs` still work.
- `python -m ruff check examples/cli.py tests/test_cli.py` → All checks passed.
- `python -m mypy examples/cli.py tests/test_cli.py` → Success: no issues found.
- `python -m black --diff` shows no violations in the added code. Pre-existing black violations in untouched blocks (e.g. `--n-iter` message folding, `--bayesian-n-initial` `with` wrapping) are unchanged from the clean baseline and not part of this change.

## Unresolved
- Pre-existing black formatting violations in `examples/cli.py` and `tests/test_cli.py` exist on the clean baseline (verified via `git stash` + `black --check`) and are outside the scope of this change. Do not reformat unrelated blocks unless the project's lint gate requires it.
- Bayesian optimizer unavailable in this environment (scikit-optimize not installed).
- `--n-jobs` validation now mirrors the other count flags; no remaining CLI count-flag gaps identified.

## One precise next task
If the project's CI enforces `black --check` on these files, run `black examples/cli.py tests/test_cli.py` and commit the resulting reformatting; then rerun `ruff`, `mypy`, and `pytest tests/test_cli.py` to confirm no regressions. Otherwise, no further action is required.