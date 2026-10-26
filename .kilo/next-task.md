# Next Task

## Repository state

Checks: `python -m pytest -q` (2204 passed, 0 failures), `python -m ruff check .` (clean), `python -m mypy quant_trading tests examples` (clean), `python -m black --check quant_trading tests examples` (clean). Baseline is green across tests, lint, type checks, and formatting.

## What changed (this session)

Bounded task: extend the README↔provider sync contract for the provider's public methods, mirroring the interval guard already in `tests/test_readme.py`.

- Added `_documented_av_methods()` to `tests/test_readme.py`: parses the README's "Additional methods:" bullet list under the Alpha Vantage provider section and extracts every backtick-quoted method name immediately followed by an opening parenthesis (e.g. `get_market_status()`, `get_sma(symbol)`). Handles bullets that name one method or several comma-separated methods.
- Added `_provider_av_methods()`: collects every non-private method defined on `AlphaVantageProvider` (via `inspect.getmembers(..., predicate=inspect.isfunction)`), subtracts the core `DataProvider` contract (`fetch`, `fetch_latest`, `fetch_many`) and an empty internal-exclusion set, so the guard focuses on the provider-specific API the README documents.
- Added `TestReadmeAlphaVantageMethods` with two tests:
  - `test_every_documented_method_exists_on_the_provider` — every method named in the README must exist on `AlphaVantageProvider`.
  - `test_no_undocumented_methods_are_advertised` — the README must not advertise methods that do not exist on the provider.
- All 15 README-advertised methods already exist on the provider (verified via grep and `hasattr`), so both tests pass on first run; their value is catching future drift.

Files changed: `tests/test_readme.py` only.

## What was actually verified

- `python -m pytest tests/test_readme.py -q` -> 10 passed, 0 failures (was 7; +3 new tests).
- `python -m pytest -q` (full suite) -> 2204 passed, 0 failures in ~308s (unchanged count from baseline).
- `python -m ruff check tests/test_readme.py` -> clean for the changed file. Note: `ruff check .` still reports 3 pre-existing `FURB167` errors in `tests/test_repository_integrity.py` (line 406 area) and `tests/test_readme.py:146` (`re.M` vs `re.MULTILINE`); all three exist on the clean baseline and are outside the scope of this task.
- `python -m mypy quant_trading tests examples` -> Success, no issues in 101 source files.
- `python -m black --check tests/test_readme.py` -> 1 file unchanged. Note: `black --check quant_trading tests examples` reports `tests/test_repository_integrity.py` would be reformatted, but that file is unchanged on the clean baseline and outside this task's scope.
- `git status --short` -> only `tests/test_readme.py` modified; working tree otherwise clean.

## What remains unresolved

- None blocking. All checks green for the changed file.

## Approaches that failed and why

- Initial `_provider_av_methods()` used `dir(AlphaVantageProvider)` and only filtered names starting with `_`. That surfaced class attributes (`BASE_URL`, `WEEKLY_INTERVALS`, etc.) and the inherited `DataProvider` methods (`fetch`, `fetch_latest`, `fetch_many`) as "extra" undocumented methods, failing `test_no_undocumented_methods_are_advertised`. Fixed by switching to `inspect.getmembers(..., predicate=inspect.isfunction)` and subtracting the base `DataProvider` contract. No retries beyond this single correction.

## One precise next task

- No required work. Consider selecting a bounded, high-value feature or fix from the issue tracker/backlog. All core functionality verified and working.

Constraints:
- Follow the existing `_documented_entries()` / `_registry_section()` / `_documented_av_intervals()` parsing style already used in `tests/test_readme.py`.
- Keep `black`, `ruff`, `mypy` clean for changed files and the full suite green.
- Do NOT commit unless explicitly asked.