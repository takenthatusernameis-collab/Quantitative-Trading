# Next Task: Unify the codebase formatter (resolve ruff-format vs black conflict)

## Status

READY to start.

## What changed this session

Cleaned up the two remaining lint/formatting issues so the project's configured quality gates all pass:

- `quant_trading/strategies/base.py` — fixed ruff import-sort error (I001): moved `from typing import Any` into correct sorted position (`ruff check --fix`).
- `quant_trading/strategies/examples.py` — fixed the same import-sort error (I001), then applied `black` formatting.
- `examples/cli.py` — applied `black` formatting.

2 files changed, 16 insertions(+), 4 deletions(-). Minimal and reversible.

## What was actually verified

- `ruff check quant_trading/ tests/ examples/` → **All checks passed!** (was 1 import-sort error)
- `black --check quant_trading/ tests/ examples/` → **78 files would be left unchanged** (clean)
- `mypy --strict quant_trading/` → **Success: no issues found in 36 source files**
- `pytest tests/` → **1096 passed, 1 skipped** (identical to pre-change baseline)
- Touched-module tests (test_cli, test_strategies_examples, test_strategy_base, test_strategy_factory): **241 passed**

## What remains unresolved / known conflict

`ruff format --check` still wants to reformat 10 files (quant_trading/optimization/{grid_search,random_search,walk_forward}.py, quant_trading/strategies/examples.py, examples/cli.py, examples/run_{parabolic_sar,backtest,vwap,optimization,backtest_offline}.py) because ruff-format prefers `i + 1` (spaces around `+`) while black — the project's configured `[tool.black]` formatter — prefers `i+1`. The two tools genuinely disagree; adopting black as canonical (done here) leaves ruff-format dissatisfied on those 10 files, and vice versa. Do NOT ping-pong between them.

## Blocked / not done

- Push of restored `.github/workflows/ci.yml` still blocked by missing `workflows` permission on the GitHub App token (per prior handoff). Do not retry unchanged.

## One precise next task

Pick ONE canonical formatter and enforce it project-wide so no gate conflicts:

**Option A (recommended — matches `[tool.black]` and this session):** black stays canonical. Add explicit project guidance that ruff-format is NOT a gate (document the `i+1` vs `i + 1` divergence), OR configure ruff to not reformat. Leave `ruff check` + `black --check` + `mypy --strict` + `pytest` as the enforced gate set.

**Option B:** switch canonical formatter to ruff-format, run `ruff format` on all 10 files, and remove/deprecate `[tool.black]` + black from dev deps so black no longer fights ruff-format.

Either option must end with: `ruff check` clean, chosen formatter clean, `mypy --strict quant_trading/` clean, `pytest tests/` green (1096 passed, 1 skipped). Update `.kilo/next_task.md` when done.

Evidence/constraints: baseline test count is 1096 passed / 1 skipped; mypy strict is currently clean (do not regress it); ruff check is currently clean (do not reintroduce import-sort issues). Working tree currently clean except the 2 files above.
