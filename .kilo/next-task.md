# Next Task

## Repository state

Checks: `python -m pytest -q` (2206 passed, 0 failures), `python -m ruff check .` (clean), `python -m mypy quant_trading tests examples` (clean), `python -m black --check quant_trading tests examples` (clean). Baseline is green across tests, lint, type checks, and formatting.

## What changed (this session)

Bounded task: close a consistency gap in `AlphaVantageProvider` (`quant_trading/data/yfinance_provider.py`) and strengthen the README↔provider guard (`tests/test_readme.py`).

- Added `WEEKLY_ADJUSTED_INTERVALS: ClassVar[set[str]] = {"1wa", "weekly_adjusted"}` and `MONTHLY_ADJUSTED_INTERVALS: ClassVar[set[str]] = {"1ma", "monthly_adjusted"}` to `AlphaVantageProvider`, matching the pattern used by every other interval category (`WEEKLY_INTERVALS`, `MONTHLY_INTERVALS`, etc.).
- Updated `DataProvider.fetch` and `AlphaVantageProvider.fetch` to route `1wa`/`weekly_adjusted` and `1ma`/`monthly_adjusted` via `interval in self.WEEKLY_ADJUSTED_INTERVALS` / `self.MONTHLY_ADJUSTED_INTERVALS` instead of hardcoded tuples (`interval in ("1wa", "weekly_adjusted")`, `interval in ("1ma", "monthly_adjusted")`).
- Updated `AlphaVantageProvider.fetch_many` similarly: added the two flags and changed the per-symbol fallback condition from `interval in ("1d", "daily", "1wa", "weekly_adjusted") or is_weekly or is_monthly` to `interval in ("1d", "daily") or is_weekly_adjusted or is_weekly or is_monthly_adjusted or is_monthly`.
- Updated `_provider_av_intervals()` in `tests/test_readme.py` to read "Weekly Adjusted" and "Monthly Adjusted" live from `provider.WEEKLY_ADJUSTED_INTERVALS` / `provider.MONTHLY_ADJUSTED_INTERVALS` instead of hardcoding `{"1wa", "weekly_adjusted"}` / `{"1ma", "monthly_adjusted"}`. Previously the guard hardcoded these two categories, so drift would not have been caught — now all 18 README interval categories are live-checked against the provider.

Files changed: `quant_trading/data/yfinance_provider.py`, `tests/test_readme.py`.

## What was actually verified

- `python -m pytest tests/test_readme.py -q` -> 7 passed, 0 failures.
- `python -m pytest -q` (full suite) -> 2206 passed, 0 failures in ~152s (unchanged from baseline).
- `python -m ruff check .` -> All checks passed.
- `python -m mypy quant_trading tests examples` -> Success, no issues in 101 source files.
- `python -m black --check quant_trading tests examples` -> 101 files unchanged.
- `git status --short` -> only the two intended files modified; working tree otherwise clean.

## What remains unresolved

- None blocking. All checks green.

## Approaches that failed and why

- None this session. The change is small, additive, and backwards-compatible; no retries or alternate approaches were needed.

## One precise next task

Extend the README↔provider sync contract the same way the interval guard does, but for the provider's public methods: add a `TestReadmeAlphaVantageMethods` class in `tests/test_readme.py` that asserts every method named in the README's "Additional methods" bullets (e.g. `get_market_status()`, `get_currency_exchange_rate(...)`, `get_technical_indicator(...)`, `get_sma/get_ema/get_rsi/get_macd/get_stoch/get_bbands(...)`, `get_sector_performance()`, `get_gold_spot(...)`, `get_gold_history(...)`, `get_commodity(...)`, `get_economic_indicator(...)`, `search_symbols(...)`) exists as a public attribute on `AlphaVantageProvider`, and fails if the README advertises a method that is missing or removes one that exists. All these methods already exist (verified via grep), so the test should pass on first run; its value is catching future drift. Keep it bounded to `tests/test_readme.py` only; do not modify provider code unless a real gap is found.

Constraints:
- Follow the existing `_documented_entries()` / `_registry_section()` parsing style already used in `tests/test_readme.py`.
- Keep `black`, `ruff`, `mypy` clean and the full suite green.
- Do NOT commit unless explicitly asked.
