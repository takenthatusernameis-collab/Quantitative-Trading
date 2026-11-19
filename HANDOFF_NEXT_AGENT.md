## Status

Verified green on 2026-11-19. Repository at 100% statement/branch coverage with a clean mypy/black/ruff gate and a passing suite (4142 passed, 146 deselected).

## What changed

Executed the previous handoff: smoke-tested the `quant-trading` console-script entry point (previously only ever exercised in-process via `examples.cli.main`), then encoded the invariant that made that smoke test meaningful.

Files touched this session:

- `tests/test_packaging.py` — added `TestConsoleScript`, which parses `[project.scripts]` from `pyproject.toml` and (a) asserts the `quant-trading` entry exists, (b) resolves `<module>:<attr>` via `importlib` and asserts it is callable. Guards against a renamed `main` or a typo in the entry-point target, which would otherwise only surface after `pip install`.
- `HANDOFF_NEXT_AGENT.md` — this file.

No production code changed; no coverage delta (source tree untouched).

## What was actually verified

Console script (installed editable with `python -m pip install -e . --no-deps --no-build-isolation`):

- `quant-trading --version` -> `quant-trading 0.1.0`, exit 0.
- `quant-trading --list-strategies` -> full 50-strategy list incl. `kst` (aliases `know_sure_thing`), exit 0.
- `quant-trading --offline --list-providers` -> `yfinance`/`alphavantage`/`synthetic`, exit 0.
- `quant-trading --offline --strategy kst --symbols AAPL --days 60` -> runs end to end on synthetic data, exit 0 (0 trades over 60 days is expected: KST needs long ROC history).
- `quant-trading --help` -> usage text, exit 0.
- `quant-trading --offline --days 0 --symbols AAPL` -> `Error: invalid --days: the value must be at least 1 (got 0)`, exit 1, no traceback.

Gate:

- `MPLBACKEND=Agg python -m pytest -q -p no:cacheprovider` -> **4142 passed, 146 deselected, 0 failed** (5m33s).
- `python -m black --check tests/test_packaging.py`, `python -m ruff check tests/test_packaging.py`, `python -m mypy tests/test_packaging.py` -> clean.

## Failed approaches / gotchas (do not repeat)

- `python -m pip install -e ".[dev]"` is not usable offline in this sandbox; `--no-deps --no-build-isolation` works and is sufficient to register the console script (deps are already present).
- The console script installs to `/home/runner/work/_temp/kilo-home/.local/bin`, which is not on `PATH`; prefix `PATH` when invoking it.
- The CI workflow (`.github/workflows/main.yml`) does **not** `pip install` the project, so any test asserting an *installed* `quant-trading` binary would fail in CI. The new guard is deliberately structural (pyproject + importlib), not subprocess-based.

## Remaining work / unresolved

None for the console-script smoke test.

## One precise next task

Verify the built **wheel** (not the editable install) ships everything needed to run the CLI from outside the source tree:

```bash
rm -rf /tmp/qw /tmp/qvenv
python -m pip wheel . --no-deps --no-build-isolation -w /tmp/qw
python -m venv --system-site-packages /tmp/qvenv
/tmp/qvenv/bin/python -m pip install --no-deps /tmp/qw/quant_trading-*.whl
cd /tmp && /tmp/qvenv/bin/quant-trading --version
cd /tmp && /tmp/qvenv/bin/quant-trading --offline --strategy kst --symbols AAPL --days 60 | tail -5
/tmp/qvenv/bin/python -c "import quant_trading, examples.cli; print('import ok')"
```

Confirm: the wheel contains `examples/` (the entry point depends on it), `quant_trading/py.typed` is present in the wheel, and all three commands exit 0 with no traceback when run from `/tmp`. If the wheel is missing `examples*` or `py.typed`, fix `[tool.setuptools.packages.find]` / `package-data` in `pyproject.toml` — do not change the entry point.
