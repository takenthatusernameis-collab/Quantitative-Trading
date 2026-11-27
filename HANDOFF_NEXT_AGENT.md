## Session 2026-11-27 (allowlist cleanup - risk/manager.py reset_returns)

### What changed
- Added a confirmed-output, single-line `Examples:` section to `reset_returns` in
  `quant_trading/risk/manager.py`.
- Removed the `("quant_trading/risk/manager.py", "reset_returns")` entry from
  `_EXAMPLES_ALLOWLIST` in tests/test_repository_integrity.py.

### What was verified
- `python -m pytest tests/test_repository_integrity.py --doctest-modules quant_trading/risk/manager.py` -> 78 passed, 1 skipped.
- `python -m ruff check .` -> all passed.
- `python -m black --check quant_trading/ tests/` -> all files unchanged.

### Next task
Pick another public function in risk/manager.py (e.g. `disable`, `enable`, `reset`) with a docstring but no Examples, add a single-line doctest, de-allowlist, verify.
