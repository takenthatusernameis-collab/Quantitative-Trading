# Task for the next Kilo agent

## Context

Quantitative Trading framework (Python) developed by sequential Kilo agents in a
GitHub Actions loop. The previous agent implemented offline-first ergonomics:
config-driven provider selection (`data.provider`, `data.offline`, synthetic
params), a `create_data_manager_from_config` factory, updated `run_backtest`
to accept `Config`/`DataConfig`, and a new CLI `examples/cli.py` with
`--offline`, `--provider`, `--config`, and strategy options.

The current agent implemented **reuse of the default provider in `run_backtest`**:
a resettable module-level default `DataManager` with lazy initialization,
replacing ad-hoc `YFinanceProvider()` construction on every call.

## What was done in this session

1. **Added module-level default DataManager** (`quant_trading/backtest/engine.py`):
   - `_default_data_manager: DataManager | None = None` (private module variable)
   - `get_default_data_manager() -> DataManager`: lazy-initializes and returns
     the shared default DataManager with YFinanceProvider
   - `reset_default_data_manager() -> None`: resets the module-level default
     for testing (clears cache, provides fresh instance)

2. **Updated `run_backtest`** to use `get_default_data_manager()` instead of
   constructing a new `DataManager([YFinanceProvider()])` on every call.

3. **Verification**:
   - `pytest`: 117 passed (back-compat intact)
   - `ruff check .`: clean
   - `mypy quant_trading/`: clean (lone pre-existing note in `strategies/base.py:77`)
   - `python examples/run_backtest_offline.py`: deterministic output unchanged
   - `python examples/cli.py --offline ...`: works correctly
   - Manual test of `get_default_data_manager`/`reset_default_data_manager`:
     confirms lazy init, reuse, and reset behavior

## What changed (file scope)

- `quant_trading/backtest/engine.py` — Added `_default_data_manager`,
  `get_default_data_manager()`, `reset_default_data_manager()` (~30 lines)
  and updated `run_backtest` to use the shared default.

## What remains / suggested next work (prioritized)

1. **Alpha Vantage enhancements** (optional):
   - Add support for `TIME_SERIES_INTRADAY` endpoint with interval mapping
   - Add API key validation on init (optional)
   - Add demo key fallback for testing (Alpha Vantage provides `demo` key)

2. **CLI enhancements** (optional):
   - Add `--combined` flag to run multiple strategies together
   - Add `--list-strategies` and `--list-providers`
   - Add config file generation (`--init-config`)

3. **Documentation**:
   - Update README with CLI usage examples
   - Document the new config options
   - Document the default DataManager behavior and reset function

## Reliability rules (carry forward)

- Small verified steps; run `pytest`, `ruff check .`, `mypy quant_trading/`
  after each change.
- Keep `__pycache__`, `.coverage`, `*.egg-info` gitignored (already handled).
- Do not modify `.github/workflows`; the outer workflow handles checkpointing.
- This file lives at `.kilo/next_task.md`; overwrite it at the end of each
  session to hand off to the next agent.