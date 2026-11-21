## Status

Audited `quant_trading/backtest/engine.py` (the `BacktestEngine` /
`run_backtest` / `Trade` / `BacktestResult` path) for degenerate/non-finite
input defects. The **live-run path was already hardened**: a 22-check probe
confirmed 0 leaks for non-finite `initial_capital` / `commission` / `slippage`
/ `periods_per_year` (rejected by `BacktestConfig.__post_init__` via
`replace()` in `_resolve_backtest_config`), non-finite data closes (sanitized
by `Portfolio.update_prices` / `Holding`), non-finite signal `strength`/`price`
(rejected by `RiskManager.check_signal`), and non-finite equity/market returns
(sanitized by `calculate_backtest_metrics`).

The real gap was the **dict/JSON deserialization boundary**:
`BacktestResult.from_dict` and `Trade.from_dict` passed NaN/inf straight
through, and `Trade.cost` / `Trade.fee` returned NaN/inf for non-finite
inputs. Fixes applied following the same sanitize-to-zero pattern used in
`quant_trading/risk/manager.py` and `quant_trading/portfolio/`.

## What Changed (this session)

`quant_trading/backtest/engine.py`:

- `Trade.cost`: return `0.0` when `quantity`/`price`/`commission`/`slippage`
  is non-finite (was NaN/inf).
- `Trade.fee`: return `0.0` under the same non-finite guard.
- `Trade.from_dict`: sanitize non-finite `quantity`/`price`/`commission`/
  `slippage`/`realized_pnl` to `0.0` via a `_finite` helper that **preserves
  the original numeric type** for finite values (so an int quantity
  round-trips as int, not float).
- `BacktestResult.from_dict`: sanitize non-finite `initial_capital`/
  `final_value`/`total_return`/`total_return_pct`/`total_costs` to `0.0`, and
  sanitize the same set of metric fields before `BacktestMetrics.from_dict`
  (so a reconstructed result's metrics never carry NaN/inf).

`tests/test_backtest_engine.py`: new `TestNonFiniteDeserialization` class
with 10 regression tests covering every leak above, including a finite
int-quantity round-trip guard and a normal round-trip sanity check.

## What Was Verified

- `python -m pytest -q tests/test_backtest_engine.py` — **150 passed**
  (140 pre-existing + 10 new).
- `python -m pytest --doctest-modules -q quant_trading/backtest/engine.py`
  — **7 passed** (docstring examples still green; the `from_dict` int-preservation
  fix keeps the `quantity` doctest output as `100`, not `100.0`).
- Neighbor suites: `tests/test_risk_manager.py tests/test_portfolio.py
  tests/test_backtest_metrics.py tests/test_integration.py` — **404 passed**.
- Full suite: `python -m pytest -q tests/` — **3993 passed, 89 skipped,
  151 deselected, 2 failed** (both pre-existing, see below).
- `python -m ruff check quant_trading/backtest/engine.py
  tests/test_backtest_engine.py` — clean.
- `python -m black --check quant_trading/backtest/engine.py
  tests/test_backtest_engine.py` — clean.
- `python -m mypy quant_trading/backtest/engine.py
  tests/test_backtest_engine.py` — clean.
- `tests/test_repository_integrity.py::test_repository_is_ruff_clean` —
  now passes (was failing on the nested-`if` ruff finding, fixed).
- Degenerate-input probe (22 checks) re-run after fix: **0 leaks remain**.

## Unresolved / Notes

- Pre-existing repo-integrity failures unrelated to this change (also fail on
  baseline `cd89df5`; left untouched):
  - `test_repository_is_black_formatted`: `quant_trading/backtest/trade_log.py`
    is not black-formatted (single file; every other module is clean).
  - `test_documented_examples_are_valid`:
    `quant_trading/portfolio/rebalancer.py:98` and `:306` have empty Examples
    sections.

## Failed Approach / Evidence

None this session. The handoff's original hypothesis (engine consumes
unvalidated `initial_capital`/prices) was disproven by probe: the live path is
already sanitized end-to-end. The probe then surfaced the real leak surface
(deserialization) and each fix resolved its leak (re-run probe shows 0 LEAKS).

## One Precise Next Task

Fix the two remaining pre-existing repo-integrity failures so the suite is
fully green. They are deterministic and low-risk:

1. `quant_trading/backtest/trade_log.py` — run `python -m black
   quant_trading/backtest/trade_log.py` to fix formatting (no logic change).
2. `quant_trading/portfolio/rebalancer.py:98` and `:306` — the `__post_init__`
   docstrings of two dataclasses have empty `Examples:` sections; add a minimal
   valid doctest (construct the dataclass and assert one field) to each.

Verify with:

```bash
python -m pytest -q tests/test_repository_integrity.py
python -m pytest -q tests/ -k "rebalancer or portfolio"
python -m ruff check quant_trading/backtest/trade_log.py quant_trading/portfolio/rebalancer.py
python -m black --check quant_trading/backtest/trade_log.py quant_trading/portfolio/rebalancer.py
python -m mypy quant_trading/backtest/trade_log.py quant_trading/portfolio/rebalancer.py
```

Relevant evidence: `python -m pytest -q tests/test_repository_integrity.py`
currently reports exactly these two failures; the rest of the suite (3993 tests)
is green.