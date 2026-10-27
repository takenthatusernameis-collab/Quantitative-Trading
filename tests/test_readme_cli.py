"""Tests that keep the README's CLI flag documentation in sync with the parser.

The README's "Command Line Interface" section is the user-facing contract for
which flags ``examples/cli.py`` accepts. Flags are advertised there both as
backtick-quoted prose (``--strategy``) and as plain tokens inside bash code
blocks (``python examples/cli.py --strategy rsi``). If a flag is advertised in
the README but removed from the parser, users following the docs hit an
argparse error. The guard below parses the README's CLI section and compares
every documented flag to the live ``parse_args()`` namespace.

The direction is one-way (README -> parser) because the README intentionally
documents a curated subset of flags, not every flag the parser accepts. This
mirrors the direction already used by ``tests/test_readme.py``'s
``TestReadmeExampleScripts.test_no_undocumented_example_scripts_are_advertised``
and the Alpha Vantage method guards, where the docs must not reference things
that do not exist.
"""

import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from examples import cli

README_PATH = Path(__file__).resolve().parent.parent / "README.md"

# Matches a backtick-quoted CLI flag such as ``--strategy`` or ``--ma-fast-range``.
_CLI_FLAG = re.compile(r"`(?P<flag>--[a-z][a-z0-9-]*)`")
# Matches a plain CLI flag inside a bash code block, e.g. ``--strategy rsi``.
# The negative lookbehind avoids matching a flag glued to a preceding word.
_FLAG_TOKEN = re.compile(r"(?<!\w)(?P<flag>--[a-z][a-z0-9-]*)")
_CODE_BLOCK = re.compile(r"```bash\n(?P<body>.*?)```", re.DOTALL)


def _cli_section() -> str:
    """Return the body of the README "Command Line Interface" section."""
    text = README_PATH.read_text(encoding="utf-8")
    start = text.index("## Command Line Interface")
    remainder = text[start + 1 :]
    end = remainder.find("\n## ")
    return remainder if end == -1 else remainder[:end]


def _documented_cli_flags() -> set[str]:
    """Return the set of CLI flags advertised in the README.

    Every backtick-quoted ``--flag`` token in the "Command Line Interface"
    section is collected, as is every plain ``--flag`` token inside a bash
    code block (the shell invocations users copy-paste). The same flag may
    appear several times; duplicates are collapsed into a set.
    """
    documented: set[str] = set()
    section = _cli_section()
    for match in _CLI_FLAG.finditer(section):
        documented.add(match.group("flag").lstrip("-"))
    for block in _CODE_BLOCK.finditer(section):
        for match in _FLAG_TOKEN.finditer(block.group("body")):
            documented.add(match.group("flag").lstrip("-"))
    return documented


def _parser_cli_flags() -> set[str]:
    """Return the set of flags the live ``parse_args()`` parser accepts.

    Built from the namespace produced by ``parse_args()`` rather than by
    scanning ``add_argument`` calls, so a flag that shares its destination
    with another (for example ``--wf-rolling``, which sets the same
    ``wf_anchored`` attribute as ``--wf-anchored``) is counted exactly once
    and reflects the flags a user can actually pass.
    """
    with patch("sys.argv", ["cli.py"]):
        args = cli.parse_args()
    return {name.replace("_", "-") for name in vars(args)}


class TestReadmeCliFlags:
    """Every CLI flag advertised in the README must be accepted by the parser."""

    def test_every_documented_flag_is_accepted_by_the_parser(self):
        """Each ``--flag`` in the README's CLI section must be a real CLI flag."""
        documented = _documented_cli_flags()
        actual = _parser_cli_flags()
        missing = sorted(documented - actual)
        assert missing == [], f"README advertises flags the CLI rejects: {missing}"


EXAMPLES_CLI = README_PATH.parent / "examples" / "cli.py"

# Commands that read a user-created input file are not self-contained: the
# README shows the file's content but expects the reader to create it first.
_INPUT_FILE_FLAGS = ("--strategy-config", "--config")


def _documented_offline_cli_commands() -> list[str]:
    """Return the standalone offline ``python examples/cli.py`` commands documented in the README CLI section.

    Only success-case, self-contained invocations are collected:

    * error-reporting examples (introduced by a ``$ `` shell prompt) are skipped;
    * commands that read a user-created input file (``--strategy-config``,
      ``--config``) are skipped because the README expects the reader to create
      that file first;
    * leading comment lines inside a block are skipped and backslash
      line-continuations are joined, so a multi-line command runs as a single
      invocation.

    Commands without ``--offline`` are skipped because they require network
    access.
    """
    commands: list[str] = []
    section = _cli_section()
    for block in _CODE_BLOCK.finditer(section):
        body = block.group("body")
        command: str | None = None
        for line in body.splitlines():
            stripped = line.strip()
            if command is None:
                # Skip leading blanks and comments until the invocation starts.
                if not stripped or stripped.startswith("#"):
                    continue
                if stripped.startswith("$ "):
                    break  # error-reporting example: documented to fail
                if not stripped.startswith("python examples/cli.py"):
                    break  # not a cli.py invocation (e.g. a run_*.py example)
                command = stripped
                continue
            # A line continuing a command the previous line started (backslash).
            if command.endswith("\\"):
                command = command[:-1].rstrip() + " " + stripped
                continue
            break  # first non-continuation line after the command: example output
        if command is None:
            continue
        command = command.rstrip("\\").rstrip()
        if "--offline" not in command:
            continue
        if any(flag in command for flag in _INPUT_FILE_FLAGS):
            continue  # reads a user-created file, not self-contained
        commands.append(command)
    return sorted(set(commands))


class TestReadmeCliExamples:
    """The offline CLI examples documented in the README must run successfully.

    The flag guard in :class:`TestReadmeCliFlags` proves every documented flag
    is accepted by the parser. This guard goes one step further and proves the
    documented invocations themselves run end to end without a traceback, so a
    future change that breaks a documented command is caught even when every
    individual flag is still accepted.
    """

    @pytest.mark.parametrize(
        "command",
        _documented_offline_cli_commands(),
        ids=lambda command: command[:70],
    )
    def test_documented_offline_cli_command_runs(self, command: str, tmp_path: Path) -> None:
        """Each documented offline CLI invocation exits 0 without a traceback."""
        args = command[len("python examples/cli.py ") :].strip()
        completed = subprocess.run(
            [sys.executable, str(EXAMPLES_CLI), *args.split()],
            check=False,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=300,
        )
        output = completed.stdout + completed.stderr
        assert (
            completed.returncode == 0
        ), f"command {command!r} exited with code {completed.returncode}\nOUTPUT:\n{output}"
        assert (
            "Traceback" not in output
        ), f"command {command!r} produced a traceback\nOUTPUT:\n{output}"
