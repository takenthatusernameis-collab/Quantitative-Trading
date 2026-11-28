## Session 2026-11-28 (synthetic OHLC invariant bug fix)

### What changed
- `quant_trading/data/synthetic.py`: `create_synthetic_data` now clamps `high`/`low`
  so the full OHLC invariant holds on every row (`high >= max(open, close)` and
  `low <= min(open, close)`). Previously open/high/low were jittered independently
  around the close, so `high < open` or `low > open` occurred frequently
  (632 violations across 50 seeds x 50 days). The clamp is applied AFTER the same
  RNG draws in the same order, so `open`, `close`, and `volume` are byte-identical
  to the previous implementation (verified) and only invalid `high`/`low` change.
- `tests/test_synthetic.py`: strengthened `test_create_synthetic_data_ohlc_invariants`
  to assert the full invariant (`high >= max(open,close)`, `low <= min(open,close)`),
  not just `low <= close <= high`. This is a true regression test: seed=3, days=30
  (the values the test uses) produced 5 violations under the old code.

### What was actually verified (evidence)
- `pytest tests/test_synthetic.py quant_trading/data/synthetic.py --doctest-modules` -> 25 passed.
- Full suite `pytest -q -p no:cacheprovider` -> 5376 passed, 259 skipped, 151 deselected,
  3 failed in 227s. The 3 failures are pre-existing `yfinance is not installed` doctests in
  `yfinance_provider.py` (ImportError), unrelated to this change and matching the prior
  baseline exactly (no new failures, same pass count).
- `ruff check` (changed files) -> All checks passed. `black --check` -> 2 files unchanged.
  `mypy quant_trading/data/synthetic.py` -> Success: no issues.
- Direct reproduction: 0 violations after fix across 100 seeds x 60 days; `open`/`close`/
  `volume` confirmed identical to the old logic via `np.allclose`/`array_equal`.

### What remains unresolved
- The 3 `yfinance` doctest failures persist because `yfinance` is not installed in this
  environment (network/optional dep). Not actionable here without installing the dep.
- `SyntheticDataProvider.fetch` still uses `datetime.now()` for `fetched_at` (non-deterministic
  field); left as-is to avoid scope creep.

### Approaches that already failed / rejected
- Regenerating high/low from scratch (re-drawing RNG) was rejected: it would change
  `open`/`close`/`volume` and break the 187 call sites / exact-value tests. The chosen
  clamp-after-draw approach preserves all other columns exactly.

### Next task
- None required; this audit is complete and verified. `quant_trading/data/providers.py` (LazySyntheticProvider delegates to `create_synthetic_data`, now invariant-safe) and `examples/run_backtest_offline.py` (consumes synthetic data via provider) contain no direct `high`/`low` equality asserts and rely on nothing from the previously-invalid `high < open` rows. No changes were needed to either file.
- If continuing, consider addressing the remaining unresolved item above (yfinance dep). Constraint: keep RNG draw order stable; verify with the full suite (expect 5376 passed / 3 yfinance doctest failures) plus `python -m ruff`/`python -m black --check`/`python -m mypy`.

---

## Session 2026-11-28 (deterministic SyntheticDataProvider.fetch)

### What changed
- `quant_trading/data/synthetic.py`: added module-level `SYNTHETIC_FETCHED_AT = datetime(2024, 1, 1)` and stamped `SyntheticDataProvider.fetch` `MarketData.fetched_at` with it instead of `datetime.now()`. Repeated fetches now produce byte-identical `FetchResult`/`MarketData` (including `fetched_at`), restoring determinism for the synthetic/offline provider. `datetime` import still used by `create_synthetic_data` (`end_date` default), so it is retained.
- `tests/test_synthetic.py`: added `test_synthetic_provider_fetch_is_deterministic` asserting repeated `fetch` calls serialize identically and each `MarketData.fetched_at == SYNTHETIC_FETCHED_AT`; imported `SYNTHETIC_FETCHED_AT`.

### What was actually verified (evidence)
- `pytest tests/test_synthetic.py quant_trading/data/synthetic.py --doctest-modules` -> 26 passed (was 25; +1 new test).
- Consumer suite `test_data_providers.py test_backtest_engine.py test_cli.py test_integration.py test_readme.py test_optimization.py test_rebalancer_execution.py test_strategy_registry_coverage.py` -> 891 passed, 103 skipped, 3 deselected (skips/deselects are slow/network-marked, expected).
- `ruff check` (changed files) -> All checks passed. `black --check` -> 2 files unchanged. `mypy quant_trading/data/synthetic.py` -> Success: no issues.
- `datetime` still used elsewhere in synthetic.py (`create_synthetic_data` end default); no unused-import risk.

### What remains unresolved
- The 3 `yfinance` doctest failures persist because `yfinance` is not installed in this environment (network/optional dep). Not actionable here without installing the dep.

### Approaches that already failed / rejected
- None new this session. (Prior: regenerating high/low from scratch rejected for breaking RNG draw order / exact-value tests.)

### Next task
- If continuing, address the remaining yfinance dep issue. Constraint: keep RNG draw order stable; verify with the full suite (expect 5376 passed / 3 yfinance doctest failures) plus `python -m ruff`/`python -m black --check`/`python -m mypy`.

---

## Session 2026-11-28 (yfinance optional dep installed)

### What changed
- Installed `yfinance>=0.2.0` (and transitive deps) into the environment. No source changes required; the 3 pre-existing yfinance doctest failures in `quant_trading/data/yfinance_provider.py` are resolved.

### What was actually verified (evidence)
- `pytest --doctest-modules quant_trading/data/yfinance_provider.py` -> 65 passed.
- Full suite `pytest -q -p no:cacheprovider` -> 5469 passed, 170 skipped, 151 deselected, 0 failures in 239s.

### What remains unresolved
- None. Optional dependency availability is an environment concern, not a code defect.

### Next task
- None required; audit complete. If continuing, run broader property-based or integration checks as needed.