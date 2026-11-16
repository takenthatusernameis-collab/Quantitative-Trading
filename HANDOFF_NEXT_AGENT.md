## What changed (this session)

- Fixed a stale strategy count in `tests/test_strategy_registry_coverage.py`: the
  module docstring claimed "47 built-in strategies" while the live registry
  exposes 48 (the previous session fixed the same drift in the README feature
  bullet but missed this docstring).
- Added a regression guard `test_module_docstring_strategy_count_matches_registry`
  that parses the module docstring with `ast` and pins the stated count to
  `len(get_registry().primary_keys())`, so the number cannot silently drift again
  when a strategy is added.

## What was actually verified (evidence)

- `python -m pytest tests/test_strategy_registry_coverage.py -q`: 10 passed.
- `python -m pytest tests/test_strategy_registry_coverage.py tests/test_readme.py tests/test_repository_integrity.py -q`: 57 passed.
- Full suite `python -m pytest -q`: 3987 passed, 144 deselected (was 3986 before;
  +1 is the new guard test).
- `python -m ruff check tests/test_strategy_registry_coverage.py`: all checks passed.
- `python -m black --check tests/test_strategy_registry_coverage.py`: unchanged.
- `python -m mypy tests/test_strategy_registry_coverage.py`: Success, no issues.
- Negative check (inline script): replacing "48" with "47" in the docstring makes
  the guard fail, confirming it actually detects drift.

## What remains unresolved / not verified

- Nothing blocking. Repo is green.

## Approaches that already failed and why

- No failed approaches this session. The prior handoff reported the repo green;
  this session confirmed that and closed the one remaining count-drift gap.

## One precise next task

- No code task required. If further work is desired, pick the next consistency
  invariant of the same class: audit remaining hard-coded strategy/feature counts
  in docs and docstrings (e.g. search for "registered strategies", "built-in
  strategies", "strategies (see") and pin each to the live registry. Evidence:
  `grep -rn "built-in strateg\|registered strateg" --include=*.py --include=*.md .`.
  Constraint: keep changes minimal and add a guard test for each pinned count.