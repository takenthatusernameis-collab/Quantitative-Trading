## Session 2026-11-27 (allowlist cleanup - risk/manager.py)

### What changed
- Added confirmed-output `Examples:` doctests to two public defs in
  `quant_trading/risk/manager.py` that lacked them:
  - `PortfolioRisk.total_value` property (`pr.total_value` -> `100000.0`)
  - `RiskManager.calculate_metrics` (`round(metrics.sharpe_ratio, 2)` ->
    `-3.75`)
- Removed those two entries from `_EXAMPLES_ALLOWLIST` in
  `tests/test_repository_integrity.py`: `("quant_trading/risk/manager.py",
  "calculate_metrics")` and `("quant_trading/risk/manager.py", "total_value")`.

### What was verified
- `python -m pytest tests/test_repository_integrity.py --doctest-modules quant_trading/risk/manager.py` -> 87 passed, 1 skipped (was 85; +2 doctests collected).
- `python -m ruff check .` -> all passed.
- `python -m black --check quant_trading/ tests/` -> 105 files unchanged.
- Full suite `python -m pytest -q` -> 5290 passed, 260 skipped, 151 deselected (was 5288; +2).

### Approach that FAILED (do not repeat unchanged)
- De-allowlisting the seven entries `as_frame`, `to_dict`,
  `total_component_var`, `total_volatility_contribution`,
  `calculate_risk_attribution`, `suggest_erc_weights`,
  `suggest_risk_budget_weights` (all already have non-empty Examples).
  **Result:** `test_documented_examples_are_valid` fails because the guard
  (`tests/test_repository_integrity.py:_validate_doctest_lines`) compiles each
  `>>>` line **independently**, and these Examples use multi-line calls such as
  `>>> attribution = RiskAttribution(` / `...     portfolio_var=0.03,` whose
  first line alone has an unclosed paren. They can only be de-allowlisted by
  first rewriting those doctests so every `>>>` statement is complete on one
  line (a source edit to manager.py docstrings), then verifying --doctest-modules
  output still matches. Leave them allowlisted until that refactor is done.

### Remaining allowlist entries in quant_trading/risk/manager.py (grandfathered)
`as_frame`, `calculate_risk_attribution`, `suggest_erc_weights`,
`suggest_risk_budget_weights`, `to_dict`, `total_component_var`,
`total_volatility_contribution` (all have multi-line `>>>` doctests the guard
cannot validate line-by-line).

### Next task
Either (a) refactor the seven multi-line doctests above to single-line `>>>`
statements, confirm --doctest-modules output still matches, then de-allowlist
them; or (b) pick the next allowlist cleanup target elsewhere in the repo and
apply the same verification (integrity doctests + ruff + black + full suite).
Do NOT add allowlist entries for new code; the guard forbids it.
