## Session 2026-11-27 (allowlist cleanup - backtest/analysis.py from_dict)

### What changed
- Added a confirmed-output, single-line `Examples:` section to the public
  `BacktestRegimeAnalysis.from_dict` classmethod docstring in
  `quant_trading/backtest/analysis.py:380` (all `>>>` statements single-line;
  outputs confirmed by the passing doctest run: `n_segments` -> `1`,
  `current_regime.value` -> 'bull_low_vol', `to_dict()["current_regime"]` ->
  'bull_low_vol', `len(to_dataframe())` -> `1`).
- Removed the `("quant_trading/backtest/analysis.py", "from_dict")` entry from
  `_EXAMPLES_ALLOWLIST` in tests/test_repository_integrity.py.
- Allowlist shrank by 1 line.

### What remains allowlisted in backtest/analysis.py (8 lines)
- `analyze_regimes`, `current_regime`, `n_segments`, `regime_for_backtest`,
  `segments`, `summary`, `to_dataframe`, `to_dict` (all have multi-line
  `...`-continuation Examples blocks; de-allowlisting requires a single-line
  rewrite first).

### What remains allowlisted in regime/detector.py (5 lines)
- `__init__` (docstring but NO Examples section yet; needs a single-line
  doctest before it can be de-allowlisted).
- `_build_segments`, `_label_series`, `_make_segment`, `_merge_segments`
  (private; do NOT de-allowlist - not public API).

### What was verified (evidence)
- `python -m pytest tests/test_repository_integrity.py --doctest-modules
  quant_trading/backtest/analysis.py` -> 63 passed, 1 skipped.
- `python -m pytest tests/test_repository_integrity.py -k "examples or
  allowlist"` -> 3 passed.
- `python -m ruff check quant_trading/backtest/analysis.py
  tests/test_repository_integrity.py` -> All checks passed.
- `python -m black --check quant_trading/backtest/analysis.py
  tests/test_repository_integrity.py` -> 2 files unchanged.
- Full `python -m pytest -q` -> 5279 passed, 260 skipped, 151 deselected
  (0 failures).

### IMPORTANT: failed approach / constraints (do not repeat)
- Do NOT try to de-allowlist private methods - they are not public API.
- Do NOT de-allowlist `__init__` until it gains a non-empty Examples section
  (the guard flags docstring-having functions without Examples unless
  allowlisted).
- Only de-allowlist functions whose Examples use single-line `>>>` statements
  only, and confirm exact output first.
- Ruff uses default rules (no E501), so long single-line `>>>` lines are fine;
  black does not reformat docstring content.

### Notes for next session
- Pattern that works: build objects directly, keep each `>>>` single-line,
  confirm exact output first.
- Non-deterministic outputs (e.g. `pd.Timestamp.now()` defaults used by
  `from_dict`) must be avoided in doctests by providing explicit values.

### Next task
Pick one more bounded public module and clear its allowlist entries. Scan
`_EXAMPLES_ALLOWLIST` (tests/test_repository_integrity.py ~line 1787) for a
public function with a docstring but NO Examples section (the guard enforces
these unless allowlisted). Good candidates: `quant_trading/risk/manager.py`
public entries (e.g. `calculate_metrics`, `clear_returns`, `disable`, `enable`,
`get_position_stop_loss`, `get_position_take_profit`, `reset`,
`reset_returns`, `should_stop_loss`, `should_take_profit`, `total_value`) or
`quant_trading/backtest/analysis.py` multi-line Examples rewrites. Add a
confirmed-output single-line doctest, then de-allowlist. Verify with
`python -m pytest tests/test_repository_integrity.py --doctest-modules
<module>`, `ruff check`, then full `python -m pytest -q`.

(End of file)
