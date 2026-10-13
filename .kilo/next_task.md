# Task for the next Kilo agent

## Context

Quantitative Trading framework (Python) developed by sequential Kilo agents in
a GitHub Actions loop. The working tree carries staged (uncommitted) work
from earlier sessions. The controller script (`.github/scripts/kilo-controller.sh`)
stages all worktree changes (`git add -A` with excludes), normalizes whitespace,
commits, and pushes after each session — do not commit/push manually.

## What was done in this session

**Assigned task (from prior handoff): inspect repository and select one
bounded, high-value task.**

The prior handoff declared "no remaining self-contained, verifiable work
items", but inspection found a genuine coverage gap: commit 3ee8247 added
`quant_trading/strategies/factory.py` (StrategyRegistry + global factory
functions, with built-ins `ma`/`rsi`/`bb`/`macd` registered in
`strategies/__init__.py`) with **zero test coverage** — it was the only
`quant_trading` module without a dedicated test file. `Strategy.from_config`
(base.py:97) also delegates to the factory and was untested. A prototype
confirmed the factory works, so the fix was test + documentation only.

Implemented and verified this session:

- `tests/test_strategy_factory.py` (new, 27 tests): `TestStrategyRegistry`
  (isolated instances: register/get, aliases, TypeError on non-Strategy,
  unknown-key None, get_all copy semantics, keys vs primary_keys,
  unregister removes key+aliases, noop on unknown, reregister overwrite,
  create with kwargs/via alias/unknown ValueError incl. message content);
  `TestGlobalRegistry` (built-in registrations and aliases resolve to the
  correct classes, strategy_keys, unknown key None, create_strategy with
  explicit and default params, register/unregister roundtrip with cleanup,
  get_registry identity, create_strategy unknown raises);
  `TestStrategyFromConfig` (creates strategy with name/parameters, name
  defaults to type, missing 'type' raises, unknown type raises).
- `README.md` — added a "Strategy Registry" section (API + from_config
  examples, built-in key/alias table) and listed `factory.py` in the
  project structure tree.
- `quant_trading/strategies/__init__.py` — added missing trailing newline
  (file previously ended without `\n`; cosmetic whitespace fix only).

## Verification (all run this session, after the changes)

- `python -m pytest tests/` → **435 passed** (was 408, +27).
- `python -m ruff check .` → All checks passed!
- `python -m mypy quant_trading/` → Success: no issues found in 36 source files.
- `python examples/run_backtest_offline.py` → runs correctly (unchanged behavior).
- `python examples/cli.py --offline --symbols AAPL --days 120` and
  `--list-strategies` → work correctly (CLI keeps its own hardcoded
  STRATEGIES dict; untouched by design).
- Note: `black --check` flags 21 pre-existing files repo-wide (including
  `strategies/base.py` and `strategies/factory.py`, both unmodified this
  session); black is not part of this repo's enforced checks (the controller
  runs ruff/mypy/pytest), so no black reformatting was applied.

## Next task (precise, prioritized)

The strategy factory is now fully tested and documented. Remaining
lower-priority candidates (pick ONE, scope to a single module + test file):

1. **CLI/factory integration**: `examples/cli.py` keeps a hardcoded
   `STRATEGIES` dict and its own `create_strategy(args)` (cli.py:29, 451)
   that shadows the factory's `create_strategy(key, **kwargs)`; custom
   strategies registered via `register_strategy()` are not reachable from
   the CLI. Wire the CLI to resolve strategies through the registry (keep
   the existing `--strategy` choices behavior identical for built-ins) and
   extend `tests/test_cli.py`. Risk: argparse `choices` validation and
   `run_combined` iteration both depend on `STRATEGIES`, so the change
   must preserve `parse_args` semantics.
2. More data providers (Polygon.io, Twelve Data, IEX Cloud); WebSocket
   streaming; Redis caching.

## Other remaining work (lower priority)

- All named enhancements (regime detection, Monte Carlo simulation,
  parameter optimization/walk-forward analysis, strategy factory) are
  implemented, tested, integrated, and documented.
