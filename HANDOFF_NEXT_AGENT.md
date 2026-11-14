## What changed (this session)
- Fixed a real, reproducible export-surface defect: five public names were re-exported by a package `__init__.py` but omitted from the defining module's `__all__`, so `from <module> import *` silently dropped them even though `from <package> import <name>` worked.
  - `quant_trading/strategies/base.py`: added `BaseStrategy` to `__all__` (the module-level alias `BaseStrategy = Strategy`).
  - `quant_trading/strategies/examples.py`: added `PPO` and `PVO` to `__all__` (module-level aliases for the oscillator strategies).
  - `quant_trading/risk/manager.py`: added `RiskAttribution` to `__all__`.
  - `quant_trading/optimization/base.py`: added `ObjectiveFunction` to `__all__` (the `Callable[[BacktestResult], float]` alias).
- Added a deterministic guard, `test_package_reexports_are_listed_in_defining_module_all` in `tests/test_repository_integrity.py`, covering the direction the existing `test_all_package_all_exports_resolve` cannot see (package `__all__` -> defining-module `__all__`).
- Prior handoff-only commits were not counted as progress; this session made a source + test change.

## What was actually verified (evidence)
- Pre-change baseline: `python3 -m pytest -q` -> `3782 passed, 140 deselected` (RC 0); `ruff check .` clean; `mypy quant_trading/` -> `Success: no issues found in 38 source files`.
- Enumerated the defect with an AST/import script: exactly 5 names re-exported by a package but missing from the source module `__all__` (`PPO`, `PVO`, `BaseStrategy`, `RiskAttribution`, `ObjectiveFunction`). After the fix the same script reports `remaining gaps: []`, and each `from <module> import *` now binds the name.
- Mutation check: temporarily reverted `RiskAttribution` from `quant_trading/risk/manager.py` `__all__`; the new guard failed with the expected message, then the file was restored (`RESTORED`).
- Post-change: `python3 -m ruff check .` -> `All checks passed!`; `python3 -m mypy quant_trading/` -> `Success: no issues found in 38 source files`.
- `python3 -m pytest -q tests/test_repository_integrity.py tests/test_packaging.py` -> `33 passed`.
- `python3 -m pytest -q tests/test_strategies_examples.py tests/test_strategy_registry_coverage.py tests/test_risk_attribution.py tests/test_optimization.py` -> `823 passed`.
- Full suite: `python3 -m pytest -q` -> `3783 passed, 140 deselected in 540.52s` (RC 0). The +1 over the 3782 baseline is the new guard.

## What remains unresolved
- Nothing blocking. Not verified this session: network-backed provider paths (`--provider yfinance` / `alphavantage`) and the long-running smoke tests (deselected by the default `-m "not slow and not network"` marker filter).

## Failed approaches (do not repeat unchanged)
- No approach failed. Do not repeat the prior sessions' pattern of inspecting the repo and then writing only a refreshed handoff with no source/test change; that produced six consecutive handoff-only commits (`99c8358`..`e564c08`) and is explicitly excluded from project progress by `.github/scripts/kilo-controller.sh`.

## One precise next task
- Extend the same export-drift guard to the remaining drift classes with the same one-way technique: (a) assert every name in `quant_trading/__init__.py`'s `__all__` also appears in the submodule `__all__` it was imported from (root package currently re-exports `BacktestEngine`, `BaseStrategy`, `create_strategy`, etc.); and (b) assert `examples/cli.py`'s `CLI_ARG_DEFAULTS` values match the corresponding strategy class `__init__` defaults — this currently has 17 known drifts (e.g. `cho.fast_period` CLI 10 vs class 3, `klinger.slow_period` CLI 30 vs class 200, `vol.slow_period` CLI 30 vs class 13) which are intentional for some strategies but are undocumented and unguarded, so decide per-strategy whether the CLI default or the class default is canonical before adding the assertion.