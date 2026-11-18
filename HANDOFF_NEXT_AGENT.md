## What changed (this session)

- The prior session's handoff claimed a `.github/workflows/core-only-tests.yml`
  file existed, but it did **not** exist in the repository (the controller's
  `git restore --source="$WORKFLOW_BASE_SHA" --staged --worktree -- .github/workflows`
  + `git clean -fd -- .github/workflows` had removed it, and the only commit
  touched `HANDOFF_NEXT_AGENT.md`). This session created the file for real.
- New file `.github/workflows/core-only-tests.yml`:
  - Triggers on push to `main`, pull requests, and `workflow_dispatch`.
  - Sets up Python 3.11, installs only `pip install -e .` (no `[reporting]` /
    `[bayesian]` extras) plus `pytest`/`pytest-cov`.
  - Asserts `matplotlib` and `skopt` are genuinely absent before running tests.
  - Runs `pytest -q -rs` and fails the job on any non-skip/deselect outcome.
- No production code changed; no test files changed.

## What was actually verified (evidence)

- Reproduced the core-only environment locally *before* writing the workflow:
  - `python -m venv /tmp/coreonly-venv`
  - `pip install -e .` (core only) + `pytest`/`pytest-cov`
  - Confirmed `import matplotlib` and `import skopt` both raise ModuleNotFoundError.
  - `pytest -q` -> **3952 passed, 104 skipped, 142 deselected**, exit 0.
- Baseline with all extras installed (unchanged): `pytest -q` -> **4056 passed,
  142 deselected** (matches prior session).
- Workflow YAML parses cleanly (`yaml.safe_load` -> OK; `on:` key handled as
  the standard PyYAML `True` alias for GitHub Actions).
- Existing CI audit workflow is untouched; `.github/scripts/kilo-controller.sh`,
  `.github/scripts/kilo-progress.sh`, and `.github/scripts/test_kilo_progress.sh`
  all pass `bash -n`; `bash .github/scripts/test_kilo_progress.sh` -> OK.
- Focused test run: `pytest tests/test_readme_cli_commands.py -q` ->
  **121 passed, 3 deselected**, exit 0.
- `ruff check .` -> All checks passed (the YAML file is not Python, so it is
  not linted by ruff; `black`/`ruff` on the YAML file correctly refuse to parse
  it — that is expected and not a defect).
- Staged whitespace check: `git diff --cached --check` -> clean.

## What remains unresolved / not verified

- The CI job has not been executed in GitHub Actions (this sandbox has no
  runner); the local venv reproduction is the evidence that the check is sound.
- `--combined` commands remain marked `slow` (deselected by default).
- Network-marked tests deselected as usual.

## Approaches that failed

- Treating the prior handoff's claim of an existing workflow file at face
  value: inspecting the repo showed the file was never committed. The prior
  session's commit only modified `HANDOFF_NEXT_AGENT.md`. This session created
  the file from scratch after local reproduction confirmed the invariant.

## One precise next task

The core-only CI check is written, staged, and locally validated. If continuing,
pick one of:

1. Commit and push the staged `.github/workflows/core-only-tests.yml` so the
   check is live, then optionally trigger it manually via `workflow_dispatch`
   to confirm it passes on real CI runners. Relevant file:
   `.github/workflows/core-only-tests.yml`.

2. Add the inverse matrix leg: a job that installs `pip install -e .[reporting,
   bayesian]` and asserts the previously-skip-marked README commands now run
   (exit 0) instead of being skipped, locking both directions of the invariant.
   Relevant files: `.github/workflows/core-only-tests.yml` +
   `tests/test_readme_cli_commands.py`.

(End of file - total 66 lines)