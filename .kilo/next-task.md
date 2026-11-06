# Next Task

## Repository state (verified this session)

All checks clean:
- `python -m ruff check .` → All checks passed.
- `python -m black --check .` → 141 files unchanged.
- `python -m mypy quant_trading/` → Success: no issues found in 37 source files.
- `python -m pytest tests/test_cli.py -q` → 170 passed.
- Full suite previously reported 2860 passed, 131 deselected.

## One precise next task

Look outside the walk-forward surface for the next under-documented user-facing flag or behavior gap (e.g. other optimizer, regime, or trade-analysis parameters that exist in code but not in the README); verify any candidate end-to-end under the mocked-network harness (`--offline`) before changing. Keep changes minimal and reversible; do not modify tests to make them pass. Any newly documented flag must be a real parser flag and its command must exit 0 (or 1 for documented error cases) with no traceback.
