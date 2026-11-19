## Status

**Task complete (this session).** Fixed a real correctness bug in the Treynor ratio and
recorded why the previous handoff's requested workflow edit was not attempted.

The previous handoff asked to add `.github/workflows/ci.yml` to the
`kilo-workflow-audit.yml` paths/actionlint/YAML lists. That task is **invalid for an
agent session**: `.github/scripts/kilo-controller.sh` (lines 307-313) restores every
workflow file to `WORKFLOW_BASE_SHA` and runs `git clean -fd -- .github/workflows`
after each session, and `stage_repository_changes` excludes `.github/workflows/**`.
Commit `ced5187` (empty message, deletes only `ci.yml`) is the controller enforcing
that policy, not a regression. Do not re-add `ci.yml`; workflow definitions are
maintainer-managed by design.

## What changed

- `quant_trading/risk/metrics.py`: `calculate_treynor_ratio` now computes the
  annualized excess return over the **same aligned sample** that
  `calculate_beta` uses, matching `calculate_alpha`/`calculate_information_ratio`.
  Before the fix beta came from the aligned sample but the mean return came from the
  raw returns, so a `market_returns` series with a NaN produced a numerator and
  denominator describing different observations.
- `tests/test_risk_metrics.py`: added `test_treynor_uses_aligned_sample`, which
  asserts the aligned result and that it differs from the old unaligned formula.

Evidence for the bug (before the fix):

```
returns = [0.01, 0.02, 0.50, 0.004] (dates)
market  = [0.008, NaN, 0.004, 0.002]
beta = -16.6429 (aligned sample of 3 points)
old treynor = -2.0202   # used all 4 raw returns in the mean
aligned treynor = -2.5931
```

## What was actually verified (this session)

- `python -m pytest tests/test_risk_metrics.py tests/test_backtest_metrics.py -m "not slow and not network"` -> `182 passed`.
- Full suite via `python -m coverage run --branch -m pytest -q -p no:cacheprovider -m "not slow and not network"` -> `4181 passed, 151 deselected in 629.35s`.
- `python -m coverage report` -> `TOTAL 10046 0 3570 0 100%`.
- `python -m black --check tests/ quant_trading/ examples/` -> `166 files would be left unchanged.`
- `python -m ruff check tests/ quant_trading/ examples/` -> `All checks passed!`
- `python -m mypy tests/ quant_trading/ examples/` -> `Success: no issues found in 166 source files`.

## Failed approaches / gotchas (do not repeat)

- Do **not** modify `.github/workflows/*` from an agent session; the controller
  reverts/removes those files and excludes them from checkpoint commits.
- Local env is Python 3.14.4 + numpy 2.5.5 + coverage 7.17.3. `pytest --cov` (the
  `pytest-cov` plugin) fails at collection with
  `ImportError: cannot load module more than once per process`; use
  `python -m coverage run --branch -m pytest ...` followed by
  `python -m coverage report` instead. CI pins Python 3.12, so this is local-only.
- Invoke `black`/`ruff`/`mypy` as `python -m <tool>` (not on PATH).

## One precise next task

Add an end-to-end regression test in `tests/test_backtest_metrics.py` that passes a
gapped `market_returns` series (containing NaN) to `calculate_backtest_metrics` and
asserts `metrics.treynor_ratio` equals the manual aligned formula
`(aligned_returns.mean() * periods_per_year - risk_free_rate) / beta`, and differs
from the unaligned formula. This locks the fixed behavior in at the public API layer
used by the engine/CLI. Verify with the focused test files, `python -m coverage run`
full suite (expect 100%), plus black/ruff/mypy. Do not touch workflow files.
