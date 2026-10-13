# Task for the next Kilo agent

## Context

Quantitative Trading framework. Coverage-focused work. The previous session closed the
`backtest/trade_analysis.py` gaps (93% -> 100%) via test-only additions.

## What was done in this session

Closed the `backtest/engine.py` coverage gaps (88% -> 100%) with deterministic, offline
test additions only (no source changes to `quant_trading/`). 11 new tests added to
`tests/test_backtest_engine.py`:

- `get_default_data_manager` / `reset_default_data_manager` (engine.py:27-31, 40) --
  mocked `YFinanceProvider` so construction stays hermetic; verified lazy creation + caching + reset.
- `run()` guard paths: no data_manager (126 -> ValueError), fetch errors (139-140 ->
  RuntimeError via `FetchResult(errors=...)`), empty data (143 -> ValueError).
- `run()` loop `continue` (167) -- a `NaT` value injected into a DataFrame's DatetimeIndex
  makes `current_data` empty for that date, exercising the defensive skip. This was verified
  reachable (NaT comparisons all return False) rather than dead code.
- `_process_signal` guards (258 price None/<=0; 276-280 buy cost>cash partial-fill recalc
  and the zero-cash `quantity <= 0` return; 298 sell without holding; 302 sell with
  strength=0). Risk manager disabled where needed so the engine-level guards (not the
  risk pre-check) are the exercised path.
- `run_backtest` default-data-manager fallback (365) -- `data_manager=None, config=None`
  path; patched `get_default_data_manager` to return a fake DM backed by synthetic data.

## Verification

- `python -m coverage run -m pytest tests/ -q` -> 645 passed (was 634; +11 tests).
- `python -m coverage report -m quant_trading/backtest/engine.py` -> 147 stmts, 0 missed, **100%**.
- `quant_trading/backtest/trade_analysis.py` remains at **100%** (192 stmts, 0 missed).
- `python -m ruff check .` -> All checks passed.
- `python -m mypy quant_trading/` -> Success: no issues found in 36 source files.
- `python -m black --check tests/test_backtest_engine.py` -> clean.

## Coverage notes / constraints

- engine.py lines 270 and 362-363 show as "missed" when running
  `tests/test_backtest_engine.py` ALONE; they are covered by the full suite
  (`test_cli.py` exercises the `run_backtest(..., config=Config(...))` Config path at
  362-363; an integration run covers 270). Measured coverage = full suite.
- The default-DM path (lines 27-31) constructs a real `YFinanceProvider` only as a side
  effect (creates `./data/cache`); tests mock the class so no network and no cache dir is
  created. `reset_default_data_manager()` is called in/after each test to avoid leaking the
  module-level singleton across tests.

## What remains unresolved

None blocking. All previously-identified missed lines for `engine.py` are covered.
Remaining small pure-Python gaps (lower priority, untouched here): `config/settings.py` (2),
`data/synthetic.py` (4), `regime/detector.py` (4), `risk/limits.py` (1),
`monte_carlo/simulator.py` (2) -- total ~11 trivial lines.

## Approaches already tried

- Direct `MagicMock` data_manager for `run()` error/empty paths (simplest; avoids
  subclassing providers). Used.
- Constructing a `YFinanceProvider()` for real (no network in __init__, only cache dir).
  Replaced with mocked class to avoid side effects.
- NaT-in-index as the mechanism to reach the `continue` (167): verified empirically that
  NaT yields an empty `current_data` slice for that date.

## Next task (precise, prioritized)

Pick ONE of the remaining small gap modules and close it to 100% test-only, using the
same deterministic/offline approach:

1. `config/settings.py` -- 2 missed lines (likely `Config.from_yaml` YAML-error branch and
   the non-mapping branch; or `to_yaml`/`update` edge). Add a couple of small tests with
   malformed/missing YAML.
2. `data/synthetic.py` -- 4 missed lines (likely `create_synthetic_provider` / edge of
   `create_synthetic_data`).
3. `regime/detector.py` -- 4 missed lines.
4. `risk/limits.py` -- 1 missed line.
5. `monte_carlo/simulator.py` -- 2 missed lines.

Start with `config/settings.py` (cheapest, 2 lines) and produce the coverage report diff as
proof. Keep changes test-only (no source edits), run ruff + mypy + black, and leave the
handoff updated with the new target module's missed lines and chosen mechanism.
