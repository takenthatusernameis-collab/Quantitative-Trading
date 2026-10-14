"""Strategies module for trading strategy implementations."""

from .base import Position, Signal, Strategy, StrategyManager
from .examples import (
    AroonStrategy,
    BollingerBandsStrategy,
    DonchianChannelStrategy,
    KeltnerChannelStrategy,
    MACDStrategy,
    MovingAverageCrossover,
    RSIStrategy,
    SuperTrendStrategy,
)
from .factory import (
    StrategyRegistry,
    create_strategy,
    get_registry,
    get_strategy,
    list_strategies,
    register_strategy,
    strategy_keys,
)

# Register built-in strategies
register_strategy("ma", MovingAverageCrossover, aliases=["moving_average", "ma_crossover"])
register_strategy("rsi", RSIStrategy, aliases=["rsi_mean_reversion"])
register_strategy("bb", BollingerBandsStrategy, aliases=["bollinger_bands", "bollinger"])
register_strategy("macd", MACDStrategy, aliases=["macd_crossover"])
register_strategy("supertrend", SuperTrendStrategy, aliases=["st", "super_trend"])
register_strategy("donchian", DonchianChannelStrategy, aliases=["donchian_channel", "dc"])
register_strategy("aroon", AroonStrategy, aliases=["aroon_oscillator"])
register_strategy("keltner", KeltnerChannelStrategy, aliases=["kc", "keltner_channel"])

__all__ = [
    "AroonStrategy",
    "BollingerBandsStrategy",
    "DonchianChannelStrategy",
    "KeltnerChannelStrategy",
    "MACDStrategy",
    "MovingAverageCrossover",
    "Position",
    "RSIStrategy",
    "Signal",
    "Strategy",
    "StrategyManager",
    "StrategyRegistry",
    "SuperTrendStrategy",
    "create_strategy",
    "get_registry",
    "get_strategy",
    "list_strategies",
    "register_strategy",
    "strategy_keys",
]
