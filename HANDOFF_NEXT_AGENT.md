## What changed (2026-11-09, this session)

- **Fixed an orphaned `noise` parameter on `BayesianOptimizer`.** The
  `BayesianOptimizerConfig` dataclass defined a `noise` field, serialized it in
  `to_dict`, and round-tripped it in `from_dict` — but `BayesianOptimizer`
  itself ignored it: the constructor rejected `noise` as an unexpected keyword
  argument, and `gp_minimize` was called with a hardcoded `noise=1e-6`
  (`quant_trading/optimization/bayesian.py:417`). A user who set `noise` on the
  config (or restored a config via `from_dict`) had no effect on the GP kernel.
  Wired the parameter through: added a `noise: float = 1e-6` constructor arg
  (matching `BayesianOptimizerConfig`'s default), stored it as `self.noise`, and
  forwarded `noise=self.noise` to `gp_minimize`.
  - `quant_trading/optimization/bayesian.py`: +1 constructor arg, +3 doc lines,
    +1 attribute, `noise=1e-6` → `noise=self.noise` (7 lines changed).
  - `tests/test_optimization.py`: added `TestBayesianOptimizerNoise` class with
    4 regression tests (constructor accepts the kwarg, default matches config
    default, configured value reaches `gp_minimize`, default reaches
    `gp_minimize`). The last two monkeypatch `skopt.gp_minimize` and assert the
    captured `noise` kwarg.

## Verified (this session, evidence)

- `python3 -m pytest tests/test_optimization.py tests/test_serialization_roundtrip.py
  tests/test_repository_integrity.py -q` → **203 passed**.
- `python3 -m pytest tests/test_optimization.py -k "bayesian or Bayesian" -q` →
  **26 passed** (no regressions in the Bayesian suite).
- `python3 -m pytest tests/test_optimization.py::TestBayesianOptimizerNoise -v` →
  **4 passed** (the new regression tests).
- `python3 -m ruff check .` → **All checks passed!**
- `python3 -m mypy quant_trading --ignore-missing-imports` → **Success: no issues
  found in 37 source files.**
- Reproduced the bug before fixing: `BayesianOptimizer(noise=1e-3)` raised
  `TypeError: unexpected keyword argument 'noise'`; confirmed fixed by
  `test_constructor_accepts_noise_kwarg`.

## Unresolved / not completed

- None. The `noise` parameter is now wired end-to-end and guarded by tests.

## Failed approaches (do not repeat unchanged)

- Initial test used a hand-rolled `_Result` class with mutable class attributes,
  which tripped ruff `RUF012`; replaced with `types.SimpleNamespace(...)` and
  rewrote the `dict(...)` call as a literal to satisfy `C408`. The
  monkeypatch approach itself (patching `skopt.gp_minimize`) is sound and kept.

## One precise next task

- **Trigger:** If a commit is explicitly requested.
- **Action:** Inspect `git status`/`diff`, re-run the verification set
  (`pytest tests/test_optimization.py tests/test_serialization_roundtrip.py
  tests/test_repository_integrity.py -q`, `ruff check .`,
  `mypy quant_trading --ignore-missing-imports`), then commit the `noise` wiring
  with a clear message. Push only if explicitly requested and remote/auth are
  verified.
- **Constraints:** No API/safety/validation changes beyond the `noise` wiring;
  do not commit secrets/caches (`data/` is gitignored and runtime-created);
  exclude unrelated modifications; do not claim checks passed without
  evidence.

## Git state

- Branch `main` up to date with `origin/main`.
- Working tree has **two uncommitted changes** (this session's work, not yet
  committed):
  - `quant_trading/optimization/bayesian.py` (+ noise wiring)
  - `tests/test_optimization.py` (+ 4 regression tests)
- No secrets/caches added.

(End of file - total 84 lines)