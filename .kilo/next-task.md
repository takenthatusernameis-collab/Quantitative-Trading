# Next Task

## Repository state (verified this session)

All checks clean:
- `python -m ruff check .` → All checks passed.
- `python -m black --check .` → 141 files unchanged.
- `python -m mypy quant_trading/` → Success: no issues found in 37 source files.
- `python -m pytest tests/test_cli.py -q` → 179 passed.

## Completed this session

Added fast unit tests in tests/test_cli.py for CLI user-error validations
that existed in parse_args() (examples/cli.py:970-1013) but were only covered
by slow subprocess smoke tests:

- --mc-confidence above 1 or equal to 0 → "invalid --mc-confidence"
- --wf-train-size at/above 1 or equal to 0 → "invalid --wf-train-size"

No production code changed. Working tree contains only the tests/test_cli.py
addition.

## One precise next task

Extend the fast CLI validation test coverage in tests/test_cli.py to the
remaining parse_args() validations that still lack fast unit tests:
--wf-step-size (<= 0), --initial-capital (<= 0), --commission (< 0), and
--slippage (< 0). Each test should use patch("sys.argv", [...]) +
pytest.raises(ValueError, match="invalid --<flag>"), mirroring the tests just
added and the existing test_mc_simulations_* style. Verify with
tests/test_cli.py plus ruff/black/mypy.
