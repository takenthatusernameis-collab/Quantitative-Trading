## Session 2026-11-27 (allowlist cleanup - risk/manager.py enable)

### What changed
- Added a confirmed-output, single-line `Examples:` section to `enable` in
  `quant_trading/risk/manager.py` (toggles `disable()` then `enable()` and
  asserts `risk_enabled` is `True`).
- Removed the `("quant_trading/risk/manager.py", "enable")` entry from
  `_EXAMPLES_ALLOWLIST` in tests/test_repository_integrity.py.

### What was verified
- `python -m pytest tests/test_repository_integrity.py --doctest-modules quant_trading/risk/manager.py` -> 79 passed, 1 skipped (one more doctest collected than the prior 78).
- `python -m ruff check .` -> all passed.
- `python -m black --check quant_trading/ tests/` -> 105 files unchanged.

### Next task
Pick another public function in risk/manager.py still on the allowlist
(e.g. `disable`, `reset`, `get_position_stop_loss`, `get_position_take_profit`,
`should_stop_loss`, `should_take_profit`) with a docstring but no Examples, add a
single-line doctest, de-allowlist, verify with the three commands above.