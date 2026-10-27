"""End-to-end tests that the CLI example commands documented in the README
actually run.

The README's "Command Line Interface" section is a set of copy-pasteable
invocations. :class:`TestReadmeCliFlags` guards that every individual flag
advertised there exists on the parser; this module guards that the documented
*invocations* themselves execute end-to-end (exit code 0) or, for the
documented error-reporting examples, exit with code 1 and a one-line message
instead of a traceback.

Only commands that need no network are executed: offline runs (``--offline``
or ``--provider synthetic``) and the info commands (``--list-strategies``,
``--list-providers``, ``--init-config``, ``--validate-config``). Commands that
default to Yahoo Finance or Alpha Vantage are skipped because they require
network access.

Commands are extracted from the README's ``## Command Line Interface`` bash
code blocks, so a newly documented command is covered automatically and a
documented command that breaks at runtime is caught immediately.
"""

import contextlib
import io
import os
import re
import sys
from pathlib import Path

import pytest

from examples.cli import main

README_PATH = Path(__file__).resolve().parent.parent / "README.md"

_CODE_BLOCK = re.compile(r"```bash\n(?P<body>.*?)```", re.DOTALL)
_COMMAND = re.compile(r"^python\s+examples/cli\.py(?P<args>.*)$")


def _cli_section() -> str:
    """Return the body of the README "Command Line Interface" section."""
    text = README_PATH.read_text(encoding="utf-8")
    start = text.index("## Command Line Interface")
    remainder = text[start + 1 :]
    end = remainder.find("\n## ")
    return remainder if end == -1 else remainder[:end]


def _readme_commands() -> list[list[str]]:
    """Extract the ``examples/cli.py`` argument lists documented in the README.

    Backslash-continued command lines are joined into a single command.
    Comment lines (``# ...``) are ignored.
    """
    commands: list[list[str]] = []
    section = _cli_section()
    for block in _CODE_BLOCK.finditer(section):
        logical_lines: list[str] = []
        for raw_line in block.group("body").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.endswith("\\"):
                logical_lines.append(line[:-1].rstrip())
                continue
            if logical_lines:
                logical_lines[-1] += " " + line
                line = logical_lines.pop()
            else:
                line = raw_line.strip()
            match = _COMMAND.match(line)
            if match:
                commands.append(match.group("args").strip().split())
    return commands


def _expects_failure(args: list[str]) -> bool:
    """Whether a documented command is one of the error-reporting examples."""
    text = " ".join(args)
    return (
        "nosuchstrategy" in text
        or "--mc-simulations 0" in text
        or "--ma-fast-range 5,20,0" in text
        or "--config missing.yaml" in text
    )


def _is_offline_command(args: list[str]) -> bool:
    """Whether a command runs without network access."""
    text = " ".join(args)
    return (
        "--offline" in text
        or "--provider synthetic" in text
        or text in {"--list-strategies", "--list-providers"}
        or text.startswith(("--init-config ", "--validate-config "))
    )


def _run_cli(args: list[str], tmp_path: Path) -> tuple[int, str]:
    """Run ``main()`` with ``args`` inside ``tmp_path`` and return (rc, output).

    The working directory is temporarily moved to ``tmp_path`` so commands that
    write files (``--init-config``, ``--output-strategy-config``) do not
    pollute the repository, and a valid ``config.yaml`` is created ahead of a
    ``--validate-config`` command.
    """
    for index, arg in enumerate(args):
        if arg in {"--validate-config", "--strategy-config"} and index + 1 < len(args):
            target_path = tmp_path / args[index + 1]
            if not target_path.exists():
                if arg == "--validate-config":
                    target_path.write_text(
                        "data:\n  provider: synthetic\n  offline: true\n",
                        encoding="utf-8",
                    )
                else:
                    target_path.write_text(
                        "type: rsi\nname: MyRSI\nparameters:\n  period: 21\n  oversold: 25\n  overbought: 75\n",
                        encoding="utf-8",
                    )

    old_cwd = Path.cwd()
    old_argv = sys.argv
    output = io.StringIO()
    try:
        os.chdir(tmp_path)
        sys.argv = ["cli.py"] + args
        with contextlib.redirect_stdout(output):
            try:
                rc = main()
            except SystemExit as exc:
                rc = exc.code if isinstance(exc.code, int) else 1
    finally:
        os.chdir(old_cwd)
        sys.argv = old_argv
    return rc, output.getvalue()


_COMMANDS = _readme_commands()


@pytest.mark.parametrize("args", _COMMANDS, ids=lambda a: " ".join(a)[:70])
class TestReadmeCliCommands:
    """Every offline-capable README CLI command must run as documented."""

    def test_network_commands_are_skipped(self, args):
        """Commands that need Yahoo Finance / Alpha Vantage are not executed here."""
        if not _is_offline_command(args) and not _expects_failure(args):
            pytest.skip("requires network access (yfinance/alphavantage)")

    def test_command_runs_with_documented_exit_code(self, args, tmp_path):
        """Offline/error README commands exit with the documented code, no traceback."""
        if _expects_failure(args):
            expected_rc = 1
        elif _is_offline_command(args):
            expected_rc = 0
        else:
            pytest.skip("requires network access (yfinance/alphavantage)")

        rc, output = _run_cli(args, tmp_path)
        assert rc == expected_rc, (
            f"expected exit code {expected_rc} for `python examples/cli.py "
            + " ".join(args)
            + f"`, got {rc}\noutput:\n{output}"
        )
        if expected_rc == 1:
            command = "python examples/cli.py " + " ".join(args)
            assert "Traceback" not in output, (
                "error-reporting command produced a traceback: `"
                + command
                + "`\noutput:\n"
                + output
            )
            assert "Error:" in output or "error" in output.lower(), (
                "error-reporting command did not report an error: `"
                + command
                + "`\noutput:\n"
                + output
            )
