# Next Task

## Repository state (verified 2026-11-09, this session)
- Branch `main` up to date with `origin/main`; last commit `e6d8a20` (handoff-only).
- Working tree has **uncommitted changes** limited to:
  - `quant_trading/portfolio/rebalancer.py` (+`to_dict`/`from_dict` on `_RebalancePlan`)
  - `tests/test_serialization_roundtrip.py` (+`_RebalancePlan` import and instance)
- `python -m ruff check .` → All checks passed.
- `python -m mypy quant_trading --ignore-missing-imports` → Success, no issues (37 files).
- `python -m pytest -q --tb=short` → **3124 passed, 1 skipped, 129 deselected** in 242.79s.
- `python -m pytest tests/test_serialization_roundtrip.py -q` → **33 passed**.
- `python -m pytest --doctest-modules quant_trading/portfolio/rebalancer.py -q` → **10 passed**.

## Completed this session

1. **Ran the full default test suite to completion** (the prior session's assigned task).
   Captured final summary: **3124 passed, 1 skipped, 129 deselected** in 242.79s. No failures.
   This resolves the confidence gap from the previous session's timeout-blocked rerun.

2. **Filled the last serialization gap in the repo.** The repo-wide serialization contract
   (`to_dict()`/`from_dict()` on every dataclass, registered in
   `tests/test_serialization_roundtrip.py`) had exactly one uncovered dataclass:
   - `quant_trading/portfolio/rebalancer.py`:
     - Added `_RebalancePlan.to_dict()` / `from_dict()` — serializes `cash`, `fee_rate`,
       and `positions` (as a plain `dict[str, float]`). No datetime field, so the in-module
       `_iso`/`_coerce_datetime` helpers are not needed here; conventions otherwise mirror
       the sibling `RebalanceAction`/`RebalanceExecution` methods (safe defaults on missing
       keys, coercion of `positions` values to `float`).
   - `tests/test_serialization_roundtrip.py`: imported `_RebalancePlan` and registered an
     instance (`_RebalancePlan(cash=10000.0, fee_rate=0.001, positions={"AAPL": 5.0})`) in the
     parametrized round-trip suite.

## One precise next task

**Trigger:** If a commit is explicitly requested.

**Action:** Inspect `git status`/`diff` (limited to the two files above), re-run the verification
set (`pytest tests/test_serialization_roundtrip.py tests/test_portfolio_rebalancer.py -q`,
`pytest --doctest-modules quant_trading/portfolio/rebalancer.py -q`, `ruff check .`,
`mypy quant_trading --ignore-missing-imports`), then commit the `_RebalancePlan` serialization
addition with a clear message. Push only if explicitly requested and remote/auth are verified.

**Constraints:** No API/safety/validation changes; do not commit secrets/caches
(`data/` is gitignored and runtime-created); exclude unrelated modifications;
do not claim checks passed without evidence.

**If a broader task arrives:** act on a new external issue/feature request with concrete
requirements — reproduce/define acceptance criteria, implement the smallest reversible change,
verify with targeted checks + `ruff` + `mypy` + relevant tests. There are no remaining
dataclasses lacking `to_dict`/`from_dict`; the serialization contract is complete across
all of `quant_trading/`.

(End of file - total 49 lines)