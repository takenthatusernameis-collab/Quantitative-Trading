"""Strategies module for trading strategy implementations."""

from .base import BaseStrategy, Position, Signal, Strategy, StrategyManager
from .examples import (
    PPO,
    PVO,
    AccumulationDistributionStrategy,
    ADXStrategy,
    AroonStrategy,
    AverageTrueRangeStrategy,
    AwesomeOscillatorStrategy,
    BollingerBandsStrategy,
    BollingerPercentBStrategy,
    CCIStrategy,
    ChaikinMoneyFlowStrategy,
    ChaikinOscillatorStrategy,
    ChandeMomentumOscillatorStrategy,
    ChoppinessIndexStrategy,
    DetrendedPriceOscillatorStrategy,
    DonchianChannelStrategy,
    EaseOfMovementStrategy,
    ElderRayStrategy,
    EMACrossover,
    ForceIndexStrategy,
    HullMovingAverageStrategy,
    IchimokuCloudStrategy,
    KeltnerChannelStrategy,
    KlingerOscillatorStrategy,
    MACDStrategy,
    MomentumStrategy,
    MoneyFlowIndexStrategy,
    MovingAverageCrossover,
    NegativeVolumeIndexStrategy,
    OBVStrategy,
    ParabolicSARStrategy,
    PercentagePriceOscillatorStrategy,
    PercentageVolumeOscillatorStrategy,
    PositiveVolumeIndexStrategy,
    PPOStrategy,
    PVOStrategy,
    RateOfChangeStrategy,
    RSIStrategy,
    StochasticMomentumIndexStrategy,
    StochasticOscillatorStrategy,
    StochRSIStrategy,
    SuperTrendStrategy,
    TrixStrategy,
    UltimateOscillatorStrategy,
    VolumeOscillatorStrategy,
    VolumePriceTrendStrategy,
    VolumeRateOfChangeStrategy,
    VortexStrategy,
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
register_strategy("bbpct", BollingerPercentBStrategy, aliases=["bollinger_bands_pct", "percent_b"])
register_strategy("macd", MACDStrategy, aliases=["macd_crossover"])
register_strategy("supertrend", SuperTrendStrategy, aliases=["st", "super_trend"])
register_strategy("donchian", DonchianChannelStrategy, aliases=["donchian_channel", "dc"])
register_strategy("eom", EaseOfMovementStrategy, aliases=["ease_of_movement"])
register_strategy("aroon", AroonStrategy, aliases=["aroon_oscillator"])
register_strategy("keltner", KeltnerChannelStrategy, aliases=["kc", "keltner_channel"])
register_strategy("klinger", KlingerOscillatorStrategy, aliases=["klinger_oscillator"])
register_strategy("stoch", StochasticOscillatorStrategy, aliases=["stochastic", "stoch_oscillator"])
register_strategy("stochrsi", StochRSIStrategy, aliases=["stochastic_rsi", "stoch_rsi"])
register_strategy("ichimoku", IchimokuCloudStrategy, aliases=["ichimoku_cloud"])
register_strategy("hma", HullMovingAverageStrategy, aliases=["hull_moving_average"])
register_strategy("sar", ParabolicSARStrategy, aliases=["parabolic_sar", "psar"])
register_strategy("vwap", VWAPStrategy)
register_strategy("vroc", VolumeRateOfChangeStrategy, aliases=["volume_rate_of_change"])
register_strategy("ao", AwesomeOscillatorStrategy, aliases=["awesome_oscillator"])
register_strategy("vol", VolumeOscillatorStrategy, aliases=["volume_oscillator"])
register_strategy("vortex", VortexStrategy, aliases=["vortex_indicator"])
register_strategy("vpt", VolumePriceTrendStrategy, aliases=["volume_price_trend"])
register_strategy(
    "ppo",
    PercentagePriceOscillatorStrategy,
    aliases=["percentage_price_oscillator", "ppo_strategy"],
)
register_strategy(
    "pvo",
    PercentageVolumeOscillatorStrategy,
    aliases=["percentage_volume_oscillator", "pvo_strategy"],
)
register_strategy("momentum", MomentumStrategy, aliases=["mom"])
register_strategy("adx", ADXStrategy, aliases=["average_directional_index"])
register_strategy("atr", AverageTrueRangeStrategy, aliases=["average_true_range", "atr_channel"])
register_strategy(
    "adl", AccumulationDistributionStrategy, aliases=["accumulation_distribution", "ad_line"]
)
register_strategy("cci", CCIStrategy, aliases=["commodity_channel_index"])
register_strategy("williamsr", WilliamsRStrategy, aliases=["williams_pct_r"])
register_strategy("obv", OBVStrategy, aliases=["on_balance_volume"])
register_strategy("cmf", ChaikinMoneyFlowStrategy, aliases=["chaikin_money_flow"])
register_strategy("cho", ChaikinOscillatorStrategy, aliases=["chaikin_oscillator"])
register_strategy("cmo", ChandeMomentumOscillatorStrategy, aliases=["chande_momentum_oscillator"])
register_strategy("elder_ray", ElderRayStrategy, aliases=["elder_ray_index", "erp"])
register_strategy("roc", RateOfChangeStrategy, aliases=["rate_of_change"])
register_strategy("force_index", ForceIndexStrategy, aliases=["forceindex", "fi"])
register_strategy("mfi", MoneyFlowIndexStrategy, aliases=["money_flow_index"])
register_strategy("nvi", NegativeVolumeIndexStrategy, aliases=["negative_volume_index"])
register_strategy("pvi", PositiveVolumeIndexStrategy, aliases=["positive_volume_index"])
register_strategy("trix", TrixStrategy)
register_strategy("ultimate_oscillator", UltimateOscillatorStrategy, aliases=["ultimate", "uo"])
register_strategy("dpo", DetrendedPriceOscillatorStrategy, aliases=["detrended_price_oscillator"])
register_strategy("smi", StochasticMomentumIndexStrategy, aliases=["stochastic_momentum_index"])
register_strategy("chop", ChoppinessIndexStrategy, aliases=["choppiness", "choppiness_index"])


__all__ = [
    "PPO",
    "PVO",
    "ADXStrategy",
    "AccumulationDistributionStrategy",
    "AroonStrategy",
    "AverageTrueRangeStrategy",
    "AwesomeOscillatorStrategy",
    "BaseStrategy",
    "BollingerBandsStrategy",
    "BollingerPercentBStrategy",
    "CCIStrategy",
    "ChaikinMoneyFlowStrategy",
    "ChaikinOscillatorStrategy",
    "ChandeMomentumOscillatorStrategy",
    "ChoppinessIndexStrategy",
    "DetrendedPriceOscillatorStrategy",
    "DonchianChannelStrategy",
    "EMACrossover",
    "EaseOfMovementStrategy",
    "ElderRayStrategy",
    "ForceIndexStrategy",
    "HullMovingAverageStrategy",
    "IchimokuCloudStrategy",
    "KeltnerChannelStrategy",
    "KlingerOscillatorStrategy",
    "MACDStrategy",
    "MomentumStrategy",
    "MoneyFlowIndexStrategy",
    "MovingAverageCrossover",
    "NegativeVolumeIndexStrategy",
    "OBVStrategy",
    "PPOStrategy",
    "PVOStrategy",
    "ParabolicSARStrategy",
    "PercentagePriceOscillatorStrategy",
    "PercentageVolumeOscillatorStrategy",
    "Position",
    "PositiveVolumeIndexStrategy",
    "RSIStrategy",
    "RateOfChangeStrategy",
    "Signal",
    "StochRSIStrategy",
    "StochasticMomentumIndexStrategy",
    "StochasticOscillatorStrategy",
    "Strategy",
    "StrategyManager",
    "StrategyRegistry",
    "SuperTrendStrategy",
    "TrixStrategy",
    "UltimateOscillatorStrategy",
    "VWAPStrategy",
    "VolumeOscillatorStrategy",
    "VolumePriceTrendStrategy",
    "VolumeRateOfChangeStrategy",
    "VortexStrategy",
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
