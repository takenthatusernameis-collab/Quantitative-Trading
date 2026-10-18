# Next Task: Push restored CI workflow and verify GitHub Actions

## Status

BLOCKED - Push to origin/main rejected: GitHub App token lacks `workflows` permission.

## What changed

- Restored `.github/workflows/ci.yml` (from history commit 8dda18f) and committed locally as `9b272db` ("Restore CI workflow (ci.yml)").
- ci.yml is present in the working tree and committed locally, but NOT pushed to origin/main.
- Local verification (before and after the change): ruff OK, black OK (61 files unchanged), mypy Success (36 files), pytest 1096 passed, 1 skipped. ci.yml YAML parses valid.

## What remains unresolved

Push to origin/main blocked: GitHub App cannot create/update `.github/workflows/ci.yml` without the `workflows` permission.

Evidence:
- `git push origin main` → `remote: refusing to allow a GitHub App to create or update workflow .github/workflows/ci.yml without workflows permission` (remote rejected)
- GH API `repos/{owner}/{repo}` permissions: `{"admin":false,"maintain":false,"push":false,"triage":false,"pull":false}`
- ci.yml absent from origin/main tree (removed in commit 6caec0f for the same reason; 8dda18f is an ancestor that added it but was reverted).

## Failed approaches (do not repeat unchanged)

- Pushing ci.yml to origin/main — rejected twice (this session and prior handoff) for the identical missing-`workflows`-permission reason. Same underlying blocker; do not retry unchanged.

## Next precise task

Grant the GitHub App the `workflows` permission on this repo (or obtain a token/personal access token with `push` + `workflows` scope), then push local commit `9b272db` to origin/main and confirm the GitHub Actions CI run (ruff, black, mypy, pytest) succeeds. If a job fails, fix with the smallest change, re-verify locally, and re-push.

Constraints: do not weaken CI checks; preserve green baseline; keep local commit 9b272db intact until pushed.
