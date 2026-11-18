## Status

All assigned work complete. Both directions of the core/optional-extras import invariant are locked and verified in an environment with extras installed.

## What changed

- No production or test code changed. `tests/test_core_only_imports.py` and `tests/test_optional_extras_readme_commands.py` remain committed and pushed in `81dd0e2`.
- Installed optional extras (`pip install -e ".[dev]"`) locally to run the inverse-direction tests.

## What was verified

- `python3 -c "import matplotlib, skopt"` → ok
- `python3 -m pytest tests/test_core_only_imports.py tests/test_optional_extras_readme_commands.py -q` → 3 passed, 0 skipped in 12.36s
- `python3 -m ruff check ...` → All checks passed
- `python3 -m black --check ...` → 2 files unchanged

## Remaining work

None. No next task.
