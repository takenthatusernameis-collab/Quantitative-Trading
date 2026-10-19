# Next Task

CI workflow `.github/workflows/ci.yml` created locally (commit 0de2c13) but push rejected: GitHub App token lacks `workflows` permission ("refusing to allow a GitHub App to create or update workflow ... without workflows permission"). Workflows are maintainer-managed.

Repo state: ruff/black/mypy/pytest all green; 100% statement coverage.

Next precise task: maintainer must grant `workflows` permission (or push ci.yml manually). Until then no further code work required; do not retry identical push.
