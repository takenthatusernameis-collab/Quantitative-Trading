## What changed (this session)

- The assigned `Strategy.update_positions` override guard was already functionally complete (added in commit ca05a40); this session closed its style gap by adding the docstrings its sibling helpers/tests all carry in `tests/test_repository_integrity.py`:
  - `_normalize_update_positions_annotation`, `_tree_update_positions_override_mismatches`, `_documented_update_positions_override_mismatches`, and `test_update_positions_overrides_annotated`.
- Added a new reverse-coverage guard in `tests/test_strategy_registry_coverage.py`:
  - `_defined_strategy_classes()` + `test_every_defined_strategy_class_is_registered()` assert every `Strategy` subclass defined in `quant_trading/strategies/examples.py` is wired up by a `register_strategy(...)` call. This is the reverse of `test_every_registered_strategy_has_an_example_script` and catches the common "added a class, forgot to register it" dead-code mistake.

## What was actually verified (evidence)

- `python -m pytest -q` -> `4008 passed, 142 deselected in 379s` (was `4007 passed` before; +1 for the new test). No regressions.
- `python -m pytest -q -m "slow and not network"` -> `142 passed, 4007 deselected` (the normally-deselected slow suite is green; total repo = 4149 tests).
- `python -m pytest tests/test_repository_integrity.py tests/test_strategy_registry_coverage.py tests/test_strategy_factory.py -q` -> `95 passed`.
- `python -m ruff check tests/test_repository_integrity.py tests/test_strategy_registry_coverage.py` -> `All checks passed!`
- `python -m black --check` on both files -> `left unchanged`.
- New guard is non-vacuous: `_defined_strategy_classes()` returns 48 names, registry exposes 48 primary keys, `defined - registered == []`.

## What remains unresolved / not verified

- CI workflow execution on GitHub Actions was not observed (workflow files are controller-managed and cannot be persisted by an agent session).
- The `network`-marked selection collects 0 tests (`pytest -m network --collect-only` -> none), so there is no network suite to run offline.

## Approaches that already failed / were ruled out (do not repeat)

- Do not modify or add files under `.github/workflows/`. The controller restores tracked workflow files, cleans untracked workflow files, and excludes `.github/workflows/**` from staging. Put durable work in `quant_trading/`, `tests/`, `examples/`, `README.md`, or `pyproject.toml`.
- Extending `See Also:`/`References:` guards is vacuous: no such sections exist anywhere in `quant_trading/` or `examples/`.
- A `Strategy.category`/`description` *assignment* guard is not viable: none of the 48 classes set `category` (or `description`) in the class body — `description` is auto-derived from the docstring by `Strategy.__init_subclass__`, and `category` is dead metadata (never set, never read). A guard would flag all 48.
- Guarding `Strategy.get_parameters`/`set_parameter` overrides is vacuous: neither is overridden anywhere.
- Guarding `Strategy.generate_signals` is redundant: it is `@abstractmethod`, so ABC already enforces implementation at instantiation.
- Duplicate-primary-key handling in `StrategyRegistry.register` (factory.py:124 overwrites silently) is *intended*: `tests/test_strategy_factory.py::test_reregister_overwrites` pins that behavior. Do not "fix" it.
- The 48 registered strategies already have full example-script + `Test<ClassName>` + registry coverage; further registered->X guards would be redundant.

## One precise next task

- Add a coverage guard in `tests/test_strategy_registry_coverage.py`: every registered strategy's auto-derived `description` (from `Strategy.__init_subclass__`) must be a non-empty string, so `--list-strategies` never shows a blank description. Implement `test_every_registered_strategy_has_a_description()` asserting `get_registry().get(key).description` is a non-empty `str` for every primary key. This currently holds 48/48 (verified: zero registered strategies with empty `description`), so it should pass on first run. Match the file's existing real-tree assertion style (no synthetic control needed, consistent with `test_every_registered_strategy_has_a_test_class`). Then rerun `python -m pytest tests/test_strategy_registry_coverage.py -q`, `ruff check`, and `black --check` on the modified file. If a real violation appears, add the missing class docstring rather than weakening the guard.