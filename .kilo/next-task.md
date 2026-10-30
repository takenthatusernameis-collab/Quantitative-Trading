# Next Task

## Repository state

Checks: `python -m ruff check .` → clean. `python -m black --check quant_trading tests examples` → clean except `quant_trading/strategies/examples.py` (pre-existing, unrelated). `python -m mypy quant_trading tests examples` → clean, 0 errors across 131 source files. `python -m pytest --doctest-modules quant_trading` → 178 passed. `python -m pytest quant_trading/data` → 12 passed.

## What changed (this session)

Converted the module-level `Examples:` block in `quant_trading/data/synthetic.py` to executable `>>>` doctests (`create_synthetic_data`, `create_synthetic_provider`), following the instantiation/attribute-check style. Outputs verified offline before editing.

## What remains unresolved

- `quant_trading/strategies/examples.py` is not black-clean (pre-existing, unrelated).
- Full `pytest -q` could not finish (one network test hangs, pre-existing, unrelated).
- Prose-only `Examples:` blocks still lacking `>>>` doctests: `config/settings.py`, `data/providers.py`, `optimization/bayesian.py`, `risk/limits.py` (CheckResult), `risk/manager.py` (trailing-stop), `strategies/factory.py`.

## Approaches that failed and why

- None.

## One precise next task

- Convert the `CheckResult` `Examples:` block in `quant_trading/risk/limits.py:314` to executable `>>>` doctests, then run focused doctests, ruff, black, mypy.
- Constraints: do NOT commit unless explicitly asked; do not disable tests; preserve working baseline; exclude secrets/env/cache artifacts.
