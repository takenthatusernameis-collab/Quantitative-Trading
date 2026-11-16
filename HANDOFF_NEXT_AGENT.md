## What changed (this session)

- Added `tests/test_rebalancer_risk_parity.py` with 4 regression tests asserting **generation/execution parity** for risk-managed buys:
  - `test_generation_execution_parity_under_leverage_cap` — `max_leverage=0.5` caps the first buy at 500 shares and crowds the second symbol out; planned quantity == executed quantity.
  - `test_generation_execution_parity_under_risk_budget_accumulates` — `max_portfolio_risk=0.04` / `stop_loss_pct=0.05` splits a multi-symbol batch (AAPL 600, MSFT 200) as planned gross/risk accumulates across actions; parity holds for both.
  - `test_generation_execution_parity_when_both_caps_bind` — leverage and risk budget together; still 500 shares planned == executed.
  - `test_generation_execution_parity_without_risk_manager` — no caps: full quantities execute and cash-constraint planning matches execution (cash residue bounded by the `_CASH_SAFETY_MARGIN` in `_plan_buy`).
- All tests use identical prices/fees for `generate_rebalance_actions` and `execute_actions`, zero commission/slippage (so generation price math equals execution avg-cost math), and assert portfolio solvency (cash >= 0, cash + holdings == total_value).
- No source changes; `quant_trading/portfolio/rebalancer.py` untouched from the prior session.

## What was actually verified (evidence)

- `python3 -m pytest tests/test_rebalancer_risk_integration.py tests/test_portfolio_rebalancer.py tests/test_risk_manager.py tests/test_rebalancer_extra_coverage.py tests/test_rebalancer_execution.py tests/test_rebalancer_risk_parity.py -q` → **379 passed in 0.63s** (375 baseline + 4 new).
- `python3 -m ruff check .` → **All checks passed**.
- `python3 -m mypy tests/test_rebalancer_risk_parity.py` → **Success: no issues found**.

## What remains unresolved / not verified

- Broader/full test suite not run (focused risk/rebalancer/portfolio suites verified only; see next task).
- Changes left uncommitted (no commit requested).

## Failed or corrected approaches

- None this session; all 4 new tests passed on the first run after a trivial cash-tolerance fix (the `_CASH_SAFETY_MARGIN` leaves a ~4e-05 cash residue, so the exact-zero cash assertion was relaxed to `< 1e-4`).

## One precise next task

Run the full test suite (`pytest -v`, which uses the project's default addopts deselecting `slow` and `network` plus doctests in `quant_trading/`), confirm everything passes, and investigate/repair any failures outside the focused suites already verified. If the full suite is clean, the session is done: summarize results in the handoff and leave the working tree as-is (no commit unless requested). Constraints: do not change source code unless a reproduced failure requires it; keep changes minimal and reversible; run ruff/mypy on any touched files.
