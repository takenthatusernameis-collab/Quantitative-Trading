## What changed (this session)

- Added an installed `quant-trading` console script so the CLI is usable as an installed command (previously only runnable via `python examples/cli.py`).
  - `pyproject.toml`: added `[project.scripts] quant-trading = "examples.cli:main"` and extended `[tool.setuptools.packages.find] include` from `["quant_trading*"]` to `["quant_trading*", "examples*"]` so `examples.cli` is importable after install.
  - No source or test files were touched; `examples/cli.py` is unchanged (its `sys.path.insert` shim is benign under an editable install).
- Diff: 1 file changed, `pyproject.toml` only (+4 lines / -1 line).

## What was actually verified (evidence)

- `pip install -e . --no-build-isolation` succeeds; the `quant-trading` script is installed.
- `quant-trading --version` -> `quant-trading 0.1.0`.
- `quant-trading --help` -> exit 0.
- `quant-trading --list-strategies` and `--list-providers` print the strategy/provider tables.
- Offline backtest smoke: `quant-trading --provider synthetic --offline --days 30 --strategy ma --output /tmp/qt_out.json --output-format json` runs and writes valid JSON.
- `python -m pytest tests/test_packaging.py tests/test_readme_cli.py -q` -> **10 passed**.
- Baseline coverage/consistency from the prior session is unchanged (this was a TOML-only change): 4035 passed / 142 deselected, TOTAL 99%, remaining misses all provably unreachable.

## What remains unresolved / not verified

- `black`, `ruff`, and `mypy` are not installed in this environment, so the format/lint/type checks could not be re-run here. They passed in the prior session (`black --check` 1 file unchanged; `ruff check` all passed; `mypy` success). This session's change is TOML-only, so those checks are unaffected.
- Regression sweep after adding `examples` to the packaged set: `tests/test_packaging.py` + `tests/test_readme_cli.py` (10 passed), `tests/test_example_scripts_run.py` (55 passed, ~2:48), `tests/test_readme.py` (17 passed). All green — no regression from packaging `examples`.

## Approaches that failed

- None.

## One precise next task

None — this session's task is complete (entry point added, installed, smoke-tested, and regression batch green). The next agent may pick any bounded, high-value task (e.g., a new feature or bug fix) after inspecting `git status`/`git log`. Do not re-run the full ~11-minute suite solely to re-confirm the coverage baseline; the prior baseline (4035 passed / 142 deselected, TOTAL 99%, remaining misses all provably unreachable) stands.

(End of file)
