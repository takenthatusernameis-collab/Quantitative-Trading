"""End-to-end tests that every example script's documented invocation runs offline.

Each ``examples/run_*.py`` script is documented in the README's "Example Scripts"
section as ``python examples/run_<name>.py`` with no arguments. The scripts use
deterministic synthetic data (seed=42), need no network access, and produce the
same output on every run, so they are safe, fast, and deterministic.

:mod:`tests.test_examples_smoke.py` already import-checks and run-checks every
example script, but its run check is marked ``slow`` and therefore deselected by
the default ``pytest -q`` invocation (``-m "not slow"``). This module locks the
README-documented invocations to live behaviour in the default suite so a
regression in a user-facing example script is caught immediately.
"""

import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def _example_scripts() -> list[Path]:
    return sorted(EXAMPLES_DIR.glob("run_*.py"))


@pytest.mark.parametrize("script", _example_scripts(), ids=lambda p: p.name)
def test_example_script_runs_documented_invocation(script: Path) -> None:
    """The README-documented ``python examples/run_<name>.py`` exits 0 cleanly."""
    # ``run_backtest.py`` is the repo's networked yfinance example (not part of
    # the offline demo set, see tests/test_repository_integrity.py). It cannot
    # run without the yfinance package, so skip it here instead of red-flagging
    # environments that simply lack that declared runtime dependency.
    if script.name == "run_backtest.py":
        pytest.importorskip(
            "yfinance",
            reason="run_backtest.py requires yfinance (networked example, not offline demo set)",
        )
    completed = subprocess.run(
        [sys.executable, str(script)],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
        cwd=Path(__file__).resolve().parent.parent,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, (
        f"{script.name} exited with code {completed.returncode}\n"
        f"STDOUT:\n{completed.stdout}\n"
        f"STDERR:\n{completed.stderr}"
    )
    assert "Traceback" not in output, (
        f"{script.name} produced a traceback: `python examples/{script.name}`\n"
        f"output:\n{output}"
    )
