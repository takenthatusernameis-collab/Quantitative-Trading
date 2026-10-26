# Next Task

## Repository state

Checks: `python -m pytest -q` (2203 passed, 0 failures), `python -m ruff check .` (clean), `python -m mypy quant_trading tests examples` (clean), `python -m black --check quant_trading tests examples` (clean). Baseline is green.

## Completed this session

Fixed a contract-drift gap: the README's "Parameter Optimization" Features bullet omitted Bayesian optimization even though `BayesianOptimizer` is implemented, exported, CLI-wired, and tested. Updated `README.md:8` and added a regression guard `test_readme_features_list_advertises_all_optimizers` in `tests/test_repository_integrity.py`.

## What was actually verified

- `python -m pytest tests/test_repository_integrity.py tests/test_readme.py -q` → 14 passed, 0 failures.
- `python -m pytest -q` (full suite) → 2203 passed, 0 failures in ~157s.
- `python -m ruff check .` → All checks passed.
- `python -m mypy quant_trading tests examples` → Success, no issues found in 101 source files.
- `python -m black --check quant_trading tests examples` → All checks passed.
- Negative test: reverting the README bullet to the old wording makes the new guard fail, confirming it is meaningful.

## What remains unresolved

- None blocking. The repository is green across tests, lint, type checks, and formatting.
- Pre-existing (not introduced by this change): `black --check README.md` fails because black is not configured to format markdown; it fails identically on the clean baseline.

## Approaches that failed

- A literal "every CLI flag is documented in the README" test was considered and rejected: the README uses prose patterns (`--*-range`, `--*-period`) rather than enumerating all 111 flags, so such a test would produce ~100 false positives. The bounded Features-list guard is the high-signal version of that idea.

## One precise next task

No assigned task remains. Baseline is green. Changes: 2 files (`README.md`, `tests/test_repository_integrity.py`). Do NOT commit unless explicitly asked.

(End of file - total 37 lines)