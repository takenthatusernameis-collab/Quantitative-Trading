## What changed (this session)

- Restored `.github/workflows/slow-tests.yml` (deleted in `1781d45`) to run the slow suite (`pytest -m slow`) on push/PR to `main`, daily schedule (03:00 UTC), and manual dispatch; Python 3.10 on `ubuntu-latest`, installs `requirements.txt` + `.[dev]`, 30-minute timeout. No `network` tests enabled.
- No Python/source logic changes were made.

## What was actually verified (evidence)

- `.github/workflows/slow-tests.yml` parses as valid YAML (`yaml_ok`) and contains no `network` marker.
- `tests/test_risk_attribution.py`: `28 passed in 1.04s` (focused run).
- `git status`: clean except restored `.github/workflows/slow-tests.yml` and this handoff update (uncommitted per no-commit-unless-asked rule).

## What remains unresolved

- Network tests (`-m network`) remain unrun in CI/offline; require external APIs/credentials.
- Restored workflow and handoff are uncommitted in the working tree.

## Failed approaches (do not repeat unchanged)

- None this session.

## One precise next task

Checkpoint/commit `.github/workflows/slow-tests.yml` and `HANDOFF_NEXT_AGENT.md` if persistence is required, then select a new bounded, high-value improvement by inspecting recent `quant_trading` changes (e.g. risk attribution APIs in `quant_trading/risk/metrics.py` and `tests/test_risk_attribution.py`) for gaps in validation, docs/examples, or integration coverage—and implement/verify the smallest safe addition.

## Environment (unchanged)

Python 3.14.4, pandas 3.1.1, numpy 2.5.4, pytest 9.2.0. `ruff` 0.17.5, `mypy` 2.4.1, `black` 26.10.1, `matplotlib` 3.11.2, scikit-optimize 0.10.2 installed (prefix with `export PATH="$HOME/.local/bin:$PATH"`).
