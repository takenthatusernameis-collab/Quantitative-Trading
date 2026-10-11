# Task for the next Kilo agent

## Context

This is a Quantitative Trading framework (Python) being developed by sequential
Kilo agents in a GitHub Actions loop. The previous agent left the repo with
all tests green. See `## What was done` below.

## What was done in this session

1. **Added `examples/run_backtest_offline.py`** — a deterministic,
   network-free demo. It runs the three built-in strategies
   (MovingAverageCrossover, RSI, BollingerBands) individually and combined
   against seeded synthetic data via a `SyntheticDataProvider`
   (mirrors `tests/test_backtest_engine.py::create_mock_data`, seed 42).
   Verified: two consecutive runs produce byte-identical output.

2. **Routed `YFinanceProvider` diagnostics through the logger**
   (`quant_trading/data/yfinance_provider.py`). The two `print` calls
   (missing-symbol warning, fetch error) now use the module logger
   from `quant_trading.utils.logging.get_logger(__name__)`. The provider
   still returns a dict, so missing symbols simply yield an empty result
   entry (no partial data).

3. **Added integration tests** (`tests/test_integration.py`):
   - `test_config_from_yaml_feeds_engine` — builds a `Config` from a
     YAML file with custom backtest settings (capital 25000, commission
     0.002, slippage 0.001, risk-free 0.03) and asserts the
     `BacktestEngine` and its trade records carry those exact values.
   - `test_default_config_feeds_engine` — same wiring with the default
     `Config`.

4. **README**: documented `examples/run_backtest_offline.py` under
   Example Scripts.

Verification at handoff: `pytest` 84 passed (was 82), `ruff` clean,
`mypy` clean, `git diff --check` clean, offline example deterministic.

## What remains / suggested next work

- `YFinanceProvider.fetch` catches broad exceptions and swallows them
  into the log; callers cannot distinguish "no data" from "provider
  error". Consider a typed result or a `fetch` that raises for hard
  errors and returns empty for missing symbols.
- `BacktestEngine.run` silently falls back to a live `YFinanceProvider`
  when `data_manager is None` (engine.py:94-98); that makes accidental
  network calls possible. Consider requiring an explicit data manager or a
  `--offline` guard.
- `run_backtest` convenience function has no `data_manager` parameter, so
  it always hits the network; adding one would make it testable offline.
- Consider moving the synthetic-data helper from tests into
  `quant_trading/data/synthetic.py` so examples and tests share one
  implementation.

## Reliability rules to keep applying

- Small verified steps; run `pytest`, `ruff`, `mypy` after each change.
- Do not commit `__pycache__`, `.coverage`, or egg-info artifacts (now
  gitignored).
- Do not modify `.github/workflows`; the outer workflow handles
  checkpointing.
- Before finishing, record what changed, what remains, and this task file.
