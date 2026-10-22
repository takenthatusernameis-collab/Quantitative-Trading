"""Smoke tests for the example scripts.

Every ``examples/*.py`` script is checked at two levels.

* **Import check** — the module-level code of the script is executed in a
  subprocess whose ``__name__`` is not ``"__main__"``. This proves that every
  import of the script resolves, which is what makes the script runnable from
  a plain checkout. The check is safe for the network-backed scripts because
  none of them touches the network at import time.
* **Execution check** — the scripts that can run without network access are
  executed end to end. They use deterministic synthetic data (seed=42), so
  this suite is safe, fast and deterministic and requires no network access.

Scripts that require network access (importing ``YFinanceProvider`` or
``AlphaVantageProvider``) are only import-checked, never executed.
"""

import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
NETWORK_PROVIDERS = ("YFinanceProvider", "AlphaVantageProvider")

# The CLI names the network providers only in the display names of the
# provider registry, so it still runs without network access.
OFFLINE_ARGUMENTS: dict[str, list[str]] = {
    "cli.py": ["--offline", "--symbols", "AAPL", "--days", "60"],
}

# User errors the CLI has to report as a one-line message instead of a
# traceback. The value of each case is a path that does not exist, except for
# the unknown strategy, which is a key that is not in the registry.
CLI_USER_ERRORS: list[tuple[str, str, str]] = [
    ("--strategy", "nosuchstrategy", "Unknown strategy"),
    ("--config", "{tmp}/missing/config.yaml", "could not read config file"),
    (
        "--strategy-config",
        "{tmp}/missing/strategy.yaml",
        "could not read strategy config",
    ),
    ("--output", "{tmp}/missing/output.json", "could not write output file"),
]


def _example_scripts() -> list[Path]:
    return sorted(EXAMPLES_DIR.glob("*.py"))


def _requires_network(script: Path) -> bool:
    if script.name in OFFLINE_ARGUMENTS:
        return False
    return any(provider in script.read_text() for provider in NETWORK_PROVIDERS)


def _offline_scripts() -> list[Path]:
    return [script for script in _example_scripts() if not _requires_network(script)]


def _import_check(script: Path) -> subprocess.CompletedProcess[str]:
    """Execute the module-level code of a script the way ``python <script>`` would.

    ``sys.path[0]`` is the directory of the script, exactly like a direct
    invocation, so a script that cannot import ``quant_trading`` from a
    plain checkout fails here.
    """
    code = (
        "import runpy, sys\n"
        f"sys.path[0] = {str(script.parent)!r}\n"
        f"runpy.run_path({str(script)!r}, run_name='__example_import_check__')\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )


@pytest.mark.parametrize("script", _example_scripts(), ids=lambda p: p.name)
def test_example_script_imports_cleanly(script: Path) -> None:
    """Every example script must resolve its imports from a plain checkout."""
    completed = _import_check(script)
    assert completed.returncode == 0, (
        f"{script.name} could not be imported\n"
        f"STDOUT:\n{completed.stdout}\n"
        f"STDERR:\n{completed.stderr}"
    )


@pytest.mark.parametrize("script", _offline_scripts(), ids=lambda p: p.name)
def test_example_script_runs_offline(script: Path) -> None:
    """The offline example scripts must run end to end."""
    completed = subprocess.run(
        [sys.executable, str(script), *OFFLINE_ARGUMENTS.get(script.name, [])],
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


@pytest.mark.parametrize(
    ("flag", "value", "message"),
    CLI_USER_ERRORS,
    ids=["unknown-strategy", "missing-config", "missing-strategy-config", "unwritable-output"],
)
def test_cli_reports_user_errors_without_a_traceback(
    flag: str, value: str, message: str, tmp_path: Path
) -> None:
    """A user error is a one-line message and a non-zero exit code.

    The library raises for these inputs on purpose; the command line
    interface has to turn them into a message the user can act on.
    """
    completed = subprocess.run(
        [
            sys.executable,
            str(EXAMPLES_DIR / "cli.py"),
            flag,
            value.format(tmp=tmp_path),
            "--offline",
            "--symbols",
            "AAPL",
            "--days",
            "30",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = completed.stdout + completed.stderr
    assert (
        completed.returncode == 1
    ), f"expected the exit code 1\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
    assert message in output, f"expected {message!r} in the output\n{output}"
    assert "Traceback" not in output, f"the output must not contain a traceback\n{output}"
