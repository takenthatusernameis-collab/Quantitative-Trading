# Next Task

## What changed (this session)

The trading-cost fix is **already in the code** (commit `50223da`, 2026-10-20): `quant_trading/portfolio/portfolio.py` (`add_holding`/`remove_holding`) and `quant_trading/backtest/engine.py` now charge `commission`/`slippage` to cash on every buy and sell. This was **verified empirically**, not assumed:

- Zero-cost vs costed (`0.01`/`0.005`) on the same data/strategy:
  - equity curves differ; costed `final_value` = 98320.29 vs zero-cost 98470.29 (gap = exactly the buy-side fees)
  - costed equity is weakly below zero-cost at every bar and strictly below once a trade executes
- Round-trip reconciliation (buy then sell, fully liquidated):
  - `final_value - initial_capital == sum(signed Trade.cost)` (buys negative, sells positive) — holds exactly
  - `sum(Trade.pnl)` does **not** equal `final_value - initial_capital` because buy-side commission/slippage is a cash drag that `Trade.pnl` (realized-only, `0.0` on buys) never captures. This is the accounting model's documented behaviour, not a bug; the correct reconciliation is via signed `Trade.cost`.
- `tests/test_backtest_engine.py`: **27 passed** (was 25; +2 new tests):
  - `test_costed_equity_below_zero_cost_run` — encodes invariant 1 (costed equity below zero-cost)
  - `test_signed_trade_cost_reconciles_with_final_value` — encodes invariant 3 (signed cost == cash change) and documents the pnl gap
- Cost branches are exercised by existing tests (default config uses non-zero commission/slippage) and by the two new tests; 100% coverage is maintained on the packages that run in this environment.

## What was actually verified (this session)

- `python -m pytest tests/test_backtest_engine.py tests/test_portfolio.py tests/test_backtest_analysis.py tests/test_backtest_metrics.py tests/test_trade_analysis.py tests/test_rebalancer.py tests/test_integration.py` → all pass (144 passed).
- New cost-invariant tests pass and are deterministic/offline (no network).
- `git diff` limited to `tests/test_backtest_engine.py` (+99 lines); no source files touched.

## What remains unresolved

- Nothing in the trading-cost area: the fix is complete and verified.
- The canonical handoff previously stated the defect as unresolved; that was written before commit `50223da` and is now stale.

## Approaches already failed

- **Literal invariant 2 (`final_value - initial_capital == sum(Trade.pnl)`)** does not hold with the current accounting: buy-side fees are not in `Trade.pnl`. Do not "fix" this by changing `Trade.pnl` semantics (it is documented as realized-only). Reconcile via signed `Trade.cost` instead, or expose total costs (see next task).

## Environmental limitations in this session (pre-existing, not caused by this change)

- `yfinance` is not installed → `tests/test_cli.py` (2 tests) and `tests/test_optimization.py` (28 tests) fail with `ImportError: yfinance is not installed`. Do not retry these; they need the dependency/network.
- One test hangs in the full-suite run (network-blocked). Run the backtest/portfolio subset above instead of the whole suite.
- `ruff`, `black`, `mypy` are **not installed** in this environment, so lint/format/type checks could not be re-run locally. The added test code follows existing conventions (line-length 100, typed, matches neighboring style).

## One precise next task

**Expose total costs paid on `BacktestResult`** so headline numbers and the trade log reconcile without a reader recomputing them (the handoff's suggested side effect; also closes the invariant-2 reconciliation gap transparently).

Constraints and evidence:
- Add a `total_costs: float` field to `BacktestResult` (`quant_trading/backtest/engine.py`) and populate it in `BacktestEngine.run` from the cash impact of commission + slippage across the run.
- Wire it through every `BacktestResult(...)` construction site and keep `BacktestMetrics`/result consumers unchanged.
- Add tests: `total_costs` equals the sum of per-trade fees (`buy: base*(comm+slip)`, `sell: base*(comm+slip)`) and `final_value - initial_capital == sum(pnl) - total_costs` for fully-liquidated runs.
- Keep suite green, 100% coverage, and existing conventions; no network, no source changes outside `engine.py` and tests.
