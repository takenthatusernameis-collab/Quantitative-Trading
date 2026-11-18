## Status

Black formatting drift in tests/test_risk_attribution.py fixed; repository integrity check passes.

## What changed

- Reformatted tests/test_risk_attribution.py with black.

## What was verified

- `python3 -m black --check tests/test_risk_attribution.py` → 1 file unchanged
- `python3 -m pytest tests/test_repository_integrity.py::test_repository_is_black_formatted` → 1 passed

## Remaining work

None. No next task.
