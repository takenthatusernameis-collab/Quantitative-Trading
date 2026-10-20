# Next Task

## What changed
- Added NaN-safe handling to `MovingAverageCrossover.generate_signals()` (check last two MA values and current price for NaN; guard division when `slow_current` is zero).
- Added `test_generate_signals_nan_values_skipped_ma` to `tests/test_strategies_examples.py` to match NaN-skip behavior of other strategies.

## Verified
- `tests/test_strategies_examples.py` 149 passed (added 1 test).
- Full suite: 1467 passed, 1 skipped.
- `ruff check` clean on modified files; `mypy` passes.

## Next task
Look for other strategies missing NaN/zero-price guards (e.g. compare edge cases across strategies) and add minimal guards + tests if missing. Prioritize deterministic, bounded changes.
