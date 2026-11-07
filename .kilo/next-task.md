# Next Task

## Repository state (verified this session)

- `python -m pytest -q` (full suite) → **2898 passed, 1 skipped, 131 deselected**.
- `python -m pytest tests/test_example_scripts_run.py -q` → 52 passed.
- `python -m ruff check .` → All checks passed.
- `python -m black --check .` → 141 files would be left unchanged.
- `python -m mypy quant_trading/` → Success: no issues found in 37 source files.
- `git status` clean; `git diff HEAD` empty after commit.

## Completed this session

Fixed a real, pre-existing regression that the prior handoff incorrectly reported as
"nothing to do, repo is green":

- `examples/run_rsi.py` had its `RSIStrategy` import deleted, leaving a stray
  `# import removed` comment. The documented invocation `python examples/run_rsi.py`
  crashed with `NameError: name 'RSIStrategy' is not defined`, failing
  `tests/test_example_scripts_run.py::test_example_script_runs_documented_invocation[run_rsi.py]`.
- Restored `from quant_trading.strategies.examples import RSIStrategy`, matching the
  import pattern used by every other `examples/run_*.py` script.
- Lesson: the prior handoff asserted the suite was green without re-running it. The
  actual baseline on arrival was 2897 passed, **1 failed**. Always re-run checks.

## One precise next task

No code changes are required; the repository is green and committed. Any future task
must come from outside this fix — there are no outstanding TODO/FIXME markers in
`quant_trading/` or `examples/`, and all green checks pass.