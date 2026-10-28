# Next Task

## Repository state

Checks: `python -m pytest -q` → 2321 passed, 44 skipped, 2 failed (the 2 failures are pre-existing on HEAD: `test_default_args` asserts `args.provider is None` but `--provider` defaults to `"yfinance"`, and `test_the_help_text_renders` asserts `"0.02 for 2%"` which never existed in `cli.py`; neither was introduced or worsened this session). `python -m ruff check .` → clean. `python -m black --check quant_trading tests examples` → clean (127 files unchanged). `python -m mypy quant_trading tests examples` → clean, 0 errors across 127 source files. 44 skips are network-dependent yfinance/Alpha Vantage tests (expected offline).

## What changed (this session)

- Fixed the broken lint baseline: removed a bare `try/except SystemExit: raise` (ruff TRY203/F841), added a `BLE001` noqa to the intentional broad `except Exception`, applied black formatting. `ruff check .` and `black --check` now pass (they were failing before this session with the installed tooling).
- Registered 31 CLI arguments the parser was missing but the README documents and the code references (`--strategy`, `--objective`, `--optimize`, `--regime`, `--trade-analysis`, `--walk-forward`, `--output`, `--monte-carlo`, etc.), plus every strategy parameter from `CLI_ARG_DEFAULTS`. This resolved ~106 of the ~108 pre-existing test failures.
- Fixed `quant_trading/regime/detector.py` so a `None` regime threshold is treated like `<= 0` (derived from the data) instead of crashing with a `TypeError`.
- Adjusted defaults to match the `tests/test_cli.py` contract (`--regime-vol-threshold`/`--regime-return-threshold` → `0.0`, `--mc-seed` → `None`).

## What was actually verified

- `python -m ruff check .` → All checks passed.
- `python -m black --check quant_trading tests examples` → clean.
- `python -m mypy quant_trading tests examples` → clean, 0 errors.
- `python -m pytest -q` → 2321 passed, 44 skipped, 2 failed (both pre-existing on HEAD).
- `python -m pytest tests/test_readme_cli.py tests/test_readme_cli_commands.py -q` → all pass.

## What remains unresolved

- 2 pre-existing `tests/test_cli.py` failures (fail on HEAD; out of scope for this session).
- 44 network-dependent tests skipped offline.

## Approaches that failed and why

- None.

## One precise next task

- Keep the full suite green on any change. The only true to-do is the 2 pre-existing `test_cli.py` failures (`provider` default, `--help` text), which fail on HEAD and are unrelated to this session's work — decide whether to take them on; otherwise nothing remains.
- Constraints: keep `ruff`, `black`, `mypy` clean for changed files; full suite green (modulo the 2 pre-existing + 44 network skips); do NOT commit unless explicitly asked; do not disable tests to hide failures.
