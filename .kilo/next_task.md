# Next Task

## What changed
- Added 7 tests to `tests/test_portfolio.py` covering short positions for `get_allocation` / `get_gross_allocation` / `get_net_allocation` with exact values and additional invariants (short-only portfolio, net-sum equals holdings-value fraction, gross exposure when leveraged).

## Verified
- `tests/test_portfolio.py` 50 passed (was 43).
- Full suite: 1466 passed, 1 skipped.
- `ruff check` clean; `mypy` clean on the test file.

## Next task
Pick a bounded, high-value task from the repo — e.g. review `examples/` or `quant_trading/strategies/` for a missing test or a deterministic bug, implement, and verify with the relevant test command.