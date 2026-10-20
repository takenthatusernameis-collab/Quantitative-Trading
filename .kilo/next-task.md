# Next Task

## What changed
- `Portfolio.get_allocation()` now accepts `use_absolute=False`; added `get_net_allocation()` and `get_gross_allocation()`.

## Verified
- `tests/test_portfolio.py` 37 passed.

## Next task
Add tests in tests/test_portfolio.py covering short positions for get_allocation/get_gross_allocation/get_net_allocation and verify invariants.
