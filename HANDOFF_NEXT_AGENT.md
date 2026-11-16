## What changed (this session)

- Executed the prior handoff's "One precise next task": decided the duplicate
  Klinger example scripts and consolidated them.
  - Decision rationale: the two scripts were genuine functional duplicates.
    `diff examples/run_klinger.py examples/run_klinger_oscillator.py` differed
    only in docstrings and the strategy `name=` string; both constructed
    `KlingerOscillatorStrategy(fast_period=55, slow_period=200)` (the class
    defaults). The README's justification for the second script ("with explicit
    fast/slow periods") was factually wrong because the first already passed
    explicit periods.
  - Change: deleted `examples/run_klinger_oscillator.py` and removed its README
    "Example Scripts" subsection (README -9 lines). The surviving
    `examples/run_klinger.py` and its README description are accurate (verified
    the strategy's `generate_signals` really does buy on fast> slow EMA cross
    and sell on the opposite cross).
- Added a durable regression guard so this class of defect cannot return:
  `test_no_duplicate_single_strategy_example_scripts` in
  `tests/test_repository_integrity.py`, plus helpers
  `_strategy_demo_signature`, `_strategy_demo_signatures`,
  `_duplicate_single_strategy_signatures` and the `_StrategySignature` alias.
  - It fails if two `examples/run_*.py` scripts each construct exactly one
    strategy with the same class and arguments (AST-structural; the cosmetic
    `name=` kwarg is ignored). Multi-strategy demos (`run_backtest*`, which
    legitimately share `RSIStrategy`/`BollingerBandsStrategy`) and zero-strategy
    demos are exempt.
  - Includes an in-memory negative control so the detector is proven to fire.

## What was actually verified (evidence)

- Guard detects the original defect: temporarily recreated the duplicate
  (`cp examples/run_klinger.py examples/run_klinger_oscillator.py`) ->
  `test_no_duplicate_single_strategy_example_scripts` FAILED with
  `KlingerOscillatorStrategy (('fast_period', 'Constant(value=55)'),
  ('slow_period', 'Constant(value=200)')): ['run_klinger.py',
  'run_klinger_oscillator.py']`; removed it -> PASSED.
- Focused suite
  `python -m pytest tests/test_repository_integrity.py tests/test_readme.py
  tests/test_example_scripts_run.py tests/test_strategy_registry_coverage.py -q`
  -> 115 passed.
- Slow smoke `python -m pytest tests/test_examples_smoke.py -m slow -q`
  -> 135 passed.
- Full default suite `python -m pytest -q` -> 3993 passed, 142 deselected
  (previous post-deletion baseline was 3992/142; +1 = the new guard; deselected
  went 144 -> 142 because one fewer slow example script exists).
- `python -m ruff check .` -> All checks passed.
- `python -m black --check tests/test_repository_integrity.py` -> clean
  (formatted only the newly added lines).
- `python -m mypy tests/test_repository_integrity.py` -> Success;
  `python -m mypy quant_trading` -> Success (39 source files).

## What remains unresolved / not verified

- Nothing blocking. Repo is green.
- `black` version drift (pre-existing, deliberately not touched): installed
  black is 26.10.1; `black --check .` reports 9 files would be reformatted:
  `quant_trading/strategies/factory.py`,
  `quant_trading/portfolio/rebalancer.py`,
  `quant_trading/strategies/examples.py`, `examples/cli.py`,
  `tests/test_backtest_report.py`, `tests/test_rebalancer_risk_integration.py`,
  `tests/test_strategy_factory.py`, `tests/test_risk_manager.py`,
  `tests/test_cli.py`.
  `pyproject.toml` declares `black>=23.0.0` (no upper bound) with
  `[tool.black] line-length=100, target-version=['py310']`, and
  `.github/workflows/main.yml` runs the Kilo controller (no lint/format gate),
  so this drift is invisible to CI. Reformatting would be unrelated churn.

## Approaches that already failed and why

- No failed approaches this session.
- Considered and rejected: a generic "unique (class, kwargs) signature across
  ALL example scripts" guard. Empirical analysis
  (`/tmp/analyze_sigs.py`, since removed) showed it would false-positive on
  `run_backtest.py` / `run_backtest_offline.py`, which legitimately reuse
  `RSIStrategy(period=14, overbought=70, oversold=30)` and
  `BollingerBandsStrategy(period=20, std_dev=2.0)`. The implemented guard is
  therefore restricted to single-strategy scripts (verified zero collisions).

## One precise next task

- Make `black --check .` reproducible, i.e. turn the deferred formatting
  decision into a deliberate, committed choice.
  - Evidence: black 26.10.1 reports the 9 files listed above would be
    reformatted; `black>=23.0.0` is unbounded; CI runs no format gate.
  - Constraints: keep the change minimal and reversible, and choose exactly one
    path (do not mix):
    (a) pin an upper bound in `[project.optional-dependencies].dev` that matches
        the committed formatting (e.g. `black>=23.0.0,<26`), or
    (b) reformat the 9 files with the installed black and accept the churn.
  - Verify: `python -m black --check .` exits clean and `python -m pytest -q`
    stays green (expect 3993 passed / 142 deselected).