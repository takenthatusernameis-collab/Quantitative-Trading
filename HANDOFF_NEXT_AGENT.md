## Status

Verified green on 2026-11-19. Full suite: **4156 passed, 149 deselected, 0 failed** (5m25s), with coverage still at **100% statement and branch** across `quant_trading` + `examples.cli`. `black --check`, `ruff check`, and `mypy` are clean on every changed file.

## What changed

Added a new built-in strategy, **True Strength Index (TSI)** — a standard double-smoothed momentum oscillator that was missing from the 50-strategy set. It is a real, registered, documented, tested, runnable feature (not a marker/control commit).

Files touched this session:

- `quant_trading/strategies/examples.py` — new `TrueStrengthIndexStrategy` (defaults `long_period=25`, `short_period=13`, `signal_period=13`). Computes `TSI = 100 * EMA_long(EMA_short(momentum)) / EMA_long(EMA_short(|momentum|))`, an EMA signal line, and emits buy/sell on signal-line crossovers. Zero denominators and short history yield `NaN` and are skipped. Added to `__all__`. Includes doctests for `_double_smooth` and `_calculate_tsi`.
- `quant_trading/strategies/__init__.py` — imported, exported in `__all__`, and registered as `tsi` with aliases `true_strength_index` and `tsi_indicator`.
- `examples/cli.py` — added `"tsi"` to `BUILTIN_STRATEGY_KEYS` (keeps `--list-strategies` and combined mode in sync with the registry).
- `examples/run_true_strength_index.py` — new offline deterministic synthetic-data demo (mirrors `run_fisher_transform.py`).
- `README.md` — bumped the feature bullet from 50 -> 51 registered strategies, mentioned TSI, added the registry bullet, and added a documented `python examples/run_true_strength_index.py` code block in the Example Scripts section.
- `tests/test_strategies_examples.py` — new `TestTrueStrengthIndexStrategy` (10 tests: init, all three validation errors, insufficient data, buy cross, sell cross, no cross, multi-symbol, missing close column, NaN close, all-NaN TSI from a flat series).
- `tests/test_strategy_registry_coverage.py` — docstring count 50 -> 51 and new alias assertions (`true_strength_index`, `tsi_indicator`).
- `tests/test_repository_integrity.py` — added `"tsi"` to `_STRATEGIES_WITHOUT_DEDICATED_CLI_FLAGS`.
- `tests/test_cli.py` — added `("True_Strength_Index", 12.0)` to the combined-mode mock result table.

No existing strategy behaviour was modified.

## What was actually verified

- `MPLBACKEND=Agg python -m pytest -q -p no:cacheprovider --cov --cov-report=term` -> **4156 passed, 149 deselected, 0 failed**; `examples.py` 2551 stmts / 966 branches, 100%; TOTAL 9998 stmts, 3554 branches, 100%.
- Focused: `tests/test_strategies_examples.py`, `test_strategy_registry_coverage.py`, `test_readme.py`, `test_repository_integrity.py` -> 678 passed.
- `tests/test_cli.py`, `test_example_scripts_run.py`, `test_examples_smoke.py`, `test_optional_extras_readme_commands.py` -> 415 passed, 144 deselected.
- `python -m black --check` / `python -m ruff check` / `python -m mypy` on all changed files -> clean.
- `python -m examples.cli --list-strategies` shows `tsi: TrueStrengthIndexStrategy ... (aliases: true_strength_index, tsi_indicator)`.
- `python -m examples.cli --offline --strategy tsi --symbols AAPL --days 90` -> runs, exit 0.
- `python examples/run_true_strength_index.py` -> exit 0 (Final Value $106,414.39, 53 trades).

## Failed approaches / gotchas (do not repeat)

- The repository-integrity gate requires **every** public method docstring to contain a non-empty `Examples:` doctest section. Adding `_double_smooth`/`_calculate_tsi` initially failed `test_documented_examples_are_valid` until doctests were added.
- That same gate runs mypy over `tests/`, so test helpers returning a `DataFrame` need `# type: ignore[no-any-return]` on the `return pd.DataFrame(...)`.
- Doctest expected values must use the exact constructor args used to compute them (first attempt omitted `signal_period=2`, so the signal EMA differed).
- `python -m pip install -e ".[dev]"` is still unusable offline; use `pip wheel/install --no-deps --no-build-isolation` if packaging checks are needed.
- Adding a strategy also requires syncing: `examples/cli.py` key list, the `_STRATEGIES_WITHOUT_DEDICATED_CLI_FLAGS` allowlist, the alias map in `test_strategy_registry_coverage.py`, the module-docstring count, the README count, and an example script + its README code block. The integrity tests enforce all of these.

## Remaining work / unresolved

None for TSI. The working tree is intentionally left uncommitted for the controller to checkpoint.

## One precise next task

Add the next missing standard oscillator — **Relative Vigor Index (RVI)** — following the exact TSI checklist, or, if a non-strategy task is preferred, audit one existing multi-condition `generate_signals` (e.g. `KlingerOscillatorStrategy`) against its canonical formula and add a regression test pinning the verified numeric output. Acceptance for either: full suite green with 100% branch coverage, black/ruff/mypy clean, README registry + example-script block in sync, and `examples/run_<name>.py` exiting 0.

Gate command:

```bash
MPLBACKEND=Agg python -m pytest -q -p no:cacheprovider --cov --cov-report=term
python -m black --check tests/ quant_trading/ examples/
python -m ruff check tests/ quant_trading/ examples/
python -m mypy tests/ quant_trading/ examples/
```
