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
* **User error check** — the command line interface is run with inputs a user
  can get wrong (an unknown strategy, a missing file, a malformed config) and
  has to report them as a one-line message with the exit code 1, never as a
  traceback.

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

# A strategy config whose *content* is wrong. The file exists, so the path is
# no longer the problem and the content has to be.
CLI_STRATEGY_CONFIG_CONTENTS: list[tuple[str, str, str]] = [
    ("not-a-mapping.yaml", "- a\n- b\n", "expected a mapping"),
    (
        "parameters-not-a-mapping.yaml",
        "type: rsi\nparameters: 5\n",
        "'parameters' must be a mapping",
    ),
    (
        "unknown-parameter.yaml",
        "type: rsi\nparameters:\n  nosuchparam: 5\n",
        "invalid strategy config",
    ),
    (
        "bad-parameter-value.yaml",
        "type: rsi\nparameters:\n  period: abc\n",
        "invalid strategy config",
    ),
]

# A config file whose *values* have the wrong type. The file exists and is
# valid YAML, so the error is only visible when the values reach the library.
CLI_CONFIG_CONTENTS: list[tuple[str, str, str]] = [
    (
        "wrong-typed-capital.yaml",
        "backtest:\n  initial_capital: abc\n",
        "invalid config field",
    ),
    (
        "bool-for-int.yaml",
        "backtest:\n  periods_per_year: true\n",
        "invalid config field",
    ),
    (
        "int-for-bool.yaml",
        "data:\n  offline: 1\n",
        "invalid config field",
    ),
    (
        "float-for-int.yaml",
        "portfolio:\n  max_positions: 20.5\n",
        "invalid config field",
    ),
    (
        "none-for-str.yaml",
        "data:\n  provider: null\n",
        "invalid config field",
    ),
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


def _run_cli(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    """Run ``examples/cli.py`` with ``arguments`` in a subprocess."""
    return subprocess.run(
        [sys.executable, str(EXAMPLES_DIR / "cli.py"), *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
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
    completed = _run_cli(
        [
            flag,
            value.format(tmp=tmp_path),
            "--offline",
            "--symbols",
            "AAPL",
            "--days",
            "30",
        ]
    )
    output = completed.stdout + completed.stderr
    assert (
        completed.returncode == 1
    ), f"expected the exit code 1\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
    assert message in output, f"expected {message!r} in the output\n{output}"
    assert "Traceback" not in output, f"the output must not contain a traceback\n{output}"


def test_cli_reports_an_invalid_optimization_range_without_a_traceback() -> None:
    """A range with a step of zero is a message, not a hang.

    A step of zero makes the grid search loop forever, so the argument has
    to be rejected before the run starts.
    """
    completed = _run_cli(
        [
            "--optimize",
            "--ma-fast-range",
            "5,20,0",
            "--offline",
            "--symbols",
            "AAPL",
            "--days",
            "30",
        ]
    )
    output = completed.stdout + completed.stderr
    assert (
        completed.returncode == 1
    ), f"expected the exit code 1\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
    assert "step must be greater than 0" in output, output
    assert "Traceback" not in output, f"the output must not contain a traceback\n{output}"


def test_cli_reports_an_inverted_optimization_range_without_a_traceback() -> None:
    """A range whose minimum is above its maximum is a message, not an empty table.

    A minimum greater than the maximum yields no grid combinations, so the
    argument has to be rejected before the run starts and name the offending
    flag.
    """
    completed = _run_cli(
        [
            "--optimize",
            "--ma-fast-range",
            "20,5,5",
            "--offline",
            "--symbols",
            "AAPL",
            "--days",
            "30",
        ]
    )
    output = completed.stdout + completed.stderr
    assert (
        completed.returncode == 1
    ), f"expected the exit code 1\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
    assert "invalid --ma-fast-range" in output, output
    assert "greater than the maximum" in output, output
    assert "Traceback" not in output, f"the output must not contain a traceback\n{output}"


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    CLI_CONFIG_CONTENTS,
    ids=[
        "wrong-typed-capital",
        "bool-for-int",
        "int-for-bool",
        "float-for-int",
        "none-for-str",
    ],
)
def test_cli_reports_a_wrongly_typed_config_without_a_traceback(
    filename: str, content: str, message: str, tmp_path: Path
) -> None:
    """A config file with wrongly-typed values is a message, not a traceback.

    The file exists and is valid YAML, so the error is only visible when the
    values are handed to the library through ``Config.from_yaml``.
    """
    config = tmp_path / filename
    config.write_text(content)
    completed = _run_cli(
        [
            "--config",
            str(config),
            "--offline",
            "--symbols",
            "AAPL",
            "--days",
            "30",
        ]
    )
    output = completed.stdout + completed.stderr
    assert (
        completed.returncode == 1
    ), f"expected the exit code 1\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
    assert message in output, f"expected {message!r} in the output\n{output}"
    assert "Traceback" not in output, f"the output must not contain a traceback\n{output}"


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    CLI_STRATEGY_CONFIG_CONTENTS,
    ids=[
        "not-a-mapping",
        "parameters-not-a-mapping",
        "unknown-parameter",
        "bad-parameter-value",
    ],
)
def test_cli_reports_a_malformed_strategy_config_without_a_traceback(
    filename: str, content: str, message: str, tmp_path: Path
) -> None:
    """A strategy config with the wrong content is a message, not a traceback.

    The file exists and is valid YAML, so the error is only visible when the
    content is handed to the strategy factory.
    """
    config = tmp_path / filename
    config.write_text(content)
    completed = _run_cli(
        [
            "--strategy-config",
            str(config),
            "--offline",
            "--symbols",
            "AAPL",
            "--days",
            "30",
        ]
    )
    output = completed.stdout + completed.stderr
    assert (
        completed.returncode == 1
    ), f"expected the exit code 1\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
    assert message in output, f"expected {message!r} in the output\n{output}"
    assert "Traceback" not in output, f"the output must not contain a traceback\n{output}"


def test_cli_reports_an_invalid_mc_simulations_count_without_a_traceback() -> None:
    """A ``--mc-simulations`` below 1 is a message, not a confusing failure.

    A simulation count of zero is a CLI usage error, not a library defect, so
    the check belongs in the CLI. The Monte Carlo module is generic and treats
    a count of zero as an empty result; the CLI has to reject it before the run
    starts and name the offending flag.
    """
    completed = _run_cli(
        [
            "--monte-carlo",
            "--mc-simulations",
            "0",
            "--offline",
            "--symbols",
            "AAPL",
            "--days",
            "30",
        ]
    )
    output = completed.stdout + completed.stderr
    assert (
        completed.returncode == 1
    ), f"expected the exit code 1\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
    assert "invalid --mc-simulations" in output, output
    assert "the value must be at least 1" in output, output
    assert "Traceback" not in output, f"the output must not contain a traceback\n{output}"
