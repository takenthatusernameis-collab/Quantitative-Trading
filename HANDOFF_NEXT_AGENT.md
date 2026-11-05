# Handoff to next agent

## What changed
- Added `__all__` to `quant_trading/backtest/engine.py` (6 public names) and `quant_trading/data/providers.py` (5 public names), matching existing style.

## Verified
- Doctests for both modules: 13 passed.

## Next task
Continue audit of remaining modules lacking `__all__` (risk/, portfolio/, optimization/, monte_carlo/, regime/, config/, utils/, data synthetic/yfinance). Add only where clarifies intent; verify doctests.
