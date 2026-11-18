"""Inverse of the core-only invariant for README-documented optional extras.

When the optional ``reporting`` (matplotlib) and ``bayesian`` (scikit-optimize)
extras are installed, representative README CLI commands that require them must
run successfully (exit 0). These commands are skip-marked in the README
end-to-end harness when the extras are absent; this test locks the opposite
direction so both sides of the invariant are covered:

- ``tests/test_core_only_imports.py``: core import/backtest works and chart
  helpers fail cleanly when extras are *absent*.
- this file: chart/bayesian README commands run when extras are *present*.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "examples" / "cli.py"


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    # Ensure the working tree is importable when running the CLI script.
    env["PYTHONPATH"] = str(ROOT) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


@pytest.mark.skipif(
    not _module_available("matplotlib"),
    reason="matplotlib not installed; install the optional 'reporting' extra",
)
def test_readme_charted_report_runs_when_matplotlib_installed(tmp_path: Path) -> None:
    """A representative README charted-report command succeeds with matplotlib."""
    report = tmp_path / "report.html"
    completed = _run_cli(
        [
            "--offline",
            "--symbols",
            "AAPL",
            "--days",
            "60",
            "--report",
            str(report),
        ],
        cwd=tmp_path,
    )
    output = completed.stdout + completed.stderr
    assert (
        completed.returncode == 0
    ), f"charted report command failed (exit {completed.returncode})\n{output}"
    assert "Traceback" not in output, f"traceback in charted report run\n{output}"
    assert report.exists(), "charted report file was not written"
    assert report.stat().st_size > 0, "charted report file is empty"


@pytest.mark.skipif(
    not _module_available("skopt"),
    reason="scikit-optimize not installed; install the optional 'bayesian' extra",
)
def test_readme_bayesian_optimize_runs_when_skopt_installed(tmp_path: Path) -> None:
    """A representative README bayesian-optimization command succeeds with skopt."""
    completed = _run_cli(
        [
            "--offline",
            "--optimize",
            "--strategy",
            "ma",
            "--optimizer",
            "bayesian",
            "--ma-fast-range",
            "5,10,5",
            "--ma-slow-range",
            "20,25,5",
            "--symbols",
            "AAPL",
            "--days",
            "60",
            "--n-jobs",
            "1",
        ],
        cwd=tmp_path,
    )
    output = completed.stdout + completed.stderr
    assert (
        completed.returncode == 0
    ), f"bayesian optimize command failed (exit {completed.returncode})\n{output}"
    assert "Traceback" not in output, f"traceback in bayesian optimize run\n{output}"
