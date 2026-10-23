"""Strategies module for trading strategy implementations."""

from .base import Position, Signal, Strategy, StrategyManager
from .examples import (
    ADXStrategy,
    AroonStrategy,
    BollingerBandsStrategy,
    CCIStrategy,
    ChaikinMoneyFlowStrategy,
    DonchianChannelStrategy,
    ElderRayStrategy,
    EMACrossover,
    ForceIndexStrategy,
    IchimokuCloudStrategy,
    KeltnerChannelStrategy,
    MACDStrategy,
    MomentumStrategy,
    MoneyFlowIndexStrategy,
    MovingAverageCrossover,
    OBVStrategy,
    ParabolicSARStrategy,
    RateOfChangeStrategy,
    RSIStrategy,
    StochasticOscillatorStrategy,
    SuperTrendStrategy,
    VolumeRateOfChangeStrategy,
    VWAPStrategy,
    WilliamsRStrategy,
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
register_strategy("ema", EMACrossover, aliases=["ema_crossover", "exponential_ma_crossover"])
register_strategy("ma", MovingAverageCrossover, aliases=["moving_average", "ma_crossover"])
register_strategy("rsi", RSIStrategy, aliases=["rsi_mean_reversion"])
register_strategy("bb", BollingerBandsStrategy, aliases=["bollinger_bands", "bollinger"])
register_strategy("macd", MACDStrategy, aliases=["macd_crossover"])
register_strategy("supertrend", SuperTrendStrategy, aliases=["st", "super_trend"])
register_strategy("donchian", DonchianChannelStrategy, aliases=["donchian_channel", "dc"])
register_strategy("aroon", AroonStrategy, aliases=["aroon_oscillator"])
register_strategy("keltner", KeltnerChannelStrategy, aliases=["kc", "keltner_channel"])
register_strategy("stoch", StochasticOscillatorStrategy, aliases=["stochastic", "stoch_oscillator"])
register_strategy("ichimoku", IchimokuCloudStrategy, aliases=["ichimoku_cloud", "ichimoku"])
register_strategy("sar", ParabolicSARStrategy, aliases=["parabolic_sar", "psar"])
register_strategy("vwap", VWAPStrategy)
register_strategy("vroc", VolumeRateOfChangeStrategy, aliases=["volume_rate_of_change"])
register_strategy("momentum", MomentumStrategy, aliases=["mom"])
register_strategy("adx", ADXStrategy, aliases=["average_directional_index"])
register_strategy("cci", CCIStrategy, aliases=["commodity_channel_index"])
register_strategy("williamsr", WilliamsRStrategy, aliases=["williams_pct_r"])
register_strategy("obv", OBVStrategy, aliases=["on_balance_volume"])
register_strategy("cmf", ChaikinMoneyFlowStrategy, aliases=["chaikin_money_flow"])
register_strategy("elder_ray", ElderRayStrategy, aliases=["elder_ray_index", "erp"])
register_strategy("roc", RateOfChangeStrategy, aliases=["rate_of_change"])
register_strategy("force_index", ForceIndexStrategy, aliases=["forceindex", "fi"])
register_strategy("mfi", MoneyFlowIndexStrategy, aliases=["money_flow_index"])


__all__ = [
    "ADXStrategy",
    "AroonStrategy",
    "BollingerBandsStrategy",
    "CCIStrategy",
    "ChaikinMoneyFlowStrategy",
    "DonchianChannelStrategy",
    "EMACrossover",
    "ElderRayStrategy",
    "ForceIndexStrategy",
    "IchimokuCloudStrategy",
    "KeltnerChannelStrategy",
    "MACDStrategy",
    "MoneyFlowIndexStrategy",
    "MovingAverageCrossover",
    "OBVStrategy",
    "ParabolicSARStrategy",
    "Position",
    "RSIStrategy",
    "RateOfChangeStrategy",
    "Signal",
    "StochasticOscillatorStrategy",
    "Strategy",
    "StrategyManager",
    "StrategyRegistry",
    "SuperTrendStrategy",
    "VolumeRateOfChangeStrategy",
    "WilliamsRStrategy",
    "available_strategies",
    "create_strategy",
    "get_available_strategies",
    "get_registry",
    "get_strategy",
    "get_strategy_factory",
    "list_strategies",
    "register_strategy",
    "strategy_keys",
]


# Convenience functions
def get_available_strategies() -> dict[str, type[Strategy]]:
    """Get the strategies registered in the global registry.

    Returns:
        Mapping of strategy key to strategy class.

    """
    return list_strategies()


def available_strategies() -> dict[str, type[Strategy]]:
    """Get the strategies registered in the global registry.

    Returns:
        Mapping of strategy key to strategy class.

    """
    return list_strategies()


def get_strategy_factory() -> StrategyRegistry:
    """Get the global strategy registry.

    Returns:
        The process-wide :class:`StrategyRegistry` instance.

    """
    return get_registry()
