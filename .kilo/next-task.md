# Next Task

## Repository state (verified this session)

All checks clean:
- `python -m ruff check .` → All checks passed.
- `python -m black --check .` → 141 files unchanged.
- `python -m mypy quant_trading/` → Success: no issues found in 37 source files.
- `python -m pytest tests/test_cli.py -q` → 172 passed.
- `python -m pytest tests/test_optimization.py -q` → 108 passed, 13 skipped.
- `python -m pytest tests/test_readme_cli.py tests/test_readme_cli_commands.py -q`
  → 85 passed, 3 deselected.
- Full suite previously reported 2860 passed, 131 deselected.

## One precise next task

The walk-forward `risk_free_rate` gap and the combined-mode Monte Carlo
`risk_free_rate` gap are both closed. Audit the remaining user-facing analysis
flags for the same "parsed/set but not forwarded" pattern — specifically the
regime and trade-analysis outlets in combined mode and any other engine that
consumes `config.backtest.*` — and verify any candidate end-to-end under the
mocked-network harness (`--offline`) before changing. Keep changes minimal and
reversible; do not modify tests to make them pass. Any newly documented flag
must be a real parser flag and its command must exit 0 (or 1 for documented
error cases) with no traceback.