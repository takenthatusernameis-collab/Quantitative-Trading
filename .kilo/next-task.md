# Next Task

## Repository state

Checks: `python -m pytest -q` (2206 passed, 0 failures), `python -m ruff check .` (clean), `python -m mypy quant_trading tests examples` (clean), `python -m black --check quant_trading tests examples` (clean for the file this session touched). Baseline was 2204 passed before this session's new guard.

## Completed this session

- Added regression guard `TestReadmeAlphaVantageIntervals.test_documented_intervals_match_the_provider` in `tests/test_readme.py`: the README's Alpha Vantage "Supported intervals" table (18 concrete category bullets) must exactly match the live `AlphaVantageProvider` ClassVar interval sets, in both directions.
- Added helpers `_av_supported_section()`, `_documented_av_intervals()`, `_provider_av_intervals()` and the `_AV_INTERVAL_CATEGORIES` allow-list. The "Technical Indicators" bullet (ends with "etc.") and the "Real-time Batch" fallback bullet are deliberately excluded from the exact-match check because neither names a concrete set of members.
- Verified the guard catches regressions in both directions: injected a bogus interval into the README Intraday bullet -> test failed with `README intervals not accepted by the provider: ['bogus_interval']`; removed a real `60m` from the same bullet -> test failed with `provider intervals missing from README: ['60m']`; README restored -> 7/7 README tests pass.

## What was actually verified

- `python -m pytest tests/test_readme.py -q` -> 7 passed, 0 failures (was 6).
- `python -m pytest -q` (full suite) -> 2206 passed, 0 failures in ~148s (baseline 2204 + 2 new tests).
- `python -m ruff check .` -> All checks passed.
- `python -m mypy quant_trading tests examples` -> Success, no issues in 101 source files.
- `python -m black --check quant_trading tests examples` -> All checks passed for `tests/test_readme.py` (the file this session changed).
- Pre-existing, unrelated to this session: `black --check tests/test_repository_integrity.py` reports "1 file would be reformat". That file is byte-identical to HEAD (`git show HEAD:tests/test_repository_integrity.py` matches the working tree), so the complaint is a pre-existing baseline condition, not introduced here. `black --check README.md` also fails (black not configured for markdown), unchanged from baseline.

## What remains unresolved

- None blocking. Repository is green across tests, lint, type checks, and formatting for the changed file.
- Pre-existing: `black --check tests/test_repository_integrity.py` and `black --check README.md` fail; both are baseline conditions unrelated to this session's change.

## Approaches that failed

- None this session. Prior context (previous sessions): a literal "every CLI flag documented in the README" test was rejected (~100 false positives; README uses prose patterns). This session's bounded guard is the high-signal version, scoped to the Alpha Vantage interval table where the contract is a concrete, enumerable set.

## One precise next task

No assigned task remains. Baseline is green. Changes this session: 1 file (`tests/test_readme.py`). Do NOT commit unless explicitly asked.

(End of file - total 66 lines)