# Task for the next Kilo agent

## Context

Quantitative Trading framework. Coverage-focused work. Previous session closed
`config/settings.py` gaps to 100% via test-only additions to `tests/test_config.py`.
Earlier session closed `risk/limits.py` to 100% via test-only additions to `tests/test_limits.py`.
This session closed `monte_carlo/simulator.py` to 100% via test-only additions to `tests/test_monte_carlo.py`.

## What was done in this session

- Added tests to `tests/test_monte_carlo.py`:
  - `test_monte_carlo_result_to_dataframe_empty` - covers empty simulations case (exercises branch when simulations is empty)
  - `test_monte_carlo_result_summary_empty` - covers empty simulations summary case
- Verified: `python -m coverage report -m quant_trading/monte_carlo/simulator.py` -> 106 stmts, 0 missed, 100% (was 98%, 2 missed lines 61, 68).
- Full suite: `python -m pytest tests/ -q` -> 651 passed (+2 tests).
- Quality: ruff check passed; mypy passed; black passed on modified test file.

## What remains unresolved

Remaining small pure-Python gaps (untouched):
- `data/synthetic.py` (4 missed, 90%) - lines 88, 92, 102-103
- `regime/detector.py` (4 missed, 97%) - lines 59, 70, 107, 113
Total ~8 lines.

## Next task (precise, prioritized)

Pick ONE and close it to 100% test-only, using deterministic/offline approach:

1. `regime/detector.py` -- 4 missed lines (regime classification edge cases).
2. `data/synthetic.py` -- 4 missed lines (synthetic data creation/provider edges).

Recommend starting with `regime/detector.py` (4 lines). Add minimal test(s) to exercise the exact missed branches.
- Line ~59: `if not isinstance(prices, pd.Series): prices = pd.Series(prices)` - test with non-Series input
- Line ~70: `if len(returns) < 1: return RegimeResult()` - test case where after pct_change/dropna we get < 1 element
- Lines ~107, 113 in label logic - edge cases around thresholds and NaN handling

Keep changes test-only, run ruff + mypy + black, verify coverage for that module and full suite still green,
then update this handoff with new missed lines and proof.
