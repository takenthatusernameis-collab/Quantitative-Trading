# Next Task: Fix remaining strict-mypy annotation gaps in optimization module

## Status

OPEN - Not yet started.

## What changed this session

- Changed three `# type: ignore[import]` comments in `quant_trading/optimization/bayesian.py` to `# type: ignore[import-untyped]` (the narrower code mypy requires). Default `mypy quant_trading/` still passes (36 files); strict mode no longer reports unused-ignore for those lines.

## Verified

- `mypy quant_trading/optimization/bayesian.py` -> Success
- `pytest tests/test_optimization.py` -> 86 passed

## Remaining work

Strict mypy (`mypy --strict`) still reports 49 errors across 13 files in `quant_trading/` (missing type args for `list`/`dict`, untyped defs, no-untyped-call in walk_forward). Highest-value, lowest-risk subset: `quant_trading/optimization/grid_search.py` (untyped `GridSearch` constructor + missing generics) and `random_search.py` (missing generics). Fix with smallest per-file changes; keep default mypy green.

## Blocked / not done

- Push of restored `.github/workflows/ci.yml` still blocked by missing `workflows` permission on the GitHub App token. Do not retry unchanged.
