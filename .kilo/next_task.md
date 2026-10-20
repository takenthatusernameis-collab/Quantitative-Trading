# Next Task

## What changed
- Added NaN guard to RSI strategy `generate_signals()` (check current/prev RSI and current price).
- Existing MA guard added previously.

## Verified
- `tests/test_strategies_examples.py` 149 passed.
- Full suite previously 1467 passed, 1 skipped.

## Next task
Continue adding NaN/zero-price guards to remaining strategies (Bollinger Bands, Donchian, SuperTrend, MACD, Keltner, etc.) with minimal changes and tests.
