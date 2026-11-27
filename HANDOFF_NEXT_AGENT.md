## Session 2026-11-27 (allowlist cleanup - risk/manager.py continued)

### What changed
- Refactored three multi-line doctests in `quant_trading/risk/manager.py` to single-line `>>>` statements:
  - `RiskManager.calculate_risk_attribution` - converted `update_portfolio_value()` and `pd.DataFrame()` calls to single lines
  - `RiskManager.suggest_erc_weights` - same conversion
  - `RiskManager.suggest_risk_budget_weights` - same conversion
- Removed the three corresponding entries from `_EXAMPLES_ALLOWLIST` in `tests/test_repository_integrity.py`:
  - `("quant_trading/risk/manager.py", "calculate_risk_attribution")`
  - `("quant_trading/risk/manager.py", "suggest_erc_weights")`
  - `("quant_trading/risk/manager.py", "suggest_risk_budget_weights")`

Note: The other four methods mentioned in the previous handoff (`as_frame`, `to_dict`, `total_component_var`, `total_volatility_contribution`) were already single-line in the current codebase and were not in the allowlist.

### What was verified
- `python -m pytest tests/test_repository_integrity.py::test_documented_examples_are_valid` -> PASSED
- `python -m pytest tests/test_repository_integrity.py --doctest-modules quant_trading/risk/manager.py` -> 88 passed (was 87)
- `python -m pytest --doctest-modules quant_trading/risk/manager.py` -> 37 passed
- `python -m ruff check .` -> all passed
- `python -m black --check quant_trading/ tests/` -> 105 files unchanged
- Risk-related tests: 923 passed, 11 skipped

### Approach that FAILED (do not repeat unchanged)
- De-allowlisting the three entries without first rewriting the multi-line doctests to single-line statements. The guard (`tests/test_repository_integrity.py:_validate_doctest_lines`) compiles each `>>>` line independently, so multi-line calls with `...` continuation fail.

### Remaining allowlist entries in quant_trading/risk/manager.py (grandfathered)
Only private/internal methods remain allowlisted:
`__init__`, `_check_exposure_increase`, `_clear_trailing_state`, `_mapping_to_series`, `_open_position_count`, `_open_returns_frame`, `_position_weights`, `_reject_new_position_if_at_the_limit`, `_reject_signal_if_in_drawdown_breach`, `_series_to_mapping`, `_tracked_trailing_symbols`, `_validate_confidence`, `_validate_periods_per_year`

All public methods in `quant_trading/risk/manager.py` now have valid, single-line doctests and are no longer allowlisted.

### Next task
Pick the next allowlist cleanup target elsewhere in the repo and apply the same verification (integrity doctests + ruff + black + full suite). The `_EXAMPLES_ALLOWLIST` still contains many entries in other files (e.g., `examples/cli.py`, `quant_trading/backtest/`, `quant_trading/data/`, `quant_trading/optimization/`, `quant_trading/portfolio/`, `quant_trading/strategies/`). Do NOT add allowlist entries for new code; the guard forbids it.