## What changed (this session)

- Recreated `.github/workflows/core-only-tests.yml` for real (the prior
  handoff's claim that it existed/staged was incorrect; the file was never
  committed). The file:
  - Triggers on push to `main`, pull requests, and `workflow_dispatch`.
  - Sets up Python 3.11, installs only `pip install -e .` (no `[reporting]`
    / `[bayesian]` extras) plus `pytest`/`pytest-cov`.
  - Asserts `matplotlib` and `skopt` are genuinely absent before running tests
    (fails the job if either imports).
  - Runs `pytest -q -rs` (fails on any non-skip/deselect outcome).
- Committed locally as `770cb0a` ("Add core-only CI workflow", 1 file,
  42 insertions). Working tree is clean.
- No production code or test files changed.

## What was actually verified (evidence)

- `.github/workflows/core-only-tests.yml` parses cleanly via both
  `ruby -e 'require "yaml"; YAML.load_file(...)'` and Python `yaml.safe_load`.
- Staged whitespace check `git diff --cached --check` -> clean (before commit).
- Local baseline (extras present, matching production env):
  `pytest -q -m "not slow and not network"` -> **4056 passed, 142 deselected**,
  exit 0 (matches prior session's "all extras" baseline).
- Note: in core-only CI `matplotlib`/`skopt` will be absent, so the
  matplotlib/skopt-dependent README commands skip instead of pass; this is the
  intended invariant (core-only path must not require optional extras).

## What remains unresolved / not verified

- **The commit has NOT been pushed.** `git push origin main` was rejected:
  `refusing to allow a GitHub App to create or update workflow
  .github/workflows/core-only-tests.yml without workflows permission`.
  The local commit `770cb0a` is 1 commit ahead of `origin/main`.
- The CI job has not run on GitHub Actions (no runner in this sandbox); local
  baseline + YAML parse are the evidence the check is sound.
- `--combined` commands remain `slow` (deselected by default).
- Network-marked tests deselected as usual.

## Approaches that failed

- `git push origin main`: rejected by the remote because the authenticating
  GitHub App lacks the `workflows` permission required to create/update a
  workflow file. Do NOT retry the same push unchanged — it will fail again
  until a token/PAT with `workflows` scope is used or the app permission is
  added.

## One precise next task

Push the local commit `770cb0a` to `origin/main` so the core-only check is
live, then optionally trigger it manually via `workflow_dispatch` to confirm it
passes on real CI runners.

Constraints/evidence:
- Commit: `770cb0a Add core-only CI workflow` (file:
  `.github/workflows/core-only-tests.yml`).
- Push requires a credential with the `workflows` permission/scope; the
  current GitHub App token does not have it. Obtain such a credential or have
  the app permission added before pushing.
- Do not alter the workflow content to work around the permission rejection;
  the permission is a safety boundary, not a code defect.
- Once pushed, verify the run succeeds via the Actions tab / `workflow_dispatch`.

(End of file)
