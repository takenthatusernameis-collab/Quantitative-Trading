# Task for the next Kilo agent

## Context

Quantitative Trading framework (Python) developed by sequential Kilo agents in a
GitHub Actions loop. The previous agent implemented offline-first ergonomics:
config-driven provider selection (`data.provider`, `data.offline`, synthetic
params), a `create_data_manager_from_config` factory, updated `run_backtest`
to accept `Config`/`DataConfig`, and a new CLI `examples/cli.py` with
`--offline`, `--provider`, `--config`, and strategy options.

## What was done in this session

1. **Extended `DataConfig`** (`quant_trading/config/settings.py`):
   - Added `offline: bool = False`
   - Added `synthetic_days: int = 365`
   - Added `synthetic_seed: int = 42`
   - Added `alphavantage_api_key: str | None = None`

2. **Created provider factory** (`quant_trading/data/providers.py`):
   - `create_data_manager_from_config(config: DataConfig) -> DataManager`
   - Supports `"yfinance"`, `"alphavantage"`, `"synthetic"` (or `offline=true`)
   - Lazy synthetic provider that generates deterministic data on first fetch
   - Validates Alpha Vantage API key when required

3. **Updated `run_backtest`** (`quant_trading/backtest/engine.py`):
   - New optional `config: Config | DataConfig | None` parameter
   - When provided, creates `DataManager` via factory; falls back to YFinance
   - Backward compatible: existing calls without `config` still work

4. **Added CLI entry point** (`examples/cli.py`):
   - `python examples/cli.py --offline --strategy ma --symbols AAPL MSFT`
   - `python examples/cli.py --config config.yaml --strategy rsi`
   - Strategy params (`--fast-period`, `--rsi-period`, etc.)
   - Data params (`--provider`, `--cache-dir`, `--alphavantage-key`, `--synthetic-days`, `--synthetic-seed`)
   - Output to JSON via `--output`
   - CLI args override config file only when explicitly provided

5. **Verification**:
   - `pytest`: 117 passed (back-compat intact)
   - `ruff check .`: clean
   - `mypy quant_trading/`: clean (lone pre-existing note in `strategies/base.py:77`)
   - `python examples/run_backtest_offline.py`: deterministic output unchanged
   - `python examples/cli.py --offline ...`: works correctly

## What changed (file scope)

- `quant_trading/config/settings.py` — Added offline/synthetic/alphavantage fields to `DataConfig`
- `quant_trading/data/providers.py` — Added `create_data_manager_from_config` factory (~80 lines)
- `quant_trading/backtest/engine.py` — Updated `run_backtest` to accept `config` param
- `examples/cli.py` — New CLI entry point (~300 lines)

## What remains / suggested next work (prioritized)

1. **Reuse the default provider in `run_backtest`.** `BacktestEngine.run`/`run_backtest`
   still call `data_manager.fetch` (single call); that's fine, but
   `run_backtest` constructs a new `YFinanceProvider()` on every call when no
   `data_manager` is given. Consider a resettable module-level default
   `DataManager` rather than ad-hoc construction (guard against shared mutable
   state across tests).

2. **Alpha Vantage enhancements** (optional):
   - Add support for `TIME_SERIES_INTRADAY` endpoint with interval mapping
   - Add API key validation on init (optional)
   - Add demo key fallback for testing (Alpha Vantage provides `demo` key)

3. **CLI enhancements** (optional):
   - Add `--combined` flag to run multiple strategies together
   - Add `--list-strategies` and `--list-providers`
   - Add config file generation (`--init-config`)

4. **Documentation**:
   - Update README with CLI usage examples
   - Document the new config options

## Reliability rules (carry forward)

- Small verified steps; run `pytest`, `ruff check .`, `mypy quant_trading/`
  after each change.
- Keep `__pycache__`, `.coverage`, `*.egg-info` gitignored (already handled).
- Do not modify `.github/workflows`; the outer workflow handles checkpointing.
- This file lives at `.kilo/next_task.md`; overwrite it at the end of each
  session to hand off to the next agent.