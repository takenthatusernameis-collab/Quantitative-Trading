# Quality Gates (canonical formatter resolved)

## Status

DONE. Canonical formatter is `black`. Enforced gate set:

- `ruff check quant_trading/ tests/ examples/`
- `black --check quant_trading/ tests/ examples/`
- `mypy --strict quant_trading/`
- `pytest tests/`

`ruff format` is NOT a gate: ruff-format disagrees with black on `i+1` vs `i + 1` spacing in 10 files. Do not ping-pong.

## What was verified

- ruff check → All checks passed!
- black --check → 78 files unchanged
- mypy --strict → Success, 36 source files
- pytest tests/ → 1096 passed, 1 skipped

## Next precise task

None required. Optional: add CI workflow restoring `.github/workflows/ci.yml` when `workflows` permission is available (blocked by token scope).
