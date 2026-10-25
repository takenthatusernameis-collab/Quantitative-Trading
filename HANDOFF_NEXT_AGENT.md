# Handoff for Next Agent

## What changed
Fixed the single-strategy `--output` JSON path in `examples/cli.py:_run_cli()`.

Root cause: when `--output` was given, the code called `result.to_json(args.output)` directly whenever the result had `to_csv`/`to_json`. `BacktestResult.to_json()` serializes `to_dict(orient="records")`, which writes a **list** `[{...}]` and omits `regime_analysis`, `monte_carlo`, `trade_analysis`, and `total_pnl`. The comprehensive `output_data` dict branch was unreachable dead code.

Change: always build the `output_data` dict (with `total_pnl`, `unrealized_pnl`, plus conditional `regime_analysis`/`monte_carlo`/`trade_analysis`) and write it via `_save_json_output`. Removed the `result.to_json()`/`result.to_csv()` shortcut.

## What was actually verified
- tests/test_cli.py: 153 passed (previously 150 passed + 3 failed).
  - `test_main_with_regime_monte_carlo_trade_analysis_output` — now passes (`regime_analysis`, `monte_carlo`, `trade_analysis`, `total_costs` present in JSON dict).
  - `test_main_regime_output_records_the_periods_per_year` — now passes (`data["regime_analysis"]["periods_per_year"] == 52`, no more `TypeError`).
  - `test_the_json_output_reconciles_the_total_return` — now passes (`total_pnl`/`unrealized_pnl` present, identity holds).
- Full test suite `tests/`: 2062 passed, 0 failures.
- `ruff check examples/cli.py`: all checks passed.
- `mypy examples/cli.py`: no new errors (the one engine.py:344 `no-any-return` note is pre-existing and untouched).

## What remains unresolved
- None from this session; all 3 pre-existing test_cli.py failures are fixed.

## One precise next task
None — the assigned task is complete. If continuing, run `git diff`/`git status` to review and consider committing; do not commit unless explicitly asked.
