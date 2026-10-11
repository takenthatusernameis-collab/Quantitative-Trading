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
    """Current position in a symbol."""
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

    def update_positions(self, positions: dict[str, Position]) -> None:
        """Update internal position tracking."""
        self.positions = positions

    def get_parameters(self) -> dict[str, Any]:
        """Get strategy parameters."""
        return self.parameters.copy()

    def set_parameter(self, key: str, value: Any) -> None:
        """Set a strategy parameter."""
        self.parameters[key] = value


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