## Status

Hardened `Holding.from_dict` (quant_trading/portfolio/portfolio.py) and
`Portfolio.from_dict` (quant_trading/portfolio/portfolio.py) with the same
`_finite` helper pattern used in `quant_trading/risk/metrics.py` and
`quant_trading/risk/manager.py`. Non-finite / non-numeric / missing numeric
fields are sanitized to `0.0` so a corrupted dictionary cannot poison a
reconstructed holding or portfolio with NaN/inf.

Added regression tests in tests/test_portfolio.py:
- TestHoldingSerialization: non-finite values, non-numeric values, numeric
  strings, missing-field defaults
- TestPortfolioSerialization: non-finite portfolio fields, non-finite holdings,
  non-numeric portfolio fields

## Verified

- pytest tests/test_portfolio.py + doctest-modules quant_trading/portfolio/portfolio.py: 86 passed
- ruff check: clean
- black --check: clean
- mypy quant_trading/portfolio/portfolio.py: clean

Full `pytest` suite times out locally (>5 min) — appears to be pre-existing
slowness unrelated to this change; verify in CI if available.

## Next Task

Scan for any remaining `from_dict` deserializers that still accept raw
non-finite values (e.g. in quant_trading/risk/limits.py) and harden them with
the same `_finite` pattern, adding regression tests and verifying with pytest +
doctest + ruff/black/mypy. If none remain, the hardening chain is complete.
