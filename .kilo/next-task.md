# Next Task

## Repository state

Checks: `python -m pytest -q`, `python -m ruff check .`, `python -m black --check .`, `python -m mypy quant_trading examples`.

Baseline: 1994 passed, 0 failed; ruff clean, black clean, mypy clean (56 files).

## Completed this session

- Added `test_every_example_script_is_documented` and
  `test_no_undocumented_example_scripts_are_advertised` to
  `tests/test_readme.py`: every `examples/run_*.py` script must be referenced
  in the README and no README reference may point at a missing script.
- Documented `examples/run_optimization.py` in the README "Example Scripts"
  section, describing the grid search over MA fast/slow periods (maximizing
  Sharpe) and the walk-forward re-optimization over sliding windows.

## Next task (one precise item)

None outstanding. The example-script / README sync guard and the missing
`run_optimization.py` entry are complete and verified.

(End of file - total 16 lines)