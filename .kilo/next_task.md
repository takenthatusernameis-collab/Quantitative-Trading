# Next Task: Coverage gate is green

## Context

Branch coverage with branch=true is at 100% across all modules (1220 branches, 0 partials). All 847 tests pass. pyproject.toml already has branch coverage enabled; no fail-under threshold is currently enforced.

## What was done (verified)

- Ran full suite with branch coverage enabled: `python -m coverage run --branch -m pytest tests/ -q` → 847 passed, 13 warnings.
- Confirmed branch coverage: 1220 branches, 0 partials, 100% covered (verified via `coverage.json`/reports). No changes made to source/tests (clean working tree aside from generated coverage artifacts).

## Remaining work / next opportunities

No immediate coverage work required. Consider one of the following bounded, high-value follow-ups (pick one and implement/verify):

1. **Harden CLI** (`examples/cli.py`) — Add minimal tests for argument parsing, error handling, and main execution paths (including dry-run/validation) to prevent regressions.
2. **Strengthen Monte Carlo edge cases** — Add targeted tests for `quant_trading/monte_carlo/simulator.py` around empty/insufficient inputs, extreme distributions, and result serialization.
3. **Improve regime detector robustness** — Add tests for boundary conditions in `quant_trading/regime/detector.py` (window sizing, all-same values, NaN handling) to lock in behavior.
4. **Expand data provider resilience** — Add tests for AlphaVantage/`data` edge cases (malformed responses, cache invalidation paths, error propagation) without weakening behavior.

## Constraints

- Do not weaken the coverage gate or disable validation. If adding tests, keep changes minimal and reversible.
- Run `python -m pytest tests/ -q` after changes. Respect existing code style and conventions.
- Exclude generated artifacts (coverage.* , htmlcov/) from commits.

## Handoff evidence

- Test run: 847 passed, 13 warnings (2026-10-14)
- Coverage: 3916 stmts, 0 miss; 1220 branches, 0 partials; 100% overall
