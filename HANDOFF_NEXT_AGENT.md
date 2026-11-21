## Status

Hardened `RiskAttribution.from_dict` and `PortfolioRisk.from_dict` in
`quant_trading/risk/manager.py` to sanitize non-finite values to 0.0 via a
`_finite` helper mirroring `quant_trading/risk/metrics.py`.

## Verified

- doctest-modules: 50 passed
- pytest tests/test_risk_manager.py tests/test_risk_metrics.py: 442 passed
- ruff, black, mypy clean

## Next Task

Harden `Holding.from_dict` (portfolio/portfolio.py:178) and
`Portfolio.from_dict` (portfolio/portfolio.py:573) with same `_finite` pattern.
Add regression tests in tests/test_portfolio.py.

Verify with pytest + doctest + ruff/black/mypy.
