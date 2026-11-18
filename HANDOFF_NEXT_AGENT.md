## What changed (this session)

- Added `tests/test_core_only_imports.py` (new file, untracked, not yet
  committed). It locks the **core-only import invariant** into the ordinary
  `pytest` run: a subprocess blocks `matplotlib` and `skopt` via a
  meta-path finder, then imports every core subpackage, runs a deterministic
  offline backtest (`create_synthetic_provider(..., seed=42, end_date=...)` +
  `MovingAverageCrossover`, fixed 2023-01-01 end date → 16 trades), and
  asserts that chart helpers raise a clean `ImportError` (not a crash) when
  the optional extras are absent.
- This is a **materially different approach** to the same goal the previous
  sessions pursued via a `.github/workflows/core-only-tests.yml` file, which
  could never be committed (see "Approaches that failed"). A committed test
  achieves the guarantee in a route that the automation *can* persist.
- No production code changed. No existing tests changed.

## What was actually verified (evidence)

- Ground-truth baseline re-confirmed at session start: `pytest -q -m "not slow
  and not network"` → **4056 passed, 142 deselected**, exit 0.
- New test passes in isolation: `pytest tests/test_core_only_imports.py -q` →
  **1 passed** (~0.5s).
- **Negative test (regression guard proof):** injecting an unguarded
  top-level `import matplotlib.pyplot` into `quant_trading/backtest/report.py`
  makes the new test **fail** (subprocess exits 1, reports the
  `ModuleNotFoundError`); restoring the file makes it **pass** again. So the
  test genuinely catches the class of regression it targets.
- Lint/format/types: `ruff check` clean, `black --check` clean, `mypy` clean
  (via `python -m ruff/black/mypy`; the bare `ruff`/`black`/`mypy` console
  scripts are not on PATH in this environment).
- Related modules re-run: `test_packaging.py test_readme_cli_commands.py
  test_repository_integrity.py test_backtest_report.py` → **257 passed, 3
  deselected**.
- Full default suite with the new test: **4057 passed, 142 deselected**, exit
  0 (was 4056; +1 = the new test). Baseline preserved, no regressions.

## Repository state / important context

- `HEAD == origin/main == b1bbda5`; working tree otherwise clean except the
  new untracked test file.
- `b1bbda5` (empty commit message, author `kilo-autonomous`) **deleted**
  `.github/workflows/core-only-tests.yml` that `770cb0a` had added, and
  rewrote `HANDOFF_NEXT_AGENT.md`. So the prior handoff's "push 770cb0a"
  task is moot: that commit is already an ancestor of `origin/main`, and the
  workflow file it introduced is gone. The workflow-based core-only check is
  not live and cannot be made live by this automation.
- The core-only CI idea is therefore superseded by the committed test added
  this session.

## Approaches that failed

- **Pushing a workflow file** (`.github/workflows/core-only-tests.yml`):
  `git push origin main` was rejected with `refusing to allow a GitHub App to
  create or update workflow ... without workflows permission`. Retried across
  multiple sessions; deterministic blocker, not transient. Do NOT retry
  pushing workflow changes unchanged — the GitHub App token lacks the
  `workflows` scope and this is a safety boundary, not a code defect.
- Treating the prior handoff at face value: it described a workflow that did
  not exist on disk (and later, a commit that was already pushed). Always
  verify against `git`/`ls` rather than trusting the handoff text.

## One precise next task

Commit `tests/test_core_only_imports.py` with a clear message (e.g. "Add
core-only import regression test") and push it to `origin/main`. Non-workflow
file pushes have succeeded before (e.g. `b1bbda5` is on `origin/main`), so
this should persist where the workflow could not.

Constraints/evidence:
- File to commit: `tests/test_core_only_imports.py` (only untracked change;
  `git status` shows nothing else). Do not touch `.github/workflows/`.
- Verify before/after: `python -m pytest tests/test_core_only_imports.py -q`
  (expect 1 passed) and `python -m ruff/black/mypy` on the file (expect
  clean).
- Optional follow-up (only if the commit lands cleanly): add the *inverse*
  direction — a companion assertion that the previously skip-marked
  matplotlib/skopt README commands actually run (exit 0) when the extras ARE
  installed — to lock both directions of the invariant. See
  `tests/test_readme_cli_commands.py` for the existing skip logic to mirror.

(End of file)