## What changed (this session)

- Added a separate CI workflow `.github/workflows/slow-tests.yml` that runs `pytest -m slow` (the slow smoke/subprocess suite) on push to `main`, pull requests, a daily schedule, and manual dispatch.
- Did NOT modify `.github/workflows/main.yml` (the Kilo controller) and did NOT enable `network` tests anywhere.
- The new workflow installs `requirements.txt` plus `.[dev]` and runs `pytest -m slow` with a 30-minute timeout on `ubuntu-latest` / Python 3.10.

## What was actually verified (evidence)

- `.github/workflows/slow-tests.yml` parses as valid YAML; contains a single `slow` job; contains no `network` marker.
- `pytest -m slow -q`: **136 passed, 0 failed**, EXIT_CODE=0, duration 428.87s (3695 fast/default tests deselected).
- Quality gates unaffected (no Python source changed).

## What remains unresolved

- The new workflow file is **uncommitted** (`M`? actually untracked: `.github/workflows/slow-tests.yml`). Per the no-commit-unless-asked rule it was left in the working tree; commit it if a checkpoint is required.
- Network tests (`-m network`) still not run; require external APIs and cannot run offline.

## Failed approaches (do not repeat unchanged)

- None new this session.

## One precise next task

Commit `.github/workflows/slow-tests.yml` (single new file, small and isolated) if the workflow requires a checkpoint, then the slow-suite CI job is complete. No further implementation needed for this task.

## Environment (unchanged)

Python 3.14.4, pandas 3.1.1, numpy 2.5.4, pytest 9.2.0. `ruff` 0.17.5, `mypy` 2.4.1, `black` 26.10.1, `matplotlib` 3.11.2, scikit-optimize 0.10.2 installed (prefix with `export PATH="$HOME/.local/bin:$PATH"`).
