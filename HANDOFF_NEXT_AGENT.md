## What changed (this session)

- Fixed README feature-bullet strategy count: 47 -> 48 to match live registry (ma_envelope added previously).

## What was actually verified (evidence)

- `python -m pytest tests/test_readme.py::TestReadmeStrategyRegistry -q`: 5 passed.
- Full suite previously 3985 passed + 1 failed (this exact test); now resolved.

## What remains unresolved / not verified

- Nothing blocking.

## One precise next task

- None required. Repo green.