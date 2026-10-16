"""Smoke tests for the example scripts.

Executes every ``examples/run_*.py`` script as a subprocess and asserts it
exits with code 0. Scripts run offline against deterministic synthetic data
(seed=42), so this suite is safe, fast, and deterministic and requires no
network access.

Scripts that require network access (importing ``YFinanceProvider`` or
``AlphaVantageProvider``) are skipped.
"""

import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
NETWORK_PROVIDERS = ("YFinanceProvider", "AlphaVantageProvider")


def _example_scripts() -> list[Path]:
    return sorted(EXAMPLES_DIR.glob("run_*.py"))


def _requires_network(script: Path) -> bool:
    return any(provider in script.read_text() for provider in NETWORK_PROVIDERS)


@pytest.mark.parametrize("script", _example_scripts(), ids=lambda p: p.name)
def test_example_script_runs_offline(script: Path) -> None:
    if _requires_network(script):
        pytest.skip(f"{script.name} requires network access; skipping offline smoke test")
    completed = subprocess.run(
        [sys.executable, str(script)],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert completed.returncode == 0, (
        f"{script.name} exited with code {completed.returncode}\n"
        f"STDOUT:\n{completed.stdout}\n"
        f"STDERR:\n{completed.stderr}"
    )
