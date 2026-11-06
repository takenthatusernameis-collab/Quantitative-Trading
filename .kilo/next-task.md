# Next Task

## Repository state (post-cleanup)

All checks clean:
- `pytest -q` → **2860 passed, 131 deselected** (slow/network deselected by default).
- `python -m ruff check .` → All checks passed.
- `python -m black --check .` → 141 files unchanged.
- `python -m mypy quant_trading/` → Success: no issues found in 37 source files.
- Full coverage: **100%** across all 37 modules (6993 stmts, 0 miss, 2382 branches, 0 partial).

## What changed (this session)

Fixed a deterministic regression left by the prior `QT_TEST_MAX_*`
configurability commit (53847b8): the env-var overrides were read into
locals but never wired into the cap logic, so the caps stayed hardcoded at
`25`/`5` (Bayesian) and `60` (GridSearch) regardless of the env vars.

Files touched (logic fix only, no behavior change for non-test invocations):
- `quant_trading/optimization/grid_search.py`: `random.sample(combinations, 60)`
  → `random.sample(combinations, _cap)` so `QT_TEST_MAX_GRID_COMBINATIONS` is honored.
- `quant_trading/optimization/bayesian.py`: `_n_calls_cap`/`_n_init_cap` were dead
  locals; the cap branches hardcoded `25`/`5`. Rewired to use the env vars
  (`n_calls_cap`/`n_init_cap`), so `QT_TEST_MAX_BAYESIAN_CALLS` and
  `QT_TEST_MAX_BAYESIAN_INIT` are honored.
- `tests/test_optimization.py`: added four cap tests (one per env var override)
  plus one that unsets `PYTEST_CURRENT_TEST` to cover the non-pytest branch
  (`305->313`), restoring 100% branch coverage.

## What was verified (this session)

- `python -m pytest tests/test_optimization.py -q` → 120 passed (6.05s).
- `python -m pytest -q` → 2860 passed, 131 deselected in 166.22s.
- `python -m pytest --cov=quant_trading --cov-report=term-missing -q` →
  6993 stmts, 0 miss, 2382 branches, 0 partial → 100% coverage.
- `python -m ruff check .` → All checks passed.
- `python -m black --check .` → 141 files unchanged.
- `python -m mypy quant_trading/` → Success: no issues found in 37 source files.
- `.github/scripts/test_kilo_progress.sh` → smoke + non-fatal state-write OK;
  `bash -n` clean on `kilo-controller.sh`, `kilo-progress.sh`,
  `test_kilo_progress.sh`.

## What remains unresolved

- Nothing functional. The tree is green on pytest, ruff, black, mypy, coverage,
  and the Kilo workflow audit scripts. The change is left unstaged for the
  controller to checkpoint (never commit unless explicitly asked).

## Approaches that failed and why

- Trusting the prior session's claim that the env-var configurability was
  wired in: `python -m pytest --cov=quant_trading --cov-report=term-missing -q`
  dropped coverage to 99% (6 miss, 4 partial branches) and revealed the dead
  locals in `bayesian.py` and the hardcoded `60` in `grid_search.py`. Lesson:
  run the coverage gate after any change that adds env-var reads; dead locals
  are invisible to ruff/black/mypy but obvious to coverage.
- Covering the `PYTEST_CURRENT_TEST` False branch is impossible while pytest
  itself sets the var, so the test must `monkeypatch.delenv("PYTEST_CURRENT_TEST")`
  to exercise it.

## One precise next task

- If another session is requested, first re-run `pytest -q`, `python -m ruff check .`,
  `python -m black --check .`, `python -m mypy quant_trading/`, and
  `python -m pytest --cov=quant_trading --cov-report=term-missing -q` to confirm
  the tree is still green, then select a new bounded task.
- Candidate directions: document more of the remaining undocumented but
  user-facing CLI flags (e.g. `--rsi-period`, `--macd-fast`, `--stoch-k-period`,
  `--mc-method`, `--mc-confidence`, `--mc-seed`), each verified to run
  end-to-end under the mocked-network harness; or extend CLI/README coverage
  for an under-documented feature.
- Constraints: Do not modify tests to make them pass. Keep changes minimal and
  reversible. The `tests/test_readme_cli.py` and `tests/test_readme_cli_commands.py`
  guards enforce bidirectional consistency between the README CLI section and
  the live parser; any newly documented flag must be a real parser flag and
  its command must exit 0 (or 1 for documented error cases) with no traceback.

(End of file - total 104 lines)