## What changed (this session)

- **Added the `Raises:` section docstring guard** `test_documented_raises_are_real_exceptions` (plus helpers `_docstring_raises_names`, `_is_documented_exception`, `_tree_raises_mismatches`, `_documented_raises_mismatches` and constants `_RAISES_EXCEPTION_NAME`, `_RAISES_BUILTIN_EXCEPTIONS`) to `tests/test_repository_integrity.py`, completing the docstring-section guard set (`Args:`, `Returns:`, `Yields:`, `Raises:`).
  - For functions with a `Raises:` section, scans entries of the form `ExceptionName: description` and fails when the documented name is not a real exception class.
  - Conservative: only exception-like names (ending in `Error`/`Exception`, or a builtin exception class, or a qualified name like `yaml.YAMLError`) are checked; prose-only `Raises:` sections, blank lines and continuation lines are skipped so the guard cannot misfire on text such as `"If the path does not exist"`.
  - AST-only, no imports; scans `quant_trading/` and `examples/`.
  - Negative control: a synthetic function documenting `NotAnError` (exception-like but not a real class) is flagged.
  - Positive control: a synthetic function documenting builtin `ValueError` and qualified `yaml.YAMLError` both pass.
  - Verified against today's state: all 7 distinct documented exception names in the repo are builtins (`ValueError`, `TypeError`, `KeyError`, `ImportError`, `FileNotFoundError`, `AssertionError`, `RuntimeError`) plus the qualified `yaml.YAMLError`; no drift found.

## What was actually verified (evidence)

- `python -m pytest tests/test_repository_integrity.py -q` -> `39 passed` (38 base + `test_documented_raises_are_real_exceptions`, each with its negative and positive controls).
- Full default suite (sample): `python -m pytest tests/test_repository_integrity.py tests/test_risk_attribution.py tests/test_risk_metrics.py tests/test_packaging.py -q` -> `197 passed`.
- `python -m ruff check .` -> `All checks passed!`
- `python -m black --check .` -> `160 files would be left unchanged`.
- `python -m mypy tests/test_repository_integrity.py` -> `Success: no issues found in 1 source file`.
- Negative/positive controls confirmed firing directly: `NotAnError` flagged, `ValueError`/`yaml.YAMLError` accepted.

## What remains unresolved / not verified

- CI workflow execution on GitHub Actions was not observed (workflow files are controller-managed and cannot be persisted by an agent session).
- The guards cover `Args:`, `Returns:`, `Yields:` and `Raises:` sections only; they do not check `Examples:`/`Example:`/`Notes:`/`Attributes:`/`See Also:`/`References:` sections for drift.
- The inverse-Args guard grandfathers existing debt via `_UNDOCUMENTED_PARAM_ALLOWLIST`; it does not yet flag functions that have a docstring but no `Args:` section at all, nor does it require every signature parameter to be documented (allowlisted ones are exempt by design).

## Approaches that already failed and why (do not repeat)

- The previous handoff's suggested task — "extend `.github/workflows/ci.yml` with a test/type gate" — is impossible to persist in this Kilo loop. The controller (`.github/scripts/kilo-controller.sh`) restores tracked workflow files to their session-start revision and runs `git clean -fd -- .github/workflows` before checkpointing, and `stage_repository_changes()` excludes `.github/workflows/**`. Evidence: `git log -- .github/workflows/ci.yml` is empty and no `ci.yml` exists on disk. Any workflow file an agent creates is deleted and never committed. Do NOT retry workflow-file changes; put durable work in `quant_trading/`, `tests/`, `examples/`, `README.md`, or `pyproject.toml` instead.

## One precise next task (if continuing this line of work)

- Add an `Examples:`/`Example:` section docstring guard to `tests/test_repository_integrity.py`: for functions with an `Examples:` section, check that the section is non-empty and (where a runnable `>>>` doctest line is present) that the doctest line parses as valid Python. Reuse the existing AST parsing infrastructure (`_parse`, `ast.get_docstring`, section-scanning pattern from `_docstring_returns_type`).
  - Constraints: AST-only, no imports; conservative (only flag a missing/empty `Examples:` section when the function advertises one, and only flag `>>>` lines that fail to parse); do not import scanned code.
  - Include a negative control (synthetic function with an `Examples:` section containing an unparseable `>>>` line must be flagged; or an empty `Examples:` section must be flagged).
  - Verify: `python -m pytest tests/test_repository_integrity.py -q` plus `ruff`, `black`, `mypy` on touched files.

(End of file - total 52 lines)