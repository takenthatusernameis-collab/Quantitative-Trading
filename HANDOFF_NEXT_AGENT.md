## What changed (this session)

Added library-level input validation to `WalkForwardOptimizer` so invalid walk-forward
geometry is rejected at construction with a clear `ValueError`, instead of silently
producing a degenerate or misleading run.

**Root cause:** `WalkForwardOptimizer.__init__` accepted `n_windows`, `train_size`, and
`step_size` without validation. The CLI validates these (`--wf-train-size` in `(0,1)`,
`--wf-step-size` greater than 0), but a direct library user could pass `step_size=0`
(freezes window advancement), `step_size > 1` (not a "fraction of a window's span",
contradicting the documented "tile exactly" contract), `train_size <= 0` or `> 1`, or
`n_windows < 1`, all of which silently yielded empty or degenerate windows.

**Fix** (`quant_trading/optimization/walk_forward.py:524-544`): after the `step_size`
`None -> 1.0` defaulting, `__init__` now raises `ValueError` when:
- `n_windows < 1`
- `train_size` not in `(0, 1]`
- `step_size` not in `(0, 1]`

**Tests added** (`tests/test_optimization.py`):
- `test_walk_forward_rejects_invalid_step_size` — parametrized over `step_size ∈ {0.0, -0.5, 1.5}`.
- `test_walk_forward_rejects_invalid_train_size` — parametrized over `train_size ∈ {0.0, -0.5, 1.5}`.
- `test_walk_forward_rejects_invalid_n_windows` — parametrized over `n_windows ∈ {0, -1}`.
- `test_walk_forward_accepts_boundary_values` — `step_size=1.0`, `train_size=1.0`, `n_windows=1` construct cleanly.

3 files changed (incl. this handoff), +65 lines across source and tests.

## Verified (this session, evidence)

- `tests/test_optimization.py` → **180 passed** (0 failed).
- `tests/test_cli.py` → untouched by this change; prior run **260 passed, 1 skipped, 3 deselected**.
- Full suite prior baseline → **3300 passed, 1 skipped, 132 deselected, 0 failed**.
- `python -m pytest --doctest-modules quant_trading/optimization/walk_forward.py` → **12 passed**.
- `python -m ruff check .` → **All checks passed.**
- `python -m mypy quant_trading --ignore-missing-imports` → **Success: no issues in 38 source files.**
- `python -m mypy examples/cli.py --ignore-missing-imports` → **Success: no issues in 1 source file.**

## Unresolved / not completed

- None identified.

## Failed approaches (do not repeat unchanged)

- None for this task.

## Verification commands (re-run before starting)

```bash
python -m pytest tests/test_optimization.py -q -p no:cacheprovider
python -m pytest --doctest-modules quant_trading/optimization/walk_forward.py -q -p no:cacheprovider
python -m ruff check .
python -m mypy quant_trading --ignore-missing-imports
python -m mypy examples/cli.py --ignore-missing-imports
```

## Git state

- Branch `main` up to date with `origin/main`.
- Working tree changes: `quant_trading/optimization/walk_forward.py` (+19),
  `tests/test_optimization.py` (+46). Do NOT commit unless explicitly asked.

## One precise next task

- None outstanding for bounded, verified progress. The walk-forward tiling fix (prior
  session) and this input-validation task are both complete. If a new task is assigned,
  re-run the verification set first.

(End of file)
