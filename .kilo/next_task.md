# Next Task: Push restored CI workflow and verify GitHub Actions

## Status

LOCAL GREEN - `.github/workflows/ci.yml` restored and committed locally as `8dda18f`. Push to origin/main still blocked by missing `workflows` permission on the GitHub App token (same blocker as prior handoff).

## What changed

- Restored `.github/workflows/ci.yml` (from 0f85f1c) and committed as `8dda18f`.
- Local verification: ruff OK, black OK (61 files unchanged), mypy Success (36 files), pytest 1096 passed, 1 skipped.

## What remains unresolved

Push to origin/main blocked: token lacks `workflows` scope. Need credentials/token with `workflows` permission, or grant the GitHub App `workflows` permission.

## Next precise task

Obtain credentials with `workflows` scope, push commit `8dda18f` to origin/main, confirm GitHub Actions CI run succeeds. If a job fails, fix with smallest change and re-verify locally before re-pushing.

Constraints: do not weaken CI checks; preserve green baseline. Keep local commits intact.
