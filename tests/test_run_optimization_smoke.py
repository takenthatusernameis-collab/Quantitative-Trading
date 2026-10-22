"""Smoke test for examples/run_optimization.py."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_run_optimization_runs():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "examples" / "run_optimization.py")],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Example script completed." in result.stdout
