## What changed (this session)

- Updated README CLI docs to reflect the installed `quant-trading` console script added in `pyproject.toml` (HEAD `0b0f8d6`).
  - `README.md`: Basic Usage now documents `quant-trading` as the primary command (after install) while keeping `python examples/cli.py` as a dev alternative; updated the opening examples and the list-strategies hint to reference `quant-trading --list-strategies` (with script fallback). No code or tests changed.
- Diff: 1 file changed, `README.md` (+34/-28 in the edited block; net documentation-only).

## What was actually verified (evidence)

- `python -m pytest tests/test_packaging.py tests/test_readme_cli.py -q` -> **10 passed** (smoke, unchanged from handoff).
- `python -m pytest tests/test_readme.py tests/test_readme_cli.py -q` -> **20 passed** after README edit (README flag/default guards and CLI doc guards remain green).
- `python -m pytest --version` -> `pytest 9.2.0`. `black 26.10.1`, `ruff 0.17.5`, `mypy 2.4.1` installed (handoff previously stated format/lint/type tools unavailable).
- `python -m black --check .` -> **160 files would be left unchanged**.
- `python -m ruff check .` -> **All checks passed**.
- `python -m mypy .` -> **Success: no issues found in 160 source files**.
- Baseline from prior handoff (not re-run): 4035 passed / 142 deselected, TOTAL 99%, remaining misses provably unreachable. Full suite not rerun (expensive; no behavioral changes).

## What remains unresolved / not verified

- Full pytest suite not rerun this session (only targeted README/packaging/CLI tests above).
- README still contains many later `python examples/cli.py ...` examples beyond the Basic Usage section; only the opening/basic block and the list-strategies hint were aligned to the console script. Converting the rest is optional/docs-only and should be done carefully to keep README↔CLI/test guards satisfied.

## Approaches that failed

- None.

## One precise next task

Optionally align remaining README CLI examples (Data Providers, Utility Commands, Optimization, etc.) to prefer `quant-trading ...` with `python examples/cli.py ...` noted as dev alternative, in a single bounded docs pass. After each edit batch run `python -m pytest tests/test_readme.py tests/test_readme_cli.py -q` to ensure README↔parser/doc guards stay green; no code/test changes expected.

(End of file)
