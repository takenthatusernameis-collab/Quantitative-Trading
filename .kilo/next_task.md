# Next Task: (HANDOFF)

## Status

COMPLETE — added `tests/test_examples_smoke.py`, a pytest smoke test that executes every `examples/run_*.py` script as a subprocess and asserts exit code 0.

## What this session did

- Added `tests/test_examples_smoke.py`: collects `examples/run_*.py` via `Path.glob`, runs each with `subprocess.run([sys.executable, str(script)], check=False, capture_output=True, text=True, timeout=300)`, and asserts `returncode == 0` with captured stdout/stderr on failure.
- Guard: any script importing `YFinanceProvider` or `AlphaVantageProvider` is skipped (`pytest.skip`) since it requires network access. Confirmed `examples/run_backtest.py` is the only network-dependent script; the other 15 use `create_synthetic_provider(seed=42)` (offline, deterministic).
- Did not modify any example scripts; only added the test file under `tests/`.

## What was verified

- `python -m pytest tests/test_examples_smoke.py -q` → 15 passed, 1 skipped (`run_backtest.py` skipped as network-dependent).
- `python -m ruff check .` → All checks passed.
- `python -m black --check .` → All files left unchanged.
- `python -m mypy quant_trading tests/test_examples_smoke.py` → Success, no issues.
- Baseline suite previously: 997 passed, ruff/black/mypy green, 100% coverage (4317 statements, 1368 branches). Adding the smoke test does not alter source coverage.

## What remains unresolved

- None for this task.

## Approaches already tried / failed

- None.

## Next precise task

Run the full test suite with coverage to confirm the project remains green after adding the smoke test:
  `python -m pytest -q` (expect ~1012 passed, 1 skipped) and
  `python -m pytest --cov=quant_trading --cov-report=term-missing` (expect 100% coverage, 0 missing).
If green, no further implementation is needed — the project is in a stable, fully-tested state and the session can close.

## Constraints / evidence

- Do not modify example scripts. Keep the smoke test offline-only.
- Only `tests/test_examples_smoke.py` was added; no source files changed.
