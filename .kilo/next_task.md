# Next Task: Strengthen data provider resilience

## Context

Branch coverage is 100% across all modules and all existing tests pass (859 passed). Recent work hardened the CLI with additional unit/integration tests (error handling, trade analysis, output with multiple analyses, optimization/walk-forward routing, parse_range validation, create_config with YAML, aroon strategy cases). These improve CLI robustness without changing runtime behavior.

## What was done (verified)

- Added CLI tests: trade analysis flag handling; start/end date handling; output file creation; main error path (ValueError bubbled from run_backtest); combined output with regime/monte-carlo/trade-analysis; create aroon strategy cases; parse_range valid/invalid; main routes to run_optimization and run_walk_forward; create_config loads from YAML.
- Verified with full test suite: `python -m pytest -q` → 859 passed, 13 warnings (11.3s). No source changes to CLI or library code; only added tests.
- No regressions observed.

## Remaining work / next opportunities

The data providers module has good coverage but could benefit from targeted resilience tests. Pick one concrete, bounded task:

1. **Expand data provider resilience tests** (`quant_trading/data/`):
- Add tests for AlphaVantage provider edge cases: malformed/empty API responses, HTTP errors/timeouts, missing required fields, rate limiting behavior, and error propagation paths.
- Add tests for YFinance provider: malformed/empty dataframes, missing columns, empty results, handle API errors, caching edge cases (cache miss/hit, invalidation), and data cleaning paths.
- Add tests for DataManager: provider selection/fallback logic, clear cache idempotency, creating from config with unknown provider validation, and behavior when no provider is configured.
- Ensure tests don’t require external network calls (mock network layer appropriately) and remain deterministic.

2. **Strengthen Monte Carlo edge cases** (already mentioned previously) — add targeted tests for `quant_trading/monte_carlo/simulator.py` around empty/insufficient inputs, extreme distributions, and result serialization/edge methods.

3. **Improve regime detector robustness** — add boundary tests for `quant_trading/regime/detector.py` (window sizing, all-same values, NaN handling, merge/segment edge cases).

Recommendation: #1 (data provider resilience) is high-value as providers are external-facing boundaries.

## Constraints

- Do not weaken coverage gate, validation, or safety controls. If adding tests, keep changes minimal and reversible.
- Never introduce network-dependent tests; mock all external calls. Preserve existing behavior.
- Run `python -m pytest -q` after changes and ensure all pass.
- Respect code style/conventions; exclude generated artifacts from commits.
- Follow existing test patterns (unittest.mock, fixtures, temp dirs).

## Handoff evidence

- Test run: 859 passed, 13 warnings (2026-10-14T11:47+Z)
- CLI tests added: trade analysis, dates, output, error handling, combined analyses, aroon cases, parse_range, optimization/walk-forward routing, YAML config load.
- No source modifications; only test additions.
