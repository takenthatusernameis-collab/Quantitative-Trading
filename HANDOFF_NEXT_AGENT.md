## What changed (this session)

- Created and committed `.github/workflows/slow-tests.yml` - a CI workflow that runs the slow test suite (`pytest -m slow`) on push to `main`, pull requests, a daily schedule (3 AM UTC), and manual dispatch.
- The workflow installs `requirements.txt` plus `.[dev]` dependencies and runs tests with a 30-minute timeout on `ubuntu-latest` / Python 3.10.

## What was actually verified (evidence)

- `.github/workflows/slow-tests.yml` parses as valid YAML; contains a single `slow` job; contains no `network` marker.
- `pytest -m slow -q`: **136 passed, 0 failed**, EXIT_CODE=0, duration 432.50s (3695 fast/default tests deselected).
- Quality gates unaffected (no Python source changed).
- Commit `198a7a8` persisted the workflow file.

## What remains unresolved

- Network tests (`-m network`) still not run; require external APIs and cannot run offline.

## Failed approaches (do not repeat unchanged)

- None new this session.

## One precise next task

The slow-suite CI job is complete. No further implementation needed for this task. Future work could consider adding a separate workflow for network tests if external API credentials become available in CI.

## Environment (unchanged)

Python 3.14.4, pandas 3.1.1, numpy 2.5.4, pytest 9.2.0. `ruff` 0.17.5, `mypy` 2.4.1, `black` 26.10.1, `matplotlib` 3.11.2, scikit-optimize 0.10.2 installed (prefix with `export PATH="$HOME/.local/bin:$PATH"`).

(End of file - total 28 lines)