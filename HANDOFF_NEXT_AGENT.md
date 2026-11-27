## Session 2026-11-27 (allowlist cleanup - `_build_crypto_intraday_params`)

### What changed
- Documented `AlphaVantageProvider._build_crypto_intraday_params` in
  `quant_trading/data/yfinance_provider.py` (def ~line 1352,
  `symbol: str, market: str = "USD", interval: str = "5min"`) with a
  deterministic single-line doctest:
  `AlphaVantageProvider(cache_dir="", warn_on_demo=False)._build_crypto_intraday_params("BTC")`
  -> `{'function': 'DIGITAL_CURRENCY_INTRADAY', 'symbol': 'BTC', 'market': 'USD', 'interval': '5min', 'apikey': 'demo', 'datatype': 'json'}`.
- Removed the `("quant_trading/data/yfinance_provider.py",
  "_build_crypto_intraday_params")` line from `_EXAMPLES_ALLOWLIST` in
  `tests/test_repository_integrity.py` (no blank line left behind).
- No production behavior changed (docstring + allowlist only).
- Diff before this handoff update: 2 files, +4/-1.

### Note on the prior handoff (stale "next task")
- The previous `HANDOFF_NEXT_AGENT.md` listed `_build_crypto_daily_params` as
  the next task, but that was ALREADY completed in the last commit
  (`0831084`, "documented `_build_crypto_daily_params` + removed its allowlist
  line"). The prior agent did not update the handoff after that commit. This
  session therefore continued with the actual next allowlist entry in order,
  `_build_crypto_intraday_params`, rather than repeating completed work.

### What was actually verified (evidence)
- `python -m pytest tests/test_repository_integrity.py --doctest-modules quant_trading/data/yfinance_provider.py`
  -> 81 passed (was 80; the new doctest executed).
- `python -m pytest tests/test_repository_integrity.py` -> 51 passed.
- `python -m pytest tests/test_yfinance_provider.py
  tests/test_alphavantage_provider.py tests/test_data_providers.py
  tests/test_yfinance_fetch_many.py` -> 454 passed.
- Bounded broader subset (`test_config, test_synthetic, test_utils,
  test_serialization_roundtrip, test_strategy_base, test_strategy_factory,
  test_core_only_imports, test_data_providers`) -> 452 passed.
- `python -m ruff check .` -> All checks passed.
- `python -m black --check quant_trading/ tests/ examples/` -> 166 files unchanged.
- `git diff --check` -> clean.
- The actual method output was checked with a live `python -c` run before editing.

### What remains unresolved
- `quant_trading/data/yfinance_provider.py` still has 75 `_EXAMPLES_ALLOWLIST`
  entries (was 77 at the prior handoff; this session removed one, the prior
  commit removed one). Total allowlist across all files is 310 (AST count via
  `tests.test_repository_integrity._EXAMPLES_ALLOWLIST`; was 312).
- Note: counting allowlist lines with `grep` undercounts (multi-line entries);
  use the AST count above for an accurate number.

### Approaches that failed / constraints (do not blindly repeat)
- Removing an allowlist line can leave a blank line that Black then flags; this
  session removed the line together with its newline so no blank line remained
  and no formatter-wide changes were needed.
- The intraday doctest output line is ~125 chars (> ruff line-length 100), but
  ruff's default rule set does NOT include E501 and Black does not reformat
  docstring content, so it passes (same as the longer `_build_crypto_daily_params`
  line added in the prior commit). Do not "fix" this by splitting the doctest;
  it must stay a single parseable line.
- `python -m pytest -q` (whole suite) previously exceeded a 300s timeout in this
  environment. This is a tooling/time-budget limit, not a demonstrated code
  failure. Prefer the focused + bounded-subset commands above; if a full run is
  needed, run it directory-by-directory or with a larger timeout.

### Next task (one precise step)
Inspect `_EXAMPLES_ALLOWLIST` for the next deterministic allowlisted method in
`quant_trading/data/yfinance_provider.py`. The next in allowlist order is
`_build_crypto_monthly_params` (def ~line 1333,
`symbol: str, market: str = "USD"`). Its actual output was already verified with
a live run:
`AlphaVantageProvider(cache_dir="", warn_on_demo=False)._build_crypto_monthly_params("BTC")`
-> `{'function': 'DIGITAL_CURRENCY_MONTHLY', 'symbol': 'BTC', 'market': 'USD', 'apikey': 'demo', 'datatype': 'json'}`.
Re-verify with a live `python -c` run, then document it with a deterministic
single-line doctest using `AlphaVantageProvider(cache_dir="", warn_on_demo=False)`
and the default market. Remove its allowlist line together with its newline (no
blank line left), then rerun the same focused integrity/module tests, provider
subset, Ruff, Black, `git diff --check`, and bounded broader subset before
selecting another def.

(End of file)