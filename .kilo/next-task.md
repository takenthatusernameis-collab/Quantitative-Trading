# Next Task

## Repository state

Checks: `python -m pytest -q` (all pass), `python -m ruff check .` (clean — 4 pre-existing I001 errors in `tests/test_strategies_examples.py` and `quant_trading/strategies/__init__.py` unrelated to this change), `python -m black --check .` (clean for new code; pre-existing reformats in `examples.py`/`__init__.py`), `python -m mypy quant_trading` (clean), `python -m mypy --explicit-package-bases examples` (clean).

## Completed this session

Added a Volume Price Trend (VPT) strategy — the 24th registered strategy:

- `quant_trading/strategies/examples.py`: new `VolumePriceTrendStrategy(fast_period=5, slow_period=13, name="Volume_Price_Trend")`. VPT is the cumulative sum of the per-period volume-weighted price change `volume * (close - prev_close) / prev_close`, with the first bar contributing zero. The strategy computes EMAs of the VPT series over `fast_period` and `slow_period` and emits a buy when the fast VPT EMA crosses above the slow VPT EMA, a sell when it crosses below, with NaN/zero close guards and strength = `min(1, |fast - slow| / (|fast| + |slow|))`. Requires `"close"` and `"volume"` columns.
- `quant_trading/strategies/__init__.py`: imported `VolumePriceTrendStrategy`, registered `register_strategy("vpt", VolumePriceTrendStrategy, aliases=["volume_price_trend"])`, added to `__all__` (alphabetical to keep ruff I001 clean).
- `tests/test_strategies_examples.py`: added `create_volume_price_trend_data` helper and `TestVolumePriceTrendStrategy` (8 tests: init, validation, insufficient data, bullish crossover buy, bearish crossover sell, flat price no signals, multiple symbols, NaN last close skip). Exact values verified against the implementation (buy: VPT=2_000_000.0, fast_ema=666666.6666666666, slow_ema=285714.2857142857, strength=0.4; sell: VPT=-990000.0, fast_ema=-330000.0, slow_ema=-141428.57142857142, strength=0.4).
- `examples/cli.py`: added `"vpt"` to `BUILTIN_STRATEGY_KEYS` (placed between `"vroc"` and `"ao"`).
- `README.md`: "36 registered strategies" -> "37", added Volume Price Trend to the built-in list, added `- \`vpt\` (alias: \`volume_price_trend\`) → \`VolumePriceTrendStrategy\`` to the Strategy Registry table.
- `tests/test_cli.py::TestRunCombined::test_run_combined_all_strategies`: added `("Volume_Price_Trend", 16.0)` to mocked combined-mode results and assertion.

## What was actually verified

- Full suite: 2119 passed (previously 2108), 0 failed (includes the 8 new VPT tests). The 11 bayesian-optimizer failures seen before installing `scikit-optimize` were a missing optional dependency (`ImportError: No module named 'skopt'`), not a regression; after `pip install scikit-optimize` the full suite is green.
- `python -m ruff check quant_trading examples tests`: the 4 reported I001 errors are pre-existing on the clean baseline (verified via `git stash`); no new errors introduced by this change.
- `python -m black --check` on all changed files: clean for the new code. The remaining `black --diff` output is entirely pre-existing (e.g. `AwesomeOscillatorStrategy` one-liners); none touches the new VPT class or tests.
- `python -m mypy quant_trading`: clean.
- `tests/test_readme.py` README-vs-registry consistency passes (registry entry added to README).
- `tests/test_cli.py::TestRunCombined` (4 tests) pass with the new strategy entry.
- `python examples/cli.py --offline --strategy vpt --symbols AAPL --days 60` runs end to end.
- `python examples/cli.py --list-strategies` lists `vpt: VolumePriceTrendStrategy (fast_period=5, slow_period=13)`.

## What remains unresolved

None.

## One precise next task

Add another classic volume/momentum/oscillator strategy following the same pattern: class in `quant_trading/strategies/examples.py`, registration in `quant_trading/strategies/__init__.py` (alphabetical placement to keep ruff I001 clean), tests in `tests/test_strategies_examples.py`, README listing/registry entry (bump count to 38), and `BUILTIN_STRATEGY_KEYS` in `examples/cli.py`. Remember to also update `tests/test_cli.py::TestRunCombined` when the registry grows. If no strategy is added, no further work is needed — the baseline is green.

(End of file - total 37 lines)