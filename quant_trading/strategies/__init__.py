"""Strategies module for trading strategy implementations."""

from .base import Position, Signal, Strategy, StrategyManager
from .examples import (
    BollingerBandsStrategy,
    MACDStrategy,
    MovingAverageCrossover,
    RSIStrategy,
)

__all__ = [
    "BollingerBandsStrategy",
    "MACDStrategy",
    "MovingAverageCrossover",
    "Position",
    "RSIStrategy",
    "Signal",
    "Strategy",
    "StrategyManager",
]
