"""Tests that keep the README in sync with the code it documents."""

import re
from pathlib import Path

from quant_trading.strategies import list_strategies

README_PATH = Path(__file__).resolve().parent.parent / "README.md"
EXAMPLES_DIR = README_PATH.parent / "examples"

# Matches a registry bullet such as:
#   - `ma` (aliases: `moving_average`, `ma_crossover`) → `MovingAverageCrossover`
REGISTRY_ENTRY = re.compile(r"^-\s+`(?P<key>[^`]+)`.*→\s+`(?P<cls>[^`]+)`\s*$")


def _registry_section() -> str:
    """Return the body of the README "Strategy Registry" section."""
    text = README_PATH.read_text(encoding="utf-8")
    start = text.index("## Strategy Registry")
    remainder = text[start + 1 :]
    end = remainder.find("\n## ")
    return remainder if end == -1 else remainder[:end]


def _documented_entries() -> dict[str, str]:
    """Map the strategy key to the class name documented in the README."""
    entries: dict[str, str] = {}
    for line in _registry_section().splitlines():
        match = REGISTRY_ENTRY.match(line.strip())
        if match:
            entries[match.group("key")] = match.group("cls")
    return entries


class TestReadmeStrategyRegistry:
    """The README registry table must match the real strategy registry."""

    def test_every_registered_strategy_is_documented(self):
        """Every primary registry key appears in the README registry table."""
        documented = _documented_entries()
        registry = list_strategies()
        missing = [key for key in registry if key not in documented]
        assert missing == []

    def test_no_undocumented_registry_entries(self):
        """The README does not advertise keys that are not registered."""
        documented = _documented_entries()
        unknown = [key for key in documented if key not in list_strategies()]
        assert unknown == []

    def test_documented_class_names_match_the_registry(self):
        """Each documented key points at the class it is actually registered to."""
        documented = _documented_entries()
        registry = list_strategies()
        mismatched = [
            (key, documented[key], registry[key].__name__)
            for key in documented
            if key in registry and documented[key] != registry[key].__name__
        ]
        assert mismatched == []


def _documented_example_scripts() -> set[str]:
    """Return the set of example script basenames referenced in the README."""
    text = README_PATH.read_text(encoding="utf-8")
    documented: set[str] = set()
    for m in re.finditer(r"`(?P<path>examples/run_[a-z_]+\.py)`", text):
        documented.add(Path(m.group("path")).name)
    return documented


class TestReadmeExampleScripts:
    """Every example script must be referenced in the README's Example Scripts section."""

    def test_every_example_script_is_documented(self):
        """Each ``examples/run_*.py`` script must appear in the README."""
        documented = _documented_example_scripts()
        actual = {path.name for path in sorted(EXAMPLES_DIR.glob("run_*.py"))}
        missing = sorted(actual - documented)
        assert missing == [], f"example scripts missing from README: {missing}"

    def test_no_undocumented_example_scripts_are_advertised(self):
        """The README must not reference example scripts that do not exist."""
        documented = _documented_example_scripts()
        actual = {path.name for path in sorted(EXAMPLES_DIR.glob("run_*.py"))}
        unknown = sorted(documented - actual)
        assert unknown == [], f"README advertises missing example scripts: {unknown}"
