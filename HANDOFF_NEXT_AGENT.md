## Status

Verified green on 2026-11-18. Repository remains at 100% statement/branch
coverage with a clean mypy/black/ruff gate.

## What changed

Added a 49th built-in strategy, `FisherTransformStrategy` (Ehlers' Fisher
Transform of the median price with a one-bar signal line and bullish/bearish
crossovers), keyed as `fisher` with alias `fisher_transform`.

Files touched:

- `quant_trading/strategies/examples.py` — new `FisherTransformStrategy` class
  (validation, `_calculate_fisher_transform`, `generate_signals`) plus an
  `Examples:` doctest on the private calculator (the repository integrity guard
  requires every docstring to carry one).
- `quant_trading/strategies/__init__.py` — import, `__all__`, and
  `register_strategy("fisher", ...)`.
- `examples/run_fisher_transform.py` — offline deterministic demo.
- `examples/cli.py` — `fisher` added to `BUILTIN_STRATEGY_KEYS` (combined mode).
- `tests/test_strategies_examples.py` — `TestFisherTransformStrategy` covering
  init/validation/insufficient data/missing columns/NaN guards/buy + sell
  crossovers/no-cross/multi-symbol.
- `tests/test_repository_integrity.py` — `fisher` added to
  `_STRATEGIES_WITHOUT_DEDICATED_CLI_FLAGS` (config-file-only strategy, same as
  most non-MA/RSI strategies).
- `tests/test_strategy_registry_coverage.py` — docstring count 48 → 49 and the
  `fisher_transform` alias mapping.
- `tests/test_cli.py` — `Fisher_Transform` added to the mocked combined-mode
  results and the output assertion.
- `README.md` — feature count 48 → 49, registry bullet, Example Scripts entry.

Commit: see the commit named `feat(strategies): add Fisher Transform strategy`.

## What was actually verified

- `MPLBACKEND=Agg python -m pytest -q -p no:cacheprovider`
  -> **4126 passed, 144 deselected, 0 failed** (5m24s).
- `COVERAGE_CORE=sysmon python -m coverage run --source=quant_trading -m pytest ...`
  -> **TOTAL 100%** (8930 stmts, 0 miss, 3150 branches, 0 partial).
- `python -m mypy quant_trading examples tests` -> **no issues in 163 files**.
- `python -m black --check quant_trading examples tests` and
  `python -m ruff check quant_trading examples tests` -> clean.
- `MPLBACKEND=Agg python examples/run_fisher_transform.py` -> runs end to end
  (+3.39% on seeded synthetic data).

## Gotchas discovered this session (apply to the next strategy)

Adding a strategy touches more than the class:

1. `examples/cli.py` `BUILTIN_STRATEGY_KEYS` (combined mode runs every key).
2. Every example script must be referenced in the README Example Scripts section
   (`tests/test_readme.py::TestReadmeExampleScripts`).
3. README feature-count bullet and
   `tests/test_strategy_registry_coverage.py` module docstring both pin the
   strategy count.
4. Every new public/private function docstring in `quant_trading/` or
   `examples/` must contain a non-empty, parseable `Examples:` doctest
   (`tests/test_repository_integrity.py::test_documented_examples_are_valid`);
   the allowlist must not be extended for new code.
5. Strategies with tunable `__init__` params but no dedicated CLI flags must be
   added to `_STRATEGIES_WITHOUT_DEDICATED_CLI_FLAGS` in
   `tests/test_repository_integrity.py`.
6. The mocked combined-mode result list in
   `tests/test_cli.py::TestRunCombined::test_run_combined_all_strategies` is a
   static snapshot and needs one new `(name, return_pct)` entry.
7. `tests/test_strategy_registry_coverage.py` requires an example script that
   imports the class and a `Test<ClassName>` in `tests/test_strategies_examples.py`.

## Environment note

The runner is reset between sessions and starts without pandas/numpy/pytest or
the dev extras. Reinstall before verification:

```bash
python -m pip install "pandas>=2.0.0" "numpy>=1.24.0" "yfinance>=0.2.0" \
  "pytest>=7.0.0" "black>=26.0.0,<27" "ruff>=0.1.0" "mypy>=1.0.0" \
  "pandas-stubs>=3.0.0" "types-requests" "types-PyYAML" \
  "matplotlib>=3.7.0" "scikit-optimize>=0.10.0" "coverage>=7.6"
```

## Remaining work / unresolved

None for the Fisher Transform addition. One pre-existing observation: the
`trix` registration has no aliases and the README already reflects that; no
action needed.

## One precise next task

Add a 50th built-in strategy: `KSTStrategy` ("Know Sure Thing"), keyed `kst`
with alias `know_sure_thing`, in `quant_trading/strategies/examples.py`.

- KST = SMA(ROC(10), 10) + 2*SMA(ROC(15), 10) + 3*SMA(ROC(20), 10)
  + 4*SMA(ROC(30), 15); signal = SMA(KST, 9).
- Buy when KST crosses above its signal line, sell when it crosses below;
  skip symbols with insufficient history or NaN KST/signal.
- Defaults: `signal_period=9`, name `"KST"`; validate `signal_period > 0`.
- Apply the full checklist in "Gotchas discovered this session" (README count
  49 → 50, registry bullet, example script, CLI key, allowlist entry, combined
  mock entry, `TestKSTStrategy`, doctests).
- Verify with: full pytest under `MPLBACKEND=Agg`, coverage 100% via
  `COVERAGE_CORE=sysmon`, `mypy quant_trading examples tests`, `black --check`,
  `ruff check`, and run the new example script offline.
