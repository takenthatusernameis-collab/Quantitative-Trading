## Session 2026-11-27 (allowlist cleanup - risk/manager.py clear_returns)

### What changed
- Added a confirmed-output, single-line `Examples:` section to `clear_returns` in
  `quant_trading/risk/manager.py`.
- Removed the `("quant_trading/risk/manager.py", "clear_returns")` entry from
  `_EXAMPLES_ALLOWLIST` in tests/test_repository_integrity.py.

### What was verified
- `python -m pytest tests/test_repository_integrity.py --doctest-modules quant_trading/risk/manager.py` -> 77 passed, 1 skipped.
- `ruff check` and `black --check` -> all passed.

### Next task
Pick another public function in risk/manager.py (e.g. `disable`, `enable`, `reset`, `reset_returns`) with a docstring but no Examples, add a single-line doctest, de-allowlist, verify.
