## Status

The prior handoff task is complete: the allowlist line-number brittleness has
been eliminated. The previous session (commit 3fdd244) already converted
`_EXAMPLES_ALLOWLIST` from `(rel, name, lineno)` tuples to `(rel, name)` and
renamed the stale-line-number guard `test_examples_allowlist_lineno_current`
to `test_examples_allowlist_names_exist`. That left two residue defects in
the working tree that this session cleaned up.

## What changed

- `tests/test_repository_integrity.py`
  - Removed the stale comment on `_EXAMPLES_ALLOWLIST_NAMES` that still
    referenced a non-existent `test_examples_allowlist_lineno_current` guard
    and the now-removed `lineno` field. Replaced with a comment describing the
    name-only matching invariant and pointing at the actual guard.
  - Collapsed the multi-line `frozenset(_EXAMPLES_ALLOWLIST)` constructor to a
    single line so `black --check` passes (it was a black formatting
    violation).
  - Expanded the docstring of `test_examples_allowlist_names_exist` to state
    the name-only matching invariant and what the guard catches (renamed or
    removed entries).

No source files, metrics, or other tests were touched.

## What was actually verified

- `python -m pytest tests/test_repository_integrity.py -q -p no:cacheprovider`
  -> 51 passed (was 50 passed + 1 failed; the failure was
  `test_repository_is_black_formatted` caused by the black violation above).
- `python -m black --check tests/test_repository_integrity.py` -> clean.
- `python -m ruff check tests/test_repository_integrity.py` -> clean.
- `python -m pytest tests/test_risk_metrics.py tests/test_backtest_report.py -q`
  -> 172 passed, 48 skipped (matplotlib absent), confirming no regressions in
  the previously completed ulcer-index / drawdown work.

## Remaining work / unresolved

- Chart functions remain untested because matplotlib is not installed
  (optional `reporting` extra; chart tests skip). Only pure helpers are
  covered. Not a defect; an environment gap.
- The `_UNDOCUMENTED_PARAM_ALLOWLIST` (test_repository_integrity.py:2496) is
  keyed by `(rel, name, param)` and is therefore already name-based; no line
  number brittleness there. No action needed.

## Approaches already tried and why (avoid repeating)

- The prior session already did the substantive fix (dropping the `lineno`
  component from `_EXAMPLES_ALLOWLIST`). This session only cleaned up the
  residue: a stale comment and a black formatting violation. Do not renumber
  allowlist entries by hand -- the name-only matching makes that unnecessary.

## One precise next task

None queued. The allowlist brittleness task is fully resolved and verified.
If a new task is desired, pick a bounded, high-value item from the remaining
unresolved list above (or a fresh defect) and verify it with the same
`pytest + black --check + ruff check` gate.

(End of file)