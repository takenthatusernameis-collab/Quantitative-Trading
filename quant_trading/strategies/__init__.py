"""Strategies module for trading strategy implementations."""

from .base import Position, Signal, Strategy, StrategyManager
from .examples import BollingerBandsStrategy, MovingAverageCrossover, RSIStrategy

__all__ = [
    "BollingerBandsStrategy",
    "MovingAverageCrossover",
    "Position",
    "RSIStrategy",
    "Signal",
    "Strategy",
    "StrategyManager",
]
