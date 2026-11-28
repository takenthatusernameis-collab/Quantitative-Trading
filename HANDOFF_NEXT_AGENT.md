## Session 2026-11-28 (synthetic_end_date serialization round-trip fix)

### What changed
- `quant_trading/config/settings.py`: `DataConfig.from_dict` now converts a string
  `synthetic_end_date` back to `datetime` via `datetime.fromisoformat` before
  constructing the dataclass. `to_dict` already serialized the field to an ISO string
  (commit 34aa422), but `from_dict` passed the string straight to the constructor, where
  `__post_init__` rejects non-`datetime` values. This broke `DataConfig.from_dict(d.to_dict())`,
  `Config.from_dict`, and `Config.update(data={...})` whenever `synthetic_end_date` was set
  (`ValueError: invalid synthetic_end_date: must be a datetime or None (got str)`).
  The `from_yaml` path was unaffected because PyYAML auto-parses ISO timestamps to
  `datetime`; the fix keeps `from_dict` consistent with it. Added a doctest line asserting
  the default is `None`.
- `tests/test_config.py`: added `TestDataConfigSyntheticEndDateSerialization` with 5 tests:
  `from_dict` round-trip (incl. time component), `to_dict` emits ISO string,
  `from_dict` parses ISO string, `Config.update(data=...)` merge, and YAML round-trip.

### What was actually verified (evidence)
- Direct repro before fix: `DataConfig.from_dict(DataConfig(synthetic_end_date=datetime(2024,6,1)).to_dict())`
  raised `ValueError ... (got str)`. After fix: round-trips equal; `Config.update` and
  `Config.to_yaml`/`from_yaml` also verified equal via a one-off script.
- `pytest tests/test_config.py` -> 220 passed. `pytest --doctest-modules quant_trading/config/settings.py`
  -> 29 passed.
- Full suite `pytest -q -p no:cacheprovider` -> 5474 passed, 170 skipped, 151 deselected,
  0 failures in 253s (was 5469 passed; +5 new tests, no new failures).
- `ruff check` (changed files) -> All checks passed. `black --check` -> 2 files unchanged.
  `mypy quant_trading/config/settings.py` -> Success: no issues.

### What remains unresolved
- None. (Historical note: earlier sessions' 3 yfinance doctest failures were resolved by
  installing the optional dep; current baseline has 0 failures.)

### Approaches that already failed / rejected
- None new this session.

### Next task
- None required; suite is green. If continuing, audit other dataclass configs for fields
  whose `to_dict` emits a non-JSON-native type that `from_dict` does not reconstruct
  (only `DataConfig.synthetic_end_date` currently does this). Constraint: keep `to_dict`
  output JSON-safe and `from_dict` its exact inverse; verify with the full suite
  (expect 5474 passed / 0 failures) plus `python -m ruff`/`python -m black --check`/`python -m mypy`.

---

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

---

## Session 2026-11-28 (CLI offline monte-carlo/trade-analysis failures + black formatting)

### What changed
- `quant_trading/data/providers.py:921`: `LazySyntheticProvider._ensure_initialized` now defaults `end_date` to `datetime.now()` instead of `datetime(2024, 1, 1)` when `synthetic_end_date` is not set. Previously the generated synthetic data ended at 2024-01-01 while the CLI's `--days` fetch window is relative to `now` (2026), so `provider.fetch` returned empty DataFrames. The backtest then produced a 1-point equity curve (< 2 returns), making `MonteCarloSimulator._extract_returns` raise "Insufficient data for Monte Carlo simulation" and leaving all metrics at 0.0 (trade Sharpe identical across risk-free-rate/periods-per-year configs). This is consistent with `create_synthetic_data`'s own `end = end_date or datetime.now()` default (synthetic.py:147); price values are unchanged (seeded RNG), only the index dates shift.
- `quant_trading/config/settings.py`: applied `black` reformatting (one line wrapped) so `test_repository_is_black_formatted` passes.

### What was actually verified (evidence)
- Direct CLI repro: `python examples/cli.py --offline --monte-carlo --mc-simulations 60 --mc-seed 42 --symbols AAPL --days 120` now prints "Probability of Profit: 76.67%" with no error (previously "Error running backtest: Insufficient data for Monte Carlo simulation", exit 1).
- Previously failing tests now pass: `test_main_offline_monte_carlo_analysis`, `test_main_offline_trade_analysis`, `test_main_trade_analysis_uses_the_configured_risk_free_rate`, `test_main_trade_analysis_uses_the_configured_periods_per_year`, `test_main_combined_monte_carlo_and_trade_analysis`, `test_main_combined_monte_carlo_uses_the_configured_risk_free_rate`, `test_main_combined_trade_analysis_uses_the_configured_periods_per_year`, `test_offline_single_mode_with_analyses_and_output`, all `test_readme_cli_commands.py` monte-carlo commands (121 passed, 5 skipped, 3 deselected).
- Full suite `pytest -q -p no:cacheprovider` -> 5469 passed, 170 skipped, 151 deselected, 0 failures in 253s (matches the pre-regression baseline exactly).
- `ruff check` (changed files) -> All checks passed. `mypy quant_trading/data/providers.py quant_trading/config/settings.py` -> Success. `black --check quant_trading/ examples/` -> 100 files unchanged.

### What remains unresolved
- None.

### Approaches that already failed / rejected
- None new this session.

### Next task
- None required; the suite is green. If continuing, consider broader property-based or integration checks.