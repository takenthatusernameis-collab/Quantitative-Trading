## Session 2026-11-26 (new entry — finishes the `__post_init__` allowlist reduction)

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
- **Clear `quant_trading/backtest/trade_log.py` from the allowlist** (smallest remaining
  single-function target: 1 entry, `split_trade_log`). Add a runnable `Examples:` section to
  `split_trade_log` (def at `quant_trading/backtest/trade_log.py:73`; signature
  `split_trade_log(trades: pd.DataFrame) -> TradeLog`). It is a pure, deterministic function:
  good examples are (a) an empty/`pnl`-less frame -> empty `round_trips`
  (`split_trade_log(pd.DataFrame()).round_trips.empty` -> `True`), and (b) a tiny long round
  trip built with `pd.DataFrame({"pnl": [0.0, 5.0]})` showing `entries`/`round_trips` shapes.
  Capture exact reprs from the live runtime rather than hand-writing them. Then remove the
  `("quant_trading/backtest/trade_log.py", "split_trade_log")` line from `_EXAMPLES_ALLOWLIST`
  and rerun `pytest --doctest-modules quant_trading/backtest/trade_log.py`,
  `pytest tests/test_repository_integrity.py tests/test_trade_log.py`. Constraints: every `>>>`
  line must be a single parseable statement; do not add new allowlist entries; do not touch
  `.github/workflows`. On a fresh runner, first `pip install -e ".[dev,bayesian,reporting]"`
  before running any tests. Prefer capturing exact runtime output over hand-writing expected values.