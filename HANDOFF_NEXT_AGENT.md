## Session 2026-11-26 (new entry — clears `backtest/metrics.py` from the allowlist)

No new user assignment was pending. The prior handoff's "Next task" was to clear
`quant_trading/backtest/metrics.py` (`from_dict`, `to_dict`) from `_EXAMPLES_ALLOWLIST`.
That is now **complete**: neither `metrics.py` entry remains in the allowlist.

### What changed (this session)
- **`quant_trading/backtest/metrics.py`**:
  - Added a runnable `Examples:` section to `BacktestMetrics.to_dict` (single-line
    `>>>` statements; exact reprs captured from the live runtime:
    `(1000.0, 1.5, 3)` and `0.0`).
  - Rewrote `BacktestMetrics.from_dict`'s example from a multi-line dict literal
    (which used `...` continuations) to a single-line dict. The integrity guard
    parses each `>>>` line as an individual statement, so the multi-line form was
    rejected with `'{' was never closed` once the allowlist line was removed.
- **`tests/test_repository_integrity.py`** (`_EXAMPLES_ALLOWLIST`): removed the two
  lines `("quant_trading/backtest/metrics.py", "from_dict")` and
  `("quant_trading/backtest/metrics.py", "to_dict")`. 2 lines deleted.

### What was verified (this runner: Python 3.14.4 / pytest / ruff / black; deps under
`/home/runner/work/_temp/kilo-home/.local`, `export PATH="/home/runner/work/_temp/kilo-home/.local/bin:$PATH"`)
- `pytest --doctest-modules quant_trading/backtest/metrics.py` -> **7 passed**.
- `pytest tests/test_repository_integrity.py` -> **51 passed** (the only consumer of
  `_EXAMPLES_ALLOWLIST`).
- `pytest tests/test_backtest_metrics.py` -> **166 passed**.
- `ruff check` + `black --check` on both touched files -> clean / unchanged.

### What remains unresolved
- `.github/workflows/tests.yml` CI workflow is still absent; durable publication needs a
  maintainer with `workflows` permission (controller restores `.github/workflows` to
  `WORKFLOW_BASE_SHA` at session end). Do not retry commit+push of workflows.
- `_EXAMPLES_ALLOWLIST` still has ~601 entries (grandfathered debt). The
  `backtest/metrics.py` category is now empty; other categories remain (largest
  single-file counts: strategies/examples.py 130, data/yfinance_provider.py 103,
  backtest/engine.py 37, backtest/report.py ~30).

### Approaches that failed
- First attempt removed the allowlist lines without touching `from_dict`; the integrity
  guard then failed on `from_dict`'s pre-existing multi-line dict example
  (`'{' was never closed`). Fixed by collapsing that example to a single parseable
  statement. No source logic touched.

### Next task
- **Clear `quant_trading/backtest/trade_analysis.py` from the allowlist** (largest
  remaining cluster after engine/report). Inspect the allowlisted symbols' signatures,
  add runnable single-line `Examples:` sections capturing exact reprs from the live
  runtime, then remove their `("quant_trading/backtest/trade_analysis.py", ...)` lines
  and rerun `pytest --doctest-modules quant_trading/backtest/trade_analysis.py` and
  `pytest tests/test_repository_integrity.py`. Constraints: every `>>>` line must be a
  single parseable statement (no `...` continuation blocks); do not add new allowlist
  entries; do not touch `.github/workflows`.

---

## Session 2026-11-26 (prior entry — finishes the `__post_init__` allowlist reduction)

No new user assignment was pending. The prior handoff's "Next task" chain was to shrink
`_EXAMPLES_ALLOWLIST` in `tests/test_repository_integrity.py` by giving each allowlisted
`__post_init__` a real, runnable `Examples:` section and then removing its allowlist line.
That chain is now **complete**: no `__post_init__` entry remains in the allowlist.

### What changed (this session)
- **`tests/test_repository_integrity.py`** (`_EXAMPLES_ALLOWLIST`): removed the last three
  `__post_init__` entries —
  `("quant_trading/optimization/base.py", "__post_init__")` (was line 2057) and the two
  duplicate `("quant_trading/portfolio/portfolio.py", "__post_init__")` lines (were 2110-2111;
  a frozenset collapses duplicates, so both had to go to drop the entry). 3 lines deleted,
  no production logic touched.
- No source files were edited this session. The matching `Examples:` sections for
  `optimization/base.py` (`ParameterSpace`, `OptimizationResult`) and `portfolio.py`
  (`Holding`, `Portfolio`) were already added in commit `d5ee676` by the prior session; that
  session added the examples but was cut off before removing the allowlist lines. This session
  verified those examples actually pass and then removed the now-redundant allowlist lines.

### What was verified (this runner: Python 3.14.4 / pytest 9.2.0 / ruff 0.17.6 / black; deps
already installed under `/home/runner/work/_temp/kilo-home/.local`,
`export PATH="/home/runner/work/_temp/kilo-home/.local/bin:$PATH"`)
- **Doctests for the two files whose allowlist lines were removed**:
  `pytest --doctest-modules quant_trading/optimization/base.py quant_trading/portfolio/portfolio.py`
  -> **29 passed**. Across all three touched modules (incl. strategies/base.py) -> **39 passed**.
- **Guards**: `pytest tests/test_repository_integrity.py::test_documented_examples_are_valid
  tests/test_repository_integrity.py::test_examples_allowlist_names_exist` -> **2 passed**.
- **Full integrity suite** (the ONLY consumer of `_EXAMPLES_ALLOWLIST` — confirmed by grep, the
  symbol is referenced nowhere else): `pytest tests/test_repository_integrity.py` -> **51 passed**.
- **Affected module suites**: `pytest tests/test_optimization.py tests/test_portfolio.py
  tests/test_portfolio_invariants.py` -> **546 passed**.
- **Linters**: `ruff check tests/test_repository_integrity.py` -> All checks passed;
  `black --check` -> 1 file would be left unchanged.
- **Full default suite** (`pytest -q`) was NOT rerun: the change is 3 deleted lines in a test
  file whose only consumer (the integrity suite) was run in full and passed, so no other test
  can be affected. (Prior sessions' full-suite green of 5438 passed still holds for the
  committed tree; this session adds only allowlist deletions on top.)

### What remains unresolved
- `.github/workflows/tests.yml` CI workflow is still absent; durable publication needs a
  maintainer with `workflows` permission (App token cannot update workflows; controller restores
  `.github/workflows` to `WORKFLOW_BASE_SHA` at session end). Do not retry commit+push of workflows.
- The slow suite (`pytest -m "slow and not network"`) was NOT rerun; the change is
  test-file-only and does not touch slow code paths.
- `_EXAMPLES_ALLOWLIST` still has **603 entries** across many files (grandfathered debt). The
  `__post_init__` category is now empty; other categories remain (largest single-file counts:
  strategies/examples.py 130, data/yfinance_provider.py 103, backtest/engine.py 37).

### Approaches that failed
- None. Single bounded, test-file-only change; all focused and full-integrity verification
  passed on first attempt.

### Next task
- **Clear `quant_trading/backtest/metrics.py` from the allowlist** (2 entries: `from_dict`,
  `to_dict`). Inspect their signatures and add runnable `Examples:` sections, capturing exact
  reprs from the live runtime. Then remove the two
  `("quant_trading/backtest/metrics.py", ...)` lines from `_EXAMPLES_ALLOWLIST` and rerun
  `pytest --doctest-modules quant_trading/backtest/metrics.py`,
  `pytest tests/test_repository_integrity.py`. Constraints: every `>>>` line must be a single
  parseable statement; do not add new allowlist entries; do not touch `.github/workflows`.