# Next Task

## Repository state

Checks: `python -m pytest -q` (2204 passed, 0 failures), `python -m ruff check .` (clean), `python -m mypy quant_trading tests examples` (clean), `python -m black --check quant_trading tests examples` (clean). Baseline is green.

## Completed this session

- Added regression guard `test_documented_aliases_match_the_registry` in `tests/test_readme.py`: the README Strategy Registry table's per-strategy aliases must match the live registry aliases (both directions).
- Fixed `ALIAS_LIST` regex in `tests/test_readme.py` to match both `alias:` (singular) and `aliases:` (plural) README forms; previously single-alias strategies parsed as having no aliases.
- Fixed real drift found by the new guard: `README.md` `ichimoku` entry listed itself as its own alias (`aliases: ichimoku_cloud, ichimoku`) → reduced to `alias: ichimoku_cloud` since `ichimoku` is the primary key.
- Verified the guard catches regression: injected a bogus alias → test failed; restored → all pass.

## What was actually verified

- `python -m pytest tests/test_readme.py -q` → 6 passed, 0 failures.
- `python -m pytest -q` (full suite) → 2204 passed, 0 failures (~150s).
- `python -m ruff check .` → All checks passed.
- `python -m mypy quant_trading tests examples` → Clean, 101 files.
- `python -m black --check quant_trading tests examples` → All checks passed.
- Pre-existing: `black --check README.md` fails (black not configured for markdown), unchanged from baseline.

## What remains unresolved

- None blocking. Repository is green across tests, lint, type checks, and formatting.

## Approaches that failed

- None this session. Prior context: a literal "every CLI flag documented in the README" test was rejected (~100 false positives; README uses prose patterns).

## One precise next task

No assigned task remains. Baseline is green. Changes this session: 2 files (`README.md`, `tests/test_readme.py`). Do NOT commit unless explicitly asked.
