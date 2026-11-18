## Status

Audited CLI/reporting paths for `ulcer_index` exposure. Already present in `examples/cli.py`: single-run console print, single-run JSON output, and combined-run JSON output (per-strategy + best). No concrete gap found; no code changes made.

## What was actually verified

- grep confirmed `ulcer_index` at lines 2044, 2084-2085, 2583, 2632, 2807 of `examples/cli.py`.
- pytest unavailable in this environment (no pytest installed); could not run tests.

## Remaining work / unresolved

- `tests/test_cli.py` has no `ulcer_index` assertions; could add focused tests if desired, but not required by guards.
- Working tree unchanged (no commits).

## One precise next task

Pick another bounded high-value task (e.g., add focused CLI tests asserting `ulcer_index` appears in JSON output) or move to a new feature area.
