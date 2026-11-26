## Session 2026-11-26 (allowlist cleanup - monte_carlo/simulator.py)

### What changed
- Added valid, runnable SINGLE-LINE `Examples:` doctests to the 9 public
  `MonteCarloResult` methods that lacked them, and removed their 9 allowlist lines:
  - `get_percentile`, `get_confidence_interval`, `probability_of_profit`,
    `probability_of_beat_benchmark`, `expected_shortfall`, `to_dataframe`,
    `to_dict`, `from_dict` (classmethod), `summary`.
  - Each doctest constructs a `MonteCarloResult` directly from 3 `BacktestMetrics`
    sims (`total_return_pct` = -5/2/10) — no heavy backtest run needed.
- Allowlist shrank by 9 entries. Remaining simulator.py entries (10 lines):
  `__init__`, `_ensure_simulations`, `_extract_returns`, `_run_bootstrap`,
  `_run_bootstrap_parallel`, `_run_parametric`, `_run_parametric_parallel`
  (private/out-of-scope) PLUS `duration_seconds`, `run`, `run_monte_carlo`
  (kept — see failed approach below).

### What was verified (evidence)
- `pytest tests/test_repository_integrity.py --doctest-modules quant_trading/monte_carlo/simulator.py`
  -> 69 passed, 1 skipped (skip = mypy not installed).
- `python -m ruff check quant_trading/monte_carlo/simulator.py tests/test_repository_integrity.py`
  -> All checks passed.
- Full default suite `pytest -q` -> 5332 passed, 171 skipped, 151 deselected (was 5321; +11
  new doctest assertions, no regressions).

### IMPORTANT: failed approach (do not repeat)
- First attempt ALSO removed `duration_seconds`, `run`, `run_monte_carlo` from the allowlist
  (they already had Examples). This FAILED `test_documented_examples_are_valid`: those three
  docstrings contain MULTI-LINE `>>>` statements (a `BacktestResult(` call with `...`
  continuation lines). `_validate_doctest_lines` compiles each `>>>` line in ISOLATION, so the
  bare `BacktestResult(` line fails with "'(' was never closed". They were only passing before
  because the allowlist exempted them.
- Fix: restored those 3 allowlist entries. RULE: only remove an allowlist entry once its
  docstring uses exclusively single-line `>>>` statements. Existing multi-line `>>>` doctests
  (open bracket / class / def at end of a `>>>` line) MUST stay allowlisted.

### Notes for next session
- Pattern that works for dataclass result methods: build the result directly from a list of
  `BacktestMetrics(...)` instead of running a real backtest/monte-carlo. Fast + deterministic.
- Do NOT retry engine.py `__init__`/`fee`/`run_backtest`/private helpers, and do NOT use
  multi-line `>>>` statements in any function docstring you are de-allowlisting.

### Next task
Pick one more bounded module and clear its PUBLIC single-line-doctestable allowlist entries.
Good candidate (per prior handoff, still untouched):
- `quant_trading/risk/limits.py`: `add_violation`, `gross_exposure`, `leverage`, `ok`,
  `portfolio_risk`, `portfolio_risk_pct`, `position_risk` (note `check` has 2 defs; `_coerce_datetime`
  /`_iso` are private — keep). Construct a small RiskManager/result directly.
- `quant_trading/backtest/report.py`: heavier (needs matplotlib + BacktestResult); the public
  `generate_*`/`to_dict`/`from_dict` are lower priority than risk/limits.py.
Verify with `pytest tests/test_repository_integrity.py --doctest-modules <module>` and `ruff check`,
then run full `pytest -q`. Remember: only de-allowlist functions whose Examples use single-line
`>>>` statements only.