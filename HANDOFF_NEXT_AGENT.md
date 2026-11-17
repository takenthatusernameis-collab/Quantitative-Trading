## What changed (this session)

- Fixed two real docstring/signature default mismatches in `quant_trading/risk/metrics.py` (from previous session):
  - `calculate_equal_risk_contribution_weights` and `calculate_risk_budget_weights` both documented `long_only: ... (default True)` while both signatures default to `long_only: bool = False`. Changed the docstrings to `(default False)`. Documentation-only fix; runtime behaviour unchanged.
- Added deterministic guard `test_documented_arg_defaults_match_signature` (plus helpers `_literal_default`, `_docstring_arg_default_notes`, `_signature_defaults`, `_tree_default_mismatches`, `_documented_default_mismatches`) to `tests/test_repository_integrity.py`.
  - AST-only (no imports of scanned code), fast and dependency-free.
  - Parses every function's `Args:` docstring section under `quant_trading/` and `examples/` and fails when a clean literal `(default X)` note disagrees with the actual signature default.
  - Conservative: only `True`/`False`/`None` and numeric literal notes are compared, only against literal signature defaults; descriptive notes (e.g. `(default 252 for daily data)`) are skipped.
  - Includes negative control that feeds a synthetic mismatched function and asserts the drift is detected.
- **Added inverse-drift guard** `test_documented_args_exist_in_signature` (plus helpers `_docstring_arg_names`, `_signature_param_names`, `_tree_documented_unknown_args`, `_documented_unknown_args`) to `tests/test_repository_integrity.py`.
  - Scans the same directories for `Args:` entries that name a parameter not present in the function signature.
  - Skips `self`/`cls` and `*args`/`**kwargs` to avoid false positives.
  - Includes negative control with a synthetic "ghost" argument to prove the guard fires.
  - Caught and removed 22 stale `function:` parameter docstring entries in `AlphaVantageProvider._fetch_economic` overloads that were removed from the signature but remained in the docstring (commit dfc58b7).

## What was actually verified (evidence)

- `python -m pytest tests/test_repository_integrity.py -q` -> `35 passed` (was 33; +2 new guards including negative controls).
- Full default suite (sample): `python -m pytest tests/test_risk_attribution.py tests/test_risk_metrics.py tests/test_packaging.py -q` -> `158 passed`.
- `python -m pytest quant_trading/risk/metrics.py -q` -> `20 passed` (doctests).
- `python -m ruff check .` -> `All checks passed!`
- `python -m black --check .` -> `160 files would be left unchanged`.
- `python -m mypy tests/test_repository_integrity.py quant_trading/data/yfinance_provider.py` -> `Success: no issues found`.

## What remains unresolved / not verified

- CI workflow execution on GitHub Actions was not observed (workflow files are controller-managed and cannot be persisted by an agent session).
- The guards cover `Args:` sections only; they do not check `Returns:`/`Raises:`/`Yields:`/`Examples:` sections for drift.
- The inverse-drift guard does not validate that every signature parameter has a corresponding `Args:` entry (missing documentation is not flagged).

## Approaches that already failed and why (do not repeat)

- The previous handoff's suggested task — "extend `.github/workflows/ci.yml` with a test/type gate" — is impossible to persist in this Kilo loop. The controller (`.github/scripts/kilo-controller.sh`) restores tracked workflow files to their session-start revision and runs `git clean -fd -- .github/workflows` before checkpointing, and `stage_repository_changes()` excludes `.github/workflows/**`. Evidence: `git log -- .github/workflows/ci.yml` is empty and no `ci.yml` exists on disk. Any workflow file an agent creates is deleted and never committed. Do NOT retry workflow-file changes; put durable work in `quant_trading/`, `tests/`, `examples/`, `README.md`, or `pyproject.toml` instead.

## One precise next task (if continuing this line of work)

- Extend the docstring guards to also scan `Returns:` sections for documented return values that don't match the function's actual return annotation (if present), reusing the existing AST parsing infrastructure in `tests/test_repository_integrity.py`.
  - Evidence: several functions in the codebase have `Returns:` docstring sections that may drift from type annotations.
  - Constraints: AST-only, no imports; conservative (only compare when both a clean literal return note and a signature return annotation exist).
  - Verify: `python -m pytest tests/test_repository_integrity.py -q` plus `ruff`, `black`, `mypy` on touched files.