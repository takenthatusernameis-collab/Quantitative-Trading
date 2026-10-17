"""Base strategy classes and interfaces."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd


@dataclass
class Signal:
    """Trading signal."""

    symbol: str
    action: str  # 'buy', 'sell', 'hold'
    strength: float = 1.0  # 0.0 to 1.0
    price: float | None = None
    timestamp: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class Position:
    """Current position in a symbol.

    Attributes:
        symbol: Traded symbol.
        quantity: Position quantity (positive for long, negative for short).
        avg_price: Average entry price per unit.
        current_price: Latest market price per unit.
        unrealized_pnl: Unrealized profit and loss.
        realized_pnl: Realized profit and loss.
    """

    symbol: str
    quantity: float = 0.0
    avg_price: float = 0.0
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def pnl(self) -> float:
        return self.unrealized_pnl + self.realized_pnl


class Strategy(ABC):
    """Abstract base class for trading strategies."""

    def __init__(self, name: str, parameters: dict[str, Any] | None = None):
        self.name = name
        self.parameters = parameters or {}
        self.signals: list[Signal] = []
        self.positions: dict[str, Position] = {}

    @abstractmethod
    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate trading signals from market data."""

    def validate_parameters(self) -> None:
        """Validate strategy parameters. Override in subclasses for specific validation."""

    def update_positions(self, positions: dict[str, Position]) -> None:
        """Update internal position tracking."""
        self.positions = positions

    def get_parameters(self) -> dict[str, Any]:
        """Get strategy parameters."""
        return self.parameters.copy()

    def set_parameter(self, key: str, value: Any) -> None:
        """Set a strategy parameter."""
        # Store old values for rollback on validation failure
        old_param_value = self.parameters.get(key)
        old_attr_value = getattr(self, key, None) if hasattr(self, key) else None

        # Tentatively update
        self.parameters[key] = value
        if hasattr(self, key):
            setattr(self, key, value)

        try:
            self.validate_parameters()
        except ValueError:
            # Rollback on validation failure
            if old_param_value is not None:
                self.parameters[key] = old_param_value
            else:
                self.parameters.pop(key, None)
            if hasattr(self, key):
                if old_attr_value is not None:
                    setattr(self, key, old_attr_value)
                else:
                    delattr(self, key)
            raise

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "Strategy":
        """Create strategy instance from configuration dictionary.

        Args:
            config: Dictionary with 'name' (optional), 'type' (strategy key),
                   and 'parameters' (dict of strategy parameters).

        Returns:
            Strategy instance.
        """
        from quant_trading.strategies.factory import create_strategy

        strategy_type = config.get("type")
        if not strategy_type:
            raise ValueError("Strategy config must contain 'type' key")

        parameters = config.get("parameters", {})
        name = config.get("name", strategy_type)

        return create_strategy(strategy_type, name=name, **parameters)


class StrategyManager:
    """Manages multiple strategies."""

    def __init__(self):
        self.strategies: dict[str, Strategy] = {}

    def add_strategy(self, strategy: Strategy) -> None:
        """Add a strategy."""
        self.strategies[strategy.name] = strategy

    def remove_strategy(self, name: str) -> None:
        """Remove a strategy."""
        self.strategies.pop(name, None)

    def get_strategy(self, name: str) -> Strategy | None:
        """Get strategy by name."""
        return self.strategies.get(name)

    def generate_all_signals(self, data: dict[str, pd.DataFrame]) -> dict[str, list[Signal]]:
        """Generate signals from all strategies."""
        signals = {}
        for name, strategy in self.strategies.items():
            signals[name] = strategy.generate_signals(data)
        return signals
