## Status

Completed the task: added a new, self-contained risk metric
`calculate_ulcer_index` to `quant_trading/risk/metrics.py`, exported it from the
module's `__all__`, and added a thorough unit-test class for it in
`tests/test_risk_metrics.py`.

The Ulcer Index is a well-known downside-risk measure (root-mean-square of the
percentage drawdowns from the running peak of an equity curve). It complements
the existing drawdown/risk metrics (`calculate_max_drawdown`, `calculate_var`,
`calculate_cvar`, `calculate_omega_ratio`, ...) by accounting for the depth
*and duration* of drawdowns rather than only the single deepest point.

This task was chosen after the prior handoff reported that the `quant_trading`
library is already at 100% branch coverage with no remaining bounded coverage
gap. A new strategy was rejected as too large/risky for one session (it would
have to satisfy ~8 cross-file invariants: registry, `BUILTIN_STRATEGY_KEYS`,
`_STRATEGIES_WITHOUT_DEDICATED_CLI_FLAGS`, README registry/count/example-script
locks, and a dedicated example script). A new standalone risk metric is bounded,
genuinely useful, and touches only one source file.

## What changed

- `quant_trading/risk/metrics.py`
  - Added `calculate_ulcer_index(equity_curve: pd.Series) -> float` with a full
    docstring (Args/Returns/Examples). It drops NaNs, computes
    `sqrt(mean(drawdown**2))` where `drawdown = (equity - cummax) / cummax`,
    and returns `0.0` for empty/all-zero-peak curves or a non-finite result.
  - Added `"calculate_ulcer_index"` to `__all__` (kept alphabetical).
  - Placement note: the function is inserted **after** `calculate_all_metrics`
    and immediately before `__all__` on purpose. `tests/test_repository_integrity.py`
    pins several `risk/metrics.py` functions to exact line numbers in
    `_EXAMPLES_ALLOWLIST`; inserting earlier would have shifted those line
    numbers and broken `test_documented_examples_are_valid`. This location shifts
    only the `__all__` assignment (not line-pinned).
- `tests/test_risk_metrics.py`
  - Imported `calculate_ulcer_index`.
  - Added `TestCalculateUlcerIndex` (12 tests): manual RMS cross-check, exact
    known value (`0.10365231137264891`), monotonic-increasing == 0, deeper
    drawdown scores higher, longer-duration drawdown scores higher, empty,
    single-value, NaN-dropped, all-zero, zero-then-positive (no NaN), and
    non-negativity.

Deliberately **not** done (to keep scope minimal and avoid breaking invariants):
- Not wired into `calculate_all_metrics` / `RiskMetrics` (that would change the
  `RiskMetrics.to_dict()` key set, which `tests/test_risk_metrics.py` asserts
  equals `RiskMetrics().to_dict().keys()`, and would ripple into
  `backtest/metrics.py` and the report). Left as a standalone function like
  `calculate_omega_ratio`'s siblings.
- Not re-exported from `quant_trading/risk/__init__.py` (that `__init__` only
  re-exports the risk-attribution subset, not the basic ratio metrics).
- README not edited (no guard requires it; the function is documented via its
  docstring).

## What was verified

- `python -m pytest tests/test_risk_metrics.py -q` -> **127 passed**
  (includes the 12 new Ulcer tests).
- `python -m pytest tests/test_repository_integrity.py tests/test_readme.py -q`
  -> **67 passed** (docstring `Examples` guard, `__all__` export/resolve guards,
  README sync guards all green; confirms no line-number allowlist drift and that
  the package import graph + `__all__` resolution still hold).
- `python -m pytest --doctest-modules quant_trading/risk/metrics.py -q`
  -> **21 passed** (the new Examples doctest produces `0.10365` and `0.0`).
- `python -m ruff check` (both files) -> All checks passed.
- `python -m black --check` (both files) -> unchanged.
- `python -m mypy quant_trading/risk/metrics.py tests/test_risk_metrics.py`
  -> Success: no issues found in 2 source files.
- Full suite against the modified tree: `python -m pytest tests/ quant_trading/ -q`
  (default `not slow and not network` markers) -> **4082 passed, 142 deselected
  in 516.05s**, 0 failures. This is the definitive confirmation that the
  additive change regresses nothing.

## Remaining work / unresolved

- Nothing is committed. Changes are left in the working tree
  (`git status` / `git diff`). Committing was not explicitly requested.

## Approaches already tried and why they were rejected

- Adding a new built-in strategy: rejected as too large for a single safe,
  verifiable session. It requires coordinated edits across `strategies/examples.py`,
  `strategies/__init__.py` (register), `examples/cli.py` (`BUILTIN_STRATEGY_KEYS`,
  and either `strategy_param_map` + `CLI_ARG_DEFAULTS` flags or an entry in
  `tests/test_repository_integrity.py::_STRATEGIES_WITHOUT_DEDICATED_CLI_FLAGS`),
  a new `examples/run_<name>.py`, a `Test<ClassName>` in
  `tests/test_strategies_examples.py`, plus README registry/count/example-script
  updates — each guarded by a dedicated invariant test. High risk of a slow
  iterate-and-rerun loop.

## One precise next task

Wire `calculate_ulcer_index` into the aggregate API **if** desired: add an
`ulcer_index: float = 0.0` field to `RiskMetrics`, populate it in
`calculate_all_metrics` via `calculate_ulcer_index(equity_curve)`, and update
`RiskMetrics.to_dict`/`from_dict` plus the `tests/test_risk_metrics.py`
orchestration tests (notably `test_without_market_returns`, which asserts
`set(result.keys()) == RiskMetrics().to_dict().keys()`). Evidence/constraints:
`RiskMetrics` is defined at `quant_trading/risk/metrics.py:28`,
`calculate_all_metrics` at ~line 972, `to_dict`/`from_dict` at lines 70/96, and
`calculate_backtest_metrics` in `quant_trading/backtest/metrics.py` maps
`RiskMetrics` -> `BacktestMetrics` (check whether a new field must be surfaced
there too). If that is out of scope, the current standalone addition is complete
and verified; just confirm the full suite is green.

(End of file)