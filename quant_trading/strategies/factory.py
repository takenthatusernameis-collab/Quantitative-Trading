"""Strategy factory and registry for dynamic strategy creation."""


from .base import Strategy


class StrategyRegistry:
    """Registry for strategy classes with dynamic registration support."""

    def __init__(self):
        self._strategies: dict[str, type[Strategy]] = {}
        self._aliases: dict[str, str] = {}

    def register(self, key: str, strategy_cls: type[Strategy], aliases: list[str] | None = None) -> None:
        """Register a strategy class.

        Args:
            key: Primary key for the strategy (e.g., 'ma', 'rsi')
            strategy_cls: Strategy class to register
            aliases: Optional list of alternative keys
        """
        if not issubclass(strategy_cls, Strategy):
            raise TypeError(f"{strategy_cls.__name__} must be a subclass of Strategy")
        self._strategies[key] = strategy_cls
        if aliases:
            for alias in aliases:
                self._aliases[alias] = key

    def unregister(self, key: str) -> None:
        """Unregister a strategy."""
        self._strategies.pop(key, None)
        # Remove aliases pointing to this key
        self._aliases = {k: v for k, v in self._aliases.items() if v != key}

    def get(self, key: str) -> type[Strategy] | None:
        """Get strategy class by key or alias."""
        actual_key = self._aliases.get(key, key)
        return self._strategies.get(actual_key)

    def get_all(self) -> dict[str, type[Strategy]]:
        """Get all registered strategies."""
        return self._strategies.copy()

    def keys(self) -> list[str]:
        """Get all registered strategy keys (including aliases)."""
        return list(self._strategies.keys()) + list(self._aliases.keys())

    def primary_keys(self) -> list[str]:
        """Get only primary strategy keys (no aliases)."""
        return list(self._strategies.keys())

    def create(self, key: str, **kwargs) -> Strategy:
        """Create a strategy instance from key and parameters."""
        strategy_cls = self.get(key)
        if strategy_cls is None:
            raise ValueError(f"Unknown strategy: {key}. Available: {self.primary_keys()}")
        return strategy_cls(**kwargs)


# Global registry instance
_registry = StrategyRegistry()


def register_strategy(key: str, strategy_cls: type[Strategy], aliases: list[str] | None = None) -> None:
    """Register a strategy in the global registry."""
    _registry.register(key, strategy_cls, aliases)


def get_strategy(key: str) -> type[Strategy] | None:
    """Get strategy class by key from global registry."""
    return _registry.get(key)


def create_strategy(key: str, **kwargs) -> Strategy:
    """Create strategy instance from global registry."""
    return _registry.create(key, **kwargs)


def list_strategies() -> dict[str, type[Strategy]]:
    """List all registered strategies."""
    return _registry.get_all()


def strategy_keys() -> list[str]:
    """Get all strategy keys from global registry."""
    return _registry.keys()


def get_registry() -> StrategyRegistry:
    """Get the global strategy registry."""
    return _registry