## What changed (this session)

- Aligned the remaining README CLI command examples to the installed `quant-trading` console script (`examples.cli:main`): renamed the `$ python examples/cli.py ...` prefix to `$ quant-trading ...` across all 20 error/command examples (Basic Usage `--days`/`--start` guards, Data Provider `--synthetic-days`/`--synthetic-seed`, Cost/Risk `--commission`/`--risk-free-rate`/`--initial-capital`, Error Reporting strategy/config/missing-file/range/MC/walk-forward/periods-per-year/regime examples).
  - Left in place the two appropriate prose mentions: the dev-alternative note (``python examples/cli.py`` in the Basic Usage intro) and the already-aligned `--list-strategies` hint (`quant-trading ...` first, `python examples/cli.py ...` as fallback).
- `README.md`: 1 file changed, 20 insertions / 20 deletions (command-prefix rename only; no code, tests, or documented `Error:` text changed).

## What was actually verified (evidence)

- `python -m pytest tests/test_readme.py tests/test_readme_cli.py tests/test_packaging.py -q` -> **27 passed** (README↔parser/doc guards, registry, packaging metadata).
- `python -m black --check .` -> **160 files would be left unchanged**.
- `python -m ruff check .` -> **All checks passed**.
- `python -m mypy .` -> **Success: no issues found in 160 source files**.
- `quant_trading` imports successfully (`quant_trading.__version__ == 0.1.0`).
- Spot-ran every renamed error example via `python examples/cli.py` (identical `main()` to the `quant-trading` console script); all documented `Error: ...` one-line messages match live output exactly (`--days 0`, `--synthetic-days 0`, `--commission 1.5`, `--risk-free-rate nan`, `--initial-capital nan`, `--strategy nosuchstrategy`, `--config missing.yaml`, `--ma-fast-range 5,20,0`, `--mc-simulations 0`, `--wf-step-size 0`, `--wf-windows 0`, `--periods-per-year 0`, `--regime-window 1`, `--regime-vol-threshold nan`, `--synthetic-seed -1`, `--strategy-config` bad mapping). The console script is `examples.cli:main`, so `quant-trading X` behaves identically to `python examples/cli.py X`.
- `git status --short` / `git diff --stat`: only `README.md` modified.

## What remains unresolved / not verified

- Full pytest suite not rerun (expensive; no behavioral changes, only docs).
- Data Providers section (`README.md:326-366`) uses `quant-trading` but several lines carry stray leading whitespace (e.g. lines 330-363), so the examples are not cleanly copy-pasteable inside the bash block.
- Observation (pre-existing, not caused by this edit): `README.md:736-737` documents `--config /tmp/cfg.yaml` (with `initial_capital: abc`) as erroring with `invalid config field BacktestConfig.initial_capital: expected <class 'float'>, got str ('abc')`, but a live run started a backtest instead ("Running backtest for MA_Crossover_10_30"). Investigate whether config loading should type-validate (to make docs accurate) or correct the README. Out of scope for this session.

## Approaches that failed

- None.

## One precise next task

Fix the Data Providers section indentation so every `quant-trading ...` example line is flush-left (copy-paste clean) within its bash block, keeping `quant-trading` as the primary command. After the edit run `python -m pytest tests/test_readme.py tests/test_readme_cli.py -q` and `python -m black --check .` / `python -m ruff check .` / `python -m mypy .` to confirm the README↔parser/doc guards and quality checks stay green. No code/test changes expected. (Optional follow-up: resolve the `--config /tmp/cfg.yaml` type-error discrepancy noted above.)

(End of file)
