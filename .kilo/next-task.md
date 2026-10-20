# Next Task

## What changed
- Added NaN/zero-price guards to the remaining strategies in `quant_trading/strategies/examples.py`:
  - `BollingerBandsStrategy.generate_signals`: skip when price/upper/lower/sma is NaN or zero.
  - `SuperTrendStrategy.generate_signals`: skip when price/supertrend/trend is NaN or price is zero.
  - `MACDStrategy.generate_signals`: skip when MACD/signal/hist/price is NaN or price is zero; zero-signal strength fallback added.
  - `DonchianChannelStrategy.generate_signals`: skip when any channel/price value is NaN or zero.
  - `KeltnerChannelStrategy.generate_signals`: skip when EMA/channel/price is NaN or zero.
  - `IchimokuCloudStrategy.generate_signals`: skip when price/tenkan/kijun/senkou is NaN or kijun is zero.
  - `ParabolicSARStrategy.generate_signals`: skip when SAR/trend/price is NaN or price is zero.
  - `EMACrossover.generate_signals`: added NaN price guard.
  - `VWAPStrategy.generate_signals`: added zero-VWAP/zero-price guard.
- Added 15 tests to `tests/test_strategies_examples.py` covering NaN and zero-price skips for each modified strategy.
- Fixed two `mypy` `var-annotated` errors (`signals: list[Signal] = []`) introduced by the guard additions.

## Verified
- `tests/test_strategies_examples.py`: 164 passed (was 149).
- Full suite: 1482 passed, 1 skipped.
- `ruff check quant_trading/ tests/`: clean.
- `mypy quant_trading/`: clean (36 source files).
- `python examples/run_backtest_offline.py`: runs successfully.

## Next task
The NaN/zero-price guard work across the 14 built-in strategies is now complete. Pick a bounded, high-value task from the repo — e.g. review `examples/` or `quant_trading/` for a missing test, a deterministic bug, or a small hardening improvement — implement, and verify with the relevant test command (`pytest tests/ -q`, `ruff check`, `mypy quant_trading/`).