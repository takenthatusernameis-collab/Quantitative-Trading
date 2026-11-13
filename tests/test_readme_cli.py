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
from pathlib import Path

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

    Built by scanning every option string registered on the parser's actions,
    so flags that share a destination with another (for example ``--wf-rolling``,
    which sets the same ``wf_anchored`` attribute as ``--wf-anchored``) are all
    counted and reflect the flags a user can actually pass.
    """
    parser = cli._create_parser()
    flags: set[str] = set()
    for action in parser._actions:
        for option in action.option_strings:
            if option.startswith("--"):
                flags.add(option.lstrip("-"))
    return flags


def _parser_defaults() -> dict[str, object]:
    """Return the default value of every flag the parser accepts.

    Built the same way as :func:`_parser_cli_flags`, keyed by the flag without
    its leading dashes. Flags whose default is a sentinel (``None``) or a
    boolean flag (``store_true``/``store_false``) are included too, so the
    README's ``default X`` claims can be compared against the live parser.
    """
    parser = cli._create_parser()
    defaults: dict[str, object] = {}
    for action in parser._actions:
        for option in action.option_strings:
            if option.startswith("--"):
                defaults[option.lstrip("-")] = action.default
    return defaults


# A README default claim is a parenthesised ``default <value>`` annotation that
# immediately follows a backtick-quoted flag token, optionally separated by up
# to a few words. The value is captured as the token after the word "default".
# Examples this matches:
#   ``--n-jobs`` (default 4)
#   ``--n-iter`` (default 50)
#   ``--rsi-period`` (default: 14)
#   ``--bayesian-acq-func`` (acquisition function: `EI`, ...; default `EI`)
#
# The value must not be a prose continuation such as "to" (from "default to the
# value of the configuration file"), so the value token is required to be a
# backtick-quoted literal or a bare number/word that is not "to"/"the"/"a".
_DEFAULT_CLAIM = re.compile(
    r"`(?P<flag>--[a-z][a-z0-9-]*)`[^`]{0,60}?\(?\s*default\s+(?P<value>`[^`]+`|-?\d+(?:\.\d+)?|True|False|None|EI|PI|LCB|gp_hedge|auto|sampling|lbfgs|grid|random|bayesian|sharpe|sortino|return|calmar|drawdown|profit_factor|win_rate|json|csv|bootstrap|parametric)\)",
    re.IGNORECASE,
)

# Prose annotations that look like a default claim but describe the output's
# *shape* rather than pinning a value. They are excluded because they are not
# defaults to compare against the parser.
_PROSE_DEFAULTS = {"default", "defaults to a value derived from --interval"}


def _documented_defaults() -> dict[str, str]:
    """Return every ``default <value>`` claim the README makes about a flag.

    The direction is README -> parser, matching the one-way direction already
    used by :func:`_documented_cli_flags`: the README documents a curated
    subset of flags, so flags the parser accepts but the README does not
    document are not asserted.
    """
    section = _cli_section()
    claims: dict[str, str] = {}
    for match in _DEFAULT_CLAIM.finditer(section):
        flag = match.group("flag").lstrip("-")
        value = match.group("value").strip("`'\"")
        claims[flag] = value
    return claims


# A CLI help-string default claim is a parenthesised ``(default: <value>)``
# annotation inside an ``add_argument`` help string. It must match the parser's
# declared default. Prose values such as ``inferred from extension`` or
# ``nondeterministic`` describe behaviour rather than pin a literal and are
# skipped.
_HELP_DEFAULT_CLAIM = re.compile(r"\(default:\s*(?P<value>[^)\s]+)")

# Help-string default claims whose value is prose rather than a pinned literal.
# They are not comparable to a parser default, so they are excluded.
_CLI_HELP_PROSE = {"inferred", "nondeterministic"}


def _cli_help_default_claims() -> list[tuple[str, str]]:
    """Return ``(flag, claimed_default)`` for every literal default claimed in cli.py help strings.

    Scans the live parser's actions and extracts each help string's
    ``(default: X)`` annotation, keyed by flag. Only literal claims are
    returned; prose claims are skipped.
    """
    parser = cli._create_parser()
    claims: list[tuple[str, str]] = []
    for action in parser._actions:
        if not action.option_strings or not action.help:
            continue
        match = _HELP_DEFAULT_CLAIM.search(action.help)
        if not match:
            continue
        claimed = match.group("value").strip("`\"'").rstrip(".,")
        if claimed in _CLI_HELP_PROSE:
            continue
        for option in action.option_strings:
            if option.startswith("--"):
                claims.append((option.lstrip("-"), claimed))
    return claims


def _coerce_default(actual: object, claimed: str) -> bool:
    """Return whether ``claimed`` matches the parser's ``actual`` default."""
    if isinstance(actual, bool):
        return claimed.lower() == str(actual).lower()
    if isinstance(actual, int) and not isinstance(actual, bool):
        try:
            return int(claimed) == actual
        except ValueError:
            return False
    if isinstance(actual, float):
        try:
            return abs(float(claimed) - actual) < 1e-9
        except ValueError:
            return False
    return str(actual) == claimed


class TestReadmeCliFlags:
    """Every CLI flag advertised in the README must be accepted by the parser."""

    def test_every_documented_flag_is_accepted_by_the_parser(self):
        """Each ``--flag`` in the README's CLI section must be a real CLI flag."""
        documented = _documented_cli_flags()
        actual = _parser_cli_flags()
        missing = sorted(documented - actual)
        assert missing == [], f"README advertises flags the CLI rejects: {missing}"

    def test_documented_defaults_match_the_parser(self):
        """Every ``default <value>`` claim the README makes must match the parser.

        The README annotates flags with their default value, for example
        ``--n-jobs`` (default 4). If the parser's default drifts without the
        README being updated, users following the docs get a different default
        than the one advertised. This guard catches that drift by comparing
        every documented default claim against the live ``parse_args()``
        namespace.

        The direction is README -> parser, matching the one-way direction of
        :func:`_documented_cli_flags`: only claims the README actually makes
        are checked, not every flag the parser accepts.
        """
        documented = _documented_defaults()
        actual = _parser_defaults()
        offenders: list[str] = []
        for flag, claimed in sorted(documented.items()):
            if flag not in actual:
                continue
            if not _coerce_default(actual[flag], claimed):
                offenders.append(
                    f"{flag}: README claims default {claimed!r}, "
                    f"parser default is {actual[flag]!r}"
                )
        assert not offenders, "README default claims out of sync with the parser:\n" + "\n".join(
            offenders
        )

    def test_cli_help_default_claims_match_the_parser(self):
        """Every ``(default: X)`` claim in a cli.py help string must match the parser default.

        Mirrors :meth:`test_documented_defaults_match_the_parser`, but checks
        the help strings declared next to the parser in ``examples/cli.py``
        instead of the README. This catches the same class of default drift
        (for example a parser default of ``None`` documented as ``365``) at the
        source rather than only in the rendered docs.
        """
        documented = _cli_help_default_claims()
        actual = _parser_defaults()
        offenders: list[str] = []
        for flag, claimed in sorted(documented):
            if flag not in actual:
                continue
            if not _coerce_default(actual[flag], claimed):
                offenders.append(
                    f"{flag}: help string claims default {claimed!r}, "
                    f"parser default is {actual[flag]!r}"
                )
        assert (
            not offenders
        ), "CLI help-string default claims out of sync with the parser:\n" + "\n".join(offenders)
