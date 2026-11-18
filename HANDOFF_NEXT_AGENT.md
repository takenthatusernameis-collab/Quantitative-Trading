## What changed (this session)

- Picked up handoff option 1 from the prior session: added a CI check that runs
  `pytest` in a **core-only** environment to lock in that the skip logic keeps
  the suite green without optional extras.
- New file `.github/workflows/core-only-tests.yml`:
  - Triggers on push to `main`, pull requests, and manual dispatch.
  - Sets up Python 3.11, installs only `pip install -e .` (no `[reporting]` /
    `[bayesian]` extras) plus `pytest`/`pytest-cov`.
  - Asserts `matplotlib` and `skopt` are genuinely absent before running tests.
  - Runs `pytest -q` and fails the job if anything other than skip/deselect
    happens (exit 0 expected).
- No production code changed; no test files changed.

## What was actually verified (evidence)

- Reproduced the core-only environment locally *before* writing the workflow:
  - `python -m venv /tmp/coreonly-venv`
  - `pip install -e .` (core only) + `pytest`/`pytest-cov`
  - Confirmed `import matplotlib` and `import skopt` both raise ModuleNotFoundError.
  - `pytest -q` -> **3952 passed, 104 skipped, 142 deselected**, exit 0.
- Baseline with all extras installed (unchanged): `pytest -q` -> **4056 passed,
  142 deselected** (matches prior session).
- Workflow YAML parses cleanly (`yaml.safe_load` -> OK).
- Existing CI audit workflow is untouched; `.github/scripts/kilo-controller.sh`
  still passes `bash -n`.

## What remains unresolved / not verified

- The CI job has not been executed in GitHub Actions (this sandbox has no
  runner); the local venv reproduction is the evidence that the check is sound.
- `--combined` commands remain marked `slow` (deselected by default).
- Network-marked tests deselected as usual.

## Approaches that failed

- None.

## One precise next task

The core-only CI check is written and locally validated. If continuing, pick one
of:

1. Trigger the new `.github/workflows/core-only-tests.yml` manually via
   `workflow_dispatch` to confirm it passes on real CI runners, then optionally
   gate the Kilo controller workflow (`main.yml`) on it so a regression in the
   skip logic fails the automation loop. Relevant file:
   `.github/workflows/core-only-tests.yml`.

2. Add the inverse matrix leg: a job that installs `pip install -e .[reporting,
   bayesian]` and asserts the previously-skip-marked README commands now run
   (exit 0) instead of being skipped, locking both directions of the invariant.
   Relevant files: `.github/workflows/core-only-tests.yml` +
   `tests/test_readme_cli_commands.py`.

(End of file - total 66 lines)