## Session 2026-11-27 (allowlist cleanup - risk/manager.py public exit/stop helpers)

### What changed
- Added confirmed-output `Examples:` doctests to six public `RiskManager`
  methods in `quant_trading/risk/manager.py` that had a docstring but no
  Examples: `get_position_stop_loss`, `get_position_take_profit`,
  `should_stop_loss`, `should_take_profit`, `reset`, `disable`.
  (`get_position_take_profit` uses `round(..., 2)` because
  `100 * (1 + 0.15)` is `114.99999999999999` in float.)
- Removed those six `(quant_trading/risk/manager.py, <name>)` entries from
  `_EXAMPLES_ALLOWLIST` in tests/test_repository_integrity.py.

### What was verified
- `python -m pytest tests/test_repository_integrity.py --doctest-modules quant_trading/risk/manager.py`
  -> 85 passed, 1 skipped (was 79 passed; +6 doctests collected).
- `python -m ruff check .` -> all passed.
- `python -m black --check quant_trading/ tests/` -> 105 files unchanged.
- Full suite `python -m pytest -q` -> 5288 passed, 260 skipped, 151 deselected.

### Next task
Continue the allowlist cleanup in `quant_trading/risk/manager.py`. Two
evidence-based options (verify with the three commands above plus the full
suite):

1. Stale entries that ALREADY have valid Examples and can simply be
   de-allowlisted (no source edit needed): `as_frame`, `to_dict`,
   `total_component_var`, `total_volatility_contribution`,
   `calculate_risk_attribution`, `suggest_erc_weights`,
   `suggest_risk_budget_weights`. Confirm each name's every def in
   manager.py has a non-empty Examples section before removing its entry.
2. Public defs still lacking Examples: `calculate_metrics` and the
   `total_value` property. Add a single confirmed-output doctest to each,
   then de-allowlist.

Do NOT add allowlist entries for new code; the guard forbids it.