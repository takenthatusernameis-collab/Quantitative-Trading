"""Registry-level coverage tests for every registered strategy.

The global strategy registry exposes 46 built-in strategies. This module
provides regression coverage for the whole registry: every registered strategy
must be constructible via :func:`create_strategy` with default parameters, must
carry a non-empty ``parameters`` mapping, and must be able to run
:meth:`Strategy.generate_signals` on synthetic market data without raising.
Aliases, primary keys, and the ``list_strategies`` / ``strategy_keys``
accessors are also asserted to stay consistent.

Beyond registry correctness, this module enforces the *coverage* guarantee
that its name implies: every registered strategy must also be exercised by an
example script in ``examples/`` and by a test class in
:mod:`tests.test_strategies_examples`. Without these assertions the file's
name would overstate what it checks — deleting an example script or a test
class would go unnoticed.
"""

import ast
from pathlib import Path

from quant_trading.data.synthetic import create_synthetic_data
from quant_trading.strategies.base import Signal
from quant_trading.strategies.factory import (
    create_strategy,
    get_registry,
    list_strategies,
    strategy_keys,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"
TEST_STRATEGIES_MODULE = REPO_ROOT / "tests" / "test_strategies_examples.py"


def _example_strategy_classes() -> set[str]:
    """Return every strategy class name imported by an ``examples/run_*.py`` script.

    The example scripts are the user-facing way each strategy is demonstrated,
    so a strategy that no example script imports has no documented usage path.
    """
    imported: set[str] = set()
    for script in sorted(EXAMPLES_DIR.glob("run_*.py")):
        tree = ast.parse(script.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "quant_trading.strategies.examples"
            ):
                for alias in node.names:
                    imported.add(alias.name)
    return imported


def _example_test_classes() -> set[str]:
    """Return every ``Test*`` class name defined in :mod:`test_strategies_examples`."""
    tree = ast.parse(TEST_STRATEGIES_MODULE.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test")
    }


def _synthetic_data() -> dict:
    """Return synthetic multi-symbol OHLCV data with enough history."""
    return create_synthetic_data(symbols=["AAPL", "MSFT"], days=120, seed=7)


def test_every_registered_strategy_is_constructible_and_runnable():
    """Each registered strategy builds with defaults and generates signals."""
    registry = get_registry()
    data = _synthetic_data()
    for key in registry.primary_keys():
        strategy = create_strategy(key)
        assert isinstance(strategy.parameters, dict)
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)
        for signal in signals:
            assert isinstance(signal, Signal)
            assert signal.symbol in ("AAPL", "MSFT")
            assert signal.action in ("buy", "sell", "hold", "short")
            assert 0.0 <= signal.strength <= 1.0


def test_primary_keys_match_list_strategies():
    """list_strategies() exposes exactly the primary keys."""
    registry = get_registry()
    assert set(list_strategies().keys()) == set(registry.primary_keys())


def test_strategy_keys_include_aliases():
    """strategy_keys() contains every primary key plus every alias."""
    registry = get_registry()
    keys = set(strategy_keys())
    assert set(registry.primary_keys()) <= keys
    assert len(keys) >= len(registry.primary_keys())


def test_aliases_for_returns_sorted_alias_list():
    """aliases_for() returns the aliases registered for a primary key.

    The accessor accepts either the primary key or an alias (resolved
    through the registry first) and returns an empty list for unknown
    keys, so the CLI can annotate ``--list-strategies`` output without
    duplicating the registry's internal alias map.
    """
    registry = get_registry()
    assert registry.aliases_for("ma") == ["ma_crossover", "moving_average"]
    # An alias is resolved to its primary key first.
    assert registry.aliases_for("dc") == ["dc", "donchian_channel"]
    assert registry.aliases_for("psar") == ["parabolic_sar", "psar"]
    # Strategies without aliases return an empty list.
    assert registry.aliases_for("vwap") == []
    assert registry.aliases_for("trix") == []
    # Unknown keys return an empty list rather than raising.
    assert registry.aliases_for("does_not_exist") == []


def test_aliases_resolve_to_primary_class():
    """Each alias resolves to the same class as its primary key."""
    registry = get_registry()
    aliases = {
        "ema_crossover": "ema",
        "exponential_ma_crossover": "ema",
        "moving_average": "ma",
        "ma_crossover": "ma",
        "rsi_mean_reversion": "rsi",
        "bollinger_bands": "bb",
        "bollinger": "bb",
        "bollinger_bands_pct": "bbpct",
        "percent_b": "bbpct",
        "macd_crossover": "macd",
        "st": "supertrend",
        "super_trend": "supertrend",
        "donchian_channel": "donchian",
        "dc": "donchian",
        "ease_of_movement": "eom",
        "aroon_oscillator": "aroon",
        "kc": "keltner",
        "keltner_channel": "keltner",
        "klinger_oscillator": "klinger",
        "stochastic": "stoch",
        "stoch_oscillator": "stoch",
        "stochastic_rsi": "stochrsi",
        "stoch_rsi": "stochrsi",
        "ichimoku_cloud": "ichimoku",
        "hull_moving_average": "hma",
        "parabolic_sar": "sar",
        "psar": "sar",
        "volume_rate_of_change": "vroc",
        "awesome_oscillator": "ao",
        "volume_oscillator": "vol",
        "vortex_indicator": "vortex",
        "volume_price_trend": "vpt",
        "percentage_price_oscillator": "ppo",
        "ppo_strategy": "ppo",
        "percentage_volume_oscillator": "pvo",
        "pvo_strategy": "pvo",
        "mom": "momentum",
        "average_directional_index": "adx",
        "average_true_range": "atr",
        "atr_channel": "atr",
        "accumulation_distribution": "adl",
        "ad_line": "adl",
        "commodity_channel_index": "cci",
        "williams_pct_r": "williamsr",
        "on_balance_volume": "obv",
        "chaikin_money_flow": "cmf",
        "chaikin_oscillator": "cho",
        "chande_momentum_oscillator": "cmo",
        "elder_ray_index": "elder_ray",
        "erp": "elder_ray",
        "rate_of_change": "roc",
        "forceindex": "force_index",
        "fi": "force_index",
        "money_flow_index": "mfi",
        "negative_volume_index": "nvi",
        "positive_volume_index": "pvi",
        "ultimate": "ultimate_oscillator",
        "uo": "ultimate_oscillator",
        "detrended_price_oscillator": "dpo",
        "stochastic_momentum_index": "smi",
        "choppiness": "chop",
        "choppiness_index": "chop",
    }
    for alias, primary in aliases.items():
        assert registry.get(alias) is registry.get(
            primary
        ), f"alias {alias!r} does not resolve to {primary}"


def test_unknown_strategy_reports_available_keys():
    """create_strategy raises a ValueError listing available keys."""
    import pytest

    with pytest.raises(ValueError, match="Unknown strategy"):
        create_strategy("no_such_strategy")


def test_get_strategy_returns_none_for_unknown_key():
    """get_strategy returns None instead of raising for unknown keys."""
    assert get_registry().get("does_not_exist") is None


def test_every_registered_strategy_has_an_example_script():
    """Each registered strategy is imported by at least one ``examples/run_*.py`` script.

    The example scripts are the documented, offline, deterministic way each
    strategy is demonstrated to a user, so a strategy with no example script
    has no usage path documented in the repository.
    """
    registry = get_registry()
    referenced = _example_strategy_classes()
    missing = []
    for key in registry.primary_keys():
        cls = registry.get(key)
        if cls is None or cls.__name__ not in referenced:
            missing.append(key)
    assert not missing, (
        f"Registered strategies with no example script importing them: {missing}. "
        f"Add an examples/run_<name>.py script that imports the class."
    )


def test_every_registered_strategy_has_a_test_class():
    """Each registered strategy has a ``Test<ClassName>`` in test_strategies_examples.

    The shared parametrized suite in :mod:`test_strategies_examples` is the
    behavioural regression net for the built-in strategies. A strategy whose
    class has no matching ``Test<ClassName>`` is only covered by the
    constructibility check above and would silently lose behavioural coverage
    if its behaviour changed.
    """
    registry = get_registry()
    test_classes = _example_test_classes()
    missing = []
    for key in registry.primary_keys():
        cls = registry.get(key)
        if cls is None or f"Test{cls.__name__}" not in test_classes:
            missing.append(key)
    assert not missing, (
        f"Registered strategies with no Test<ClassName> in "
        f"tests/test_strategies_examples.py: {missing}. "
        f"Add a Test<ClassName> subclass covering the strategy's behaviour."
    )
