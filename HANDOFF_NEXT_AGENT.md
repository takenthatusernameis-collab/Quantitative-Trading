## What changed (this session)

- Rejected non-finite `max_positions` in `RiskManager.__init__`:
  `quant_trading/risk/manager.py:217` is now
  `if not math.isfinite(max_positions) or max_positions < 1` (previously a naked
  `max_positions < 1`, which `nan` slips past since `nan < 1` is `False`).
  The whole validation block was moved ahead of `PositionLimit`/`PortfolioLimit`
  construction so `RiskManager(initial_capital=nan)` still raises
  `invalid initial_capital` (existing tests at tests/test_risk_manager.py:66-69
  depend on that ordering).
- Added `__post_init__` finite guards to `PositionLimit` and `PortfolioLimit` in
  `quant_trading/risk/limits.py`, so direct limit construction (and
  `from_dict` deserialization) rejects `nan`/`inf`/`-inf` on every numeric field
  with an `invalid <field>: ...` message prefix:
  - `max_positions` also requires `>= 0` (0 still constructible: it means "no
    positions may be opened", exercised by
    tests/test_risk_manager.py::test_portfolio_check_branches).
  - Zero/negative still allowed for `max_leverage`, `max_portfolio_risk`,
    `max_drawdown` because existing tests use `0.0` to disable those checks;
    range enforcement stays at the RiskManager boundary.
- Tests:
  - `tests/test_risk_manager.py`: `max_positions` parametrization extended with
    `nan`/`inf`/`-inf`; same extension for `max_position_size`,
    `max_portfolio_risk`, `max_drawdown`, `stop_loss_pct`, `take_profit_pct`,
    `trailing_stop_pct`, `trailing_stop_activation_pct` (guards already reject
    non-finite via chained comparisons; tests now document it).
  - `tests/test_limits.py`: new `TestPositionLimitValidation` and
    `TestPortfolioLimitValidation` (non-finite rejection for every field,
    `max_positions < 0` rejection, zero still accepted for `max_positions`/
    `max_leverage`/`max_portfolio_risk`/`max_drawdown`).
- **Files changed:** `quant_trading/risk/manager.py`,
  `quant_trading/risk/limits.py`, `tests/test_risk_manager.py`,
  `tests/test_limits.py`. Changes are **not committed**.

## What was actually verified (evidence)

- Library probes: all of `nan`/`inf`/`-inf` rejected for `RiskManager`
  (`initial_capital`, `max_positions`, `max_leverage`) and for direct
  `PositionLimit`/`PortfolioLimit` construction; finite valid values still
  construct; `max_leverage=0.0`/`max_portfolio_risk=0.0`/`max_drawdown=0.0`
  still construct.
- `python -m py_compile` on all changed files: OK.
- `pytest tests/test_risk_manager.py tests/test_limits.py
  tests/test_rebalancer_risk_integration.py tests/test_rebalancer_sizing_invariants.py
  tests/test_serialization_roundtrip.py quant_trading/risk/`: **421 passed**.
- Full suite: **3535 passed, 17 failed, 131 skipped, 136 deselected**. All 17
  failures are pre-existing environmental ones (matplotlib not installed ->
  test_backtest_report.py + TestHtmlReportFlag; scikit-optimize not installed ->
  bayesian README CLI commands). None touch the changed code.

### Environment caveat (unchanged)

Minimal env (Python 3.14.4, pandas 3.1.1, numpy 2.5.4, pytest 9.2.0).
`ruff`, `mypy`, `matplotlib`, `scikit-optimize` are **NOT** installed, so
lint/type checks cannot run and the 17 tests above fail for environmental
reasons only.

## Unresolved / not completed

- Lint/type checks not run (no ruff/mypy).
- Not committed (no explicit request).

## Failed approaches (do not repeat unchanged)

- None this session.

## One precise next task

- **`quant_trading/config/settings.py` has the same nan-acceptance hole in
  naked guards in other `__post_init__` methods** (invalid config silently
  propagates to the portfolio rebalancer):
  - `DataConfig.__post_init__` line 96: `if self.synthetic_days < 1:` — `nan`
    accepted.
  - `DataConfig.__post_init__` line 101: `if self.synthetic_seed < 0 or ...` —
    `nan` accepted (both comparisons are `False` for `nan`).
  - `RiskConfig.__post_init__` line 468: `if self.max_leverage < 1e-9:` —
    `nan` accepted.
  - `PortfolioConfig.__post_init__` line 578: `if self.max_positions < 1:` —
    `nan` accepted; its docstring (settings.py:573-576) explicitly says it
    "Mirrors RiskManager so invalid values are rejected ... instead of silently
    propagating".
  - Concrete step: add `not math.isfinite(x) or` to each guard (`synthetic_days`
    / `max_positions`: `< 1`; `max_leverage`: `< 1e-9`; `synthetic_seed`: `< 0
    or > 2**32 - 1`). Keep the `invalid <field>` message prefix so existing
    tests pass. Verify with library probes
    (`DataConfig(synthetic_days=nan)`, `PortfolioConfig(max_positions=nan)`,
    `RiskConfig(max_leverage=nan)`) and extend `tests/test_config.py`
    parametrizations. Run `tests/test_config.py` plus
    `tests/test_repository_integrity.py`. Constraints: minimal, localized; do
    not change existing range semantics — only reject non-finite values.
