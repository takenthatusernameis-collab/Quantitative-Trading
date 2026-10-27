"""Tests for the strategy factory and registry."""

import pytest

from quant_trading.strategies import (
    BollingerBandsStrategy,
    MACDStrategy,
    MovingAverageCrossover,
    RSIStrategy,
    Strategy,
    available_strategies,
    create_strategy,
    get_available_strategies,
    get_registry,
    get_strategy,
    get_strategy_factory,
    list_strategies,
    register_strategy,
    strategy_keys,
)
from quant_trading.strategies.factory import StrategyRegistry


class DummyStrategy(Strategy):
    """Minimal concrete strategy for registry tests."""

    def __init__(self, name: str = "Dummy", factor: float = 1.0):
        super().__init__(name, {"factor": factor})
        self.factor = factor

    def generate_signals(self, data):
        return []


class OtherStrategy(Strategy):
    """Second concrete strategy for overwrite tests."""

    def __init__(self, name: str = "Other"):
        super().__init__(name)

    def generate_signals(self, data):
        return []


class TestStrategyRegistry:
    """Tests for StrategyRegistry using isolated instances."""

    def test_register_and_get(self):
        registry = StrategyRegistry()
        registry.register("dummy", DummyStrategy)
        assert registry.get("dummy") is DummyStrategy

    def test_register_with_aliases(self):
        registry = StrategyRegistry()
        registry.register("dummy", DummyStrategy, aliases=["d", "dummy_s"])
        assert registry.get("dummy") is DummyStrategy
        assert registry.get("d") is DummyStrategy
        assert registry.get("dummy_s") is DummyStrategy

    def test_register_non_strategy_raises_typeerror(self):
        registry = StrategyRegistry()
        with pytest.raises(TypeError, match="must be a subclass of Strategy"):
            registry.register("bad", dict)

    def test_get_unknown_returns_none(self):
        registry = StrategyRegistry()
        assert registry.get("missing") is None

    def test_get_all_returns_copy(self):
        registry = StrategyRegistry()
        registry.register("dummy", DummyStrategy)
        all_strategies = registry.get_all()
        all_strategies["injected"] = OtherStrategy
        assert "injected" not in registry.get_all()

    def test_keys_includes_aliases(self):
        registry = StrategyRegistry()
        registry.register("dummy", DummyStrategy, aliases=["d"])
        assert set(registry.keys()) == {"dummy", "d"}

    def test_primary_keys_excludes_aliases(self):
        registry = StrategyRegistry()
        registry.register("dummy", DummyStrategy, aliases=["d"])
        assert registry.primary_keys() == ["dummy"]

    def test_unregister_removes_key_and_aliases(self):
        registry = StrategyRegistry()
        registry.register("dummy", DummyStrategy, aliases=["d"])
        registry.unregister("dummy")
        assert registry.get("dummy") is None
        assert registry.get("d") is None
        assert registry.primary_keys() == []

    def test_unregister_unknown_is_noop(self):
        registry = StrategyRegistry()
        registry.register("dummy", DummyStrategy)
        registry.unregister("missing")
        assert registry.get("dummy") is DummyStrategy

    def test_reregister_overwrites(self):
        registry = StrategyRegistry()
        registry.register("dummy", DummyStrategy, aliases=["d"])
        registry.register("dummy", OtherStrategy)
        assert registry.get("dummy") is OtherStrategy
        # Stale alias from the first registration remains pointing to the key
        assert registry.get("d") is OtherStrategy

    def test_create_instantiates_with_kwargs(self):
        registry = StrategyRegistry()
        registry.register("dummy", DummyStrategy)
        strategy = registry.create("dummy", name="Custom", factor=2.5)
        assert isinstance(strategy, DummyStrategy)
        assert strategy.name == "Custom"
        assert strategy.factor == 2.5

    def test_create_via_alias(self):
        registry = StrategyRegistry()
        registry.register("dummy", DummyStrategy, aliases=["d"])
        assert isinstance(registry.create("d"), DummyStrategy)

    def test_create_unknown_raises_valueerror(self):
        registry = StrategyRegistry()
        registry.register("dummy", DummyStrategy)
        with pytest.raises(ValueError, match="Unknown strategy: missing"):
            registry.create("missing")

    def test_create_error_message_lists_available(self):
        registry = StrategyRegistry()
        registry.register("dummy", DummyStrategy)
        registry.register("other", OtherStrategy)
        with pytest.raises(ValueError, match="Available: \\['dummy', 'other'\\]"):
            registry.create("missing")


class TestGlobalRegistry:
    """Tests for the module-level global registry functions."""

    def test_builtin_strategies_registered(self):
        strategies = list_strategies()
        assert strategies["ma"] is MovingAverageCrossover
        assert strategies["rsi"] is RSIStrategy
        assert strategies["bb"] is BollingerBandsStrategy
        assert strategies["macd"] is MACDStrategy

    def test_builtin_aliases_resolve(self):
        assert get_strategy("moving_average") is MovingAverageCrossover
        assert get_strategy("ma_crossover") is MovingAverageCrossover
        assert get_strategy("rsi_mean_reversion") is RSIStrategy
        assert get_strategy("bollinger_bands") is BollingerBandsStrategy
        assert get_strategy("bollinger") is BollingerBandsStrategy
        assert get_strategy("macd_crossover") is MACDStrategy

    def test_strategy_keys_include_builtins_and_aliases(self):
        keys = strategy_keys()
        for key in ("ma", "rsi", "bb", "macd", "moving_average", "bollinger"):
            assert key in keys

    def test_strategy_keys_are_unique(self):
        """``strategy_keys()`` must not contain duplicates.

        A duplicate arises when a primary key is also listed as one of its own
        aliases (e.g. ``register_strategy("ichimoku", ..., aliases=["ichimoku"])``).
        The primary key is then emitted twice, so callers that iterate the list
        (such as the CLI's combined mode) run the same strategy twice.
        """
        keys = strategy_keys()
        duplicates = sorted({k for k in keys if keys.count(k) > 1})
        assert duplicates == [], f"duplicate strategy keys: {duplicates}"

    def test_no_alias_collides_with_a_primary_key(self):
        """An alias must not shadow a primary key of another strategy.

        If an alias resolves to a primary key that is also a primary key, the
        alias silently overwrites the primary in ``_aliases`` and the primary
        key's own class becomes unreachable through the alias.
        """
        registry = get_registry()
        primaries = set(registry.primary_keys())
        offenders = sorted(set(registry._aliases) & primaries)
        assert offenders == [], f"aliases colliding with primary keys: {offenders}"

    def test_get_strategy_unknown_returns_none(self):
        assert get_strategy("not_a_real_strategy") is None

    def test_create_strategy_builtin(self):
        strategy = create_strategy("ma", fast_period=5, slow_period=20)
        assert isinstance(strategy, MovingAverageCrossover)
        assert strategy.fast_period == 5
        assert strategy.slow_period == 20

    def test_create_strategy_default_parameters(self):
        strategy = create_strategy("rsi")
        assert isinstance(strategy, RSIStrategy)
        assert strategy.period == 14

    def test_register_strategy_roundtrip(self):
        key = "test_unique_strategy_key"
        try:
            register_strategy(key, DummyStrategy, aliases=["test_unique_alias"])
            assert get_strategy(key) is DummyStrategy
            assert get_strategy("test_unique_alias") is DummyStrategy
            instance = create_strategy(key, name="Roundtrip", factor=3.0)
            assert isinstance(instance, DummyStrategy)
            assert instance.name == "Roundtrip"
        finally:
            get_registry().unregister(key)
        assert get_strategy(key) is None
        assert get_strategy("test_unique_alias") is None

    def test_get_registry_is_global_instance(self):
        registry = get_registry()
        assert isinstance(registry, StrategyRegistry)
        assert registry is get_registry()
        assert registry.get("ma") is MovingAverageCrossover

    def test_create_strategy_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown strategy"):
            create_strategy("not_a_real_strategy")


class TestStrategyConvenienceHelpers:
    """Tests for the convenience helpers exported by the strategies package."""

    def test_get_available_strategies_returns_the_registered_strategies(self):
        assert get_available_strategies() == list_strategies()
        assert get_available_strategies()["ma"] is MovingAverageCrossover

    def test_available_strategies_returns_the_registered_strategies(self):
        assert available_strategies() == list_strategies()

    def test_get_strategy_factory_returns_the_global_registry(self):
        assert get_strategy_factory() is get_registry()


class TestStrategyFromConfig:
    """Tests for Strategy.from_config, which delegates to the factory."""

    def test_from_config_creates_strategy(self):
        config = {
            "type": "ma",
            "name": "MyCrossover",
            "parameters": {"fast_period": 5, "slow_period": 15},
        }
        strategy = Strategy.from_config(config)
        assert isinstance(strategy, MovingAverageCrossover)
        assert strategy.name == "MyCrossover"
        assert strategy.fast_period == 5
        assert strategy.slow_period == 15

    def test_from_config_defaults_name_to_type(self):
        strategy = Strategy.from_config({"type": "bb", "parameters": {}})
        assert isinstance(strategy, BollingerBandsStrategy)
        assert strategy.name == "bb"

    def test_from_config_missing_type_raises(self):
        with pytest.raises(ValueError, match="must contain 'type'"):
            Strategy.from_config({"parameters": {}})

    def test_from_config_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown strategy"):
            Strategy.from_config({"type": "not_a_real_strategy"})


class TestStrategyBase:
    """Tests for the Strategy base class (base.py)."""

    def test_generate_signals_abstract_body_executed(self):
        """A subclass delegating to super() runs the abstract body (base.py:179)."""

        class DelegatingStrategy(Strategy):
            def generate_signals(self, data):
                return super().generate_signals(data)

        strategy = DelegatingStrategy(name="Delegating")
        assert strategy.generate_signals({}) is None
