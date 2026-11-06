# Next Task

## Repository state (post-cleanup)

All checks clean:
- `pytest -q` → **2860 passed, 131 deselected** (slow/network deselected by default).
- `python -m ruff check .` → All checks passed.
- `python -m black --check .` → 141 files unchanged.
- `python -m mypy quant_trading/` → Success: no issues found in 37 source files.
- Full coverage: **100%** across all 37 modules (6993 stmts, 0 miss, 2382 branches, 0 partial).

## What changed (this session)

Closed a genuine user-facing gap: `WalkForwardOptimizer.step_size` was a
documented constructor parameter (with its own test,
`test_walk_forward_step_size_override`) but had no CLI flag, so users could
not control the step between walk-forward windows from the command line.
Added `--wf-step-size` end to end.

Files touched (logic + docs + test-mirror only):
- `examples/cli.py`: new `--wf-step-size` flag (default `None` → library
  default `1.0`), validation rejecting values `<= 0`, printed in the
  walk-forward summary, forwarded to `WalkForwardOptimizer(step_size=...)`,
  and serialized as `step_size` in the JSON output.
- `README.md`: documented `--wf-step-size` in the "Walk-Forward Optimization"
  section with a runnable command, and added an error-reporting example
  (`--wf-step-size 0` → exit 1, one-line message) to the "Error Reporting"
  section.
- `tests/test_readme_cli_commands.py`: registered the new error example in
  `_expects_failure` so the auto-extracted README command suite exercises it.
- `tests/test_cli.py`: added `wf_step_size: None` to the `TestSaveStrategyConfig`
  namespace mirror (the helper builds a hand-rolled `argparse.Namespace` that
  must match the parser's attributes).

## What was verified (this session)

- `python -m pytest tests/test_readme_cli.py tests/test_readme_cli_commands.py
  tests/test_optimization.py -q` → 206 passed, 3 deselected.
- `python -m pytest -q` → 2860 passed, 131 deselected in 112.48s.
- `python -m pytest --cov=quant_trading --cov-report=term-missing -q` →
  6993 stmts, 0 miss, 2382 branches, 0 partial → 100% coverage.
- `python -m ruff check .` → All checks passed.
- `python -m black --check .` → 141 files unchanged.
- `python -m mypy quant_trading/` → Success: no issues found in 37 source files.
- Manual end-to-end: `--walk-forward --wf-step-size 0.5` prints
  `Step size: 0.50` and completes exit 0; `--wf-step-size 0` exits 1 with
  `Error: invalid --wf-step-size: the value must be greater than 0 (got 0.0)`
  and no traceback.
- `.github/scripts/test_kilo_progress.sh` → smoke + non-fatal state-write OK;
  `bash -n` clean on `kilo-controller.sh`, `kilo-progress.sh`,
  `test_kilo_progress.sh`.

## What remains unresolved

- Nothing functional. The tree is green on pytest, ruff, black, mypy, coverage,
  and the Kilo workflow audit scripts. The change is left unstaged for the
  controller to checkpoint (never commit unless explicitly asked).

## Approaches that failed and why

- The first full-suite run surfaced one regression: `tests/test_cli.py`
  `TestSaveStrategyConfig.test_walk_forward_saves_last_window_params_config`
  failed with `AttributeError: 'Namespace' object has no attribute 'wf_step_size'`.
  The test builds a hand-rolled namespace (not the real parser), so it had to
  be mirrored explicitly. Fixed by adding the attribute to the helper's base
  dict; this is the same pattern already used for `wf_windows`, `wf_train_size`,
  etc. Lesson: when adding a parser attribute, check every hand-rolled
  `argparse.Namespace` mirror in the tests, not just the parser itself.
- No approach was retried: the fix was deterministic and the rerun was green.

## One precise next task

- If another session is requested, first re-run `pytest -q`, `python -m ruff check .`,
  `python -m black --check .`, `python -m mypy quant_trading/`, and
  `python -m pytest --cov=quant_trading --cov-report=term-missing -q` to confirm
  the tree is still green, then select a new bounded task.
- Candidate directions: look outside the walk-forward surface for the next
  under-documented user-facing flag or behavior gap (e.g. other optimizer,
  regime, or trade-analysis parameters that exist in code but not in the
  README); verify any candidate end-to-end under the mocked-network harness
  before changing.
- Constraints: Do not modify tests to make them pass. Keep changes minimal and
  reversible. The `tests/test_readme_cli.py` and `tests/test_readme_cli_commands.py`
  guards enforce bidirectional consistency between the README CLI section and
  the live parser; any newly documented flag must be a real parser flag and
  its command must exit 0 (or 1 for documented error cases) with no traceback.

(End of file - total 108 lines)