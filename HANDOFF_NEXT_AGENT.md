## What changed (this session)

- Documented that `examples/run_backtest.py` requires network access via yfinance in README "Example Scripts" (README.md:886) to avoid implying it is offline-capable.
- Synced CLI strategy registry surface with the newly-added `ma_envelope` strategy so integrity checks stay green:
  - Added `ma_envelope` to `BUILTIN_STRATEGY_KEYS` in `examples/cli.py`.
  - Added `ma_envelope` to `_STRATEGIES_WITHOUT_DEDICATED_CLI_FLAGS` in `tests/test_repository_integrity.py` (strategy is tunable via `--strategy-config` only, consistent with other config-only strategies).

## What was actually verified (evidence)

- `python -m pytest tests/test_readme_cli_commands.py -q`: 100 passed, 3 deselected.
- `python -m pytest tests/test_repository_integrity.py -q`: 32 passed.
- `python -m ruff check .`: All checks passed.
- `python -m mypy quant_trading tests`: Success, no issues in 103 source files.
- `python examples/cli.py --list-strategies` shows `ma_envelope` (aliases: `envelope`, `moving_average_envelope`).
- `python examples/run_backtest.py` executed (networked): produced output for MA/RSI/BB strategies (observed during inspection; not part of offline test suite).

## What remains unresolved / not verified

- Nothing blocking. Repo is green. Intentionally-not-chased defensive-branch coverage gaps remain (sensitivity.py 99%; rebalancer.py 98%; engine.py 99%; settings.py 99%; risk/metrics.py 98%). Do not chase these.

## Failed or corrected approaches

- None. Initial integrity test run (before this session's fixes) showed `ma_envelope` missing from CLI allowlists/registry sync; corrected with minimal, evidence-based edits to `examples/cli.py` and `tests/test_repository_integrity.py`, then all targeted checks passed.

## One precise next task

- No further required work. Repository is green and committed. Next agent may pick any bounded, high-value task if assigned; otherwise leave as-is. If extending CLI, consider whether `ma_envelope` deserves dedicated `--envelope-period`/`--envelope-percentage` flags and optimization ranges (currently config-only by design like other allowlisted strategies).
