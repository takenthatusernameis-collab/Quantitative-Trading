# Task for the next Kilo agent

## Context

Quantitative Trading framework. Coverage-focused work. Previous session closed
`config/settings.py` gaps to 100% via test-only additions to `tests/test_config.py`.
This session closed `risk/limits.py` to 100% via test-only additions to `tests/test_limits.py`.

## What was done in this session

- Added two tests to `tests/test_limits.py`:
  - `test_check_skips_zero_quantity_position` - covers the `continue` branch when `pos.quantity == 0` in `PortfolioLimit.check()` (line 65)
  - `test_check_zero_quantity_with_other_violations` - ensures zero-quantity positions are correctly skipped even when other violations exist
- Verified: `python -m coverage report -m quant_trading/risk/limits.py` -> 53 stmts, 0 missed, 100%.
- Full suite: `python -m pytest tests/ -q` -> 649 passed (+2 tests over prior baseline).
- Quality: ruff check passed; mypy passed; black reformat of modified test passed.

## What remains unresolved

Remaining small pure-Python gaps (untouched):
- `data/synthetic.py` (4 missed, 90%) - lines 88, 92, 102-103
- `regime/detector.py` (4 missed, 97%) - lines 59, 70, 107, 113
- `monte_carlo/simulator.py` (2 missed, 98%) - lines 61, 68
Total ~10 lines.

## Next task (precise, prioritized)

Pick ONE and close it to 100% test-only, using deterministic/offline approach:

1. `monte_carlo/simulator.py` -- 2 missed lines (simulation edge cases).
2. `regime/detector.py` -- 4 missed lines (regime classification edge cases).
3. `data/synthetic.py` -- 4 missed lines (synthetic data creation/provider edges).

Recommend starting with `monte_carlo/simulator.py` (2 lines). Add minimal test(s) to exercise the exact missed branches.
Keep changes test-only, run ruff + mypy + black, verify coverage for that module and full suite still green,
then update this handoff with new missed lines and proof.