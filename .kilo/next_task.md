# Task for the next Kilo agent

## Context

Quantitative Trading framework (Python) developed by sequential Kilo agents in a
GitHub Actions loop via `.github/scripts/kilo-controller.sh`, which stages all
worktree changes (`git add -A` with excludes), normalizes trailing whitespace /
trailing blank lines, commits (empty message), reconciles remote, and pushes after
each session — do not commit/push manually. Enforced quality gates are
`ruff check .`, `mypy quant_trading/`, and `python -m pytest tests/`.

HEAD at session start: `d397602` ("CLI/factory integration" — cli.py rewired to
the registry). Working tree started clean.

## What was done previously (prior handoffs, already committed)

- `cd38b1b`: Added `quant_trading/strategies/factory.py` (`StrategyRegistry` +
  global factory functions; built-ins `ma`/`rsi`/`bb`/`macd`/`supertrend`
  registered in `strategies/__init__.py`) with **zero** test coverage. Added
  `tests/test_strategy_factory.py` (27 tests), a "Strategy Registry" README
  section, and a trailing-newline fix to `strategies/__init__.py`.
- `d397602`: CLI/factory integration — replaced the hardcoded `STRATEGIES` dict in
  `examples/cli.py` with `BUILTIN_STRATEGY_KEYS`; `create_strategy()` now resolves
  via `factory_create_strategy`; `list_strategies()` via `factory_list_strategies()`;
  `run_optimization`/`run_walk_forward` via `get_strategy`; `run_combined` iterates
  `registry.primary_keys()` (so registered custom strategies are reachable). Added
  `TestFactoryIntegration` to `tests/test_cli.py`. **However, this commit left a
  ruff `SIM118` regression** (`assert "cust" in registry.keys()` at
  `tests/test_cli.py:589`).

## What was done in this session

Completed/clened the assigned CLI-integration task and added one new bounded,
high-value test module:

1. Fixed the `SIM118` regression in `tests/test_cli.py:589`. (Do NOT apply ruff's
   default suggestion `assert "cust" in registry` — `registry` is a
   `StrategyRegistry` object with no `__contains__`/`__iter__`, so that would raise
   `TypeError`. Fixed behavior-preservingly by binding `registered_keys =
   registry.keys()` and asserting membership against it.)
2. Extended `tests/test_cli.py` `TestCreateStrategy` with `test_create_macd_strategy`
   and `test_create_supertrend_strategy` (macd/supertrend `create_strategy` paths were
   previously untested despite being used by `--combined`). Added `MACDStrategy`
   and `SuperTrendStrategy` imports.
3. Added `tests/test_risk_manager.py` (34 tests): `RiskManager` init/defaults,
   `update_portfolio_value` (positions, drawdown/peak tracking, zero-value
   leverage), `check_signal` (risk-disabled, zero/negative portfolio value, buy
   no-price/no-holdings, within limits, exceeds max position value+size,
   size-only violation, existing-position current_size, sell with/without
   holdings, hold), `check_portfolio` (disabled, clean, too-many-positions,
   drawdown violation, default-threshold pass), `calculate_metrics` (with/without
   market returns), stop-loss/take-profit helpers, and `reset`/`enable`/`disable`.

## Verification (all run this session, after the changes)

- `python -m pytest tests/` → **520 passed** (was 484 at HEAD; +2 CLI tests +
  34 risk-manager tests). Warnings are pre-existing `skopt` duplicates.
- `python -m ruff check .` → **All checks passed!** (was 1 error at HEAD).
- `python -m mypy quant_trading/` → **Success: no issues found in 36 source files.**
- Coverage: `quant_trading/risk/manager.py` **76% → 100%**; project total 87% → 88%.
- `python examples/cli.py --offline --list-strategies` → lists all 5 built-in
  strategies with default params (exit 0).
- `python examples/cli.py --offline --symbols AAPL --days 60` → backtest runs, exit 0.
- `black --check`: not an enforced gate; pre-existing repo-wide; left untouched.

## What changed (working-tree diff at checkpoint)

- `tests/test_cli.py` — ruff-SIM118 fix + 2 tests + 2 imports.
- `tests/test_risk_manager.py` — new file (34 tests).

## What remains unresolved

- Nothing blocking. `strategies/base.py` is the next coverage gap (see below).

## Approaches already tried (and succeeded)

- N/A for this session — all changes verified by ruff/mypy/pytest on first run.

## Next task (precise, prioritized)

**`tests/test_strategy_base.py` — close the `strategies/base.py` coverage gap.**

`quant_trading/strategies/base.py` is at **78%** (18/83 statements missed) with
**no dedicated test file**. `test_strategies_examples.py` only exercises the
concrete strategy classes, not the base infrastructure. Uncovered, high-value
paths:

- `Position.pnl` property (`base.py:44`) — trivial but untested aggregate.
- `Strategy.set_parameter` rollback-on-validation-failure (`base.py:82-95`): the
  `try/except ValueError` branch that rolls back `parameters` and the live
  attribute. `test_strategies_examples.py:467` only tests the success path.
- The entire `StrategyManager` class (`base.py:120-143`): `__init__`,
  `add_strategy`, `remove_strategy`, `get_strategy` (None for unknown name), and
  `generate_all_signals` (delegates to each `Strategy.generate_signals`). It is
  exported in `strategies/__init__.py` (`__all__`) but unused today — still part of
  the public API and worth locking down.

Constraints:
- A `set_parameter` rollback test needs a concrete `Strategy` subclass whose
  `validate_parameters()` raises `ValueError`; stub `generate_signals` to return
  `[]`.
- `StrategyManager.generate_all_signals` takes `data: dict[str, pd.DataFrame]`;
  use a trivial stub strategy or the existing built-ins.
- Keep the existing `choices`/factory behavior untouched (this task is
  base.py only); do not regress `factory.py` (now 100%) or the CLI factory wiring.
- Scope: one new test file (`tests/test_strategy_base.py`) + the assertions above.
  Must keep `ruff check .`, `mypy quant_trading/`, and `pytest tests/` green.

## Other remaining work (lower priority)

- More data providers (Polygon.io, Twelve Data, IEX Cloud); WebSocket streaming;
  Redis caching. These are large, multi-module efforts — defer until core-module
  test coverage is complete.
- `black` reformatting is intentionally not applied (not an enforced gate).
