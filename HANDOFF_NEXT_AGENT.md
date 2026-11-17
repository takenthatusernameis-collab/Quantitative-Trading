## What changed (this session)

- Added a new AST-only docstring guard in `tests/test_repository_integrity.py` that flags functions with a docstring but no `Args:` section when they have documentable parameters:
  - `_tree_missing_args_section` (lines ~2432-2477): Checks functions, async functions for missing `Args:` header while excluding `self`/`cls` and `*args`/`**kwargs`. Uses `_UNDOCUMENTED_PARAM_ALLOWLIST` to grandfather existing debt — a function is only reported when at least one documentable parameter is not allowlisted.
  - `_documented_missing_args_section` (lines ~2479-2488): Scans the existing `_DOC_SCAN_DIRS` (`quant_trading` and `examples`).
  - `test_documented_functions_have_args_section` (lines ~2541-2594): Includes negative control (documented function with parameters but no `Args:` must be flagged), positive control (populated `Args:` passes), and a control for functions without documentable parameters.

## What was actually verified (evidence)

- New focused guard: `python -m pytest tests/test_repository_integrity.py::test_documented_functions_have_args_section -q` -> `1 passed`.
- Related guards still pass: `python -m pytest tests/test_repository_integrity.py::test_documented_args_cover_signature_params tests/test_repository_integrity.py::test_documented_notes_are_valid tests/test_repository_integrity.py::test_documented_attributes_are_valid tests/test_repository_integrity.py::test_documented_cross_reference_sections_are_valid -q` -> `4 passed`.
- Full integrity suite: `python -m pytest tests/test_repository_integrity.py -q` -> `44 passed`.
- `python -m ruff check .` -> `All checks passed!`.
- `python -m black --check .` -> `160 files would be left unchanged`.
- `python -m mypy tests/test_repository_integrity.py` -> `Success: no issues found in 1 source file` (mypy also printed existing unused-pyproject-section notes for other test modules).
- `git diff --check` passed.

## What remains unresolved / not verified

- CI workflow execution on GitHub Actions was not observed; workflow files are controller-managed and cannot be persisted by an agent session.
- Documentation section guards are conservative structural checks; they do not prove that prose, examples, or cross-reference targets are semantically correct.

## Approaches that already failed and why (do not repeat)

- Do not modify or add files under `.github/workflows/`. The controller restores tracked workflow files, cleans untracked workflow files, and excludes `.github/workflows/**` from staging. Prior evidence: no `ci.yml` exists and `git log -- .github/workflows/ci.yml` is empty. Put durable work in `quant_trading/`, `tests/`, `examples/`, `README.md`, or `pyproject.toml` instead.

## One precise next task (if continuing this line of work)

- Consider extending the docstring guards to validate `See Also:` and `References:` section content quality (e.g., ensure referenced names resolve to real objects), but this would require import-time analysis rather than pure AST checks.

(End of file - total 37 lines)