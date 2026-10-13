# Task for the next Kilo agent

## Context

Quantitative Trading framework. Coverage-focused work. Previous session closed
`config/settings.py` gaps to 100% via test-only additions to `tests/test_config.py`.

## What was done in this session

- Added `test_from_yaml_non_mapping_raises` to cover the non-mapping branch in
  `Config.from_yaml` (settings.py:82-83) and `test_filter_fields_non_dict_returns_empty`
  to cover `_filter_fields` when `values` is not a dict (settings.py:26-27).
- Verified: `python -m coverage report -m quant_trading/config/settings.py` -> 69 stmts, 0 missed, 100%.
- Full suite: `python -m pytest tests/ -q` -> 647 passed (+2 tests over prior relevant baseline).
- Quality: ruff check passed; mypy passed (36 files); black reformat of modified test passed.

## What remains unresolved

Remaining small pure-Python gaps (untouched): `data/synthetic.py` (4 missed, 90%),
`regime/detector.py` (4 missed, 97%), `monte_carlo/simulator.py` (2 missed, 98%),
`risk/limits.py` (1 missed, 98%) — total ~11 lines.

## Next task (precise, prioritized)

Pick ONE and close it to 100% test-only, using deterministic/offline approach:

1. `risk/limits.py` -- 1 missed line (cheapest). Likely an edge case in position/portfolio limit checking.
2. `monte_carlo/simulator.py` -- 2 missed lines (simulation edge cases).
3. `regime/detector.py` -- 4 missed lines (regime classification edge cases).
4. `data/synthetic.py` -- 4 missed lines (synthetic data creation/provider edges).

Recommend starting with `risk/limits.py` (1 line). Add minimal test(s) to exercise the exact missed branch.
Keep changes test-only, run ruff + mypy + black, verify coverage for that module and full suite still green,
then update this handoff with new missed lines and proof.
