## What changed (this session)
- Completed the assigned incremental mypy-strictness task for `tests/test_holding_pnl_invariants.py`.
  - Added `seed: int` parameter and `-> None` return annotations to the three parametrized tests
    (`test_unrealized_pnl_pct_is_cost_basis_fraction`,
    `test_unrealized_pnl_pct_sign_matches_pnl`,
    `test_unrealized_pnl_pct_long_short_are_mirror_images`).
  - Added a targeted mypy override in `pyproject.toml` enabling `disallow_untyped_defs = true`
    only for `tests.test_holding_pnl_invariants`. The global setting remains `false`.
- No runtime behavior was intentionally changed.

## What was actually verified (evidence)
- `python3 -m pytest -q tests/test_holding_pnl_invariants.py -p no:cacheprovider` -> `15 passed in 0.45s`.
- `python3 -m mypy quant_trading/ tests/test_holding_pnl_invariants.py --show-error-codes` -> `Success: no issues found in 39 source files`.
- `python3 -m mypy quant_trading/ tests/ examples/ --show-error-codes` -> `Found 4 errors in 2 files`
  (all pre-existing in `tests/test_optimization.py` and `tests/test_readme_cli_commands.py`;
  unrelated to this change).
- `python3 -m ruff check .` -> `All checks passed!`.
- `git diff --check` -> clean.

## What remains unresolved
- The full test suite is too slow for the 300-second command window; the focused suites and
  project-wide mypy/Ruff checks do pass.
- Repository-wide `disallow_untyped_defs = true` remains impractical without a much larger migration.
- Pre-existing mypy errors in `tests/test_optimization.py` (line 1542, `MockDataProvider` list item)
  and `tests/test_readme_cli_commands.py` (lines 53/64 `pytest.mark.param` used as a type,
  line 117 `no-any-return`) are still outstanding.

## Failed or corrected approaches
- Do not enable global `disallow_untyped_defs` without first addressing the project-wide untyped
  definitions. Continue the file-by-file targeted override approach.

## One precise next task
- Extend the targeted mypy-strictness migration to `tests/test_rebalancer_risk_integration.py`.
  - Evidence: this is the smallest remaining candidate. It has three untyped test functions
    (lines 27, 61, 86) plus three untyped helpers (lines 10, 14, 18).
  - Annotate helpers:
    - `_risk_manager() -> RiskManager` (returns `RiskManager`)
    - `_total_holdings_value(portfolio: Portfolio) -> float`
    - `_assert_solvency(portfolio: Portfolio, risk_manager: RiskManager) -> None`
  - Annotate tests: `def test_...( ) -> None`.
  - Add `tests.test_rebalancer_risk_integration` to `[[tool.mypy.overrides]]` with
    `disallow_untyped_defs = true`.
  - Constraints: keep `pytest tests/test_rebalancer_risk_integration.py`,
    `mypy quant_trading/ tests/test_rebalancer_risk_integration.py`, `ruff check .`, and
    `git diff --check` clean. Do not flip the global mypy setting.