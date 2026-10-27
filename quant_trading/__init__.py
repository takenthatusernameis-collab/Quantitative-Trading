"""Quantitative Trading System.

A modular framework for algorithmic trading strategies, backtesting, and portfolio management.
"""

__version__ = "0.1.0"
__author__ = "Kilo Autonomous Agent"

from .backtest import BacktestEngine, BacktestResult, run_backtest
from .data import (
    SyntheticDataProvider,
    create_synthetic_data,
    create_synthetic_provider,
)
from .strategies import BaseStrategy, Strategy
from .strategies.factory import create_strategy, list_strategies

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "BaseStrategy",
    "Strategy",
    "SyntheticDataProvider",
    "create_strategy",
    "create_synthetic_data",
    "create_synthetic_provider",
    "list_strategies",
    "run_backtest",
]
