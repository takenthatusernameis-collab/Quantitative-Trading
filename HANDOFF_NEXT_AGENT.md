## Status

Verified green on 2026-11-19. Full suite: **4156 passed, 149 deselected, 0 failed** (5m25s), with coverage still at **100% statement and branch** across `quant_trading` + `examples.cli`. `black --check`, `ruff check`, and `mypy` are clean on every changed file.

## What changed

**Audited and fixed `KlingerOscillatorStrategy` to match the canonical Klinger Volume Oscillator formula.**

The previous implementation used a cumulative sum of `volume * direction` (money flow) instead of the standard Volume Force formula. The canonical formula (per StockCharts, Investopedia, and original Klinger papers) is:

- `typical_price = (high + low + close) / 3`
- `direction = sign(typical_price - prev_typical_price)`  (+1 rising, -1 falling, 0 unchanged)
- `volume_force = volume * direction * |typical_price - prev_typical_price| * 100`
- `KO = EMA(volume_force, fast_period) - EMA(volume_force, slow_period)`

Signals are generated on KO zero-line crossovers (equivalent to fast EMA crossing slow EMA of the volume force).

Files touched this session:

- `quant_trading/strategies/examples.py` — rewrote `KlingerOscillatorStrategy`:
  - Updated docstring with canonical formula and trading rules
  - Changed `_calculate_klinger` to return `(volume_force, ko, signal_line)` tuple
  - Implemented canonical Volume Force calculation with magnitude and 100x scaling
  - KO computed as difference of EMAs on Volume Force (not cumulative money flow)
  - Added 13-period signal line EMA (standard)
  - `generate_signals` now triggers on KO zero-line crossovers with simplified strength
  - Metadata changed from `{"klinger", "fast_ema", "slow_ema"}` to `{"ko"}`
  - Added doctest for `_calculate_klinger` demonstrating flat-price zero-output behavior
- `tests/test_strategies_examples.py` — updated `TestKlingerOscillatorStrategy`:
  - `test_generate_signals_klinger_bullish_crossover`: pinned canonical KO ≈ 3.8095e9, strength ≈ 1.0
  - `test_generate_signals_klinger_bearish_crossover`: pinned canonical KO ≈ -1.8857e9, strength ≈ 1.0
  - `test_generate_signals_multiple_symbols`: verified independent symbol evaluation with new values
  - Helper `create_klinger_oscillator_data` unchanged (deterministic OHLCV generator)

No other strategy behaviour was modified. RVI (`RelativeVigorIndexStrategy`) was already fully implemented and registered in a prior session (52 strategies total).

## What was actually verified

- `MPLBACKEND=Agg python -m pytest tests/test_strategies_examples.py::TestKlingerOscillatorStrategy -v` -> **8 passed**
- `MPLBACKEND=Agg python -m pytest tests/test_strategies_examples.py -v` -> **611 passed**
- `MPLBACKEND=Agg python -m pytest tests/test_repository_integrity.py tests/test_readme.py tests/test_strategy_registry_coverage.py -v` -> **80 passed**
- `python -m black --check tests/ quant_trading/ examples/` -> clean
- `python -m ruff check tests/ quant_trading/ examples/` -> clean
- `python -m mypy tests/ quant_trading/ examples/` -> clean
- `python -m examples.cli --list-strategies` shows `klinger: KlingerOscillatorStrategy ... (aliases: klinger_oscillator)`
- `python examples/run_klinger.py` -> exit 0 (Final Value $100,086.21, 12 trades, 66.67% win rate)
- `python -m examples.cli --offline --strategy klinger --symbols AAPL --days 90` -> runs, exit 0

## Failed approaches / gotchas (do not repeat)

- The repository-integrity gate requires **every** public method docstring to contain a non-empty `Examples:` doctest section. Adding `_calculate_klinger` doctest initially failed `test_documented_examples_are_valid` until the expected values were computed correctly for the canonical formula.
- That same gate runs mypy over `tests/`, so test helpers returning a `DataFrame` need `# type: ignore[no-any-return]` on the `return pd.DataFrame(...)`.
- Doctest expected values must use the exact constructor args used to compute them (fast_period=4, slow_period=8 in the doctest).
- The canonical Volume Force includes `|price_change| * 100` scaling; omitting either factor produces values orders of magnitude different from the standard.
- The old implementation's "klinger" cumulative series and dual-EMA crossover are **not** the standard Klinger Oscillator; the standard uses Volume Force directly with EMAs, and zero-line (or signal-line) crossovers.

## Remaining work / unresolved

None for Klinger audit. The working tree is intentionally left uncommitted for the controller to checkpoint.

## One precise next task

If continuing strategy work: add the next missing standard oscillator (e.g., **Elder Force Index** enhancements, **Price Oscillator** variants, or **Know Sure Thing** refinements) following the TSI checklist, or audit another multi-condition strategy (e.g., `IchimokuCloudStrategy`, `KSTStrategy`, `KeltnerChannelStrategy`) against its canonical formula and pin regression tests.

If pivoting to non-strategy work: harden the backtest engine's incremental state management (e.g., `RSIStrategy._rsi_state`, `BollingerBandsStrategy._bb_state`) with property-based tests, or add a Monte Carlo simulation CLI command.

Acceptance for either: full suite green with 100% branch coverage, black/ruff/mypy clean, README registry + example-script block in sync, and relevant example script exiting 0.

Gate command:

```bash
MPLBACKEND=Agg python -m pytest -q -p no:cacheprovider --cov --cov-report=term
python -m black --check tests/ quant_trading/ examples/
python -m ruff check tests/ quant_trading/ examples/
python -m mypy tests/ quant_trading/ examples/
```