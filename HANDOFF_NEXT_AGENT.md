## What changed (this session)

- Fixed two real docstring/signature default mismatches in
  `quant_trading/risk/metrics.py`:
  - `calculate_equal_risk_contribution_weights` and
    `calculate_risk_budget_weights` both documented
    ``long_only: ... (default True)`` while both signatures default to
    ``long_only: bool = False``. Changed the docstrings to ``(default False)``.
    This is a documentation-only fix; runtime behaviour is unchanged (smallest
    reversible change).
- Added a new deterministic guard `test_documented_arg_defaults_match_signature`
  (plus helpers `_literal_default`, `_docstring_arg_default_notes`,
  `_signature_defaults`, `_tree_default_mismatches`,
  `_documented_default_mismatches`) to `tests/test_repository_integrity.py`.
  - AST-only (no imports of the scanned code), so it is fast and dependency-free.
  - Parses every function's ``Args:`` docstring section under `quant_trading/`
    and `examples/` and fails when a clean literal ``(default X)`` note
    disagrees with the actual signature default.
  - Conservative by design: only ``True``/``False``/``None`` and numeric
    literal notes are compared, only against literal signature defaults, and
    descriptive notes (e.g. ``(default 252 for daily data)``) are skipped, so it
    cannot misfire on prose. `tests/` is excluded to avoid internal-helper noise.
  - Includes a negative control that feeds a synthetic mismatched function and
    asserts the drift is detected (proves the guard is not vacuous).

## What was actually verified (evidence)

- `python -m pytest tests/test_repository_integrity.py -q` -> `34 passed`
  (was 33; the +1 is the new guard, including its negative control).
- Full default suite: `python -m pytest -q` -> `3994 passed, 142 deselected in
  568.54s` (baseline was 3993 passed; +1 is the new guard).
- `python -m pytest quant_trading/risk/metrics.py -q` -> `20 passed` (doctests).
- `python -m pytest tests/test_risk_attribution.py tests/test_risk_metrics.py
  tests/test_packaging.py -q` -> `158 passed`.
- `python -m ruff check .` -> `All checks passed!`.
- `python -m black --check .` -> `160 files would be left unchanged`.
- `python -m mypy quant_trading/risk/metrics.py` and
  `python -m mypy tests/test_repository_integrity.py` -> `Success: no issues
  found`.
- Prototype scan of the guard logic across `quant_trading/`, `examples/`,
  `tests/` reported exactly the 2 mismatches above before the fix and 0 after,
  confirming the guard targets a real, bounded defect class.

## What remains unresolved / not verified

- CI workflow execution on GitHub Actions was not observed (see the blocker
  below: workflow files are controller-managed and cannot be persisted by an
  agent session anyway).
- The guard covers `(default X)` notes only; it does not check the inverse
  drift (a documented `Args:` entry that names a parameter the signature does
  not have) or `Returns:`/`Raises:` sections.

## Approaches that already failed and why (do not repeat)

- The previous handoff's suggested task — "extend `.github/workflows/ci.yml`
  with a test/type gate" — is impossible to persist in this Kilo loop. The
  controller (`.github/scripts/kilo-controller.sh`) restores tracked workflow
  files to their session-start revision and runs `git clean -fd --
  .github/workflows` before checkpointing, and `stage_repository_changes()`
  excludes `.github/workflows/**`. Evidence: `git log -- .github/workflows/ci.yml`
  is empty and no `ci.yml` exists on disk, despite the prior handoff claiming it
  was added. Any workflow file an agent creates is deleted and never committed.
  Do NOT retry workflow-file changes; put durable work in `quant_trading/`,
  `tests/`, `examples/`, `README.md`, or `pyproject.toml` instead.

## One precise next task

- Run a focused follow-up guard that catches the inverse drift the current guard
  cannot see: a docstring `Args:` entry whose name is not a parameter of the
  function (a documented-but-nonexistent argument), reusing the existing
  `_docstring_arg_default_notes`/`_signature_defaults` helpers in
  `tests/test_repository_integrity.py`.
  - Evidence: this session fixed the `(default X)` direction; the same class of
    doc-drift bug also appears when an `Args:` entry names a removed/renamed
    parameter, which no current test covers.
  - Constraints: smallest reversible change; AST-only, no imports; keep it
    conservative (skip `*args`/`**kwargs` and `self`) so it does not misfire.
  - Verify: `python -m pytest tests/test_repository_integrity.py -q` (currently
    34 passed) plus `python -m ruff check .` and `python -m black --check .`.