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
- None required; this fix is complete and verified. If continuing, audit the other synthetic/
  offline data paths for the same OHLC-invariant assumption: `quant_trading/data/providers.py`
  and `examples/run_backtest_offline.py` consume this data; confirm no downstream code relied
  on the previously-invalid `high < open` rows (grep for direct `high`/`low` equality asserts).
  Constraint: keep RNG draw order stable; verify with the full suite (expect 5376 passed / 3
  yfinance doctest failures) plus `ruff`/`black`/`mypy`.