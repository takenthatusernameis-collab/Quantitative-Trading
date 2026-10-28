# Next Task

## Repository state

Checks: `python -m ruff check .` → clean. `python -m black --check quant_trading tests examples` → clean (131 files unchanged). `python -m mypy quant_trading tests examples` → clean, 0 errors across 131 source files. `python -m pytest tests/test_cli.py tests/test_readme_cli.py tests/test_readme_cli_commands.py tests/test_readme.py -q` → 205 passed, 44 skipped (network).

## What changed (this session)

Fixed `examples/cli.py`: `_create_parser()` only defined `--ma-fast-range`/`--ma-slow-range`, but `create_param_grid()` reads ~20 `args.*_range` attributes (rsi, bb, macd, supertrend, donchian, aroon, keltner, stoch, ichimoku, sar, atr). So `--optimize`/`--walk-forward` crashed with `AttributeError` for every non-MA strategy. Added all 20 missing `--*-range` flags and fixed `%%K`/`%%D` help-text escaping. Added `tests/test_cli.py::test_parser_accepts_every_range_flag_create_param_grid_references` regression test.

## What was actually verified

- Offline `--optimize` runs end-to-end for `rsi`, `bb`, `macd`; `--walk-forward` for `rsi` (previously crashed).
- ruff/black/mypy all clean; 205 CLI/readme tests passed, 44 network skips.

## What remains unresolved

- Full `pytest -q` could not finish (one network test hangs, pre-existing, unrelated to this change).
- 55 network tests skipped offline.

## Approaches that failed and why

- None.

## One precise next task

- Keep baseline green: run ruff/black/mypy and `python -m pytest tests/test_cli.py tests/test_readme_cli_commands.py -q` before/after any change; fix any regression with the smallest reversible change.
- Constraints: do NOT commit unless explicitly asked; do not disable tests; preserve working baseline; exclude secrets/env/cache artifacts.
