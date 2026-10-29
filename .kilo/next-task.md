# Next Task

## Repository state

Checks: `python -m ruff check .` → clean. `python -m black --check quant_trading tests examples` → clean except `quant_trading/strategies/examples.py` (pre-existing, unrelated). `python -m mypy quant_trading tests examples` → clean, 0 errors across 131 source files. `python -m pytest tests/test_cli.py tests/test_readme_cli_commands.py -q` → 192 passed, 44 skipped (network).

## What changed (this session)

Converted the `Examples:` blocks in `quant_trading/portfolio/portfolio.py` to executable `>>>` doctests (module-level, `Holding`, `Portfolio`), following the instantiation/attribute-check style. Verified: doctests pass (3), ruff/black/mypy clean, `pytest quant_trading/portfolio tests/test_portfolio.py -q` → 72 passed.

## What remains unresolved

- `quant_trading/strategies/examples.py` is not black-clean (pre-existing, unrelated to this change).
- Full `pytest -q` could not finish (one network test hangs, pre-existing, unrelated to this change).
- 55 network tests skipped offline.
- Many modules still lack `>>>` doctests (e.g. `quant_trading/risk/manager.py`, `quant_trading/backtest/trade_analysis.py`, `quant_trading/monte_carlo/simulator.py`, `quant_trading/optimization/*`).

## Approaches that failed and why

- None.

## One precise next task

- Convert the `Examples:` blocks in another module lacking `>>>` doctests (e.g. `quant_trading/risk/manager.py` or `quant_trading/monte_carlo/simulator.py`) to executable `>>>` doctests, then run focused doctests, ruff, black, mypy.
- Constraints: do NOT commit unless explicitly asked; do not disable tests; preserve working baseline; exclude secrets/env/cache artifacts.

(End of file - total 28 lines)