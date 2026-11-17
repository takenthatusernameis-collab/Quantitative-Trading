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
- **Completed the pending `Returns:` guard** (commit 23cc6b3): `test_documented_returns_match_signature` plus helpers `_docstring_returns_type`, `_normalize_return_annotation`, `_returns_type_match`, `_tree_returns_mismatches`, `_documented_returns_mismatches`. AST-only, conservative, with negative control.
- **Added the complementary inverse-Args guard** `test_documented_args_cover_signature_params` (plus helpers `_tree_undocumented_params`, `_undocumented_params` and allowlist `_UNDOCUMENTED_PARAM_ALLOWLIST`) to `tests/test_repository_integrity.py`.
  - Flags every signature parameter with no matching entry in the function's docstring `Args:` section (skips `self`/`cls` and `*args`/`**kwargs`).
  - Grandfathers 116 pre-existing undocumented parameters in an explicit allowlist keyed by `(path, function, parameter)` so the guard prevents regressions without failing on today's state; entries are removed as parameters get documented.
  - Includes negative control: a synthetic function documenting `a` but not `b` must be flagged.
  - AST-only, no imports; scans `quant_trading/` and `examples/`.

## What was actually verified (evidence)

- `python -m pytest tests/test_repository_integrity.py -q` -> `37 passed` (35 base + `test_documented_returns_match_signature` + `test_documented_args_cover_signature_params`, each with its negative control).
- Full default suite (sample): `python -m pytest tests/test_risk_attribution.py tests/test_risk_metrics.py tests/test_packaging.py -q` -> `158 passed`.
- `python -m pytest quant_trading/risk/metrics.py -q` -> `20 passed` (doctests).
- `python -m ruff check .` -> `All checks passed!`
- `python -m black --check .` -> `160 files would be left unchanged`.
- `python -m mypy tests/test_repository_integrity.py quant_trading/data/yfinance_provider.py` -> `Success: no issues found`.

## What remains unresolved / not verified

- CI workflow execution on GitHub Actions was not observed (workflow files are controller-managed and cannot be persisted by an agent session).
- The guards cover `Args:` and `Returns:` sections only; they do not check `Raises:`/`Yields:`/`Examples:` sections for drift.
- The inverse-Args guard grandfathers existing debt via `_UNDOCUMENTED_PARAM_ALLOWLIST`; it does not yet flag functions that have a docstring but no `Args:` section at all, nor does it require every signature parameter to be documented (allowlisted ones are exempt by design).

## Approaches that already failed and why (do not repeat)

- The previous handoff's suggested task — "extend `.github/workflows/ci.yml` with a test/type gate" — is impossible to persist in this Kilo loop. The controller (`.github/scripts/kilo-controller.sh`) restores tracked workflow files to their session-start revision and runs `git clean -fd -- .github/workflows` before checkpointing, and `stage_repository_changes()` excludes `.github/workflows/**`. Evidence: `git log -- .github/workflows/ci.yml` is empty and no `ci.yml` exists on disk. Any workflow file an agent creates is deleted and never committed. Do NOT retry workflow-file changes; put durable work in `quant_trading/`, `tests/`, `examples/`, `README.md`, or `pyproject.toml` instead.

## One precise next task (if continuing this line of work)

- Add a `Yields:` section docstring guard to `tests/test_repository_integrity.py`: for generator functions whose return annotation is `Generator[YieldT, ...]` / `Iterator[YieldT, ...]` / `AsyncGenerator[YieldT, ...]`, compare the documented yield type prefix in the `Yields:` section against the annotation's yield type argument. Reuse the existing AST parsing infrastructure (`_parse`, `ast.get_docstring`, section-scanning pattern from `_docstring_returns_type`).
  - Constraints: AST-only, no imports; conservative (only compare when both a clean literal yield-type note and a signature return annotation with a yield type argument exist); skip `Raises:`/`Examples:` for now.
  - Include a negative control (synthetic generator documenting `int` yields while annotated `-> Generator[str, None, None]` must be flagged).
  - Verify: `python -m pytest tests/test_repository_integrity.py -q` plus `ruff`, `black`, `mypy` on touched files.