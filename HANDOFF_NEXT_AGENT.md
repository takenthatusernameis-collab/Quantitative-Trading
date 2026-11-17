## What changed (this session)

- Confirmed the assigned `Notes:` guard was already present in `HEAD` and verified it together with the `Attributes:` guard.
- Added an AST-only `See Also:` / `References:` docstring guard in `tests/test_repository_integrity.py`:
  - `_docstring_cross_reference_content` distinguishes an absent section (`None`) from a present but empty section.
  - `_tree_cross_reference_mismatches` checks functions, async functions, and classes without importing scanned code.
  - `_documented_cross_reference_mismatches` scans the existing `_DOC_SCAN_DIRS` (`quant_trading` and `examples`).
  - `test_documented_cross_reference_sections_are_valid` includes negative controls for both empty sections and a positive control with populated sections.
- No allowlist was needed because the current scanned source tree passes the new guard.

## What was actually verified (evidence)

- Assigned guards before the new change: `python -m pytest tests/test_repository_integrity.py::test_documented_notes_are_valid tests/test_repository_integrity.py::test_documented_attributes_are_valid -q` -> `2 passed`.
- New focused guard: `python -m pytest tests/test_repository_integrity.py::test_documented_cross_reference_sections_are_valid -q` -> `1 passed`.
- Full integrity suite: `python -m pytest tests/test_repository_integrity.py -q` -> `43 passed`.
- `python -m ruff check .` -> `All checks passed!`.
- `python -m black --check .` -> `160 files would be left unchanged`.
- `python -m mypy tests/test_repository_integrity.py` -> `Success: no issues found in 1 source file` (mypy also printed existing unused-pyproject-section notes for other test modules).
- `git diff --check` passed.

## What remains unresolved / not verified

- CI workflow execution on GitHub Actions was not observed; workflow files are controller-managed and cannot be persisted by an agent session.
- The inverse-Args guard still does not flag functions that have a docstring but omit the entire `Args:` section. Existing parameter-level debt remains grandfathered through `_UNDOCUMENTED_PARAM_ALLOWLIST`.
- Documentation section guards are conservative structural checks; they do not prove that prose, examples, or cross-reference targets are semantically correct.

## Approaches that already failed and why (do not repeat)

- Do not modify or add files under `.github/workflows/`. The controller restores tracked workflow files, cleans untracked workflow files, and excludes `.github/workflows/**` from staging. Prior evidence: no `ci.yml` exists and `git log -- .github/workflows/ci.yml` is empty. Put durable work in `quant_trading/`, `tests/`, `examples/`, `README.md`, or `pyproject.toml` instead.

## One precise next task (if continuing this line of work)

- Extend `tests/test_repository_integrity.py` so a function with a docstring but no `Args:` header is reported when its signature has documentable parameters. Reuse `_signature_param_names`, `_tree_undocumented_params`, and `_UNDOCUMENTED_PARAM_ALLOWLIST` around lines 2142-2426.
  - Constraints: AST-only and no imports; exclude `self`/`cls` and `*args`/`**kwargs`; keep the guard conservative and add an explicit allowlist for existing API debt rather than rewriting current docstrings.
  - Include a negative control (documented function with parameters but no `Args:` must be flagged) and a positive control (populated `Args:` passes).
  - Verify with `python -m pytest tests/test_repository_integrity.py -q`, `python -m ruff check tests/test_repository_integrity.py`, `python -m black --check tests/test_repository_integrity.py`, and `python -m mypy tests/test_repository_integrity.py`.