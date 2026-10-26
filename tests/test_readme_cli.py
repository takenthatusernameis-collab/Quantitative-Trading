"""Tests that keep the README's CLI flag documentation in sync with the parser.

The README's "Command Line Interface" section is the user-facing contract for
which flags ``examples/cli.py`` accepts. If a flag is advertised in the README
but removed from the parser, users following the docs hit an argparse error.
The guard below catches that drift by parsing the README's CLI section and
comparing it to the live ``parse_args()`` namespace.

The direction is one-way (README -> parser) because the README intentionally
documents a curated subset of flags, not every flag the parser accepts. This
mirrors the direction already used by ``tests/test_readme.py``'s
``TestReadmeExampleScripts.test_no_undocumented_example_scripts_are_advertised``
and the Alpha Vantage method guards, where the docs must not reference things
that do not exist.
"""

import re
from pathlib import Path
from unittest.mock import patch

from examples import cli

README_PATH = Path(__file__).resolve().parent.parent / "README.md"

# Matches a backtick-quoted CLI flag such as ``--strategy`` or ``--ma-fast-range``.
_CLI_FLAG = re.compile(r"`(?P<flag>--[a-z][a-z0-9-]*)`")


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
    section is collected. The same flag may appear several times (for example
    in shell invocations such as ``--strategy rsi --symbols AAPL``); duplicates
    are collapsed into a set.
    """
    documented: set[str] = set()
    for match in _CLI_FLAG.finditer(_cli_section()):
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
