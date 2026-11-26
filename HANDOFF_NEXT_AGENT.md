## Session 2026-11-26 (batch 1 of allowlist cleanup)

### Task
Continue clearing `quant_trading/backtest/engine.py` from `_EXAMPLES_ALLOWLIST`
(`tests/test_repository_integrity.py`). Handoff asked to batch ~5 symbols.

### What changed
- Added single-line `>>>` doctests (all verified against live runtime) to the 11
  `BacktestResult` metric properties: `unrealized_pnl`, `num_trades`,
  `trade_count`, `win_rate`, `sharpe_ratio`, `sortino_ratio`, `calmar_ratio`,
  `profit_factor`, `max_drawdown_pct`, `max_drawdown`, `total_pnl`. Pattern:
  `>>> result = BacktestResult.from_dict({...})` then `>>> result.<prop>`.
- Removed 14 now-satisfied allowlist entries: the 11 properties above plus
  `remove_strategy`, `run`, `reset_default_data_manager` (these three already had
  valid single-line doctests — stale entries). Also dropped 2 redundant duplicate
  `from_dict`/`to_dict` lines.
- engine.py allowlist lines: 35 -> 19.

### What was verified (evidence)
- `pytest quant_trading/backtest/engine.py` -> 23 passed (was 12; +11 new doctests).
- `pytest tests/test_repository_integrity.py` -> 50 passed, 1 skipped
  (skip = mypy test; mypy not installed in this env).
- `pytest tests/test_backtest_engine.py` -> 154 passed.
- `ruff check` on both changed files -> clean.

### Key learning (important constraint)
`_validate_doctest_lines` compiles each `>>>` line IN ISOLATION. Any multi-line
statement (open paren/bracket at end of a `>>>` line) is reported as
"unparseable" and the function MUST stay allowlisted. I initially removed `fee`
and `run_backtest` (they have valid *runnable* but multi-line doctests); the
integrity test failed and I restored both. To clear a function, EVERY `>>>` line
must be a complete, balanced single-line statement.

### Remaining engine.py allowlist (19)
- Empty Examples, need single-line doctests: `cost`, `pnl` (Trade props, trivial),
  `to_dataframe`, `to_csv`, `to_json`, `from_dict`/`to_dict` (BacktestResult),
  `__init__` (BacktestEngine), and private helpers `_benchmark_returns`,
  `_process_signal`, `_process_stop_exits`, `_open_long`, `_reduce_long`,
  `_open_short`, `_cover_short`, `_resolve_backtest_config`,
  `_resolve_data_interval`.
- Multi-line doctests (stay unless rewritten single-line): `fee`, `run_backtest`.

### Next task (batch 2)
Add single-line doctests to `cost` and `pnl` (Trade properties) and the
`BacktestResult` serializers `to_dataframe`/`to_csv`/`to_json`/`to_dict`/
`from_dict`, then remove their allowlist lines. Construct inputs via
`BacktestResult.from_dict({...})` (keep every `>>>` line balanced/single-line).
Rerun: `pytest quant_trading/backtest/engine.py`,
`pytest tests/test_repository_integrity.py`, `pytest tests/test_backtest_engine.py`.