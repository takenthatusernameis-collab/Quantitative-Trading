# Next Task

## Repository state (verified this session)
- Branch `main` up to date with `origin/main`; working tree clean except for the change below.
- Prior serialization work is complete and committed: every dataclass in `quant_trading/`
  (33 total, verified by introspection) defines `to_dict()`/`from_dict()`;
  `_RebalancePlan` round-trips and is registered in `tests/test_serialization_roundtrip.py`.

## Completed this session

**Added an introspection guard for the serialization contract.** The round-trip test
(`tests/test_serialization_roundtrip.py`) used explicit parametrization, so a new dataclass
added to `quant_trading/` without `to_dict()`/`from_dict()` would not be caught by any test.
Added `test_every_dataclass_declares_to_dict_and_from_dict`, which walks all
`quant_trading/` modules via `pkgutil.walk_packages` and asserts every dataclass defined
there declares both methods (skipping imported/re-exported classes so each is checked once
where defined).
  - `tests/test_serialization_roundtrip.py`: added `import dataclasses`/`importlib`/`pkgutil`
    and the new introspection test (+35 lines).

## Verified (this session, evidence)
- `python3 -m pytest tests/test_serialization_roundtrip.py -q` → **34 passed** (was 33; +1 guard).
- `python3 -m pytest tests/test_serialization_roundtrip.py tests/test_portfolio_rebalancer.py
  tests/test_rebalancer.py tests/test_rebalancer_execution.py tests/test_rebalancer_risk_integration.py
  tests/test_rebalancer_sizing_invariants.py tests/test_rebalancer_extra_coverage.py
  --doctest-modules quant_trading/portfolio/rebalancer.py -q` → **240 passed**.
- `python3 -m ruff check .` → **All checks passed!**
- `python3 -m mypy quant_trading --ignore-missing-imports` → **Success: no issues found in 37 source files.**

## Unresolved / not completed
- None. The serialization contract is complete (33/33 dataclasses define `to_dict`/`from_dict`)
  and is now guarded by an automated introspection test.

## Failed approaches (do not repeat unchanged)
- None this session.

## One precise next task

**Trigger:** If a commit is explicitly requested.

**Action:** Inspect `git status`/`diff` (limited to `tests/test_serialization_roundtrip.py`),
re-run the verification set (`pytest tests/test_serialization_roundtrip.py -q`, `ruff check .`,
`mypy quant_trading --ignore-missing-imports`), then commit the introspection-guard addition
with a clear message. Push only if explicitly requested and remote/auth are verified.

**Constraints:** No API/safety/validation changes; do not commit secrets/caches
(`data/` is gitignored and runtime-created); exclude unrelated modifications;
do not claim checks passed without evidence.

**If a broader task arrives:** act on a new external issue/feature request with concrete
requirements — reproduce/define acceptance criteria, implement the smallest reversible change,
verify with targeted checks + `ruff` + `mypy` + relevant tests.

## Git state
- Branch `main` up to date with `origin/main`.
- Working tree has **one uncommitted change**: `tests/test_serialization_roundtrip.py`
  (+ introspection guard test).
- No secrets/caches added.
