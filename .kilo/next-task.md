# Next Task

## Repository state (verified this session)

All checks clean:
- `python -m ruff check .` → All checks passed.
- `python -m black --check .` → 141 files unchanged.
- `python -m mypy quant_trading/` → Success: no issues found in 37 source files.
- `python -m pytest tests/test_cli.py -q` → 172 passed.
- Full suite previously reported 2847 passed, 15 skipped, 131 deselected.

## Completed audit (this session)

Audited all user-facing analysis flags for the "parsed/set but not forwarded"
pattern across single-strategy, walk-forward, and combined modes, plus every
engine consuming `config.backtest.*`:

- Combined mode regime/monte-carlo/trade-analysis outlets (examples/cli.py:2392-2411): all fields forwarded; regime detector consumes no `risk_free_rate`.
- Single-strategy outlets (cli.py:2216-2238): all forwarded.
- Walk-forward outlet (cli.py:1859): `risk_free_rate` forwarded.
- Engine (quant_trading/backtest/engine.py:737): `risk_free_rate` read from config, populated from `--risk-free-rate` at cli.py:1336.
- End-to-end offline combined run with `--regime --monte-carlo --trade-analysis --risk-free-rate` exited 0 with no traceback.

Result: no forwarding gap found; no code changes made. Working tree clean at HEAD 6b5501d.

## One precise next task

None — this task is complete. Select a new bounded, high-value task only when one is identified; do not re-audit this area without a concrete new symptom.
