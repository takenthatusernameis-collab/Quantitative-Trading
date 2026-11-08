# Handoff to next agent

## What changed (this session, 2026-11-08)

Fixed a real, reproducible README/CLI drift and added a regression guard so it
cannot recur silently.

- **`README.md:500`** — the "Command Line Interface" section claimed
  `--n-jobs` had a default of `1`. The live parser default is `4`
  (`examples/cli.py:650`, `default=4`, and its own `help` string says
  `Number of parallel jobs (default: 4)`). Users following the docs got a
  different default than advertised. Changed the README claim to `(default 4)`.
- **`tests/test_readme_cli.py`** — added `TestReadmeCliFlags.test_documented_defaults_match_the_parser`,
  which parses every `default <value>` claim the README makes about a flag and
  compares it against the live `parse_args()` namespace. Verified to **fail**
  on the old README (`n-jobs: README claims default '1', parser default is 4`)
  and to **pass** after the fix.

- **`examples/cli.py:793`** — `--wf-step-size` had parser `default=None`, but its
  help text (`(default: 1.0, ...)`) and the README both documented default `1.0`,
  and `walk_forward.py` normalizes `None -> 1.0`. Changed the parser default to
  `1.0` so the declared default matches the documented/effective default (same
  class of bug as the `--n-jobs` fix above).
- **`README.md:590-591`** — rephrased the `--wf-step-size` default claim into the
  backtick-quoted `` `--wf-step-size` (default `1.0`) `` form so it is now
  covered by the existing `tests/test_readme_cli.py` default-claim guard
  (previously the prose "It defaults to `1.0`" slipped past the regex).

No code, dependency, or behavior changes beyond the parser default (which now
matches the value `walk_forward.py` already used internally).

## Verified (this session, 2026-11-08)

- `git status --short`: clean before work; 2 files modified after (`README.md`,
  `examples/cli.py`). No unrelated changes.
- `python3 -m ruff check .` → **All checks passed**.
- `python3 -m mypy quant_trading/` → **Success: no issues found in 37 source
  files**. (`examples/cli.py` is not type-checked by the project's mypy
  invocation.)
- `python3 -m pytest -q tests/test_cli.py tests/test_readme_cli.py
  tests/test_readme_cli_commands.py tests/test_readme.py` → **307 passed,
  1 skipped, 3 deselected** (~4:10).
- The `--wf-step-size` default-claim guard proven to catch drift: confirmed
  `_coerce_default(None, '1.0')` is `False` (the old parser default would have
  failed the test) and `_coerce_default(1.0, '1.0')` is `True` after the fix.

## Unresolved / not completed

- None. The task is complete and verified.

## Failed approaches (do not repeat unchanged)

- **First default-drift scan was too loose.** A naive regex matched prose
  phrases like ``--risk-free-rate`` "default **to** the value of the
  configuration file" and raised a false positive. Fixed by tightening the
  claim regex to require a parenthesised, literal value token (number, bool,
  `None`, or one of the documented enum strings). Do not reuse the loose
  regex; use the tightened one in `tests/test_readme_cli.py`.
- Prior constraints still apply: do not run the full fast suite with a
  120000 ms timeout (~410s; use > 300000 ms); `rg` is not installed (use
  `grep`/Python); do not refactor speculatively or weaken safety/permissions;
  `tests/test_cli.py` Bayesian-without-skopt skipif is environment-dependent.

## One precise next task

- **If the user provides a concrete request (failing test, documented API
  drift, reproducible CLI/data/dependency issue):** implement the smallest
  reversible change, then verify:
  1. `python3 -m ruff check .`
  2. `python3 -m mypy quant_trading/`
  3. Focused `pytest` module(s) for the changed area
  4. For cross-cutting changes, `python3 -m pytest -q -m "not slow and not
     network"` with timeout > 300000 ms
  Record evidence and `git status`/diff summary in this handoff; commit/push
  only if explicitly requested.
- **If still unassigned:** re-run the baseline checks (ruff + mypy + fast
  suite) before acting on any future report. The new regression guard in
  `tests/test_readme_cli.py` now protects the README's `default <value>`
  claims against parser drift, so any future README/CLI desync is caught
  automatically.

## Environment notes

- Use `python3 -m pytest|ruff|mypy`.
- `data/` gitignored; do not commit runtime data/secrets.
- `rg` unavailable.
- Commit/push only when explicitly requested.

(End of file)