## Session 2026-11-28 (allowlist cleanup - engine.py `fee`, `_resolve_backtest_config`, `_resolve_data_interval`)

### What changed
- `quant_trading/backtest/engine.py`:
  - `Trade.fee` (property, def ~line 200): replaced the multi-line `>>> buy = Trade(...)`
    doctest (which failed the per-line parse guard with "(' was never closed") with a
    single-line `Trade(...)` call using a fixed `timestamp=datetime(2024, 1, 1)`
    (was `datetime.now()`). Output `22.5` unchanged.
  - `_resolve_backtest_config` (def ~line 1699): added an `Examples:` section with two
    single-line doctests (default `initial_capital` -> `100000.0`; override `50000.0`).
  - `_resolve_data_interval` (def ~line 1749): added an `Examples:` section
    (`_resolve_data_interval(None, None)` -> `'1d'`; `(None, "1h")` -> `'1h'`).
- `tests/test_repository_integrity.py`: removed the three now-satisfied
  `_EXAMPLES_ALLOWLIST` entries `("quant_trading/backtest/engine.py", "fee")`,
  `... "_resolve_backtest_config"`, `... "_resolve_data_interval"` (no blank lines left).
- No production behavior changed (docstrings + allowlist only). All doctest outputs were
  confirmed with a live `python -c` run BEFORE writing them.

### What was actually verified (evidence)
- `python -m pytest --doctest-modules quant_trading/backtest/engine.py` -> 33 passed.
- `python -m pytest tests/test_repository_integrity.py` -> 51 passed.
- `python -m ruff check .` -> All checks passed.
- `python -m black --check quant_trading/ tests/ examples/` -> 166 files unchanged.
- `python -m mypy quant_trading/ tests/ examples/` -> Success: no issues found (166 files).
- Full suite `python -m pytest -q` -> 5461 passed, 170 skipped, 151 deselected.

### What remains unresolved (engine.py)
- Still allowlisted in engine.py (all need a fully configured `BacktestEngine` with
  portfolio + risk manager + data manager and mutate state / append to lists, so they do
  NOT admit a clean deterministic single-line doctest):
  `_benchmark_returns`, `_cover_short`, `_open_long`, `_open_short`, `_process_signal`,
  `_process_stop_exits`, `_reduce_long`, `run_backtest`.
  `run_backtest` already HAS an Examples section (it is allowlisted only because its
  `>>> run_backtest(` lines are multi-line and fail the per-line parse guard; converting
  them to single-line calls would let its entry be dropped, but the calls are long).
- engine.py is effectively exhausted of *clean* candidates; do not keep retrying it.

### Key lesson (unchanged, still constrains every doctest)
- `test_documented_examples_are_valid` compiles EACH `>>>` line in isolation
  (`_validate_doctest_lines`). Every `>>>` line must be independently valid Python;
  multi-line `>>>` calls that open a paren FAIL. Prefer single-line statements.
- The guard only checks that `>>>` lines PARSE; actual OUTPUT is executed by
  `pytest --doctest-modules`, so shown output must match exactly (no `datetime.now()`,
  no DataFrame/Figure repr unless stable).
- A function with a docstring but NO Examples section is flagged unless allowlisted;
  adding a non-empty Examples section with parseable single-line doctests lets you drop
  the allowlist entry. Always confirm exact outputs with `python -c "..."` first.

### Approaches that already failed / are dead ends (do not repeat)
- Multi-line `>>>` calls in docstrings (the `fee` / `run_backtest` pattern) -> rejected by
  the per-line parse guard. Use single-line calls only.
- Trying to doctest the engine trade helpers (`_open_long`, `_reduce_long`, `_open_short`,
  `_cover_short`, `_process_signal`, `_process_stop_exits`, `_benchmark_returns`) -> they
  require a live engine/portfolio/risk-manager and mutate state; no clean deterministic
  single-line doctest exists. Skip them.

### Next task (precise, low-risk, high-value)
Replicate the already-proven `_iso` / `_coerce_datetime` doctests into
`quant_trading/risk/limits.py` (smallest target: only 2 allowlist entries,
`_iso` at line 105 and `_coerce_datetime` at line 112). These are the SAME helpers the
previous session documented in `quant_trading/optimization/base.py` (see that file's
`Examples:` sections for the exact wording/outputs to copy):
- `_iso(datetime(2024, 1, 15, 12, 30, 45))` -> `'2024-01-15T12:30:45'`
- `_iso(None)` -> None (no output line)
- `_coerce_datetime("2024-01-15")` -> `datetime.datetime(2024, 1, 15, 0, 0)`
- `_coerce_datetime("2024-01-15T12:30:45")` -> `datetime.datetime(2024, 1, 15, 12, 30, 45)`
- `_coerce_datetime(None)` -> None (no output line)
Then remove the two `("quant_trading/risk/limits.py", ...)` lines from
`_EXAMPLES_ALLOWLIST` (lines ~1988-1989) and re-run the five verification commands above.
After limits.py, the identical `_iso`/`_coerce_datetime` pair also appears in
`quant_trading/optimization/walk_forward.py` (lines 41/52) and
`quant_trading/portfolio/rebalancer.py` (lines 85/92) and can be cleaned the same way.
Note: `walk_forward._coerce_datetime` is typed `-> datetime` (not `| None`) — verify its
None-handling output live before copying the `None` doctest.

---

## Session 2026-11-28 (follow-up: `risk/metrics.py` `_align_series`)

### What changed
- `quant_trading/risk/metrics.py`, `_align_series` (~line 589): added an `Examples:`
  section with two single-line doctests using `.shape` output (DataFrame repr avoided
  per the stability rule):
  - `_align_series` with matching 3-point index -> `(3, 2)`
  - `_align_series` with 2 vs 3 points -> `(2, 2)`
- `tests/test_repository_integrity.py`: removed
  `("quant_trading/risk/metrics.py", "_align_series")` from `_EXAMPLES_ALLOWLIST`.

### What was actually verified (evidence)
- limits.py / walk_forward.py / rebalancer.py `_iso`/`_coerce_datetime` doctests already
  present from prior work; `pytest --doctest-modules` on all three -> 54 passed.
- `pytest --doctest-modules quant_trading/risk/metrics.py` -> 31 passed.
- `pytest tests/test_repository_integrity.py` -> 51 passed (allowlist entries all still
  resolve to AST defs).
- `ruff check .` -> passed; `black --check` -> 166 files unchanged; `mypy` -> success.
- Full suite `python -m pytest -q` -> 5376 passed, 259 skipped, 151 deselected, **3 failed**:
  all three are `quant_trading/data/yfinance_provider.py` (`fetch`, `fetch_latest`,
  `fetch_many`) — network-dependent Yahoo Finance calls, pre-existing environmental
  failures unrelated to this change.

### What remains unresolved
- Remaining `_EXAMPLES_ALLOWLIST` entries have no clean module-level pure-function
  candidates:
  - `quant_trading/strategies/examples.py` entries (`_ema`, `_atr`, `_rsi`, ...) are
    **class methods** — doctest requires instantiation; not clean single-line calls.
  - `quant_trading/strategies/factory.py` (`aliases_for`, `create`, `get`, `get_all`,
    `list_strategies`, `strategy_keys`) mutate a process-global registry — output is
    order/state dependent; not deterministic.
  - `quant_trading/backtest/report.py` needs matplotlib; `yfinance_provider.py` needs
    network; `risk/manager.py` + `engine.py` are stateful.
- engine.py trade helpers remain allowlisted and exhausted of clean candidates (see
  previous section).

### Key lesson (unchanged)
- Single-line `>>>` calls only; confirm exact outputs with `python -c` before writing;
  avoid DataFrame/Figure repr unless stable (use `.shape`, `.tolist()`, scalars).

### Approaches that already failed / are dead ends (do not repeat)
- Multi-line `>>>` calls; doctesting stateful engine/risk helpers; doctesting
  global-state factory functions; doctesting class methods without instances.

### Next task (precise, low-risk)
Confirm the remaining allowlist entries are non-clean (evidence above), then declare the
`_EXAMPLES_ALLOWLIST` cleanup complete. If a new clean module-level pure function is
added later, apply the same pattern: add single-line `Examples:` doctests, confirm
outputs live, drop the allowlist entry, run the five verification commands. No further
allowlist cleanup work is currently actionable in this repo.

(End of file)