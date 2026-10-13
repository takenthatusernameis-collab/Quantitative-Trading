# Task for the next Kilo agent

## Context

Quantitative Trading framework. Coverage-focused work. Previous sessions closed
`config/settings.py`, `risk/limits.py`, and `monte_carlo/simulator.py` to 100%
via test-only additions. Earlier this cycle closed `regime/detector.py` and
`data/synthetic.py` to 100%. This session closed `data/providers.py` to 100%.

## What was done in this session

- **`data/providers.py`** — closed 94% → 100% (8 missed lines → 0).
  Added 7 tests to `tests/test_data_providers.py`:
  - `test_fetch_result_has_missing` — `FetchResult.has_missing` property (line 50).
  - `test_data_manager_add_provider` — `DataManager.add_provider` appends to list (line 128).
  - `test_data_manager_get_provider_returns_none` — no-match returns `None` (line 135).
  - `test_data_manager_get_provider_found` — matching provider returned (covers 133-134).
  - `test_data_manager_fetch_no_provider_raises` — `ValueError` with no provider (line 157).
  - `test_data_manager_clear_cache` — `clear_cache` empties the cache (line 173).
  - `test_lazy_synthetic_provider_fetch_latest` — exercises
    `LazySyntheticProvider.fetch_latest` (lines 275-276). NOTE: the prior handoff
    assumed `mgr.fetch_latest(...)`, but `DataManager` has no `fetch_latest` method;
    the call is made on the provider directly via `mgr.providers[0].fetch_latest(...)`.
  - `test_create_data_manager_from_config_unknown_provider` — `ValueError` for unknown
    provider (line 293).

  Verified: `python -m coverage report -m --include="*/data/providers.py"` ->
  143 stmts, 0 missed, 100%.

- Full suite: `pytest tests/ -q` -> **667 passed** (+9 tests; was 658).
- Quality gates: `ruff check .` -> All checks passed!; `mypy quant_trading/` ->
  Success, no issues in 36 source files; `black --check` on modified files ->
  2 files left unchanged (clean). (15 unrelated pre-existing files in the repo
  would be reformatted by black; none of them are this session's modifications.)

## What remains unresolved

Every source module under `quant_trading/` is now at 100% coverage **except**
`data/yfinance_provider.py` (1534 stmts, 279 missed, 82%). It is a 3070-line
module whose uncovered branches are dominated by network/Alpha Vantage API paths
requiring mocks; it is too large to bound in a single session.

## Next task (precise, prioritized)

**Close `quant_trading/data/yfinance_provider.py` to 100% (or meaningfully raise it).**

This is a large, network-bound module (1534 statements, 279 missed). Approach:

1. Inspect the missed lines via
   `python -m coverage report -m --include="*/data/yfinance_provider.py"` and group
   them by method/endpoint.
2. Pick one bounded cluster of uncovered code that is offline-testable (e.g. a
   pure helper, an interval-mapping table, a `_request_key`-style transform, or a
   well-isolated method) rather than attempting the entire 279-line gap at once.
3. Add tests to `tests/test_yfinance_fetch_many.py` (or the existing Alpha Vantage
   test file), reusing the `FakeResponse`/monkeypatch patterns already present in
   `tests/test_data_providers.py` and `tests/test_yfinance_fetch_many.py`.
4. Re-run `python -m coverage report -m --include="*/data/yfinance_provider.py"`
   and the full suite + quality gates; update this handoff with the new miss count.

Constraint: keep each step small and verifiable. Do NOT attempt to mock the entire
network surface in one pass — chip away method by method.
