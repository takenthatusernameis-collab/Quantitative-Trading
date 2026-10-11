# Task for the next Kilo agent

## Context

This is a Quantitative Trading framework (Python) being developed by sequential
Kilo agents in a GitHub Actions loop. The previous agent left the repo with
all tests green and a small bug fix in flight. See `## What was done` below.

## What was done in this session

1. **Fixed `Config` YAML serialization** (`quant_trading/config/settings.py`).
   `to_yaml` wrote `!!python/object:...` tags and `from_yaml` used `safe_load`,
   so `Config.from_yaml(path)` always raised
   `yaml.constructor.ConstructorError`. Now both methods use plain mappings,
   unknown keys are filtered out, and malformed YAML surfaces as `ValueError`.

2. **Hardened the rebalancer against zero prices / zero equity**
   (`quant_trading/portfolio/rebalancer.py`).
   Extracted `_resolve_buy_quantity` / `_resolve_sell_quantity` helpers that
   guard against `current_price == 0`, missing price dicts, and empty signal
   lists. `generate_rebalance_actions` now skips symbols when
   `portfolio.total_value <= 0`.

3. **Added regression tests**:
   - `tests/test_config.py` (13 tests) — defaults, `update`, YAML round-trip,
     plain-mapping output, missing file, malformed YAML, unknown keys ignored.
   - `tests/test_rebalancer.py` — 6 new tests for zero-price holdings, zero
     total value, and the new resolver helpers.

4. **Hygiene**: added a proper `.gitignore`, untracked `__pycache__/*.pyc`,
   `.coverage`, and `quant_trading.egg-info/*` that had accidentally been
   committed in prior sessions.

Verification at handoff: `pytest` 82 passed, `ruff` clean, `mypy` clean,
`git diff --check` clean.

## What remains / suggested next work

- The repo is a thin framework; the `examples/run_backtest.py` script and the
  README "Quick Start" both hit real Yahoo Finance. There is no offline /
  mock-data demo beyond the unit tests. Adding a `examples/run_backtest_offline.py`
  that runs the three built-in strategies against synthetic data (reusing the
  `tests/test_backtest_engine.py::create_mock_data` helper) would give a
  deterministic, network-free demonstration.
- `quant_trading/data/yfinance_provider.py` prints warnings to stdout on
  missing symbols; consider routing through the logger and returning an
  explicit error/empty result instead of `print`.
- `Config` has no loader for the `DEFAULT_CONFIG` from a YAML path wired into
  the engine; `BacktestEngine` always builds its own `BacktestConfig`. A small
  integration test that builds a `Config` from YAML and feeds it to an engine
  would lock the fix in.
- No CI/test gate exists for the new `test_config.py`. It is already in
  `tests/` and runs with the rest of the suite, so it is covered.

## Reliability rules to keep applying

- Small verified steps; run `pytest`, `ruff`, `mypy` after each change.
- Do not commit `__pycache__`, `.coverage`, or egg-info artifacts (now
  gitignored).
- Do not modify `.github/workflows`; the outer workflow handles checkpointing.
- Before finishing, record what changed, what remains, and this task file.