## Session 2026-11-26 (allowlist cleanup - complete)

### What changed
- Batch 2 (`cost`, `pnl`, `to_dict`/`from_dict`/`to_dataframe`/`to_csv`/`to_json`) was completed in commit `be8ed29` (HEAD): allowlist entries removed, single-line doctests added. Verified green.
- This session: cleared `BacktestEngine.__init__` from `_EXAMPLES_ALLOWLIST` by adding a single-line doctest (`>>> engine = BacktestEngine()` / `>>> engine.portfolio.cash` -> `100000.0`) and removing its allowlist line (`tests/test_repository_integrity.py:1823`).

### What was verified (evidence)
- `pytest quant_trading/backtest/engine.py tests/test_repository_integrity.py tests/test_backtest_engine.py` -> 235 passed, 1 skipped (skip = mypy test; mypy not installed). Was 234 before this session (+1 `__init__` doctest).
- `ruff check quant_trading/backtest/engine.py tests/test_repository_integrity.py` -> clean.

### Remaining engine.py allowlist (11) - NOT boundedly clearable this session
- `_benchmark_returns`, `_cover_short`, `_open_long`, `_open_short`, `_process_signal`, `_process_stop_exits`, `_reduce_long`, `_resolve_backtest_config`, `_resolve_data_interval`: private helpers with docstrings but NO `Examples:` section. The integrity test (`_tree_examples_mismatches`) flags any docstring'd function lacking a non-empty Examples section unless allowlisted, so clearing them requires adding `Examples:` sections with valid doctests to private helpers - out of scope for a bounded session.
- `fee`, `run_backtest`: have multi-line `>>>` doctests. `_validate_doctest_lines` compiles each `>>>` line in isolation; an open paren/bracket at end of a line is "unparseable", so these must stay allowlisted unless every doctest line is rewritten as a complete balanced single-line statement (prior attempt failed; restored per key learning).

### Next task
Allowlist cleanup of clearable public API is complete. No bounded engine.py allowlist subtask remains. Either (a) leave the 11 entries as-is, or (b) pick a different bounded, high-value task elsewhere in the repo (e.g. another module's clearable allowlist entries that already have single-line doctests). Do NOT blindly retry clearing `__init__`/`fee`/`run_backtest`/private helpers - approaches already tried and verified.
