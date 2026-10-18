"""Strategy factory and registry for dynamic strategy creation.

This module provides a :class:`StrategyRegistry` that maps string keys to
strategy classes, along with a set of convenience functions operating on a
process-wide global registry. Strategies can be looked up by primary key or
by alias, and instantiated with arbitrary keyword arguments.

Examples:
    Register a custom strategy and look it up::

        from quant_trading.strategies.factory import register_strategy, get_strategy, create_strategy

        class MyStrategy(Strategy):
            def generate_signals(self, data):
                return []

        register_strategy("my", MyStrategy)
        assert get_strategy("my") is MyStrategy
        instance = create_strategy("my")
        assert isinstance(instance, MyStrategy)

    List every registered strategy key::

        from quant_trading.strategies.factory import strategy_keys

        assert "ma" in strategy_keys()
"""

from .base import Strategy


class StrategyRegistry:
    """Registry mapping string keys to strategy classes.

    Each strategy is stored under a primary key, with optional aliases that
    resolve to the same primary key. Aliases are useful for providing
    human-friendly or backwards-compatible names.

    Attributes:
        _strategies: Mapping of primary key to strategy class.
        _aliases: Mapping of alias to primary key.

    Examples:
        >>> from quant_trading.strategies.factory import StrategyRegistry
        >>> from quant_trading.strategies.examples import MovingAverageCrossover
        >>> registry = StrategyRegistry()
        >>> registry.register("ma", MovingAverageCrossover, aliases=["moving_average"])
        >>> registry.get("ma") is MovingAverageCrossover
        True
        >>> registry.get("moving_average") is MovingAverageCrossover
        True
        >>> registry.primary_keys()
        ['ma']
        >>> registry.keys()
        ['ma', 'moving_average']
    """

    def __init__(self):
        """Initialize an empty strategy registry.

        Creates empty mappings for strategies and aliases.

        Returns:
            None.
        """
        self._strategies: dict[str, type[Strategy]] = {}
        self._aliases: dict[str, str] = {}

    def register(
        self, key: str, strategy_cls: type[Strategy], aliases: list[str] | None = None
    ) -> None:
        """Register a strategy class under a primary key.

        Args:
            key: Primary key for the strategy (e.g. ``"ma"``, ``"rsi"``).
            strategy_cls: Strategy class to register. Must be a subclass of
                :class:`~quant_trading.strategies.base.Strategy`.
            aliases: Optional list of alternative keys that resolve to the
                same strategy.

        Raises:
            TypeError: If ``strategy_cls`` is not a subclass of
                :class:`~quant_trading.strategies.base.Strategy`.

        Returns:
            None.
        """
        if not issubclass(strategy_cls, Strategy):
            raise TypeError(f"{strategy_cls.__name__} must be a subclass of Strategy")
        self._strategies[key] = strategy_cls
        if aliases:
            for alias in aliases:
                self._aliases[alias] = key

    def unregister(self, key: str) -> None:
        """Unregister a strategy and any aliases pointing to it.

        Args:
            key: Primary key of the strategy to remove.

        Returns:
            None.
        """
        self._strategies.pop(key, None)
        # Remove aliases pointing to this key
        self._aliases = {k: v for k, v in self._aliases.items() if v != key}

    def get(self, key: str) -> type[Strategy] | None:
        """Get a strategy class by primary key or alias.

        Args:
            key: Primary key or alias of the strategy.

        Returns:
            The matching strategy class, or ``None`` when the key is not
            registered.
        """
        actual_key = self._aliases.get(key, key)
        return self._strategies.get(actual_key)

    def get_all(self) -> dict[str, type[Strategy]]:
        """Get all registered strategies keyed by primary key.

        Returns:
            A shallow copy of the primary-key-to-class mapping, so callers
            cannot mutate the registry's internal state.
        """
        return self._strategies.copy()

    def keys(self) -> list[str]:
        """Get all registered strategy keys, including aliases.

        Returns:
            List of primary keys followed by alias keys.
        """
        return list(self._strategies.keys()) + list(self._aliases.keys())

    def primary_keys(self) -> list[str]:
        """Get only the primary strategy keys (excluding aliases).

        Returns:
            List of primary keys in insertion order.
        """
        return list(self._strategies.keys())

    def create(self, key: str, **kwargs) -> Strategy:
        """Create a strategy instance from a key and parameters.

        Args:
            key: Primary key or alias of the strategy to instantiate.
            **kwargs: Keyword arguments forwarded to the strategy
                constructor.

        Returns:
            A new strategy instance.

        Raises:
            ValueError: If ``key`` is not registered. The error message
                lists the available primary keys.
        """
        strategy_cls = self.get(key)
        if strategy_cls is None:
            raise ValueError(f"Unknown strategy: {key}. Available: {self.primary_keys()}")
        return strategy_cls(**kwargs)


# Global registry instance
_registry = StrategyRegistry()


def register_strategy(
    key: str, strategy_cls: type[Strategy], aliases: list[str] | None = None
) -> None:
    """Register a strategy in the global registry.

    Args:
        key: Primary key for the strategy.
        strategy_cls: Strategy class to register.
        aliases: Optional list of alternative keys.

    Returns:
        None.
    """
    _registry.register(key, strategy_cls, aliases)


def get_strategy(key: str) -> type[Strategy] | None:
    """Get a strategy class by key from the global registry.

    Args:
        key: Primary key or alias of the strategy.

    Returns:
        The matching strategy class, or ``None`` when not found.
    """
    return _registry.get(key)


def create_strategy(key: str, **kwargs) -> Strategy:
    """Create a strategy instance from the global registry.

    Args:
        key: Primary key or alias of the strategy to instantiate.
        **kwargs: Keyword arguments forwarded to the strategy constructor.

    Returns:
        A new strategy instance.

    Raises:
        ValueError: If ``key`` is not registered.
    """
    return _registry.create(key, **kwargs)


def list_strategies() -> dict[str, type[Strategy]]:
    """List all registered strategies from the global registry.

    Returns:
        Mapping of primary key to strategy class.
    """
    return _registry.get_all()


def strategy_keys() -> list[str]:
    """Get all strategy keys from the global registry.

    Returns:
        List of primary keys and aliases.
    """
    return _registry.keys()


def get_registry() -> StrategyRegistry:
    """Get the global strategy registry instance.

    Returns:
        The process-wide :class:`StrategyRegistry` instance.
    """
    return _registry
