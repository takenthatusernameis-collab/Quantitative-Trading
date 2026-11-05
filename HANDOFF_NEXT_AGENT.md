# Handoff to next agent

## What changed

- Added `test_readme_backtick_quant_trading_names_resolve` to `tests/test_repository_integrity.py`: scans README backticks for `quant_trading.*` dotted names and asserts each resolves via `importlib.import_module`.

## Verified (evidence)

- `python -m ruff check .` → All checks passed.
- `python -m pytest tests/test_repository_integrity.py -q` → 24 passed.

## Unresolved

- None.

## Next task (precise)

- Candidate: extend CLI flag coverage or add guard for README-documented flags. Keep minimal and reversible.
"