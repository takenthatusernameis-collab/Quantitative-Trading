## What changed (this session)

- No production or test code changed. The prior session's assigned work is **already complete**:
  - `tests/test_core_only_imports.py` is committed in `81dd0e2` and pushed (`HEAD == origin/main`). It locks the core-only import invariant (core import + deterministic backtest succeed; chart helpers raise clean `ImportError` when matplotlib/skopt are absent).
  - `tests/test_optional_extras_readme_commands.py` is also committed and tracked. It locks the inverse direction (README chart/bayesian CLI commands run exit 0 when matplotlib/skopt are present), skip-marked when the extras are absent.
- Corrected this handoff file (it previously described `test_core_only_imports.py` as untracked and its commit/push as pending; both are already done).

## What was actually verified (evidence, this session)

- `pip install -r requirements.txt` succeeded; core deps (pandas/numpy/PyYAML/requests) importable.
- `python3 -m pytest tests/test_core_only_imports.py tests/test_optional_extras_readme_commands.py -q` → **1 passed, 2 skipped** in 0.73s.
  - core-only test passes (extras absent here).
  - the two inverse-direction tests correctly skip because matplotlib/skopt are not installed in this env.
- `python3 -m ruff check` on both files → **All checks passed**.
- `python3 -m black --check` on both files → **2 files would be left unchanged**.
- `git status` clean; `git rev-parse HEAD == origin/main == 81dd0e2`.

Note: the full default suite (`4057 passed`) was verified in the prior session in a fully-provisioned env; this session's env lacks the optional extras, so the inverse-direction tests skip rather than run here.

## Repository state / important context

- `HEAD == origin/main == 81dd0e27666fb895005783c8abdc6553b63335bc`; working tree clean.
- Both invariant tests are committed and pushed. Do NOT re-commit or re-push them.
- Do NOT touch `.github/workflows/` — workflow pushes are blocked by the GitHub App token (lacks `workflows` scope; deterministic blocker, see prior handoff).
- pytest/ruff/black console scripts are not on PATH in this env; use `python3 -m pytest/ruff/black`.

## Approaches that failed

- Pushing `.github/workflows/core-only-tests.yml`: rejected (`workflows` permission). Do not retry unchanged. Superseded by the committed tests.

## One precise next task

Run the full verification in an environment where the optional extras ARE installed, so the inverse-direction test actually executes (exit 0) instead of skipping — this completes "lock both directions of the invariant":

```
pip install -e ".[dev]"      # installs matplotlib + scikit-optimize
python3 -m pytest tests/test_core_only_imports.py tests/test_optional_extras_readme_commands.py -q
# expect: core-only test passes; both inverse tests run and pass (no skips)
python3 -m ruff check tests/test_core_only_imports.py tests/test_optional_extras_readme_commands.py
python3 -m black --check tests/test_core_only_imports.py tests/test_optional_extras_readme_commands.py
```

Constraint: only proceed if `matplotlib` and `skopt` are importable; otherwise the inverse tests legitimately skip. Once this passes, the assigned work is fully done and there is no remaining task.

(End of file)
