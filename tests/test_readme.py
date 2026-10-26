"""Tests that keep the README in sync with the code it documents."""

import re
from pathlib import Path

from quant_trading.strategies import get_registry, list_strategies

README_PATH = Path(__file__).resolve().parent.parent / "README.md"
EXAMPLES_DIR = README_PATH.parent / "examples"

# Matches a registry bullet such as:
#   - `ma` (aliases: `moving_average`, `ma_crossover`) → `MovingAverageCrossover`
REGISTRY_ENTRY = re.compile(r"^-\s+`(?P<key>[^`]+)`.*→\s+`(?P<cls>[^`]+)`\s*$")

# Matches the parenthesised alias list of a registry bullet:
#   - `ma` (aliases: `moving_average`, `ma_crossover`) → ...
ALIAS_LIST = re.compile(r"\(alias(es)?:\s*(?P<aliases>[^)]*)\)")


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


def _documented_aliases() -> dict[str, set[str]]:
    """Map each documented primary key to its documented alias set.

    Strategies with no documented alias map to an empty set.
    """
    aliases: dict[str, set[str]] = {}
    for line in _registry_section().splitlines():
        match = REGISTRY_ENTRY.match(line.strip())
        if not match:
            continue
        key = match.group("key")
        alias_match = ALIAS_LIST.search(line)
        if alias_match:
            aliases[key] = {
                a.strip().strip("`").strip()
                for a in alias_match.group("aliases").split(",")
                if a.strip()
            }
        else:
            aliases.setdefault(key, set())
    return aliases


def _registry_aliases() -> dict[str, set[str]]:
    """Map each primary strategy key to its live registry aliases.

    Built only from the public API (``keys()`` / ``primary_keys()`` / ``get()``)
    so the test does not reach into the registry's private state.
    """
    registry = get_registry()
    primaries = set(registry.primary_keys())
    alias_map: dict[str, set[str]] = {primary: set() for primary in primaries}
    for key in registry.keys():  # noqa: SIM118 - registry is StrategyRegistry, not a dict
        if key in primaries:
            continue
        target = registry.get(key)
        for primary in primaries:
            if registry.get(primary) is target:
                alias_map[primary].add(key)
                break
    return alias_map


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

    def test_documented_aliases_match_the_registry(self):
        """The aliases documented in the README registry table must match the live registry.

        The README lists the aliases of every strategy (e.g. ``ma`` documents
        ``moving_average`` and ``ma_crossover``). If a strategy's aliases are
        changed in code but the README table is not updated, users are pointed
        at keys that do not resolve, silently. This test locks the documented
        aliases to the registry so such drift is caught immediately.
        """
        documented = _documented_aliases()
        actual = _registry_aliases()
        offenders: list[str] = []
        for key, documented_aliases in documented.items():
            if key not in actual:
                offenders.append(f"{key}: documented in README but not a registered primary key")
                continue
            actual_aliases = actual[key]
            missing = sorted(actual_aliases - documented_aliases)
            extra = sorted(documented_aliases - actual_aliases)
            if missing:
                offenders.append(f"{key}: registry aliases missing from README: {missing}")
            if extra:
                offenders.append(f"{key}: README aliases not present in the registry: {extra}")
        assert (
            not offenders
        ), "README strategy aliases out of sync with the registry:\n" + "\n".join(offenders)


# Names imported from ``quant_trading.data`` in the README's DataManager example.
# The snippet must stay in sync with ``quant_trading.data.__all__``; a future
# export change must not silently desync the docs.
def _documented_data_import_names() -> set[str]:
    """Return the set of names imported from quant_trading.data in the README."""
    text = README_PATH.read_text(encoding="utf-8")
    start = text.index("from quant_trading.data import (")
    end = text.index(")", start)
    snippet = text[start:end]
    names = set(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*,?\s*$", snippet, re.M))
    return names


class TestReadmeDataImports:
    """The README's quant_trading.data import snippet must match quant_trading.data.__all__."""

    def test_data_imports_match_data_all(self):
        from quant_trading import data

        documented = _documented_data_import_names()
        exported = set(data.__all__)
        missing = sorted(exported - documented)
        extra = sorted(documented - exported)
        offenders: list[str] = []
        if missing:
            offenders.append(f"missing from README: {missing}")
        if extra:
            offenders.append(f"not in quant_trading.data.__all__: {extra}")
        assert not offenders, "README quant_trading.data imports out of sync:\n" + "\n".join(
            offenders
        )


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


# The README "Supported intervals" bullets that name a concrete set of
# intervals, each mapped to a ClassVar set on ``AlphaVantageProvider``. The
# README is the user-facing contract for which intervals the provider accepts;
# if a set is renamed or its members change without updating the README,
# users are silently pointed at keys the provider rejects. The guard below
# locks the two in sync.
#
# Two README bullets are deliberately excluded from the exact-match check:
#   * "Technical Indicators" ends with "etc." and is intentionally a partial
#     sample, so an exact match would be the wrong contract.
#   * "Real-time Batch" describes the fallback rule (any other interval),
#     not a concrete set of members.
_AV_INTERVAL_CATEGORIES: tuple[str, ...] = (
    "Daily",
    "Weekly",
    "Weekly Adjusted",
    "Monthly",
    "Monthly Adjusted",
    "Intraday",
    "Global Quote",
    "Market Status",
    "FX Daily",
    "FX Intraday",
    "Crypto Daily",
    "Crypto Weekly",
    "Crypto Monthly",
    "Crypto Intraday",
    "Sector Performance",
    "Commodities",
    "Precious Metals",
    "Economic Indicators",
)


def _av_supported_section() -> str:
    """Return the README "Supported intervals" block under Alpha Vantage."""
    text = README_PATH.read_text(encoding="utf-8")
    start = text.index("Supported intervals:")
    end = text.index("\n\n", start)
    return text[start:end]


def _documented_av_intervals() -> dict[str, set[str]]:
    """Map each README Alpha Vantage category to its documented interval set."""
    documented: dict[str, set[str]] = {}
    for line in _av_supported_section().splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        name = line[2:].split(":", 1)[0].strip()
        rest = line.split(":", 1)[1] if ":" in line else ""
        members = {
            m.strip().strip("`").strip()
            for m in re.findall(r"`([^`]+)`", rest)
            if "(" not in m  # prose calls like `get_gold_spot()` are not intervals
        }
        documented[name] = members
    return documented


def _provider_av_intervals() -> dict[str, set[str]]:
    """Map the same category names to the live ``AlphaVantageProvider`` sets."""
    from quant_trading.data.yfinance_provider import AlphaVantageProvider

    provider = AlphaVantageProvider
    return {
        "Daily": {"1d", "daily"},
        "Weekly": set(provider.WEEKLY_INTERVALS),
        "Weekly Adjusted": set(provider.WEEKLY_ADJUSTED_INTERVALS),
        "Monthly": set(provider.MONTHLY_INTERVALS),
        "Monthly Adjusted": set(provider.MONTHLY_ADJUSTED_INTERVALS),
        "Intraday": set(provider.INTRADAY_INTERVALS),
        "Global Quote": set(provider.QUOTE_INTERVALS),
        "Market Status": set(provider.MARKET_STATUS_INTERVALS),
        "FX Daily": set(provider.FX_DAILY_INTERVALS),
        "FX Intraday": set(provider.FX_INTRADAY_INTERVALS),
        "Crypto Daily": {"crypto_daily", "digital_daily"},
        "Crypto Weekly": {"crypto_weekly", "digital_weekly"},
        "Crypto Monthly": {"crypto_monthly", "digital_monthly"},
        "Crypto Intraday": {"crypto_intraday", "digital_intraday"},
        "Sector Performance": set(provider.SECTOR_INTERVALS),
        "Commodities": set(provider.COMMODITIES_INTERVALS),
        "Precious Metals": set(provider.GOLD_INTERVALS),
        "Economic Indicators": set(provider.ECONOMIC_INDICATORS),
    }


class TestReadmeAlphaVantageIntervals:
    """The README's Alpha Vantage "Supported intervals" must match the provider."""

    def test_documented_intervals_match_the_provider(self):
        """Every concrete README interval category must match the live provider."""
        documented = _documented_av_intervals()
        actual = _provider_av_intervals()
        offenders: list[str] = []
        for category in _AV_INTERVAL_CATEGORIES:
            readme_set = documented.get(category)
            if readme_set is None:
                offenders.append(f"README has no '{category}' supported-intervals bullet")
                continue
            provider_set = actual[category]
            missing = sorted(provider_set - readme_set)
            extra = sorted(readme_set - provider_set)
            if missing:
                offenders.append(f"{category}: provider intervals missing from README: {missing}")
            if extra:
                offenders.append(
                    f"{category}: README intervals not accepted by the provider: {extra}"
                )
        assert (
            not offenders
        ), "README Alpha Vantage intervals out of sync with the provider:\n" + "\n".join(offenders)
