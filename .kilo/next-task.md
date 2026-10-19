# Next Task

## What changed (this session)
- `examples/cli.py`: added `"ema"` and `"momentum"` to `BUILTIN_STRATEGY_KEYS` (cli.py:41-54). Both are already registered in `quant_trading/strategies/__init__.py` and already supported by `create_strategy`; this makes combined CLI runs include them (ema was previously excluded only by the `k != "ema"` guard at cli.py:1726).
- `tests/test_cli.py`: added `("EMA_Crossover_10_30", 6.5)` and `("Momentum", 9.5)` to `mock_results` in `TestRunCombined.test_run_combined_all_strategies` so the mocked `run_backtest` covers every strategy combined mode actually iterates.
- No changes to `quant_trading/` source or the registry.

## What was actually verified (this session)
- `tests/test_cli.py::TestRunCombined` → 4 passed (includes `test_run_combined_all_strategies`, previously failing with `Momentum: Error - Unknown strategy`).
- Offline end-to-end combined tests (`test_main_offline_combined_end_to_end`, `test_main_offline_combined_with_output`) → pass.
- Full suite: `pytest` → 1123 passed, 1 skipped (~150s). Previously 1122 passed, 1 failed — the pre-existing combined-run failure is resolved.
- Linting: `python -m ruff check .` → All checks passed.
- Formatting: `python -m black --check examples/cli.py tests/test_cli.py` → 2 files unchanged.
- Type checking: `python -m mypy quant_trading examples/cli.py` → Success, no issues in 37 source files.

## What remains unresolved
- External CI workflow permission issue (from prior handoffs): GitHub App token lacks `workflows` permission; workflow files are maintainer-managed. Requires external maintainer action, not a code change. Do not retry the identical workflow push.

## Approaches already failed
- Adding only `"momentum"`/`"ema"` to `BUILTIN_STRATEGY_KEYS` without updating the test mock: insufficient — `momentum` was already iterated via the registry loop (cli.py:1725-1727), and the mocked `run_backtest` raised `ValueError("Unknown strategy")` for any strategy name absent from `mock_results`. Fix required both the key-list change and the mock entries.

## One precise next task
- No code work remains; the codebase is green. Next session: (a) commit the two changed files when authorized (changes are currently uncommitted: `examples/cli.py`, `tests/test_cli.py`), and (b) wait for the maintainer to grant the `workflows` permission to the GitHub App token or push `.github/workflows/ci.yml` manually. Inspect `.kilo/next-task.md` evidence rather than re-running full verification or retrying the workflow push.
