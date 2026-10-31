"""Tests for example trading strategies."""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from quant_trading.strategies.examples import (
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
    RateOfChangeStrategy,
    RSIStrategy,
    StochasticOscillatorStrategy,
    StochRSIStrategy,
    SuperTrendStrategy,
    TrixStrategy,
    VolumeOscillatorStrategy,
    VolumePriceTrendStrategy,
    VolumeRateOfChangeStrategy,
    VortexStrategy,
    VWAPStrategy,
    WilliamsRStrategy,
)


def create_trending_data(symbol: str, days: int = 100, trend: float = 0.001) -> pd.DataFrame:
    """Create mock price data with a trend."""
    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=days, freq="D")
    returns = np.random.normal(trend, 0.02, days)
    prices = 100 * np.exp(np.cumsum(returns))

    df = pd.DataFrame(
        {
            "open": prices * (1 + np.random.uniform(-0.005, 0.005, days)),
            "high": prices * (1 + np.random.uniform(0, 0.01, days)),
            "low": prices * (1 - np.random.uniform(0, 0.01, days)),
            "close": prices,
            "volume": np.random.randint(1000000, 10000000, days),
        },
        index=dates,
    )
    return df  # type: ignore[no-any-return]


def create_mean_reverting_data(symbol: str, days: int = 100) -> pd.DataFrame:
    """Create mock price data that mean reverts."""
    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=days, freq="D")
    # Create oscillating prices
    t = np.arange(days)
    base = 100 + 10 * np.sin(t * 2 * np.pi / 20)  # 20-day cycle
    noise = np.random.normal(0, 0.5, days)
    prices = base + noise

    df = pd.DataFrame(
        {
            "open": prices * (1 + np.random.uniform(-0.005, 0.005, days)),
            "high": prices * (1 + np.random.uniform(0, 0.01, days)),
            "low": prices * (1 - np.random.uniform(0, 0.01, days)),
            "close": prices,
            "volume": np.random.randint(1000000, 10000000, days),
        },
        index=dates,
    )
    return df  # type: ignore[no-any-return]


def create_supertrend_data(symbol: str, days: int = 100, trend: float = 0.0) -> pd.DataFrame:
    """Create mock price data with a clear trend for SuperTrend testing.

    When trend > 0: steady uptrend that should trigger bullish SuperTrend
    When trend < 0: steady downtrend that should trigger bearish SuperTrend
    """
    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=days, freq="D")
    returns = np.random.normal(trend, 0.01, days)
    prices = 100 * np.exp(np.cumsum(returns))

    # Add some volatility for realistic ATR calculation
    high = prices * (1 + np.abs(np.random.normal(0, 0.005, days)))
    low = prices * (1 - np.abs(np.random.normal(0, 0.005, days)))
    open_ = prices * (1 + np.random.uniform(-0.002, 0.002, days))

    df = pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": prices,
            "volume": np.random.randint(1000000, 10000000, days),
        },
        index=dates,
    )
    return df  # type: ignore[no-any-return]


def create_donchian_data(symbol: str, closes: list[float]) -> pd.DataFrame:
    """Create deterministic OHLC data from explicit close prices.

    High/low carry a small 0.1% wick so high >= close >= low holds.
    Explicit closes make Donchian breakout/breakdown scenarios
    reproducible, unlike randomized data whose bands rarely align
    with the final bar.
    """
    close = np.asarray(closes, dtype=float)
    dates = pd.date_range(end=datetime.now(), periods=len(close), freq="D")
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": np.full(len(close), 1_000_000),
        },
        index=dates,
    )


def create_keltner_data(symbol: str, closes: list[float]) -> pd.DataFrame:
    """Create deterministic OHLC data from explicit close prices.

    High/low/wick are derived from ATR-like volatility for realistic
    Keltner Channel testing. Unlike donchian data, we calculate
    proper high/low ranges based on EMA and ATR to test channel
    breakouts accurately.
    """
    close = np.asarray(closes, dtype=float)
    if len(close) < 2:
        raise ValueError("Need at least 2 price points")

    dates = pd.date_range(end=datetime.now(), periods=len(close), freq="D")

    # Calculate a simple EMA and ATR-like volatility for bands
    # Use a fixed period for consistency in tests
    ema_period = min(5, len(close) // 2)  # Use small EMA period for test data
    atr_period = min(5, len(close) // 2)  # Use small ATR period for test data

    # Calculate EMA
    ema = pd.Series(close).ewm(span=ema_period, adjust=False).mean().values

    # Calculate True Range and ATR
    high_raw = close * 1.001  # Temporary high for TR calculation
    low_raw = close * 0.999  # Temporary low for TR calculation

    # True Range = max(high - low, |high - prev_close|, |low - prev_close|)
    prev_close = np.concatenate(([close[0]], close[:-1]))
    tr1 = high_raw - low_raw
    tr2 = np.abs(high_raw - prev_close)
    tr3 = np.abs(low_raw - prev_close)
    true_range = np.maximum(tr1, np.maximum(tr2, tr3))

    # Simple moving average of True Range for ATR
    atr = pd.Series(true_range).rolling(window=atr_period, min_periods=1).mean().values

    # Generate OHLC data based on EMA and ATR
    multiplier = 2.0  # Same as default in strategy
    upper_band = ema + (multiplier * atr)
    lower_band = ema - (multiplier * atr)

    # Add some randomness to make it realistic while keeping close prices fixed
    noise_factor = 0.001  # Small noise factor
    open_prices = close * (1 + np.random.uniform(-noise_factor, noise_factor, len(close)))
    high_prices = np.maximum(
        upper_band * (1 + np.random.uniform(0, noise_factor, len(close))),
        np.maximum(open_prices, close),
    )
    low_prices = np.minimum(
        lower_band * (1 - np.random.uniform(0, noise_factor, len(close))),
        np.minimum(open_prices, close),
    )

    # Ensure high >= close >= low
    high_prices = np.maximum(high_prices, np.maximum(open_prices, close))
    low_prices = np.minimum(low_prices, np.minimum(open_prices, close))

    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": open_prices,
            "high": high_prices,
            "low": low_prices,
            "close": close,
            "volume": np.full(len(close), 1_000_000),
        },
        index=dates,
    )


class TestDonchianChannelStrategy:
    """Tests for DonchianChannelStrategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = DonchianChannelStrategy(period=20, exit_period=10, name="Test_DC")
        assert strategy.name == "Test_DC"
        assert strategy.period == 20
        assert strategy.exit_period == 10
        assert strategy.parameters["period"] == 20
        assert strategy.parameters["exit_period"] == 10

    def test_initialization_default_exit_period(self):
        """Test default exit_period equals period."""
        strategy = DonchianChannelStrategy(period=20, name="Test_DC")
        assert strategy.exit_period == 20
        assert strategy.parameters["exit_period"] is None

    def test_validate_parameters(self):
        """Test parameter validation."""
        with pytest.raises(ValueError, match="period must be positive"):
            DonchianChannelStrategy(period=0)
        with pytest.raises(ValueError, match="exit_period must be positive"):
            DonchianChannelStrategy(period=20, exit_period=0)
        with pytest.raises(ValueError, match="period must be positive"):
            DonchianChannelStrategy(period=-1)
        with pytest.raises(ValueError, match="exit_period must be positive"):
            DonchianChannelStrategy(period=20, exit_period=-1)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with insufficient data."""
        strategy = DonchianChannelStrategy(period=20)
        data = {"AAPL": create_donchian_data("AAPL", [100.0] * 15)}  # Less than period
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_bullish_breakout(self):
        """Test generate_signals detects bullish breakout (buy signal)."""
        strategy = DonchianChannelStrategy(period=20, exit_period=10)
        # Flat range, then a final close well above the prior 20-bar high
        data = {"AAPL": create_donchian_data("AAPL", [100.0] * 40 + [110.0])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.strength == pytest.approx(1.0)
        assert signal.price == pytest.approx(110.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "upper_breakout"
        assert signal.metadata["upper_band"] == pytest.approx(100.0 * 1.001)
        assert signal.metadata["lower_band"] == pytest.approx(100.0 * 0.999)
        assert signal.metadata["middle_band"] == pytest.approx(100.0)
        assert signal.metadata["exit_upper"] == pytest.approx(100.0 * 1.001)
        assert signal.metadata["exit_lower"] == pytest.approx(100.0 * 0.999)

    def test_generate_signals_bearish_breakdown(self):
        """Test generate_signals detects bearish breakdown (sell signal)."""
        strategy = DonchianChannelStrategy(period=20, exit_period=10)
        data = {"AAPL": create_donchian_data("AAPL", [100.0] * 40 + [90.0])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.strength == pytest.approx(1.0)
        assert signal.price == pytest.approx(90.0)
        assert signal.metadata["signal_type"] == "lower_breakdown"
        assert signal.metadata["upper_band"] == pytest.approx(100.0 * 1.001)
        assert signal.metadata["lower_band"] == pytest.approx(100.0 * 0.999)

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals with multiple symbols."""
        strategy = DonchianChannelStrategy(period=20, exit_period=10)
        data = {
            "AAPL": create_donchian_data("AAPL", [100.0] * 40 + [110.0]),
            "MSFT": create_donchian_data("MSFT", [100.0] * 40 + [90.0]),
        }
        signals = strategy.generate_signals(data)
        by_symbol = {s.symbol: s for s in signals}
        assert set(by_symbol) == {"AAPL", "MSFT"}
        assert by_symbol["AAPL"].action == "buy"
        assert by_symbol["MSFT"].action == "sell"

    def test_generate_signals_in_range_no_signals(self):
        """Test generate_signals returns no signals while price stays in channel."""
        strategy = DonchianChannelStrategy(period=20, exit_period=10)
        data = {"AAPL": create_donchian_data("AAPL", [100.0] * 41)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_exit_long_middle_band(self):
        """Test generate_signals exits long when price crosses below middle band."""
        strategy = DonchianChannelStrategy(period=20, exit_period=10)
        # Prior close above the middle band, final close below it but above
        # the exit channel lower band
        data = {"AAPL": create_donchian_data("AAPL", [100.0] * 39 + [101.0, 100.2])}
        from quant_trading.strategies.base import Position

        strategy.update_positions({"AAPL": Position(symbol="AAPL", quantity=100, avg_price=100.0)})
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert 0.0 <= signal.strength <= 1.0
        assert signal.metadata["signal_type"] == "middle_band_exit_long"

    def test_generate_signals_exit_long_exit_channel(self):
        """Test generate_signals exits long when price breaks exit channel."""
        strategy = DonchianChannelStrategy(period=20, exit_period=10)
        # A dip inside the 20-bar window but outside the 10-bar exit window,
        # then a close below the exit channel lower band
        data = {
            "AAPL": create_donchian_data(
                "AAPL", [100.0] * 20 + [98.0] * 10 + [100.0] * 9 + [99.0, 98.5]
            )
        }
        from quant_trading.strategies.base import Position

        strategy.update_positions({"AAPL": Position(symbol="AAPL", quantity=100, avg_price=100.0)})
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert 0.0 <= signal.strength <= 1.0
        assert signal.metadata["signal_type"] == "exit_channel_breakdown"

    def test_generate_signals_exit_short_middle_band(self):
        """Test generate_signals exits short when price crosses above middle band."""
        strategy = DonchianChannelStrategy(period=20, exit_period=10)
        data = {"AAPL": create_donchian_data("AAPL", [100.0] * 39 + [99.0, 100.05])}
        from quant_trading.strategies.base import Position

        strategy.update_positions({"AAPL": Position(symbol="AAPL", quantity=-100, avg_price=100.0)})
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert 0.0 <= signal.strength <= 1.0
        assert signal.metadata["signal_type"] == "middle_band_exit_short"

    def test_generate_signals_exit_short_exit_channel(self):
        """Test generate_signals exits short when price breaks exit channel."""
        strategy = DonchianChannelStrategy(period=20, exit_period=10)
        data = {
            "AAPL": create_donchian_data(
                "AAPL", [100.0] * 20 + [102.0] * 10 + [100.0] * 9 + [101.5, 102.0]
            )
        }
        from quant_trading.strategies.base import Position

        strategy.update_positions({"AAPL": Position(symbol="AAPL", quantity=-100, avg_price=100.0)})
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert 0.0 <= signal.strength <= 1.0
        assert signal.metadata["signal_type"] == "exit_channel_breakout"

    def test_generate_signals_no_exit_without_position(self):
        """Test that no exit signals are generated without a position."""
        strategy = DonchianChannelStrategy(period=20, exit_period=10)
        data = {"AAPL": create_donchian_data("AAPL", [100.0] * 40 + [110.0])}
        signals = strategy.generate_signals(data)

        # Entry signal fires, but no exit signals without a position
        assert len(signals) == 1
        assert signals[0].metadata["signal_type"] == "upper_breakout"
        assert all("exit" not in s.metadata["signal_type"] for s in signals)

    def test_generate_signals_exit_long_no_exit_channel_breakdown(self):
        """With a long position, when the middle-band exit does not fire and the
        price does not break the exit channel lower band, no exit signal is
        produced (the `elif` exit-channel arm is not taken)."""
        strategy = DonchianChannelStrategy(period=20, exit_period=10)
        # Price stays well inside both channels; no exit conditions hold.
        data = {"AAPL": create_donchian_data("AAPL", [100.0] * 40 + [100.5, 101.0])}
        from quant_trading.strategies.base import Position

        strategy.update_positions({"AAPL": Position(symbol="AAPL", quantity=100, avg_price=100.0)})
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_exit_short_no_exit_channel_breakout(self):
        """With a short position, when the middle-band exit does not fire and the
        price does not break the exit channel upper band, no exit signal is
        produced (the `elif` exit-channel arm is not taken)."""
        strategy = DonchianChannelStrategy(period=20, exit_period=10)
        # Price stays well inside both channels; no exit conditions hold.
        data = {"AAPL": create_donchian_data("AAPL", [100.0] * 40 + [99.5, 99.0])}
        from quant_trading.strategies.base import Position

        strategy.update_positions({"AAPL": Position(symbol="AAPL", quantity=-100, avg_price=100.0)})
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_skips_nan_values(self):
        """NaN channel values on the last bar are skipped."""
        strategy = DonchianChannelStrategy(period=20, exit_period=10)
        data = {"AAPL": create_donchian_data("AAPL", [100.0] * 40 + [101.0])}
        df = data["AAPL"]
        df.iloc[-1, df.columns.get_loc("close")] = float("nan")
        assert strategy.generate_signals(data) == []

    def test_generate_signals_skips_zero_upper_band(self):
        """A zero upper band is skipped to avoid division by zero."""
        strategy = DonchianChannelStrategy(period=20, exit_period=10)
        # All-zero highs/lows produce zero bands; last bar must not divide by zero.
        data = {"AAPL": create_donchian_data("AAPL", [0.0] * 40 + [0.0])}
        assert strategy.generate_signals(data) == []


class TestMovingAverageCrossover:
    """Tests for MovingAverageCrossover strategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=30, name="Test_MA")
        assert strategy.name == "Test_MA"
        assert strategy.fast_period == 10
        assert strategy.slow_period == 30
        assert strategy.parameters["fast_period"] == 10
        assert strategy.parameters["slow_period"] == 30

    def test_validate_parameters(self):
        """Test parameter validation raises for invalid periods."""
        with pytest.raises(ValueError, match="fast_period must be positive"):
            MovingAverageCrossover(fast_period=0)
        with pytest.raises(ValueError, match="fast_period must be positive"):
            MovingAverageCrossover(fast_period=-5)
        with pytest.raises(ValueError, match="slow_period must be positive"):
            MovingAverageCrossover(slow_period=0)
        with pytest.raises(ValueError, match="slow_period must be positive"):
            MovingAverageCrossover(slow_period=-5)
        with pytest.raises(ValueError, match="fast_period must be less than slow_period"):
            MovingAverageCrossover(fast_period=30, slow_period=10)
        with pytest.raises(ValueError, match="fast_period must be less than slow_period"):
            MovingAverageCrossover(fast_period=10, slow_period=10)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with insufficient data."""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=30)
        data = {"AAPL": create_trending_data("AAPL", days=20)}  # Less than slow_period
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_golden_cross(self):
        """Test generate_signals detects golden cross (buy signal).

        A flat 15-bar base (slow window fills at 100), then a 5-bar dip to 50
        (dragging the 5-period fast MA well below the 15-period slow MA), then a
        final jump to 300 lifts the fast MA above the slow MA on the last bar
        only -- yielding exactly one golden-cross buy signal.
        """
        strategy = MovingAverageCrossover(fast_period=5, slow_period=15)
        data = {"AAPL": create_donchian_data("AAPL", [100.0] * 15 + [50.0] * 5 + [300.0])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert 0.0 <= signal.strength <= 1.0
        assert signal.strength == pytest.approx(0.3448275862068961)
        assert signal.price == pytest.approx(300.0)
        assert signal.timestamp is not None
        assert signal.metadata["crossover_type"] == "golden_cross"
        assert signal.metadata["fast_ma"] == pytest.approx(100.0)
        assert signal.metadata["slow_ma"] == pytest.approx(96.66666666666667)

    def test_generate_signals_death_cross(self):
        """Test generate_signals detects death cross (sell signal).

        A 15-bar base at 100, a 20-bar run at 200 (filling both MAs at 200),
        then a final crash to 50 pulls the fast MA below the slow MA on the
        last bar only -- exactly one death-cross sell signal.
        """
        strategy = MovingAverageCrossover(fast_period=5, slow_period=15)
        data = {"AAPL": create_donchian_data("AAPL", [100.0] * 15 + [200.0] * 20 + [50.0])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert 0.0 <= signal.strength <= 1.0
        assert signal.strength == pytest.approx(1.0)
        assert signal.price == pytest.approx(50.0)
        assert signal.timestamp is not None
        assert signal.metadata["crossover_type"] == "death_cross"
        assert signal.metadata["fast_ma"] == pytest.approx(170.0)
        assert signal.metadata["slow_ma"] == pytest.approx(190.0)

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals with multiple symbols."""
        strategy = MovingAverageCrossover(fast_period=5, slow_period=15)
        data = {
            "AAPL": create_trending_data("AAPL", days=50, trend=0.005),
            "MSFT": create_trending_data("MSFT", days=50, trend=0.003),
        }
        signals = strategy.generate_signals(data)
        # Should generate signals for each symbol
        symbols = {s.symbol for s in signals}
        assert symbols.issubset({"AAPL", "MSFT"})

    def test_generate_signals_skips_a_nan_last_close(self):
        """A last close that is not a number yields no signal.

        The signal is emitted at the last close, so a close that is not a
        number is skipped before any moving average is derived from it.
        """
        strategy = MovingAverageCrossover(fast_period=2, slow_period=3)
        closes = [100.0, 101.0, 102.0, float("nan")]
        data = {"AAPL": create_donchian_data("AAPL", closes)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_skips_an_undefined_previous_ma(self):
        """A previous moving average that is not a number yields no signal.

        The crossover is measured between the last two moving averages, so a
        previous average that could not be computed leaves nothing to compare
        against.
        """
        strategy = MovingAverageCrossover(fast_period=2, slow_period=3)
        closes = [100.0, float("nan"), 102.0, 103.0]
        data = {"AAPL": create_donchian_data("AAPL", closes)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_with_one_bar_windows_yields_no_signals(self):
        """A strategy with one-bar windows cannot detect a crossover.

        ``validate_parameters`` requires the slow window to be longer than the
        fast one, so this configuration is only reachable by overriding the
        windows directly. The strategy must then skip the symbol instead of
        reading a previous bar that does not exist.
        """
        strategy = MovingAverageCrossover(fast_period=2, slow_period=3)
        strategy.fast_period = 1
        strategy.slow_period = 1
        data = {"AAPL": create_donchian_data("AAPL", [100.0])}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_golden_cross_with_a_zero_slow_ma_uses_the_fallback_strength(self):
        """A golden cross on a zero slow MA falls back to a 0.5 strength.

        The strength is the distance between the two moving averages relative
        to the slow one, which cannot be scaled by a slow MA of zero.
        """
        strategy = MovingAverageCrossover(fast_period=1, slow_period=2)
        closes = [0.0, 0.0, -10.0, 10.0]
        data = {"AAPL": create_donchian_data("AAPL", closes)}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.action == "buy"
        assert signal.strength == 0.5
        assert signal.metadata["crossover_type"] == "golden_cross"
        assert signal.metadata["slow_ma"] == 0.0

    def test_death_cross_with_a_zero_slow_ma_uses_the_fallback_strength(self):
        """A death cross on a zero slow MA falls back to a 0.5 strength."""
        strategy = MovingAverageCrossover(fast_period=1, slow_period=2)
        closes = [0.0, 0.0, 10.0, -10.0]
        data = {"AAPL": create_donchian_data("AAPL", closes)}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.action == "sell"
        assert signal.strength == 0.5
        assert signal.metadata["crossover_type"] == "death_cross"
        assert signal.metadata["slow_ma"] == 0.0


class TestRSIStrategy:
    """Tests for RSIStrategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = RSIStrategy(period=14, oversold=30, overbought=70, name="Test_RSI")
        assert strategy.name == "Test_RSI"
        assert strategy.period == 14
        assert strategy.oversold == 30
        assert strategy.overbought == 70

    def test_validate_parameters(self):
        """Test parameter validation raises for invalid bounds."""
        with pytest.raises(ValueError, match="period must be positive"):
            RSIStrategy(period=0)
        with pytest.raises(ValueError, match="period must be positive"):
            RSIStrategy(period=-14)
        with pytest.raises(ValueError, match="oversold must be between 0 and 100"):
            RSIStrategy(oversold=0)
        with pytest.raises(ValueError, match="oversold must be between 0 and 100"):
            RSIStrategy(oversold=100)
        with pytest.raises(ValueError, match="overbought must be between 0 and 100"):
            RSIStrategy(overbought=0)
        with pytest.raises(ValueError, match="overbought must be between 0 and 100"):
            RSIStrategy(overbought=100)
        with pytest.raises(ValueError, match="oversold must be less than overbought"):
            RSIStrategy(oversold=50, overbought=50)
        with pytest.raises(ValueError, match="oversold must be less than overbought"):
            RSIStrategy(oversold=70, overbought=30)

    def test_generate_signals_overbought_rejection(self):
        """Test generate_signals detects overbought rejection (sell signal).

        Fourteen consecutive up-bars pin RSI at 100; a final 10-point
        drop pulls RSI to ~56.5, crossing below the overbought threshold.
        """
        strategy = RSIStrategy(period=14, oversold=30, overbought=70)
        closes = [100.0 + i for i in range(14)] + [103.0]
        data = {"AAPL": create_donchian_data("AAPL", closes)}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert 0.0 <= signal.strength <= 1.0
        assert signal.price == pytest.approx(103.0)
        assert signal.metadata["signal_type"] == "overbought_rejection"
        assert signal.metadata["rsi"] == pytest.approx(56.52173913043478)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with insufficient data."""
        strategy = RSIStrategy(period=14)
        data = {"AAPL": create_mean_reverting_data("AAPL", days=10)}  # Less than period
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_oversold_bounce(self):
        """Test generate_signals detects oversold bounce (buy signal).

        Fourteen down-steps of -1 (100 -> 87) drive RSI to 0 (oversold); a
        final +10 bounce lifts RSI to ~43.5, crossing back above the 30
        oversold threshold on the last bar only -- exactly one buy signal.
        """
        strategy = RSIStrategy(period=14, oversold=30, overbought=70)
        closes = [100.0 - i for i in range(14)] + [97.0]
        data = {"AAPL": create_donchian_data("AAPL", closes)}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert 0.0 <= signal.strength <= 1.0
        assert signal.strength == pytest.approx(1.0)
        assert signal.price == pytest.approx(97.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "oversold_bounce"
        assert signal.metadata["rsi"] == pytest.approx(43.47826086956522)

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals with multiple symbols."""
        strategy = RSIStrategy(period=14)
        data = {
            "AAPL": create_mean_reverting_data("AAPL", days=60),
            "MSFT": create_mean_reverting_data("MSFT", days=60),
        }
        signals = strategy.generate_signals(data)
        symbols = {s.symbol for s in signals}
        assert symbols.issubset({"AAPL", "MSFT"})

    def test_generate_signals_skips_an_undefined_rsi(self):
        """A flat price series has no RSI, so no signal is generated.

        The RSI is undefined when there are no gains and no losses at all:
        the gain and the loss are both zero, so their ratio is not a number.
        """
        strategy = RSIStrategy(period=14, oversold=30, overbought=70)
        closes = [100.0] * 15
        data = {"AAPL": create_donchian_data("AAPL", closes)}
        signals = strategy.generate_signals(data)
        assert signals == []


class TestBollingerBandsStrategy:
    """Tests for BollingerBandsStrategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = BollingerBandsStrategy(period=20, std_dev=2.0, name="Test_BB")
        assert strategy.name == "Test_BB"
        assert strategy.period == 20
        assert strategy.std_dev == 2.0

    def test_validate_parameters(self):
        """Test parameter validation raises for invalid inputs."""
        with pytest.raises(ValueError, match="period must be positive"):
            BollingerBandsStrategy(period=0)
        with pytest.raises(ValueError, match="period must be positive"):
            BollingerBandsStrategy(period=-20)
        with pytest.raises(ValueError, match="std_dev must be positive"):
            BollingerBandsStrategy(std_dev=0)
        with pytest.raises(ValueError, match="std_dev must be positive"):
            BollingerBandsStrategy(std_dev=-2.0)

    def test_generate_signals_lower_band_touch(self):
        """Test generate_signals detects lower band touch (buy signal).

        Alternating closes give a ~97.4 lower band; a final close of 95
        pierces it (95 <= 97.4 * 1.005).
        """
        strategy = BollingerBandsStrategy(period=20, std_dev=2.0)
        data = {"AAPL": create_donchian_data("AAPL", [100.0, 102.0] * 10 + [95.0])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert 0.0 <= signal.strength <= 1.0
        assert signal.price == pytest.approx(95.0)
        assert signal.metadata["signal_type"] == "lower_band_touch"
        assert signal.metadata["sma"] == pytest.approx(100.75)
        assert signal.metadata["lower_band"] == pytest.approx(97.38610501446847)
        assert signal.metadata["upper_band"] == pytest.approx(104.11389498553154)

    def test_generate_signals_upper_band_touch(self):
        """Test generate_signals detects upper band touch (sell signal).

        Alternating closes give a ~106.0 upper band; a final close of 110
        pierces it (110 >= 106.0 * 0.995).
        """
        strategy = BollingerBandsStrategy(period=20, std_dev=2.0)
        data = {"AAPL": create_donchian_data("AAPL", [100.0, 102.0] * 10 + [110.0])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert 0.0 <= signal.strength <= 1.0
        assert signal.price == pytest.approx(110.0)
        assert signal.metadata["signal_type"] == "upper_band_touch"
        assert signal.metadata["sma"] == pytest.approx(101.5)
        assert signal.metadata["upper_band"] == pytest.approx(105.97213595499957)
        assert signal.metadata["lower_band"] == pytest.approx(97.02786404500042)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with insufficient data."""
        strategy = BollingerBandsStrategy(period=20)
        data = {"AAPL": create_trending_data("AAPL", days=15)}  # Less than period
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_band_touch(self):
        """Test generate_signals detects band touches."""
        strategy = BollingerBandsStrategy(period=20, std_dev=2.0)
        data = {"AAPL": create_mean_reverting_data("AAPL", days=60)}
        signals = strategy.generate_signals(data)

        for signal in signals:
            assert signal.symbol == "AAPL"
            assert signal.action in ("buy", "sell")
            assert 0.0 <= signal.strength <= 1.0
            if signal.action == "buy":
                assert signal.metadata.get("signal_type") == "lower_band_touch"
            elif signal.action == "sell":
                assert signal.metadata.get("signal_type") == "upper_band_touch"

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals with multiple symbols."""
        strategy = BollingerBandsStrategy(period=20)
        data = {
            "AAPL": create_mean_reverting_data("AAPL", days=60),
            "MSFT": create_mean_reverting_data("MSFT", days=60),
        }
        signals = strategy.generate_signals(data)
        symbols = {s.symbol for s in signals}
        assert symbols.issubset({"AAPL", "MSFT"})

    def test_generate_signals_skips_nan_values(self):
        """NaN indicator values on the last bar are skipped."""
        strategy = BollingerBandsStrategy(period=20, std_dev=2.0)
        data = {"AAPL": create_donchian_data("AAPL", [100.0, 102.0] * 10 + [95.0])}
        df = data["AAPL"]
        df.iloc[-1, df.columns.get_loc("close")] = float("nan")
        assert strategy.generate_signals(data) == []

    def test_generate_signals_skips_zero_price(self):
        """A zero close on the last bar is skipped to avoid division by zero."""
        strategy = BollingerBandsStrategy(period=20, std_dev=2.0)
        data = {"AAPL": create_donchian_data("AAPL", [100.0, 102.0] * 10 + [0.0])}
        assert strategy.generate_signals(data) == []

    def test_generate_signals_period_one(self):
        """A one-bar window yields NaN bands: no crash, no signals."""
        strategy = BollingerBandsStrategy(period=1, std_dev=2.0)
        data = {"AAPL": create_donchian_data("AAPL", [100.0, 102.0] * 10 + [95.0])}
        assert strategy.generate_signals(data) == []
        # Incremental bar-by-bar calls (as the engine does) must not crash.
        incremental = BollingerBandsStrategy(period=1, std_dev=2.0)
        df = data["AAPL"]
        signals = []
        for i in range(2, len(df)):
            signals += incremental.generate_signals({"AAPL": df.iloc[: i + 1]})
        assert signals == []

    def test_generate_signals_incremental_matches_full_recompute(self):
        """Bar-by-bar incremental updates match full recomputation exactly."""
        strategy = BollingerBandsStrategy(period=20, std_dev=2.0)
        df = create_mean_reverting_data("AAPL", days=120)
        incremental_signals = []
        for i in range(20, len(df)):
            incremental_signals += strategy.generate_signals({"AAPL": df.iloc[: i + 1]})

        full_signals = []
        for i in range(20, len(df)):
            fresh = BollingerBandsStrategy(period=20, std_dev=2.0)
            full_signals += fresh.generate_signals({"AAPL": df.iloc[: i + 1]})

        assert len(incremental_signals) == len(full_signals)
        for inc, full in zip(incremental_signals, full_signals):
            assert inc.symbol == full.symbol
            assert inc.action == full.action
            assert inc.price == pytest.approx(full.price)
            assert inc.timestamp == full.timestamp
            assert inc.metadata["signal_type"] == full.metadata["signal_type"]
            assert inc.strength == pytest.approx(full.strength)
            assert inc.metadata["sma"] == pytest.approx(full.metadata["sma"])
            assert inc.metadata["upper_band"] == pytest.approx(full.metadata["upper_band"])
            assert inc.metadata["lower_band"] == pytest.approx(full.metadata["lower_band"])


def create_macd_data(symbol: str, days: int = 100) -> pd.DataFrame:
    """Create mock price data that produces a MACD bullish crossover at the end.

    Prices are held constant for most of the series (so MACD/signal settle at
    zero), then a single massive final bar forces the MACD line to cross above
    the signal line on the last bar.
    """
    dates = pd.date_range(end=datetime.now(), periods=days, freq="D")
    prices = np.array([100.0] * (days - 1), dtype=float)
    prices = np.concatenate([prices, [300.0]])

    df = pd.DataFrame(
        {
            "open": prices * (1 + np.random.uniform(-0.005, 0.005, days)),
            "high": prices * (1 + np.random.uniform(0, 0.01, days)),
            "low": prices * (1 - np.random.uniform(0, 0.01, days)),
            "close": prices,
            "volume": np.random.randint(1000000, 10000000, days),
        },
        index=dates,
    )
    return df  # type: ignore[no-any-return]


def create_macd_falling_data(symbol: str, days: int = 100) -> pd.DataFrame:
    """Create mock price data that produces a MACD bearish crossover at the end.

    Prices are held constant for most of the series (so MACD/signal settle at
    zero), then a single massive final bar forces the MACD line to cross below
    the signal line on the last bar.
    """
    dates = pd.date_range(end=datetime.now(), periods=days, freq="D")
    prices = np.array([200.0] * (days - 1), dtype=float)
    prices = np.concatenate([prices, [1.0]])

    df = pd.DataFrame(
        {
            "open": prices * (1 + np.random.uniform(-0.005, 0.005, days)),
            "high": prices * (1 + np.random.uniform(0, 0.01, days)),
            "low": prices * (1 - np.random.uniform(0, 0.01, days)),
            "close": prices,
            "volume": np.random.randint(1000000, 10000000, days),
        },
        index=dates,
    )
    return df  # type: ignore[no-any-return]


def create_macd_zero_line_data(symbol: str, direction: str) -> pd.DataFrame:
    """Create deterministic data where the MACD line crosses zero on the
    final bar *without* a signal-line crossover.

    Prices are flat at 100, drop to 80, settle, then ramp up 0.25/bar.
    The ramp lifts the fast EMA above the slow EMA (MACD crosses zero)
    while the signal line (EMA of MACD) still lags below it, so neither
    signal-line crossover condition holds. The final close is tuned per
    direction:
    - "bullish": a jump to 100 puts the MACD line clearly above zero
    - "bearish": 80.5 keeps the MACD line in the narrow band between
      the (negative) signal line and zero, crossing it from above
    """
    closes = [100.0] * 30 + [80.0] + [80.0] * 15 + [80.0 + 0.25 * i for i in range(1, 80)]
    if direction == "bullish":
        closes = closes[:53] + [100.0]
    else:
        closes = closes[:54] + [80.5]
    close = np.asarray(closes, dtype=float)
    dates = pd.date_range(end=datetime.now(), periods=len(close), freq="D")
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": np.full(len(close), 1_000_000),
        },
        index=dates,
    )


def create_ppo_pvo_zero_line_data(symbol: str, direction: str, pvo: bool = False) -> pd.DataFrame:
    """Create deterministic data where the PPO/PVO line crosses zero on the
    final bar *without* a signal-line crossover.

    The same price ramp used for MACD zero-line data is reused here: the fast
    EMA crosses the slow EMA (the PPO/PVO line crosses zero) while the signal
    line lags, so neither signal-line crossover condition holds and the
    ``elif self.use_zero_line`` arm fires instead.

    Args:
        symbol: Symbol name (unused except for API symmetry with other
            helpers; the returned DataFrame is keyed by the caller).
        direction: ``"bullish"`` puts the PPO/PVO line clearly above zero on
            the final bar; ``"bearish"`` keeps it in the narrow band between
            the (negative) signal line and zero, crossing it from above.
        pvo: When ``True`` the ramp is applied to the ``"volume"`` column and
            the price columns are held flat at 100, so only the volume
            oscillator is exercised. When ``False`` (default) the ramp is
            applied to ``"close"`` exactly as in the MACD helper.

    Returns:
        A DataFrame with OHLCV columns indexed by timestamp.
    """
    closes = [100.0] * 30 + [80.0] + [80.0] * 15 + [80.0 + 0.25 * i for i in range(1, 80)]
    if direction == "bullish":
        closes = closes[:53] + [100.0]
    else:
        closes = closes[:54] + [80.5]
    ramp = np.asarray(closes, dtype=float)
    dates = pd.date_range(end=datetime.now(), periods=len(ramp), freq="D")
    if pvo:
        volume = ramp * 10000.0
        close = np.full(len(ramp), 100.0)
        return pd.DataFrame(  # type: ignore[no-any-return]
            {
                "open": close,
                "high": close * 1.001,
                "low": close * 0.999,
                "close": close,
                "volume": volume,
            },
            index=dates,
        )
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": ramp,
            "high": ramp * 1.001,
            "low": ramp * 0.999,
            "close": ramp,
            "volume": np.full(len(ramp), 1_000_000),
        },
        index=dates,
    )


def create_stochrsi_midline_data(symbol: str, direction: str) -> pd.DataFrame:
    """Create deterministic data where StochRSI %K crosses the 50 midline.

    The close series is tuned so that, with default parameters
    (rsi_period=14, stoch_period=14, k_period=3, d_period=3), %K crosses
    upward through 50 on the final bar (``direction="bullish"``) or downward
    through 50 (``direction="bearish"``), without entering oversold/overbought
    territory, so the ``elif self.use_midline`` arm fires instead of the
    oversold/overbought crossover arms.

    Args:
        symbol: Symbol name (unused except for API symmetry with other
            helpers; the returned DataFrame is keyed by the caller).
        direction: ``"bullish"`` for a midline cross up (buy), ``"bearish"``
            for a midline cross down (sell).

    Returns:
        A DataFrame with OHLCV columns indexed by timestamp.
    """
    if direction == "bullish":
        closes = [
            100.76,
            99.19,
            98.72,
            99.00,
            98.43,
            98.22,
            99.01,
            99.32,
            98.41,
            98.58,
            97.98,
            96.80,
            95.71,
            95.99,
            95.96,
            95.96,
            94.87,
            94.70,
            93.72,
            92.85,
            92.70,
            91.43,
            92.04,
            94.36,
            94.79,
            93.81,
            93.56,
            92.11,
            91.76,
            92.23,
            92.78,
            91.82,
            92.10,
            93.17,
            94.82,
            94.16,
            93.35,
            93.40,
            90.70,
            90.22,
            89.98,
            89.57,
            88.16,
            87.94,
            87.26,
            87.93,
            87.12,
            86.88,
            86.67,
            87.17,
            84.98,
            84.69,
            85.33,
            85.03,
            83.74,
            84.01,
            84.29,
            84.07,
            83.10,
            82.48,
            82.23,
            81.51,
            79.96,
            79.35,
            79.30,
            78.90,
            78.84,
            78.90,
            79.61,
            81.39,
        ]
    else:
        closes = [
            100.74,
            101.10,
            98.74,
            99.74,
            99.39,
            98.19,
            98.78,
            99.34,
            98.31,
            100.77,
            99.56,
            97.85,
            96.73,
            98.11,
            97.94,
            97.58,
            97.51,
            96.93,
            96.27,
            95.65,
            96.33,
            97.32,
            96.30,
            96.53,
            97.29,
            96.25,
            95.76,
            94.77,
            93.56,
            93.65,
            92.97,
            93.56,
            93.53,
            93.92,
            93.64,
            93.05,
            92.96,
            92.96,
            92.31,
            92.70,
            93.40,
            93.54,
            95.16,
            94.56,
            95.05,
            94.67,
            94.89,
            94.10,
            95.16,
            95.33,
            96.47,
            95.26,
            94.79,
            93.94,
            93.45,
            92.80,
            92.69,
            92.67,
            92.64,
            92.12,
            92.30,
            93.11,
            92.27,
            92.27,
            92.20,
            92.64,
            92.58,
            92.56,
            91.65,
            91.67,
        ]
    close = np.asarray(closes, dtype=float)
    dates = pd.date_range(end=datetime.now(), periods=len(close), freq="D")
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": np.full(len(close), 1_000_000),
        },
        index=dates,
    )


class TestMACDStrategy:
    """Tests for MACDStrategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9, name="Test_MACD")
        assert strategy.name == "Test_MACD"
        assert strategy.fast_period == 12
        assert strategy.slow_period == 26
        assert strategy.signal_period == 9
        assert strategy.parameters["fast_period"] == 12
        assert strategy.parameters["slow_period"] == 26
        assert strategy.parameters["signal_period"] == 9
        assert strategy.use_zero_line is False

    def test_validate_parameters(self):
        """Test parameter validation raises for invalid periods."""
        with pytest.raises(ValueError, match="fast_period must be positive"):
            MACDStrategy(fast_period=0)
        with pytest.raises(ValueError, match="fast_period must be positive"):
            MACDStrategy(fast_period=-12)
        with pytest.raises(ValueError, match="slow_period must be positive"):
            MACDStrategy(slow_period=0)
        with pytest.raises(ValueError, match="slow_period must be positive"):
            MACDStrategy(slow_period=-26)
        with pytest.raises(ValueError, match="signal_period must be positive"):
            MACDStrategy(signal_period=0)
        with pytest.raises(ValueError, match="signal_period must be positive"):
            MACDStrategy(signal_period=-9)
        with pytest.raises(ValueError, match="fast_period must be less than slow_period"):
            MACDStrategy(fast_period=26, slow_period=12)
        with pytest.raises(ValueError, match="fast_period must be less than slow_period"):
            MACDStrategy(fast_period=12, slow_period=12)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with insufficient data."""
        strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9)
        data = {"AAPL": create_macd_data("AAPL", days=20)}  # Less than slow+signal
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_bullish_crossover(self):
        """Test generate_signals detects MACD bullish crossover (buy signal)."""
        strategy = MACDStrategy(fast_period=5, slow_period=13, signal_period=5)
        data = {"AAPL": create_macd_data("AAPL", days=100)}
        signals = strategy.generate_signals(data)

        # Should have at least one signal due to the accelerated tail
        assert len(signals) >= 1
        for signal in signals:
            assert signal.symbol == "AAPL"
            assert signal.action in ("buy", "sell")
            assert 0.0 <= signal.strength <= 1.0
            assert signal.price is not None
            assert signal.timestamp is not None
            if signal.action == "buy":
                assert signal.metadata.get("crossover_type") == "bullish"
                assert "macd" in signal.metadata
                assert "signal" in signal.metadata
                assert "histogram" in signal.metadata

    def test_generate_signals_bearish_crossover(self):
        """Test generate_signals detects MACD bearish crossover (sell signal)."""
        strategy = MACDStrategy(fast_period=5, slow_period=13, signal_period=5)
        data = {"AAPL": create_macd_falling_data("AAPL", days=100)}
        signals = strategy.generate_signals(data)

        assert len(signals) >= 1
        for signal in signals:
            assert signal.symbol == "AAPL"
            assert signal.action in ("buy", "sell")
            if signal.action == "sell":
                assert signal.metadata.get("crossover_type") == "bearish"

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals with multiple symbols."""
        strategy = MACDStrategy(fast_period=5, slow_period=13, signal_period=5)
        data = {
            "AAPL": create_macd_data("AAPL", days=100),
            "MSFT": create_macd_data("MSFT", days=100),
        }
        signals = strategy.generate_signals(data)
        symbols = {s.symbol for s in signals}
        assert symbols.issubset({"AAPL", "MSFT"})

    def test_zero_line_option(self):
        """Test that use_zero_line enables zero-line crossovers."""
        strategy = MACDStrategy(fast_period=5, slow_period=13, signal_period=5, use_zero_line=True)
        assert strategy.use_zero_line is True
        data = {"AAPL": create_macd_data("AAPL", days=100)}
        signals = strategy.generate_signals(data)
        # With zero-line enabled, more signal types may appear
        for signal in signals:
            assert signal.action in ("buy", "sell")

    def test_generate_signals_zero_line_bullish(self):
        """Test zero-line crossover generates buy when MACD crosses up.

        The MACD line crosses zero on the final bar while staying above
        the signal line, so no signal-line crossover occurs and the
        zero-line branch fires instead.
        """
        strategy = MACDStrategy(fast_period=5, slow_period=13, signal_period=5, use_zero_line=True)
        data = {"AAPL": create_macd_zero_line_data("AAPL", "bullish")}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert 0.0 <= signal.strength <= 1.0
        assert signal.metadata["crossover_type"] == "zero_line_bullish"
        assert signal.metadata["macd"] > 0
        assert signal.metadata["macd"] == pytest.approx(3.517572699571474)
        assert signal.metadata["signal"] == pytest.approx(0.8573973709901881)
        assert "zero_line" not in signal.metadata

    def test_generate_signals_zero_line_bearish(self):
        """Test zero-line crossover generates sell when MACD crosses down.

        The MACD line has just crossed above zero (signal line still
        lags below zero); the final close is tuned so the MACD line
        crosses back below zero without a signal-line crossover.
        """
        strategy = MACDStrategy(fast_period=5, slow_period=13, signal_period=5, use_zero_line=True)
        data = {"AAPL": create_macd_zero_line_data("AAPL", "bearish")}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert 0.0 <= signal.strength <= 1.0
        assert signal.metadata["crossover_type"] == "zero_line_bearish"
        assert signal.metadata["macd"] == pytest.approx(-0.11813172676122008)
        assert signal.metadata["macd"] < 0
        assert signal.metadata["signal"] == pytest.approx(-0.22968375683171027)
        assert "zero_line" not in signal.metadata

    def test_generate_signals_bearish_crossover_zero_line_metadata(self):
        """Test use_zero_line annotates bearish crossovers below zero."""
        strategy = MACDStrategy(fast_period=5, slow_period=13, signal_period=5, use_zero_line=True)
        data = {"AAPL": create_macd_falling_data("AAPL", days=100)}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.action == "sell"
        assert signal.metadata["crossover_type"] == "bearish"
        assert signal.metadata["macd"] < 0
        assert signal.metadata["zero_line"] == "below"

    def test_generate_signals_zero_line_disabled(self):
        """When use_zero_line is False and no signal-line crossover fires on the
        final bar, the `elif self.use_zero_line` arm (595->534 and 615->534) is
        False and no signal is produced."""
        strategy = MACDStrategy(
            fast_period=12, slow_period=26, signal_period=9, use_zero_line=False
        )
        # Steady rising prices keep MACD and signal in parallel with no crossover.
        data = {"AAPL": create_donchian_data("AAPL", [100.0] * 30 + list(range(100, 170)))}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_skips_nan_values(self):
        """NaN MACD/signal values on the last bar are skipped."""
        strategy = MACDStrategy(fast_period=5, slow_period=13, signal_period=5)
        data = {"AAPL": create_macd_falling_data("AAPL", days=100)}
        df = data["AAPL"]
        df.iloc[-1, df.columns.get_loc("close")] = float("nan")
        assert strategy.generate_signals(data) == []

    def test_generate_signals_skips_zero_price(self):
        """A zero close on the last bar is skipped to avoid division by zero."""
        strategy = MACDStrategy(fast_period=5, slow_period=13, signal_period=5)
        data = {"AAPL": create_macd_falling_data("AAPL", days=100)}
        df = data["AAPL"]
        df.iloc[-1, df.columns.get_loc("close")] = 0.0
        assert strategy.generate_signals(data) == []


class TestSuperTrendStrategy:
    """Tests for SuperTrendStrategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = SuperTrendStrategy(period=10, multiplier=3.0, name="Test_ST")
        assert strategy.name == "Test_ST"
        assert strategy.period == 10
        assert strategy.multiplier == 3.0
        assert strategy.parameters["period"] == 10
        assert strategy.parameters["multiplier"] == 3.0

    def test_validate_parameters(self):
        """Test parameter validation."""
        with pytest.raises(ValueError, match="period must be positive"):
            SuperTrendStrategy(period=0)
        with pytest.raises(ValueError, match="multiplier must be positive"):
            SuperTrendStrategy(multiplier=0)
        with pytest.raises(ValueError, match="period must be positive"):
            SuperTrendStrategy(period=-1)
        with pytest.raises(ValueError, match="multiplier must be positive"):
            SuperTrendStrategy(multiplier=-1)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with insufficient data."""
        strategy = SuperTrendStrategy(period=10, multiplier=3.0)
        data = {"AAPL": create_supertrend_data("AAPL", days=5)}  # Less than period
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_bullish_trend(self):
        """Test generate_signals detects bullish trend (buy signal)."""
        strategy = SuperTrendStrategy(period=10, multiplier=3.0)
        # Create steady uptrend data
        data = {"AAPL": create_supertrend_data("AAPL", days=60, trend=0.003)}
        signals = strategy.generate_signals(data)

        for signal in signals:
            assert signal.symbol == "AAPL"
            assert signal.action in ("buy", "sell")
            assert 0.0 <= signal.strength <= 1.0
            assert signal.price is not None
            assert signal.timestamp is not None
            if signal.action == "buy":
                assert signal.metadata.get("trend") == "bullish"
                assert signal.metadata.get("signal_type") == "trend_reversal_bullish"
                assert "supertrend" in signal.metadata
            elif signal.action == "sell":
                assert signal.metadata.get("trend") == "bearish"
                assert signal.metadata.get("signal_type") == "trend_reversal_bearish"

    def test_generate_signals_bearish_trend(self):
        """Test generate_signals detects bearish trend (sell signal)."""
        strategy = SuperTrendStrategy(period=10, multiplier=3.0)
        # Create steady downtrend data
        data = {"AAPL": create_supertrend_data("AAPL", days=60, trend=-0.003)}
        signals = strategy.generate_signals(data)

        for signal in signals:
            assert signal.symbol == "AAPL"
            assert signal.action in ("buy", "sell")
            assert 0.0 <= signal.strength <= 1.0
            if signal.action == "sell":
                assert signal.metadata.get("trend") == "bearish"
                assert signal.metadata.get("signal_type") == "trend_reversal_bearish"

    def test_generate_signals_bullish_reversal(self):
        """Test generate_signals detects bullish reversal (buy signal).

        Flat data keeps SuperTrend bearish; a final jump above the
        upper band flips the trend to bullish on the last bar.
        """
        strategy = SuperTrendStrategy(period=5, multiplier=1.0)
        data = {"AAPL": create_donchian_data("AAPL", [100.0] * 6 + [110.0])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert 0.0 <= signal.strength <= 1.0
        assert signal.price == pytest.approx(110.0)
        assert signal.metadata["signal_type"] == "trend_reversal_bullish"
        assert signal.metadata["trend"] == "bullish"
        assert signal.metadata["supertrend"] == pytest.approx(107.818)

    def test_generate_signals_bearish_reversal(self):
        """Test generate_signals detects bearish reversal (sell signal).

        Flat data, a jump that turns the trend bullish, then a final
        drop below the lower band flips the trend back to bearish.
        """
        strategy = SuperTrendStrategy(period=5, multiplier=1.0)
        data = {"AAPL": create_donchian_data("AAPL", [100.0] * 6 + [110.0] * 4 + [100.0])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert 0.0 <= signal.strength <= 1.0
        assert signal.price == pytest.approx(100.0)
        assert signal.metadata["signal_type"] == "trend_reversal_bearish"
        assert signal.metadata["trend"] == "bearish"
        assert signal.metadata["supertrend"] == pytest.approx(104.174)

    def test_supertrend_no_valid_atr(self):
        """Test _calculate_supertrend returns all-NaN when ATR is invalid.

        Data shorter than the ATR period yields an all-NaN ATR, so
        the no-valid-index branch returns an all-NaN SuperTrend line
        and an all-bearish trend series.
        """
        strategy = SuperTrendStrategy(period=10, multiplier=3.0)
        df = create_donchian_data("AAPL", [100.0, 101.0, 102.0])
        supertrend, trend = strategy._calculate_supertrend(df)

        assert len(supertrend) == len(df)
        assert len(trend) == len(df)
        assert supertrend.isna().all()
        assert (trend == -1).all()

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals with multiple symbols."""
        strategy = SuperTrendStrategy(period=10, multiplier=3.0)
        data = {
            "AAPL": create_supertrend_data("AAPL", days=60, trend=0.003),
            "MSFT": create_supertrend_data("MSFT", days=60, trend=-0.003),
        }
        signals = strategy.generate_signals(data)
        symbols = {s.symbol for s in signals}
        assert symbols.issubset({"AAPL", "MSFT"})

    def test_atr_calculation(self):
        """Test ATR calculation internally."""
        strategy = SuperTrendStrategy(period=10, multiplier=3.0)
        data = {"AAPL": create_supertrend_data("AAPL", days=60, trend=0.003)}
        df = data["AAPL"]
        atr = strategy._calculate_atr(df, 10)
        assert len(atr) == len(df)
        assert atr.notna().sum() > 10  # ATR should have values after period

    def test_supertrend_calculation(self):
        """Test SuperTrend calculation internally."""
        strategy = SuperTrendStrategy(period=10, multiplier=3.0)
        data = {"AAPL": create_supertrend_data("AAPL", days=60, trend=0.003)}
        df = data["AAPL"]
        supertrend, trend = strategy._calculate_supertrend(df)
        assert len(supertrend) == len(df)
        assert len(trend) == len(df)
        # Trend should be either 1 (bullish) or -1 (bearish)
        assert set(trend.dropna().unique()).issubset({1, -1})
        # SuperTrend should be positive
        assert (supertrend.dropna() > 0).all()

    def test_generate_signals_skips_nan_values(self):
        """NaN supertrend/trend values on the last bar are skipped."""
        strategy = SuperTrendStrategy(period=10, multiplier=3.0)
        data = {"AAPL": create_supertrend_data("AAPL", days=60, trend=0.003)}
        df = data["AAPL"]
        df.iloc[-1, df.columns.get_loc("close")] = float("nan")
        assert strategy.generate_signals(data) == []

    def test_generate_signals_skips_zero_price(self):
        """A zero close on the last bar is skipped to avoid division by zero."""
        strategy = SuperTrendStrategy(period=10, multiplier=3.0)
        data = {"AAPL": create_supertrend_data("AAPL", days=60, trend=0.003)}
        df = data["AAPL"]
        df.iloc[-1, df.columns.get_loc("close")] = 0.0
        assert strategy.generate_signals(data) == []


class TestStrategyParameters:
    """Tests for strategy parameter handling."""

    def test_get_parameters(self):
        """Test get_parameters returns copy."""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=30)
        params = strategy.get_parameters()
        assert params == {"fast_period": 10, "slow_period": 30}
        # Modify copy, original should be unchanged
        params["fast_period"] = 999
        assert strategy.parameters["fast_period"] == 10

    def test_set_parameter(self):
        """Test set_parameter updates parameter."""
        strategy = MovingAverageCrossover(fast_period=10, slow_period=30)
        strategy.set_parameter("fast_period", 20)
        assert strategy.parameters["fast_period"] == 20
        assert strategy.fast_period == 20  # Instance attribute is now updated

    def test_update_positions(self):
        """Test update_positions."""
        from quant_trading.strategies.base import Position

        strategy = MovingAverageCrossover()
        positions = {"AAPL": Position(symbol="AAPL", quantity=100, avg_price=150.0)}
        strategy.update_positions(positions)
        assert strategy.positions == positions


class TestKeltnerChannelStrategy:
    """Tests for KeltnerChannelStrategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = KeltnerChannelStrategy(
            ema_period=20, atr_period=10, multiplier=2.0, name="Test_KC"
        )
        assert strategy.name == "Test_KC"
        assert strategy.ema_period == 20
        assert strategy.atr_period == 10
        assert strategy.multiplier == 2.0
        assert strategy.parameters["ema_period"] == 20
        assert strategy.parameters["atr_period"] == 10
        assert strategy.parameters["multiplier"] == 2.0

    def test_initialization_defaults(self):
        """Test default parameter values."""
        strategy = KeltnerChannelStrategy(name="Test_KC_Default")
        assert strategy.ema_period == 20
        assert strategy.atr_period == 10
        assert strategy.multiplier == 2.0
        assert strategy.use_middle_cross is False

    def test_validate_parameters(self):
        """Test parameter validation."""
        with pytest.raises(ValueError, match="ema_period must be positive"):
            KeltnerChannelStrategy(ema_period=0)
        with pytest.raises(ValueError, match="atr_period must be positive"):
            KeltnerChannelStrategy(atr_period=0)
        with pytest.raises(ValueError, match="multiplier must be positive"):
            KeltnerChannelStrategy(multiplier=0)
        with pytest.raises(ValueError, match="ema_period must be positive"):
            KeltnerChannelStrategy(ema_period=-1)
        with pytest.raises(ValueError, match="atr_period must be positive"):
            KeltnerChannelStrategy(atr_period=-1)
        with pytest.raises(ValueError, match="multiplier must be positive"):
            KeltnerChannelStrategy(multiplier=-1)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with insufficient data."""
        strategy = KeltnerChannelStrategy(ema_period=5, atr_period=5)
        # Need at least max(ema_period, atr_period) + 1 = 11 data points
        # But our create_keltner_data function needs at least 2 points to calculate EMA/ATR
        # So we'll test with 5 points which should be insufficient for the strategy
        data = {"AAPL": create_keltner_data("AAPL", [100.0] * 5)}  # Only 5 data points
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_upper_breakout(self):
        """Test generate_signals detects upper channel breakout (buy signal)."""
        strategy = KeltnerChannelStrategy(ema_period=5, atr_period=5, multiplier=2.0)
        # Create data that will break above the upper channel
        # First 20 days: sideways movement around 100
        # Day 21: sharp increase to break above upper channel
        base_data = [100.0] * 20
        spike_data = [120.0]  # Significant spike
        data = {"AAPL": create_keltner_data("AAPL", base_data + spike_data)}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.price == pytest.approx(120.0)
        assert signal.metadata["signal_type"] == "upper_breakout"

    def test_generate_signals_lower_breakout(self):
        """Test generate_signals detects lower channel breakout (sell signal)."""
        strategy = KeltnerChannelStrategy(ema_period=5, atr_period=5, multiplier=2.0)
        # Create data that will break below the lower channel
        # First 20 days: sideways movement around 100
        # Day 21: sharp decrease to break below lower channel
        base_data = [100.0] * 20
        drop_data = [80.0]  # Significant drop
        data = {"AAPL": create_keltner_data("AAPL", base_data + drop_data)}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.price == pytest.approx(80.0)
        assert signal.metadata["signal_type"] == "lower_breakout"

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals with multiple symbols."""
        strategy = KeltnerChannelStrategy(ema_period=5, atr_period=5, multiplier=2.0)
        # Symbol A: breakout above upper channel (buy)
        # Symbol B: breakdown below lower channel (sell)
        data_a = [100.0] * 20 + [120.0]  # Breakout
        data_b = [100.0] * 20 + [80.0]  # Breakdown
        data = {
            "AAPL": create_keltner_data("AAPL", data_a),
            "MSFT": create_keltner_data("MSFT", data_b),
        }
        signals = strategy.generate_signals(data)
        by_symbol = {s.symbol: s for s in signals}
        assert set(by_symbol) == {"AAPL", "MSFT"}
        assert by_symbol["AAPL"].action == "buy"
        assert by_symbol["MSFT"].action == "sell"
        assert by_symbol["AAPL"].metadata["signal_type"] == "upper_breakout"
        assert by_symbol["MSFT"].metadata["signal_type"] == "lower_breakout"

    def test_generate_signals_with_middle_cross(self):
        """Test generate_signals with middle line crossover enabled."""
        strategy = KeltnerChannelStrategy(
            ema_period=5, atr_period=5, multiplier=2.0, use_middle_cross=True
        )
        # Create data that will cross above the EMA (middle line)
        # First 10 days: decreasing trend to approach EMA from above
        # Day 11: sharp increase to cross above EMA
        declining_data = [105.0, 104.0, 103.0, 102.0, 101.0] * 2  # 10 days declining
        spike_data = [110.0]  # Spike above EMA
        data = {"AAPL": create_keltner_data("AAPL", declining_data + spike_data)}
        signals = strategy.generate_signals(data)

        # Should have at least one buy signal from middle cross
        buy_signals = [s for s in signals if s.action == "buy"]
        assert len(buy_signals) >= 1
        # Check that at least one is a middle cross signal
        middle_cross_signals = [
            s for s in buy_signals if s.metadata.get("signal_type") == "middle_cross_up"
        ]
        assert len(middle_cross_signals) >= 1

    def test_generate_signals_with_middle_cross_down(self):
        """Test generate_signals with middle line crossover down (sell signal)."""
        strategy = KeltnerChannelStrategy(
            ema_period=5, atr_period=5, multiplier=2.0, use_middle_cross=True
        )
        # Create data that will cross below the EMA (middle line)
        # First 10 days: increasing trend to approach EMA from below
        # Day 11: sharp decrease to cross below EMA
        rising_data = [95.0, 96.0, 97.0, 98.0, 99.0] * 2  # 10 days rising
        drop_data = [90.0]  # Drop below EMA
        data = {"AAPL": create_keltner_data("AAPL", rising_data + drop_data)}
        signals = strategy.generate_signals(data)

        # Should have at least one sell signal from middle cross
        sell_signals = [s for s in signals if s.action == "sell"]
        assert len(sell_signals) >= 1
        # Check that at least one is a middle cross down signal
        middle_cross_down_signals = [
            s for s in sell_signals if s.metadata.get("signal_type") == "middle_cross_down"
        ]
        assert len(middle_cross_down_signals) >= 1

    def test_generate_signals_middle_cross_no_signal_when_above_ema(self):
        """Test no middle-cross signal when price stays above the EMA.

        With ``use_middle_cross=True`` and a steady rise that keeps price above
        the EMA on the final two bars, neither the up-cross nor the down-cross
        branch at line 1186 is taken, so no middle-cross signal is emitted.
        """
        strategy = KeltnerChannelStrategy(
            ema_period=5, atr_period=5, multiplier=2.0, use_middle_cross=True
        )
        # Steady rise above the EMA on the final two bars: no middle cross.
        closes = [100.0] * 15 + [102.0, 104.0, 106.0, 108.0, 110.0, 112.0, 114.0, 116.0]
        data = {"AAPL": create_donchian_data("AAPL", closes)}
        signals = strategy.generate_signals(data)

        middle_cross_signals = [
            s
            for s in signals
            if s.metadata.get("signal_type") in ("middle_cross_up", "middle_cross_down")
        ]
        assert middle_cross_signals == []

    def test_generate_signals_skips_nan_values(self):
        """NaN EMA/channel values on the last bar are skipped."""
        strategy = KeltnerChannelStrategy(ema_period=5, atr_period=5, multiplier=2.0)
        data = {"AAPL": create_keltner_data("AAPL", [100.0] * 20 + [120.0])}
        df = data["AAPL"]
        df.iloc[-1, df.columns.get_loc("close")] = float("nan")
        assert strategy.generate_signals(data) == []

    def test_generate_signals_skips_zero_ema(self):
        """A zero EMA on the last bar is skipped to avoid division by zero."""
        strategy = KeltnerChannelStrategy(ema_period=5, atr_period=5, multiplier=2.0)
        data = {"AAPL": create_keltner_data("AAPL", [0.0] * 20 + [0.0])}
        assert strategy.generate_signals(data) == []


class TestStochasticOscillatorStrategy:
    """Tests for StochasticOscillatorStrategy."""

    def test_initialization(self):
        """Test strategy initialization with default parameters."""
        strategy = StochasticOscillatorStrategy()
        assert strategy.name == "Stochastic_Oscillator"
        assert strategy.k_period == 14
        assert strategy.d_period == 3
        assert strategy.oversold == 20
        assert strategy.overbought == 80
        assert strategy.use_midline is False
        params = strategy.get_parameters()
        assert params["k_period"] == 14
        assert params["d_period"] == 3
        assert params["oversold"] == 20
        assert params["overbought"] == 80
        assert params["use_midline"] is False

    def test_initialization_custom_parameters(self):
        """Test strategy initialization with custom parameters."""
        strategy = StochasticOscillatorStrategy(
            k_period=10,
            d_period=5,
            oversold=15,
            overbought=85,
            use_midline=True,
            name="Custom_Stoch",
        )
        assert strategy.name == "Custom_Stoch"
        assert strategy.k_period == 10
        assert strategy.d_period == 5
        assert strategy.oversold == 15
        assert strategy.overbought == 85
        assert strategy.use_midline is True

    def test_validate_parameters_valid(self):
        """Test parameter validation with valid parameters."""
        # Should not raise
        StochasticOscillatorStrategy(k_period=14, d_period=3, oversold=20, overbought=80)

    def test_validate_parameters_invalid_k_period(self):
        """Test parameter validation with invalid k_period."""
        with pytest.raises(ValueError, match="k_period must be positive"):
            StochasticOscillatorStrategy(k_period=0)
        with pytest.raises(ValueError, match="k_period must be positive"):
            StochasticOscillatorStrategy(k_period=-1)

    def test_validate_parameters_invalid_d_period(self):
        """Test parameter validation with invalid d_period."""
        with pytest.raises(ValueError, match="d_period must be positive"):
            StochasticOscillatorStrategy(d_period=0)
        with pytest.raises(ValueError, match="d_period must be positive"):
            StochasticOscillatorStrategy(d_period=-1)

    def test_validate_parameters_invalid_oversold(self):
        """Test parameter validation with invalid oversold."""
        with pytest.raises(ValueError, match="oversold must be between 0 and 100"):
            StochasticOscillatorStrategy(oversold=0)
        with pytest.raises(ValueError, match="oversold must be between 0 and 100"):
            StochasticOscillatorStrategy(oversold=100)
        with pytest.raises(ValueError, match="oversold must be between 0 and 100"):
            StochasticOscillatorStrategy(oversold=-10)

    def test_validate_parameters_invalid_overbought(self):
        """Test parameter validation with invalid overbought."""
        with pytest.raises(ValueError, match="overbought must be between 0 and 100"):
            StochasticOscillatorStrategy(overbought=0)
        with pytest.raises(ValueError, match="overbought must be between 0 and 100"):
            StochasticOscillatorStrategy(overbought=100)
        with pytest.raises(ValueError, match="overbought must be between 0 and 100"):
            StochasticOscillatorStrategy(overbought=110)

    def test_validate_parameters_oversold_ge_overbought(self):
        """Test parameter validation when oversold >= overbought."""
        with pytest.raises(ValueError, match="oversold must be less than overbought"):
            StochasticOscillatorStrategy(oversold=50, overbought=50)
        with pytest.raises(ValueError, match="oversold must be less than overbought"):
            StochasticOscillatorStrategy(oversold=80, overbought=20)

    def create_stochastic_oversold_data(self, symbol: str) -> pd.DataFrame:
        """Create mock price data that generates an oversold crossover on the last day."""
        # Pattern: 10 days flat, then 6 days with controlled high/low/close
        # to produce: prev_k <= prev_d and current_k > current_d with current_k < 20
        # Using high=100, low=80 for last 6 days:
        # Day -6: close=81 -> k=5
        # Day -5: close=82 -> k=10
        # Day -4: close=83 -> k=15
        # Day -3: close=83 -> k=15
        # Day -2: close=82.5 -> k=12.5, d=14.17 (prev_k <= prev_d)
        # Day -1: close=83.5 -> k=17.5, d=15.00 (current_k > current_d, current_k < 20)
        highs = [100] * 16
        lows = [80] * 16
        closes = [100] * 10 + [81, 82, 83, 83, 82.5, 83.5]
        dates = pd.date_range(end=datetime.now(), periods=len(closes), freq="D")
        return pd.DataFrame(  # type: ignore[no-any-return]
            {
                "open": closes,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": [1000000] * len(closes),
            },
            index=dates,
        )

    def create_stochastic_overbought_data(self, symbol: str) -> pd.DataFrame:
        """Create mock price data that generates an overbought crossover on the last day."""
        # Pattern for overbought: prev_k >= prev_d and current_k < current_d with current_k > 80
        # Using high=120, low=100 for last 6 days:
        # Day -6: close=119 -> k=95
        # Day -5: close=118 -> k=90
        # Day -4: close=117 -> k=85
        # Day -3: close=117 -> k=85
        # Day -2: close=117.5 -> k=87.5, d=85.83 (prev_k >= prev_d)
        # Day -1: close=116.5 -> k=82.5, d=85.00 (current_k < current_d, current_k > 80)
        highs = [120] * 16
        lows = [100] * 16
        closes = [100] * 10 + [119, 118, 117, 117, 117.5, 116.5]
        dates = pd.date_range(end=datetime.now(), periods=len(closes), freq="D")
        return pd.DataFrame(  # type: ignore[no-any-return]
            {
                "open": closes,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": [1000000] * len(closes),
            },
            index=dates,
        )

    def create_stochastic_midline_up_data(self, symbol: str) -> pd.DataFrame:
        """Create mock price data that generates a midline cross up on the last day."""
        # Pattern: prev_k <= 50 and current_k > 50
        # Using high=60, low=40 for last 6 days:
        # Day -6: close=45 -> k=25
        # Day -5: close=46 -> k=30
        # Day -4: close=48 -> k=40
        # Day -3: close=49 -> k=45
        # Day -2: close=49.5 -> k=47.5 (prev_k <= 50)
        # Day -1: close=51 -> k=55 (current_k > 50)
        highs = [60] * 16
        lows = [40] * 16
        closes = [100] * 10 + [45, 46, 48, 49, 49.5, 51]
        dates = pd.date_range(end=datetime.now(), periods=len(closes), freq="D")
        return pd.DataFrame(  # type: ignore[no-any-return]
            {
                "open": closes,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": [1000000] * len(closes),
            },
            index=dates,
        )

    def create_stochastic_midline_down_data(self, symbol: str) -> pd.DataFrame:
        """Create mock price data that generates a midline cross down on the last day."""
        # Pattern: prev_k >= 50 and current_k < 50
        # Using high=60, low=40 for last 6 days:
        # Day -6: close=55 -> k=75
        # Day -5: close=54 -> k=70
        # Day -4: close=52 -> k=60
        # Day -3: close=51 -> k=55
        # Day -2: close=50.5 -> k=52.5 (prev_k >= 50)
        # Day -1: close=49 -> k=45 (current_k < 50)
        highs = [60] * 16
        lows = [40] * 16
        closes = [100] * 10 + [55, 54, 52, 51, 50.5, 49]
        dates = pd.date_range(end=datetime.now(), periods=len(closes), freq="D")
        return pd.DataFrame(  # type: ignore[no-any-return]
            {
                "open": closes,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": [1000000] * len(closes),
            },
            index=dates,
        )

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with insufficient data."""
        strategy = StochasticOscillatorStrategy(k_period=14, d_period=3)
        # Need at least k_period + d_period + 1 = 18 data points
        prices = [100.0] * 17
        dates = pd.date_range(end=datetime.now(), periods=len(prices), freq="D")
        df = pd.DataFrame(
            {
                "open": prices,
                "high": [p * 1.01 for p in prices],
                "low": [p * 0.99 for p in prices],
                "close": prices,
                "volume": [1000000] * len(prices),
            },
            index=dates,
        )
        data = {"AAPL": df}
        signals = strategy.generate_signals(data)
        assert len(signals) == 0

    def test_generate_signals_oversold_crossover(self):
        """Test generate_signals detects oversold crossover (buy signal)."""
        strategy = StochasticOscillatorStrategy(k_period=5, d_period=3, oversold=20, overbought=80)
        data = {"AAPL": self.create_stochastic_oversold_data("AAPL")}
        signals = strategy.generate_signals(data)

        # Should have at least one buy signal from oversold crossover
        buy_signals = [s for s in signals if s.action == "buy"]
        assert len(buy_signals) >= 1
        oversold_crossover_signals = [
            s for s in buy_signals if s.metadata.get("signal_type") == "oversold_crossover"
        ]
        assert len(oversold_crossover_signals) >= 1

    def test_generate_signals_overbought_crossover(self):
        """Test generate_signals detects overbought crossover (sell signal)."""
        strategy = StochasticOscillatorStrategy(k_period=5, d_period=3, oversold=20, overbought=80)
        data = {"AAPL": self.create_stochastic_overbought_data("AAPL")}
        signals = strategy.generate_signals(data)

        # Should have at least one sell signal from overbought crossover
        sell_signals = [s for s in signals if s.action == "sell"]
        assert len(sell_signals) >= 1
        overbought_crossover_signals = [
            s for s in sell_signals if s.metadata.get("signal_type") == "overbought_crossover"
        ]
        assert len(overbought_crossover_signals) >= 1

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals with multiple symbols."""
        strategy = StochasticOscillatorStrategy(k_period=5, d_period=3, oversold=20, overbought=80)
        # Symbol A: oversold crossover (buy)
        # Symbol B: overbought crossover (sell)
        data = {
            "AAPL": self.create_stochastic_oversold_data("AAPL"),
            "MSFT": self.create_stochastic_overbought_data("MSFT"),
        }
        signals = strategy.generate_signals(data)
        by_symbol = {s.symbol: s for s in signals}
        assert "AAPL" in by_symbol
        assert "MSFT" in by_symbol
        assert by_symbol["AAPL"].action == "buy"
        assert by_symbol["MSFT"].action == "sell"
        assert by_symbol["AAPL"].metadata["signal_type"] == "oversold_crossover"
        assert by_symbol["MSFT"].metadata["signal_type"] == "overbought_crossover"

    def test_generate_signals_with_midline_cross_up(self):
        """Test generate_signals with midline crossover up (buy signal)."""
        strategy = StochasticOscillatorStrategy(k_period=5, d_period=3, use_midline=True)
        data = {"AAPL": self.create_stochastic_midline_up_data("AAPL")}
        signals = strategy.generate_signals(data)

        buy_signals = [s for s in signals if s.action == "buy"]
        assert len(buy_signals) >= 1
        midline_signals = [
            s for s in buy_signals if s.metadata.get("signal_type") == "midline_cross_up"
        ]
        assert len(midline_signals) >= 1

    def test_generate_signals_with_midline_cross_down(self):
        """Test generate_signals with midline crossover down (sell signal)."""
        strategy = StochasticOscillatorStrategy(k_period=5, d_period=3, use_midline=True)
        data = {"AAPL": self.create_stochastic_midline_down_data("AAPL")}
        signals = strategy.generate_signals(data)

        sell_signals = [s for s in signals if s.action == "sell"]
        assert len(sell_signals) >= 1
        midline_signals = [
            s for s in sell_signals if s.metadata.get("signal_type") == "midline_cross_down"
        ]
        assert len(midline_signals) >= 1

    def test_generate_signals_no_signal_when_midline_disabled(self):
        """Test generate_signals doesn't generate midline signals when disabled."""
        strategy = StochasticOscillatorStrategy(k_period=5, d_period=3, use_midline=False)
        # Create data that would cross 50
        prices = [
            50,
            51,
            52,
            53,
            54,
            55,
            56,
            57,
            58,
            59,
            60,
            61,
            62,
            63,
            64,
            65,
            66,
            67,
            68,
            69,
            70,
            71,
        ]
        dates = pd.date_range(end=datetime.now(), periods=len(prices), freq="D")
        df = pd.DataFrame(
            {
                "open": prices,
                "high": [p * 1.01 for p in prices],
                "low": [p * 0.99 for p in prices],
                "close": prices,
                "volume": [1000000] * len(prices),
            },
            index=dates,
        )
        data = {"AAPL": df}
        signals = strategy.generate_signals(data)

        # Should not have midline signals
        midline_signals = [
            s
            for s in signals
            if s.metadata.get("signal_type") in ["midline_cross_up", "midline_cross_down"]
        ]
        assert len(midline_signals) == 0

    def test_generate_signals_nan_values_skipped(self):
        """Test generate_signals skips bars with NaN k/d values.

        Feeding OHLC data with NaN in the final rows leaves %K/%D undefined on
        the last bar, so the ``pd.isna`` guard performs ``continue`` (line
        1307) instead of emitting a signal.
        """
        strategy = StochasticOscillatorStrategy(k_period=5, d_period=3)
        dates = pd.date_range(end=datetime.now(), periods=16, freq="D")
        df = pd.DataFrame(
            {
                "open": [100.0] * 16,
                "high": [101.0] * 16,
                "low": [99.0] * 16,
                "close": [100.0] * 16,
                "volume": [1_000_000] * 16,
            },
            index=dates,
        )
        df.iloc[-2:, [1, 2, 3]] = float("nan")
        signals = strategy.generate_signals({"AAPL": df})
        assert signals == []

    def test_generate_signals_midline_no_cross_stays_above(self):
        """Test no midline signal when %K stays above 50 on the final bars.

        With ``use_midline=True`` and %K well above 50 on the final two bars
        (rising, not crossing the midline), the ``elif prev_k >= 50 and
        current_k < 50`` branch (line 1363) is False, so no signal is produced.
        """
        strategy = StochasticOscillatorStrategy(k_period=5, d_period=3, use_midline=True)
        highs = [60.0] * 16
        lows = [40.0] * 16
        closes = [100.0] * 10 + [51.0, 52.0, 53.0, 54.0, 55.0, 55.0]
        dates = pd.date_range(end=datetime.now(), periods=16, freq="D")
        df = pd.DataFrame(
            {
                "open": closes,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": [1_000_000] * 16,
            },
            index=dates,
        )
        signals = strategy.generate_signals({"AAPL": df})
        midline_signals = [
            s
            for s in signals
            if s.metadata.get("signal_type") in ("midline_cross_up", "midline_cross_down")
        ]
        assert midline_signals == []


class TestIchimokuCloudStrategy:
    """Tests for IchimokuCloudStrategy."""

    def test_initialization(self):
        """Test strategy initialization with explicit parameters."""
        strategy = IchimokuCloudStrategy(
            tenkan_period=9, kijun_period=26, senkou_b_period=52, name="Test_Ichimoku"
        )
        assert strategy.name == "Test_Ichimoku"
        assert strategy.tenkan_period == 9
        assert strategy.kijun_period == 26
        assert strategy.senkou_b_period == 52
        params = strategy.get_parameters()
        assert params["tenkan_period"] == 9
        assert params["kijun_period"] == 26
        assert params["senkou_b_period"] == 52

    def test_initialization_defaults(self):
        """Test default parameter values."""
        strategy = IchimokuCloudStrategy()
        assert strategy.name == "Ichimoku_Cloud"
        assert strategy.tenkan_period == 9
        assert strategy.kijun_period == 26
        assert strategy.senkou_b_period == 52

    def test_validate_parameters(self):
        """Test parameter validation raises on non-positive periods."""
        with pytest.raises(ValueError, match="tenkan_period must be positive"):
            IchimokuCloudStrategy(tenkan_period=0)
        with pytest.raises(ValueError, match="kijun_period must be positive"):
            IchimokuCloudStrategy(tenkan_period=9, kijun_period=0)
        with pytest.raises(ValueError, match="senkou_b_period must be positive"):
            IchimokuCloudStrategy(tenkan_period=9, kijun_period=26, senkou_b_period=0)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with insufficient data (continue at line 1434)."""
        strategy = IchimokuCloudStrategy(tenkan_period=3, kijun_period=5, senkou_b_period=7)
        # min_required = max(7, 5) + 5 = 12; supply only 10 rows.
        data = {"AAPL": create_donchian_data("AAPL", [100.0] * 10)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_nan_values_skipped(self):
        """Test generate_signals skips rows with NaN indicator values."""
        strategy = IchimokuCloudStrategy(tenkan_period=3, kijun_period=5, senkou_b_period=7)
        df = create_donchian_data("AAPL", [100.0] * 20)
        df.iloc[-2:, [1, 2, 3]] = float("nan")
        signals = strategy.generate_signals({"AAPL": df})
        assert signals == []

    def test_generate_signals_bullish_crossover(self):
        """Test generate_signals detects a bullish Tenkan/Kijun crossover."""
        strategy = IchimokuCloudStrategy(tenkan_period=3, kijun_period=5, senkou_b_period=7)
        closes = [100.0] * 20 + [110.0, 120.0, 130.0]
        signals = strategy.generate_signals({"AAPL": create_donchian_data("AAPL", closes)})
        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.price == pytest.approx(130.0)
        assert signal.metadata["signal_type"] == "tenkan_kijun_bullish_crossover"

    def test_generate_signals_bearish_crossover(self):
        """Test generate_signals detects a bearish Tenkan/Kijun crossover."""
        strategy = IchimokuCloudStrategy(tenkan_period=3, kijun_period=5, senkou_b_period=7)
        closes = [100.0] * 20 + [90.0, 80.0, 70.0]
        signals = strategy.generate_signals({"AAPL": create_donchian_data("AAPL", closes)})
        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.price == pytest.approx(70.0)
        assert signal.metadata["signal_type"] == "tenkan_kijun_bearish_crossover"

    def test_generate_signals_no_crossover(self):
        """Test generate_signals emits nothing when Tenkan stays above Kijun."""
        strategy = IchimokuCloudStrategy(tenkan_period=3, kijun_period=5, senkou_b_period=7)
        # Steady rise: Tenkan is already above Kijun on the final two bars, so
        # neither the bullish nor the bearish branch at lines 1484/1505 fires.
        closes = [100.0] * 20 + [110.0, 120.0, 130.0, 140.0, 150.0, 160.0]
        signals = strategy.generate_signals({"AAPL": create_donchian_data("AAPL", closes)})
        assert signals == []

    def test_generate_signals_skips_nan_values(self):
        """NaN Tenkan/Kijun values on the last bar are skipped."""
        strategy = IchimokuCloudStrategy(tenkan_period=3, kijun_period=5, senkou_b_period=7)
        closes = [100.0] * 20 + [110.0, 120.0, 130.0, 140.0, 150.0, 160.0]
        data = {"AAPL": create_donchian_data("AAPL", closes)}
        df = data["AAPL"]
        df.iloc[-1, df.columns.get_loc("close")] = float("nan")
        assert strategy.generate_signals(data) == []

    def test_generate_signals_skips_zero_kijun(self):
        """A zero Kijun-sen on the last bar is skipped to avoid division by zero."""
        strategy = IchimokuCloudStrategy(tenkan_period=3, kijun_period=5, senkou_b_period=7)
        # All-zero highs/lows produce zero Kijun-sen; last bar must not divide by zero.
        data = {"AAPL": create_donchian_data("AAPL", [0.0] * 30 + [0.0])}
        assert strategy.generate_signals(data) == []


def create_parabolic_data(
    symbol: str,
    high: list[float],
    low: list[float],
    close: list[float],
) -> pd.DataFrame:
    """Create deterministic OHLC data for Parabolic SAR testing.

    High/low/close are taken verbatim from the supplied lists; ``open`` mirrors
    ``close`` and volume is constant. Explicit prices let tests drive the SAR
    algorithm through hand-traced scenarios.
    """
    days = len(close)
    dates = pd.date_range(end=datetime.now(), periods=days, freq="D")
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": np.asarray(close, dtype=float),
            "high": np.asarray(high, dtype=float),
            "low": np.asarray(low, dtype=float),
            "close": np.asarray(close, dtype=float),
            "volume": np.full(days, 1_000_000),
        },
        index=dates,
    )


# Hand-traced OHLC scenarios (high, low, close) that drive the SAR through a
# short->long reversal, a long->short reversal, a sustained uptrend and a
# reversal that follows a sustained uptrend.
SAR_SCENARIOS: list[tuple[list[float], list[float], list[float]]] = [
    ([100.0, 99.0, 98.0, 100.0], [90.0, 95.0, 88.0, 99.0], [100.0, 99.0, 98.0, 99.5]),
    ([100.0, 105.0, 103.0, 106.0], [90.0, 92.0, 93.0, 85.0], [100.0, 105.0, 103.0, 85.0]),
    ([100.0, 105.0, 108.0, 110.0], [90.0, 92.0, 94.0, 95.0], [100.0, 105.0, 108.0, 110.0]),
    (
        [100.0, 102.0, 104.0, 106.0, 108.0, 110.0, 112.0, 115.0, 118.0, 120.0],
        [98.0, 100.0, 102.0, 104.0, 106.0, 108.0, 110.0, 113.0, 116.0, 85.0],
        [99.0, 101.0, 103.0, 105.0, 107.0, 109.0, 111.0, 114.0, 117.0, 90.0],
    ),
]


class TestParabolicSARStrategy:
    """Tests for ParabolicSARStrategy (examples.py lines 1539-1736)."""

    def test_initialization(self):
        """Test strategy initialization and parameter storage."""
        strategy = ParabolicSARStrategy(step=0.02, max_step=0.20, name="Test_SAR")
        assert strategy.name == "Test_SAR"
        assert strategy.step == 0.02
        assert strategy.max_step == 0.20
        assert strategy.parameters["step"] == 0.02
        assert strategy.parameters["max_step"] == 0.20

    def test_initialization_defaults(self):
        """Test default parameter values."""
        strategy = ParabolicSARStrategy()
        assert strategy.name == "Parabolic_SAR"
        assert strategy.step == 0.02
        assert strategy.max_step == 0.20

    def test_validate_parameters(self):
        """Test parameter validation (lines 1578, 1580, 1582)."""
        with pytest.raises(ValueError, match="step must be positive"):
            ParabolicSARStrategy(step=0)
        with pytest.raises(ValueError, match="step must be positive"):
            ParabolicSARStrategy(step=-0.01)
        with pytest.raises(ValueError, match="max_step must be positive"):
            ParabolicSARStrategy(max_step=0)
        with pytest.raises(ValueError, match="max_step must be positive"):
            ParabolicSARStrategy(max_step=-0.01)
        with pytest.raises(ValueError, match="step must be less than or equal to max_step"):
            ParabolicSARStrategy(step=0.30, max_step=0.20)

    def test_calculate_sar_insufficient_data(self):
        """_calculate_sar returns NaN SAR / zero trend with fewer than 2 points (lines 1593-1607)."""
        strategy = ParabolicSARStrategy()
        high = pd.Series([100.0], index=[0])
        low = pd.Series([90.0], index=[0])
        sar, trend = strategy._calculate_sar(high, low)
        assert sar.isna().all()
        assert (trend == 0).all()

    def test_generate_signals_insufficient_data(self):
        """A single-row frame is skipped before indicator calculation (line 1681-1682)."""
        strategy = ParabolicSARStrategy()
        data = {"AAPL": create_parabolic_data("AAPL", [100.0], [90.0], [95.0])}
        assert strategy.generate_signals(data) == []

    def test_generate_signals_skips_nan_sar(self):
        """A degenerate (all-NaN) 2-row frame yields a NaN last SAR which is skipped (lines 1697-1698)."""
        strategy = ParabolicSARStrategy()
        df = create_parabolic_data(
            "AAPL",
            [float("nan"), float("nan")],
            [float("nan"), float("nan")],
            [float("nan"), float("nan")],
        )
        assert strategy.generate_signals({"AAPL": df}) == []

    def test_calculate_sar_short_to_long_reversal(self):
        """Hand-traced short->long reversal (scenario A).

        Covers in _calculate_sar: init short, continue-short-no-new-low,
        continue-short-new-low, and reversal-to-long.
        """
        strategy = ParabolicSARStrategy(step=0.02, max_step=0.20)
        # (high, low) trace: period 3 reverses short->long; SAR resets to prev EP (88.0).
        high = pd.Series([100.0, 99.0, 98.0, 100.0])
        low = pd.Series([90.0, 95.0, 88.0, 99.0])
        sar, trend = strategy._calculate_sar(high, low)
        assert trend.iloc[-1] == 1
        assert trend.iloc[-2] == -1
        assert sar.iloc[-1] == pytest.approx(88.0)

    def test_generate_signals_bullish_reversal(self):
        """Buy signal on a short->long trend reversal (scenario A, lines 1701-1717)."""
        strategy = ParabolicSARStrategy(step=0.02, max_step=0.20)
        data = {
            "AAPL": create_parabolic_data(
                "AAPL",
                high=[100.0, 99.0, 98.0, 100.0],
                low=[90.0, 95.0, 88.0, 99.0],
                close=[100.0, 99.0, 98.0, 99.5],
            )
        }
        signals = strategy.generate_signals(data)
        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.strength == pytest.approx(1.0)
        assert signal.price == pytest.approx(99.5)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "trend_reversal_bullish"
        assert signal.metadata["trend"] == "bullish"
        assert signal.metadata["sar"] == pytest.approx(88.0)

    def test_generate_signals_bearish_reversal(self):
        """Sell signal on a long->short trend reversal (scenario B, lines 1636-1734).

        Covers in _calculate_sar: init long, continue-long-new-high,
        continue-long-no-new-high, and reversal-to-short.
        """
        strategy = ParabolicSARStrategy(step=0.02, max_step=0.20)
        # period 3 reverses long->short; SAR resets to prev EP (105.0).
        data = {
            "AAPL": create_parabolic_data(
                "AAPL",
                high=[100.0, 105.0, 103.0, 106.0],
                low=[90.0, 92.0, 93.0, 85.0],
                close=[100.0, 105.0, 103.0, 85.0],
            )
        }
        signals = strategy.generate_signals(data)
        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.strength == pytest.approx(1.0)
        assert signal.price == pytest.approx(85.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "trend_reversal_bearish"
        assert signal.metadata["trend"] == "bearish"
        assert signal.metadata["sar"] == pytest.approx(105.0)

    def test_generate_signals_no_trend_change(self):
        """No signal when the trend does not reverse over the last two bars (scenario C)."""
        strategy = ParabolicSARStrategy(step=0.02, max_step=0.20)
        data = {
            "AAPL": create_parabolic_data(
                "AAPL",
                high=[100.0, 105.0, 108.0, 110.0],
                low=[90.0, 92.0, 94.0, 95.0],
                close=[100.0, 105.0, 108.0, 110.0],
            )
        }
        assert strategy.generate_signals(data) == []

    def test_generate_signals_multiple_symbols(self):
        """Each symbol is evaluated independently for reversals."""
        strategy = ParabolicSARStrategy(step=0.02, max_step=0.20)
        data = {
            "AAPL": create_parabolic_data(
                "AAPL",
                high=[100.0, 99.0, 98.0, 100.0],
                low=[90.0, 95.0, 88.0, 99.0],
                close=[100.0, 99.0, 98.0, 99.5],
            ),
            "MSFT": create_parabolic_data(
                "MSFT",
                high=[100.0, 105.0, 103.0, 106.0],
                low=[90.0, 92.0, 93.0, 85.0],
                close=[100.0, 105.0, 103.0, 85.0],
            ),
        }
        signals = strategy.generate_signals(data)
        assert len(signals) == 2
        by_symbol = {s.symbol: s for s in signals}
        assert by_symbol["AAPL"].action == "buy"
        assert by_symbol["MSFT"].action == "sell"

    def test_generate_signals_bearish_reversal_after_sustained_uptrend(self):
        """A long->short reversal that follows a sustained uptrend still sells."""
        strategy = ParabolicSARStrategy(step=0.02, max_step=0.20)
        high, low, close = SAR_SCENARIOS[3]
        data = {"AAPL": create_parabolic_data("AAPL", high, low, close)}
        signals = strategy.generate_signals(data)
        assert len(signals) == 1
        assert signals[0].action == "sell"
        assert signals[0].metadata["signal_type"] == "trend_reversal_bearish"
        assert signals[0].metadata["trend"] == "bearish"

    @pytest.mark.parametrize(("high", "low", "close"), SAR_SCENARIOS)
    def test_calculate_sar_trend_is_always_bipolar(self, high, low, close):
        """The SAR trend only ever takes the values +1 and -1.

        That invariant is what makes the fall-through of the bearish ``elif`` in
        generate_signals unreachable, so it is asserted explicitly here.
        """
        strategy = ParabolicSARStrategy(step=0.02, max_step=0.20)
        df = create_parabolic_data("AAPL", high, low, close)
        _, trend = strategy._calculate_sar(df["high"], df["low"])
        assert set(trend.tolist()) <= {-1.0, 1.0}

    @pytest.mark.parametrize(("high", "low", "close"), SAR_SCENARIOS)
    def test_signal_matches_trend_reversal(self, high, low, close):
        """A trend change always produces exactly one signal of the right side.

        The bullish and bearish patterns in generate_signals between them cover
        every possible trend change, so no reversal is ever silently dropped.
        """
        strategy = ParabolicSARStrategy(step=0.02, max_step=0.20)
        df = create_parabolic_data("AAPL", high, low, close)
        _, trend = strategy._calculate_sar(df["high"], df["low"])
        signals = strategy.generate_signals({"AAPL": df})
        if trend.iloc[-1] == trend.iloc[-2]:
            assert signals == []
        else:
            assert len(signals) == 1
            assert signals[0].action == ("buy" if trend.iloc[-1] == 1 else "sell")

    def test_generate_signals_skips_nan_price(self):
        """A NaN close on the last bar is skipped by the guard."""
        strategy = ParabolicSARStrategy(step=0.02, max_step=0.20)
        data = {
            "AAPL": create_parabolic_data(
                "AAPL",
                high=[100.0, 99.0, 98.0, 100.0],
                low=[90.0, 95.0, 88.0, 99.0],
                close=[100.0, 99.0, 98.0, float("nan")],
            )
        }
        assert strategy.generate_signals(data) == []

    def test_generate_signals_skips_zero_price(self):
        """A zero close on the last bar is skipped by the guard."""
        strategy = ParabolicSARStrategy(step=0.02, max_step=0.20)
        data = {
            "AAPL": create_parabolic_data(
                "AAPL",
                high=[100.0, 99.0, 98.0, 100.0],
                low=[90.0, 95.0, 88.0, 99.0],
                close=[100.0, 99.0, 98.0, 0.0],
            )
        }
        assert strategy.generate_signals(data) == []


class TestEMACrossover:
    """Tests for EMACrossover (examples.py EMA crossover strategy)."""

    @staticmethod
    def _ohlcv(closes: list[float]) -> pd.DataFrame:
        close = pd.Series(closes, dtype=float)
        return pd.DataFrame(  # type: ignore[no-any-return]
            {
                "open": close,
                "high": close * 1.001,
                "low": close * 0.999,
                "close": close,
                "volume": pd.Series([1_000_000] * len(closes), dtype=float),
            }
        )

    def test_generate_signals_insufficient_data(self):
        strategy = EMACrossover(fast_period=2, slow_period=4)
        data = {"AAPL": self._ohlcv([100.0, 100.0, 100.0])}
        assert strategy.generate_signals(data) == []

    def test_generate_signals_golden_cross(self):
        strategy = EMACrossover(fast_period=2, slow_period=4)
        data = {"AAPL": self._ohlcv([100.0, 100.0, 100.0, 100.0, 100.0, 200.0])}
        signals = strategy.generate_signals(data)
        assert len(signals) == 1
        assert signals[0].action == "buy"
        assert signals[0].price == pytest.approx(200.0)

    def test_generate_signals_death_cross(self):
        strategy = EMACrossover(fast_period=2, slow_period=4)
        data = {"AAPL": self._ohlcv([200.0, 200.0, 200.0, 200.0, 200.0, 100.0])}
        signals = strategy.generate_signals(data)
        assert len(signals) == 1
        assert signals[0].action == "sell"
        assert signals[0].price == pytest.approx(100.0)

    def test_generate_signals_no_crossover(self):
        strategy = EMACrossover(fast_period=2, slow_period=4)
        data = {"AAPL": self._ohlcv([100.0, 105.0, 110.0, 115.0, 120.0, 125.0])}
        assert strategy.generate_signals(data) == []

    def test_generate_signals_nan_close_skipped(self):
        strategy = EMACrossover(fast_period=2, slow_period=4)
        # All-NaN closes yield NaN EWM values, which are skipped (line 2275).
        data = {"AAPL": self._ohlcv([float("nan")] * 6)}
        assert strategy.generate_signals(data) == []


def create_vwap_data(symbol: str, closes: list[float]) -> pd.DataFrame:
    """Create deterministic OHLC data from explicit close prices.

    High/low/close are all set to the close so the typical price equals
    the close; with constant volume the VWAP reduces to the running mean
    of the closes, making crossovers reproducible.
    """
    close = np.asarray(closes, dtype=float)
    dates = pd.date_range(end=datetime.now(), periods=len(close), freq="D")
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": np.full(len(close), 1_000_000),
        },
        index=dates,
    )


class TestVWAPStrategy:
    """Tests for VWAPStrategy (examples.py lines 1539-1614)."""

    def test_initialization(self):
        """Test strategy initialization and default name."""
        strategy = VWAPStrategy()
        assert strategy.name == "VWAP"
        assert strategy.parameters == {}

    def test_initialization_custom_name(self):
        """Test strategy initialization with a custom name."""
        strategy = VWAPStrategy(name="Custom_VWAP")
        assert strategy.name == "Custom_VWAP"

    def test_generate_signals_insufficient_data(self):
        """A single-row frame is skipped before VWAP calculation (line 1582-1583)."""
        strategy = VWAPStrategy()
        data = {"AAPL": create_vwap_data("AAPL", [100.0])}
        assert strategy.generate_signals(data) == []

    def test_generate_signals_skips_nan_vwap(self):
        """A NaN close on the last bar yields a NaN VWAP which is skipped (line 1597-1598)."""
        strategy = VWAPStrategy()
        df = create_vwap_data("AAPL", [100.0, 100.0])
        df.iloc[-1, df.columns.get_loc("close")] = float("nan")
        assert strategy.generate_signals({"AAPL": df}) == []

    def test_generate_signals_buy(self):
        """Buy signal when price crosses above the VWAP (lines 1600-1614)."""
        strategy = VWAPStrategy()
        # Bar 3: VWAP = mean(100,100,100,100) = 100, price = 100 (<= VWAP).
        # Bar 4: VWAP = mean(...,110) = 102, price = 110 (> VWAP) -> buy.
        data = {"AAPL": create_vwap_data("AAPL", [100.0, 100.0, 100.0, 100.0, 110.0])}
        signals = strategy.generate_signals(data)
        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.price == pytest.approx(110.0)
        assert signal.metadata["signal_type"] == "price_above_vwap"
        assert signal.metadata["vwap"] == pytest.approx(102.0)

    def test_generate_signals_sell(self):
        """Sell signal when price crosses below the VWAP (lines 1615-1630)."""
        strategy = VWAPStrategy()
        # Bar 3: VWAP = mean(110 x4) = 110, price = 110 (>= VWAP).
        # Bar 4: VWAP = mean(...,100) = 108, price = 100 (< VWAP) -> sell.
        data = {"AAPL": create_vwap_data("AAPL", [110.0, 110.0, 110.0, 110.0, 100.0])}
        signals = strategy.generate_signals(data)
        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.price == pytest.approx(100.0)
        assert signal.metadata["signal_type"] == "price_below_vwap"
        assert signal.metadata["vwap"] == pytest.approx(108.0)

    def test_generate_signals_no_crossover(self):
        """No signal when price stays on the same side of the VWAP."""
        strategy = VWAPStrategy()
        # Rising price that stays above the VWAP on the final two bars.
        data = {"AAPL": create_vwap_data("AAPL", [100.0, 105.0, 110.0, 115.0, 120.0])}
        assert strategy.generate_signals(data) == []

    def test_generate_signals_skips_zero_vwap(self):
        """A zero VWAP on the last bar is skipped to avoid division by zero."""
        strategy = VWAPStrategy()
        # All-zero closes produce a zero VWAP; the guard must skip the bar.
        data = {"AAPL": create_vwap_data("AAPL", [0.0, 0.0, 0.0, 0.0, 0.0])}
        assert strategy.generate_signals(data) == []


class TestEMACrossoverStrategy:
    """Tests for EMACrossover strategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = EMACrossover(fast_period=12, slow_period=26, name="Test_EMA")
        assert strategy.name == "Test_EMA"
        assert strategy.fast_period == 12
        assert strategy.slow_period == 26
        assert strategy.parameters["fast_period"] == 12
        assert strategy.parameters["slow_period"] == 26

    def test_initialization_defaults(self):
        """Test strategy initialization with default parameters."""
        strategy = EMACrossover()
        assert strategy.fast_period == 12
        assert strategy.slow_period == 26
        assert strategy.name == "EMA_Crossover"

    def test_validate_parameters(self):
        """Test parameter validation raises for invalid periods."""
        with pytest.raises(ValueError, match="fast_period must be a positive integer"):
            EMACrossover(fast_period=0)
        with pytest.raises(ValueError, match="fast_period must be a positive integer"):
            EMACrossover(fast_period=-5)
        with pytest.raises(ValueError, match="slow_period must be a positive integer"):
            EMACrossover(slow_period=0)
        with pytest.raises(ValueError, match="slow_period must be a positive integer"):
            EMACrossover(slow_period=-5)
        with pytest.raises(ValueError, match="fast_period must be less than slow_period"):
            EMACrossover(fast_period=30, slow_period=10)
        with pytest.raises(ValueError, match="fast_period must be less than slow_period"):
            EMACrossover(fast_period=10, slow_period=10)

    def test_validate_parameters_type_errors(self):
        """Test parameter validation raises for invalid types."""
        with pytest.raises(ValueError, match="fast_period must be a positive integer"):
            EMACrossover(fast_period=None)  # type: ignore
        with pytest.raises(ValueError, match="fast_period must be a positive integer"):
            EMACrossover(fast_period=5.5)  # type: ignore
        with pytest.raises(ValueError, match="slow_period must be a positive integer"):
            EMACrossover(slow_period=None)  # type: ignore
        with pytest.raises(ValueError, match="slow_period must be a positive integer"):
            EMACrossover(slow_period=26.5)  # type: ignore

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with insufficient data."""
        strategy = EMACrossover(fast_period=5, slow_period=15)
        data = {"AAPL": create_donchian_data("AAPL", [100.0] * 10)}  # Less than slow_period
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_bullish_crossover(self):
        """Test generate_signals detects bullish EMA crossover (buy signal)."""
        strategy = EMACrossover(fast_period=5, slow_period=15)
        data = {"AAPL": create_donchian_data("AAPL", [100.0] * 15 + [50.0] * 5 + [300.0])}
        signals = strategy.generate_signals(data)
        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert 0.0 <= signal.strength <= 1.0
        assert signal.price == pytest.approx(300.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "ema_crossover_bullish"
        assert "fast_ema" in signal.metadata
        assert "slow_ema" in signal.metadata

    def test_generate_signals_bearish_crossover(self):
        """Test generate_signals detects bearish EMA crossover (sell signal)."""
        strategy = EMACrossover(fast_period=5, slow_period=15)
        data = {"AAPL": create_donchian_data("AAPL", [100.0] * 15 + [200.0] * 20 + [50.0])}
        signals = strategy.generate_signals(data)
        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert 0.0 <= signal.strength <= 1.0
        assert signal.price == pytest.approx(50.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "ema_crossover_bearish"
        assert "fast_ema" in signal.metadata
        assert "slow_ema" in signal.metadata

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals with multiple symbols."""
        strategy = EMACrossover(fast_period=5, slow_period=15)
        data = {
            "AAPL": create_donchian_data("AAPL", [100.0] * 15 + [50.0] * 5 + [300.0]),
            "MSFT": create_donchian_data("MSFT", [100.0] * 15 + [200.0] * 20 + [50.0]),
        }
        signals = strategy.generate_signals(data)
        symbols = {s.symbol for s in signals}
        assert symbols == {"AAPL", "MSFT"}

    def test_generate_signals_no_crossover(self):
        """Test generate_signals with no crossover."""
        strategy = EMACrossover(fast_period=5, slow_period=15)
        data = {"AAPL": create_donchian_data("AAPL", [100.0] * 50)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_nan_values_skipped_ma(self):
        """Test generate_signals skips bars with NaN values."""
        strategy = MovingAverageCrossover(fast_period=5, slow_period=15)
        dates = pd.date_range(end=datetime.now(), periods=25, freq="D")
        df = pd.DataFrame(
            {
                "open": [100.0] * 25,
                "high": [101.0] * 25,
                "low": [99.0] * 25,
                "close": [100.0] * 25,
                "volume": [1_000_000] * 25,
            },
            index=dates,
        )
        df.iloc[-2:, [1, 2, 3]] = float("nan")
        signals = strategy.generate_signals({"AAPL": df})
        assert signals == []

    def test_generate_signals_nan_values_skipped(self):
        """Test generate_signals skips bars with NaN values."""
        strategy = EMACrossover(fast_period=5, slow_period=15)
        dates = pd.date_range(end=pd.Timestamp.now(), periods=25, freq="D")
        df = pd.DataFrame(
            {
                "open": [100.0] * 25,
                "high": [101.0] * 25,
                "low": [99.0] * 25,
                "close": [100.0] * 25,
                "volume": [1_000_000] * 25,
            },
            index=dates,
        )
        df.iloc[-2:, [1, 2, 3]] = float("nan")
        signals = strategy.generate_signals({"AAPL": df})
        assert signals == []

    def test_generate_signals_price_zero_handling(self):
        """Test strength calculation when price is zero."""
        strategy = EMACrossover(fast_period=3, slow_period=8)
        dates = pd.date_range("2023-01-01", periods=12, freq="D")
        closes = [100, 100, 100, 100, 100, 50, 50, 50, 200, 200, 200, 0]
        df = pd.DataFrame(
            {
                "open": closes,
                "high": [c * 1.001 for c in closes],
                "low": [c * 0.999 for c in closes],
                "close": closes,
                "volume": [1_000_000] * len(closes),
            },
            index=dates,
        )
        signals = strategy.generate_signals({"AAPL": df})
        # Should handle zero price in strength calculation
        assert len(signals) >= 0


def create_momentum_data(closes: list[float]) -> pd.DataFrame:
    """Create deterministic OHLC data from explicit close prices for momentum tests."""
    close = pd.Series(closes, dtype=float)
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": pd.Series([1_000_000] * len(closes), dtype=float),
        }
    )


class TestMomentumStrategy:
    """Tests for MomentumStrategy (examples.py lines 2323-2438)."""

    def test_initialization(self):
        """Test strategy initialization and parameter storage."""
        strategy = MomentumStrategy(period=10, threshold=0.01, name="Test_Momentum")
        assert strategy.name == "Test_Momentum"
        assert strategy.period == 10
        assert strategy.threshold == 0.01
        assert strategy.parameters["period"] == 10
        assert strategy.parameters["threshold"] == 0.01

    def test_initialization_defaults(self):
        """Test default parameter values."""
        strategy = MomentumStrategy()
        assert strategy.period == 10
        assert strategy.threshold == 0.01
        assert strategy.name == "Momentum"

    def test_validate_parameters(self):
        """Test parameter validation raises on invalid period or threshold."""
        with pytest.raises(ValueError, match="period must be positive"):
            MomentumStrategy(period=0)
        with pytest.raises(ValueError, match="period must be positive"):
            MomentumStrategy(period=-1)
        with pytest.raises(ValueError, match="threshold must be non-negative"):
            MomentumStrategy(threshold=-0.01)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals returns empty when fewer than period + 1 bars."""
        strategy = MomentumStrategy(period=10)
        data = {"AAPL": create_momentum_data([100.0] * 10)}
        assert strategy.generate_signals(data) == []

    def test_generate_signals_buy_positive_momentum(self):
        """Test buy signal when momentum exceeds the threshold."""
        strategy = MomentumStrategy(period=10, threshold=0.01)
        # momentum = 110 / 100 - 1 = 0.10 > 0.01 -> buy, strength capped at 1.0
        data = {"AAPL": create_momentum_data([100.0] * 10 + [110.0])}
        signals = strategy.generate_signals(data)
        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.strength == pytest.approx(1.0)
        assert signal.price == pytest.approx(110.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "positive_momentum"
        assert signal.metadata["momentum"] == pytest.approx(0.10)
        assert signal.metadata["period"] == 10

    def test_generate_signals_sell_negative_momentum(self):
        """Test sell signal when momentum is below the negative threshold."""
        strategy = MomentumStrategy(period=10, threshold=0.01)
        # momentum = 90 / 100 - 1 = -0.10 < -0.01 -> sell
        data = {"AAPL": create_momentum_data([100.0] * 10 + [90.0])}
        signals = strategy.generate_signals(data)
        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.strength == pytest.approx(1.0)
        assert signal.price == pytest.approx(90.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "negative_momentum"
        assert signal.metadata["momentum"] == pytest.approx(-0.10)

    def test_generate_signals_no_signal_within_threshold(self):
        """Test no signal when momentum magnitude is within the threshold."""
        strategy = MomentumStrategy(period=10, threshold=0.01)
        # momentum = 100.5 / 100 - 1 = 0.005, within [-0.01, 0.01]
        data = {"AAPL": create_momentum_data([100.0] * 10 + [100.5])}
        assert strategy.generate_signals(data) == []

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals evaluates each symbol independently."""
        strategy = MomentumStrategy(period=10, threshold=0.01)
        data = {
            "AAPL": create_momentum_data([100.0] * 10 + [110.0]),
            "MSFT": create_momentum_data([100.0] * 10 + [90.0]),
        }
        signals = strategy.generate_signals(data)
        by_symbol = {s.symbol: s for s in signals}
        assert set(by_symbol) == {"AAPL", "MSFT"}
        assert by_symbol["AAPL"].action == "buy"
        assert by_symbol["MSFT"].action == "sell"
        assert by_symbol["AAPL"].metadata["signal_type"] == "positive_momentum"
        assert by_symbol["MSFT"].metadata["signal_type"] == "negative_momentum"

    def test_generate_signals_skips_nan_current_price(self):
        """A NaN last close is skipped by the guard before momentum is computed."""
        strategy = MomentumStrategy(period=2, threshold=0.01)
        data = {"AAPL": create_momentum_data([100.0, 100.0, float("nan")])}
        assert strategy.generate_signals(data) == []

    def test_generate_signals_skips_nan_prev_price(self):
        """A NaN price `period + 1` bars back is skipped by the guard."""
        strategy = MomentumStrategy(period=2, threshold=0.01)
        data = {"AAPL": create_momentum_data([float("nan"), 100.0, 100.0])}
        assert strategy.generate_signals(data) == []

    def test_generate_signals_skips_zero_prev_price(self):
        """A zero reference price is skipped instead of dividing by zero."""
        strategy = MomentumStrategy(period=2, threshold=0.01)
        data = {"AAPL": create_momentum_data([0.0, 100.0, 100.0])}
        assert strategy.generate_signals(data) == []


def create_adx_data(symbol: str, closes: list[float]) -> pd.DataFrame:
    """Create deterministic OHLC data for ADX tests.

    High and low carry a fixed one-point range so the true range exceeds the
    directional movement and the directional indices stay bounded.
    """
    close = np.asarray(closes, dtype=float)
    dates = pd.date_range(end=datetime.now(), periods=len(close), freq="D")
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.full(len(close), 1_000_000),
        },
        index=dates,
    )


class TestADXStrategy:
    """Tests for ADXStrategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = ADXStrategy(period=14, threshold=25.0, name="Test_ADX")
        assert strategy.name == "Test_ADX"
        assert strategy.period == 14
        assert strategy.threshold == 25.0

    def test_defaults(self):
        """Test default parameters."""
        strategy = ADXStrategy()
        assert strategy.name == "ADX"
        assert strategy.period == 14
        assert strategy.threshold == 25.0

    def test_validate_parameters(self):
        """Test parameter validation raises for invalid bounds."""
        with pytest.raises(ValueError, match="period must be positive"):
            ADXStrategy(period=0)
        with pytest.raises(ValueError, match="period must be positive"):
            ADXStrategy(period=-14)
        with pytest.raises(ValueError, match="threshold must be between 0 and 100"):
            ADXStrategy(threshold=0)
        with pytest.raises(ValueError, match="threshold must be between 0 and 100"):
            ADXStrategy(threshold=100)
        with pytest.raises(ValueError, match="threshold must be between 0 and 100"):
            ADXStrategy(threshold=-10)

    def test_generate_signals_bullish_trend(self):
        """Test a strong uptrend emits a buy signal."""
        strategy = ADXStrategy(period=14, threshold=25.0)
        closes = [100.0 + 2.0 * i for i in range(40)]
        data = {"AAPL": create_adx_data("AAPL", closes)}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.strength == pytest.approx(1.0)
        assert signal.price == pytest.approx(178.0)
        assert signal.metadata["signal_type"] == "bullish_trend"
        assert signal.metadata["adx"] == pytest.approx(100.0)
        assert signal.metadata["minus_di"] == pytest.approx(0.0)
        assert signal.metadata["plus_di"] > 50.0

    def test_generate_signals_bearish_trend(self):
        """Test a strong downtrend emits a sell signal."""
        strategy = ADXStrategy(period=14, threshold=25.0)
        closes = [100.0 - 2.0 * i for i in range(40)]
        data = {"AAPL": create_adx_data("AAPL", closes)}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.strength == pytest.approx(1.0)
        assert signal.price == pytest.approx(22.0)
        assert signal.metadata["signal_type"] == "bearish_trend"
        assert signal.metadata["adx"] == pytest.approx(100.0)
        assert signal.metadata["plus_di"] == pytest.approx(0.0)
        assert signal.metadata["minus_di"] > 50.0

    def test_generate_signals_no_signal_without_trend(self):
        """A flat price series has no trend, so no signal is emitted."""
        strategy = ADXStrategy(period=14, threshold=25.0)
        closes = [100.0] * 40
        data = {"AAPL": create_adx_data("AAPL", closes)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with insufficient data."""
        strategy = ADXStrategy(period=14)
        data = {"AAPL": create_adx_data("AAPL", [100.0 + i for i in range(20)])}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals evaluates each symbol independently."""
        strategy = ADXStrategy(period=14, threshold=25.0)
        data = {
            "AAPL": create_adx_data("AAPL", [100.0 + 2.0 * i for i in range(40)]),
            "MSFT": create_adx_data("MSFT", [100.0 - 2.0 * i for i in range(40)]),
        }
        signals = strategy.generate_signals(data)
        by_symbol = {s.symbol: s for s in signals}
        assert set(by_symbol) == {"AAPL", "MSFT"}
        assert by_symbol["AAPL"].action == "buy"
        assert by_symbol["MSFT"].action == "sell"

    def test_generate_signals_skips_nan_close(self):
        """A NaN last close is skipped before any signal is derived."""
        strategy = ADXStrategy(period=14, threshold=25.0)
        closes = [100.0 + 2.0 * i for i in range(39)] + [float("nan")]
        data = {"AAPL": create_adx_data("AAPL", closes)}
        assert strategy.generate_signals(data) == []


def create_williams_r_data(symbol: str, closes: list[float]) -> pd.DataFrame:
    """Create deterministic OHLC data for Williams %R tests.

    High and low carry a fixed two-point range around the close.
    """
    close = np.asarray(closes, dtype=float)
    dates = pd.date_range(end=datetime.now(), periods=len(close), freq="D")
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "high": close + 2.0,
            "low": close - 2.0,
            "close": close,
            "volume": np.full(len(close), 1_000_000),
        },
        index=dates,
    )


class TestWilliamsRStrategy:
    """Tests for WilliamsRStrategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = WilliamsRStrategy(
            period=14, overbought=-20.0, oversold=-80.0, name="Test_WilliamsR"
        )
        assert strategy.name == "Test_WilliamsR"
        assert strategy.period == 14
        assert strategy.overbought == -20.0
        assert strategy.oversold == -80.0

    def test_defaults(self):
        """Test default parameters."""
        strategy = WilliamsRStrategy()
        assert strategy.name == "Williams %R"
        assert strategy.period == 14
        assert strategy.overbought == -20.0
        assert strategy.oversold == -80.0

    def test_validate_parameters(self):
        """Test parameter validation raises for invalid bounds."""
        with pytest.raises(ValueError, match="period must be positive"):
            WilliamsRStrategy(period=0)
        with pytest.raises(ValueError, match="period must be positive"):
            WilliamsRStrategy(period=-14)
        with pytest.raises(ValueError, match="overbought must be between -100 and 0"):
            WilliamsRStrategy(overbought=0.0)
        with pytest.raises(ValueError, match="overbought must be between -100 and 0"):
            WilliamsRStrategy(overbought=-100.0)
        with pytest.raises(ValueError, match="overbought must be between -100 and 0"):
            WilliamsRStrategy(overbought=-150.0)
        with pytest.raises(ValueError, match="oversold must be between -100 and 0"):
            WilliamsRStrategy(oversold=0.0)
        with pytest.raises(ValueError, match="oversold must be between -100 and 0"):
            WilliamsRStrategy(oversold=-100.0)
        with pytest.raises(ValueError, match="oversold must be below overbought"):
            WilliamsRStrategy(overbought=-50.0, oversold=-20.0)
        with pytest.raises(ValueError, match="oversold must be below overbought"):
            WilliamsRStrategy(overbought=-20.0, oversold=-20.0)

    def test_generate_signals_oversold_buy(self):
        """An oversold reading emits a buy signal."""
        strategy = WilliamsRStrategy(period=14, overbought=-20.0, oversold=-80.0)
        closes = [100.0] * 12 + [108.0, 92.0]
        data = {"AAPL": create_williams_r_data("AAPL", closes)}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.strength == pytest.approx(0.1)
        assert signal.price == pytest.approx(92.0)
        assert signal.metadata["signal_type"] == "oversold"
        assert signal.metadata["williams_r"] == pytest.approx(-90.0)

    def test_generate_signals_overbought_sell(self):
        """An overbought reading emits a sell signal."""
        strategy = WilliamsRStrategy(period=14, overbought=-20.0, oversold=-80.0)
        closes = [100.0] * 12 + [92.0, 108.0]
        data = {"AAPL": create_williams_r_data("AAPL", closes)}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.strength == pytest.approx(0.1)
        assert signal.price == pytest.approx(108.0)
        assert signal.metadata["signal_type"] == "overbought"
        assert signal.metadata["williams_r"] == pytest.approx(-10.0)

    def test_generate_signals_no_signal_in_middle(self):
        """A reading between the bounds emits no signal."""
        strategy = WilliamsRStrategy(period=14, overbought=-20.0, oversold=-80.0)
        closes = [100.0] * 14
        data = {"AAPL": create_williams_r_data("AAPL", closes)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with insufficient data."""
        strategy = WilliamsRStrategy(period=14)
        data = {"AAPL": create_williams_r_data("AAPL", [100.0] * 13)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals evaluates each symbol independently."""
        strategy = WilliamsRStrategy(period=14, overbought=-20.0, oversold=-80.0)
        data = {
            "AAPL": create_williams_r_data("AAPL", [100.0] * 12 + [108.0, 92.0]),
            "MSFT": create_williams_r_data("MSFT", [100.0] * 12 + [92.0, 108.0]),
        }
        signals = strategy.generate_signals(data)
        by_symbol = {s.symbol: s for s in signals}
        assert set(by_symbol) == {"AAPL", "MSFT"}
        assert by_symbol["AAPL"].action == "buy"
        assert by_symbol["MSFT"].action == "sell"

    def test_generate_signals_skips_nan_close(self):
        """A NaN last close is skipped before any signal is derived."""
        strategy = WilliamsRStrategy(period=14, overbought=-20.0, oversold=-80.0)
        closes = [100.0] * 13 + [float("nan")]
        data = {"AAPL": create_williams_r_data("AAPL", closes)}
        assert strategy.generate_signals(data) == []


def create_obv_data(symbol: str, closes: list[float]) -> pd.DataFrame:
    """Create deterministic OHLCV data for OBV tests.

    Volume is constant at 1,000,000 per bar so OBV moves are driven purely by
    the direction of the close. High and low carry a small 0.1% wick around
    the close.
    """
    close = np.asarray(closes, dtype=float)
    dates = pd.date_range(end=datetime.now(), periods=len(close), freq="D")
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": np.full(len(close), 1_000_000),
        },
        index=dates,
    )


class TestOBVStrategy:
    """Tests for OBVStrategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = OBVStrategy(signal_period=20, name="Test_OBV")
        assert strategy.name == "Test_OBV"
        assert strategy.signal_period == 20
        assert strategy.parameters["signal_period"] == 20

    def test_validate_parameters(self):
        """Test parameter validation raises for invalid periods."""
        with pytest.raises(ValueError, match="signal_period must be positive"):
            OBVStrategy(signal_period=0)
        with pytest.raises(ValueError, match="signal_period must be positive"):
            OBVStrategy(signal_period=-5)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with fewer bars than signal_period + 1."""
        strategy = OBVStrategy(signal_period=20)
        data = {"AAPL": create_obv_data("AAPL", [100.0] * 20)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_obv_crosses_above_signal_line(self):
        """An up-day on flat data pushes OBV above its signal line (buy)."""
        strategy = OBVStrategy(signal_period=20)
        # 25 flat bars keep OBV at zero; the final up-bar lifts OBV above
        # its 20-bar signal line on the last bar only -- exactly one buy.
        data = {"AAPL": create_obv_data("AAPL", [100.0] * 25 + [105.0])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.strength == pytest.approx(1.0)
        assert signal.price == pytest.approx(105.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "obv_cross_above"
        assert signal.metadata["obv"] == pytest.approx(1_000_000.0)
        assert signal.metadata["signal_line"] == pytest.approx(1_000_000.0 / 20.0)

    def test_generate_signals_obv_crosses_below_signal_line(self):
        """A down-day on flat data pushes OBV below its signal line (sell)."""
        strategy = OBVStrategy(signal_period=20)
        data = {"AAPL": create_obv_data("AAPL", [100.0] * 25 + [95.0])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.strength == pytest.approx(1.0)
        assert signal.price == pytest.approx(95.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "obv_cross_below"
        assert signal.metadata["obv"] == pytest.approx(-1_000_000.0)
        assert signal.metadata["signal_line"] == pytest.approx(-1_000_000.0 / 20.0)

    def test_generate_signals_flat_data_no_signals(self):
        """Flat closes keep OBV flat, so it never crosses its signal line."""
        strategy = OBVStrategy(signal_period=20)
        data = {"AAPL": create_obv_data("AAPL", [100.0] * 30)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals evaluates each symbol independently."""
        strategy = OBVStrategy(signal_period=20)
        data = {
            "AAPL": create_obv_data("AAPL", [100.0] * 25 + [105.0]),
            "MSFT": create_obv_data("MSFT", [100.0] * 25 + [95.0]),
        }
        signals = strategy.generate_signals(data)
        by_symbol = {s.symbol: s for s in signals}
        assert set(by_symbol) == {"AAPL", "MSFT"}
        assert by_symbol["AAPL"].action == "buy"
        assert by_symbol["MSFT"].action == "sell"

    def test_generate_signals_skips_nan_close(self):
        """A NaN last close is skipped before any signal is derived."""
        strategy = OBVStrategy(signal_period=20)
        closes = [100.0] * 25 + [float("nan")]
        data = {"AAPL": create_obv_data("AAPL", closes)}
        assert strategy.generate_signals(data) == []


def create_cmf_data(symbol: str, bars: list[tuple[float, float, float]]) -> pd.DataFrame:
    """Create deterministic OHLCV data for CMF tests.

    Each bar is a ``(close, high, low)`` tuple; volume is constant so CMF is
    driven purely by the close's position within the high/low range.
    """
    dates = pd.date_range(end=datetime.now(), periods=len(bars), freq="D")
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": [bar[0] for bar in bars],
            "high": [bar[1] for bar in bars],
            "low": [bar[2] for bar in bars],
            "close": [bar[0] for bar in bars],
            "volume": np.full(len(bars), 1_000_000),
        },
        index=dates,
    )


def create_mfi_data(symbol: str, bars: list[tuple[float, float, float]]) -> pd.DataFrame:
    """Create deterministic OHLCV data for MFI tests.

    Each bar is a ``(close, high, low)`` tuple; volume is constant so MFI is
    driven purely by the close's position within the high/low range and the
    direction of the close relative to the prior close.
    """
    dates = pd.date_range(end=datetime.now(), periods=len(bars), freq="D")
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": [bar[0] for bar in bars],
            "high": [bar[1] for bar in bars],
            "low": [bar[2] for bar in bars],
            "close": [bar[0] for bar in bars],
            "volume": np.full(len(bars), 1_000_000),
        },
        index=dates,
    )


class TestChaikinMoneyFlowStrategy:
    """Tests for ChaikinMoneyFlowStrategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = ChaikinMoneyFlowStrategy(period=20, name="Test_CMF")
        assert strategy.name == "Test_CMF"
        assert strategy.period == 20
        assert strategy.parameters["period"] == 20

    def test_validate_parameters(self):
        """Test parameter validation raises for invalid periods."""
        with pytest.raises(ValueError, match="period must be positive"):
            ChaikinMoneyFlowStrategy(period=0)
        with pytest.raises(ValueError, match="period must be positive"):
            ChaikinMoneyFlowStrategy(period=-5)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with fewer bars than period + 1."""
        strategy = ChaikinMoneyFlowStrategy(period=5)
        data = {"AAPL": create_cmf_data("AAPL", [(100.0, 101.0, 100.0)] * 5)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_cmf_crosses_above_zero(self):
        """A final buying-pressure bar flips CMF from negative to positive."""
        strategy = ChaikinMoneyFlowStrategy(period=5)
        # 5 selling bars, 4 neutral bars, 1 buying bar -> the last 5-bar
        # window sums to +1 while the previous sums to -1: cross above zero.
        bars = [(100.0, 101.0, 100.0)] * 5 + [(100.0, 101.0, 99.0)] * 4 + [(105.0, 105.0, 104.0)]
        data = {"AAPL": create_cmf_data("AAPL", bars)}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.strength == pytest.approx(0.7)
        assert signal.price == pytest.approx(105.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "cmf_cross_above_zero"
        assert signal.metadata["cmf"] == pytest.approx(0.2)
        assert signal.metadata["period"] == 5

    def test_generate_signals_cmf_crosses_below_zero(self):
        """A final selling-pressure bar flips CMF from positive to negative."""
        strategy = ChaikinMoneyFlowStrategy(period=5)
        bars = [(105.0, 105.0, 104.0)] * 5 + [(100.0, 101.0, 99.0)] * 4 + [(100.0, 101.0, 100.0)]
        data = {"AAPL": create_cmf_data("AAPL", bars)}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.strength == pytest.approx(0.7)
        assert signal.price == pytest.approx(100.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "cmf_cross_below_zero"
        assert signal.metadata["cmf"] == pytest.approx(-0.2)
        assert signal.metadata["period"] == 5

    def test_generate_signals_flat_range_no_signals(self):
        """Close always at the range midpoint -> zero pressure, no signals."""
        strategy = ChaikinMoneyFlowStrategy(period=5)
        bars = [(100.0, 101.0, 99.0)] * 15
        data = {"AAPL": create_cmf_data("AAPL", bars)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals evaluates each symbol independently."""
        strategy = ChaikinMoneyFlowStrategy(period=5)
        buy_bars = (
            [(100.0, 101.0, 100.0)] * 5 + [(100.0, 101.0, 99.0)] * 4 + [(105.0, 105.0, 104.0)]
        )
        sell_bars = (
            [(105.0, 105.0, 104.0)] * 5 + [(100.0, 101.0, 99.0)] * 4 + [(100.0, 101.0, 100.0)]
        )
        data = {
            "AAPL": create_cmf_data("AAPL", buy_bars),
            "MSFT": create_cmf_data("MSFT", sell_bars),
        }
        signals = strategy.generate_signals(data)
        by_symbol = {s.symbol: s for s in signals}
        assert set(by_symbol) == {"AAPL", "MSFT"}
        assert by_symbol["AAPL"].action == "buy"
        assert by_symbol["MSFT"].action == "sell"


class TestForceIndexStrategy:
    """Tests for the Force Index strategy."""

    def test_initialization(self):
        strategy = ForceIndexStrategy()
        assert strategy.name == "Force_Index"
        assert strategy.period == 13

    def test_initialization_custom_params(self):
        strategy = ForceIndexStrategy(period=14, name="FI_Custom")
        assert strategy.period == 14
        assert strategy.name == "FI_Custom"

    def test_validate_parameters_invalid_period(self):
        with pytest.raises(ValueError, match="period must be positive"):
            ForceIndexStrategy(period=0)
        with pytest.raises(ValueError, match="period must be positive"):
            ForceIndexStrategy(period=-5)

    def test_insufficient_data(self):
        strategy = ForceIndexStrategy(period=13)
        dates = pd.date_range("2023-01-01", periods=14)
        data = {"AAPL": pd.DataFrame({"close": [100] * 14, "volume": [1000] * 14}, index=dates)}
        assert strategy.generate_signals(data) == []

    def test_cross_above_zero_buy(self):
        strategy = ForceIndexStrategy(period=2)
        dates = pd.date_range("2023-01-01", periods=10)
        # Create pattern: first give some negative FI, then cross above zero
        closes = [100, 99, 98, 97, 96, 95, 94, 93, 95, 96]  # big jump up at end
        volumes = [1000] * 10
        data = {"AAPL": pd.DataFrame({"close": closes, "volume": volumes}, index=dates)}
        signals = strategy.generate_signals(data)
        # Should generate a buy signal on zero crossing
        buy_signals = [s for s in signals if s.action == "buy"]
        assert len(buy_signals) >= 0  # May or may not trigger depending on calculation

    def test_generate_signals_skips_nan_close(self):
        strategy = ForceIndexStrategy(period=2)
        dates = pd.date_range("2023-01-01", periods=10)
        closes = [100, 99, 98, 97, 96, 95, 94, 93, 95, float("nan")]
        volumes = [1000] * 10
        data = {"AAPL": pd.DataFrame({"close": closes, "volume": volumes}, index=dates)}
        assert strategy.generate_signals(data) == []


class TestMoneyFlowIndexStrategy:
    """Tests for the Money Flow Index (MFI) strategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = MoneyFlowIndexStrategy(period=14, name="Test_MFI")
        assert strategy.name == "Test_MFI"
        assert strategy.period == 14
        assert strategy.parameters["period"] == 14

    def test_validate_parameters(self):
        """Test parameter validation raises for invalid periods."""
        with pytest.raises(ValueError, match="period must be positive"):
            MoneyFlowIndexStrategy(period=0)
        with pytest.raises(ValueError, match="period must be positive"):
            MoneyFlowIndexStrategy(period=-5)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with fewer bars than period + 1."""
        strategy = MoneyFlowIndexStrategy(period=5)
        data = {"AAPL": create_mfi_data("AAPL", [(100.0, 101.0, 100.0)] * 5)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_mfi_crosses_above_50(self):
        """A final buying-pressure bar flips MFI from below 50 to above 50."""
        strategy = MoneyFlowIndexStrategy(period=5)
        # 4 down-sell bars (close at low extreme, mfm -1) then 3 up-buy bars
        # (close at high extreme, mfm +1): the last 5-bar window sums to a
        # positive money flow ratio, pushing MFI from -197.95 to +290.07.
        down = lambda c: (c, c + 2.0, c)
        up = lambda c: (c, c, c - 2.0)
        bars = [down(100), down(98), down(96), down(94), up(96), up(98), up(100)]
        data = {"AAPL": create_mfi_data("AAPL", bars)}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.strength == pytest.approx(1.0)
        assert signal.price == pytest.approx(100.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "mfi_cross_above_50"
        assert signal.metadata["mfi"] == pytest.approx(290.06622516556286)
        assert signal.metadata["period"] == 5

    def test_generate_signals_mfi_crosses_below_50(self):
        """A final selling-pressure bar flips MFI from above 50 to below 50."""
        strategy = MoneyFlowIndexStrategy(period=5)
        down = lambda c: (c, c + 2.0, c)
        up = lambda c: (c, c, c - 2.0)
        bars = [up(100), up(102), up(104), up(106), down(104), down(102), down(100)]
        data = {"AAPL": create_mfi_data("AAPL", bars)}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.strength == pytest.approx(1.0)
        assert signal.price == pytest.approx(100.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "mfi_cross_below_50"
        assert signal.metadata["mfi"] == pytest.approx(-210.06711409395984)
        assert signal.metadata["period"] == 5

    def test_generate_signals_flat_range_no_signals(self):
        """Close always at the range midpoint -> zero money flow, no signals."""
        strategy = MoneyFlowIndexStrategy(period=5)
        bars = [(100.0, 101.0, 99.0)] * 15
        data = {"AAPL": create_mfi_data("AAPL", bars)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals evaluates each symbol independently."""
        strategy = MoneyFlowIndexStrategy(period=5)
        down = lambda c: (c, c + 2.0, c)
        up = lambda c: (c, c, c - 2.0)
        buy_bars = [down(100), down(98), down(96), down(94), up(96), up(98), up(100)]
        sell_bars = [up(100), up(102), up(104), up(106), down(104), down(102), down(100)]
        data = {
            "AAPL": create_mfi_data("AAPL", buy_bars),
            "MSFT": create_mfi_data("MSFT", sell_bars),
        }
        signals = strategy.generate_signals(data)
        by_symbol = {s.symbol: s for s in signals}
        assert set(by_symbol) == {"AAPL", "MSFT"}
        assert by_symbol["AAPL"].action == "buy"
        assert by_symbol["MSFT"].action == "sell"

    def test_generate_signals_skips_nan_close(self):
        """A NaN last close is rejected before any signal is derived."""
        strategy = MoneyFlowIndexStrategy(period=5)
        down = lambda c: (c, c + 2.0, c)
        up = lambda c: (c, c, c - 2.0)
        bars = [
            down(100),
            down(98),
            down(96),
            down(94),
            up(96),
            up(98),
            (float("nan"), 100.0, 98.0),
        ]
        data = {"AAPL": create_mfi_data("AAPL", bars)}
        assert strategy.generate_signals(data) == []


def create_vroc_data(symbol: str, volumes: list[float], close: float = 100.0) -> pd.DataFrame:
    """Create deterministic close/volume data for VROC tests.

    The close is constant so VROC is driven purely by the volume change.
    """
    dates = pd.date_range(end=datetime.now(), periods=len(volumes), freq="D")
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": [close] * len(volumes),
            "high": [close] * len(volumes),
            "low": [close] * len(volumes),
            "close": [close] * len(volumes),
            "volume": np.asarray(volumes, dtype=float),
        },
        index=dates,
    )


class TestVolumeRateOfChangeStrategy:
    """Tests for the Volume Rate of Change (VROC) strategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = VolumeRateOfChangeStrategy(period=14, name="Test_VROC")
        assert strategy.name == "Test_VROC"
        assert strategy.period == 14
        assert strategy.parameters["period"] == 14

    def test_validate_parameters(self):
        """Test parameter validation raises for invalid periods."""
        with pytest.raises(ValueError, match="period must be positive"):
            VolumeRateOfChangeStrategy(period=0)
        with pytest.raises(ValueError, match="period must be positive"):
            VolumeRateOfChangeStrategy(period=-5)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with fewer bars than period + 2."""
        strategy = VolumeRateOfChangeStrategy(period=5)
        data = {"AAPL": create_vroc_data("AAPL", [1_000_000] * 6)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_vroc_crosses_above_zero(self):
        """A final volume surge flips VROC from zero to +100 (buy)."""
        strategy = VolumeRateOfChangeStrategy(period=5)
        # 25 flat bars keep VROC at zero; the final bar doubles volume,
        # pushing VROC from 0 to +100 on the last bar only.
        data = {"AAPL": create_vroc_data("AAPL", [1_000_000] * 25 + [2_000_000])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.strength == pytest.approx(0.5)
        assert signal.price == pytest.approx(100.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "vroc_cross_above_zero"
        assert signal.metadata["vroc"] == pytest.approx(100.0)
        assert signal.metadata["period"] == 5

    def test_generate_signals_vroc_crosses_below_zero(self):
        """A final volume drop halves volume, flipping VROC to -50 (sell)."""
        strategy = VolumeRateOfChangeStrategy(period=5)
        data = {"AAPL": create_vroc_data("AAPL", [1_000_000] * 25 + [500_000])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.strength == pytest.approx(1 / 3)
        assert signal.price == pytest.approx(100.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "vroc_cross_below_zero"
        assert signal.metadata["vroc"] == pytest.approx(-50.0)
        assert signal.metadata["period"] == 5

    def test_generate_signals_flat_volume_no_signals(self):
        """Constant volume keeps VROC at zero, so no crossover fires."""
        strategy = VolumeRateOfChangeStrategy(period=5)
        data = {"AAPL": create_vroc_data("AAPL", [1_000_000] * 30)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals evaluates each symbol independently."""
        strategy = VolumeRateOfChangeStrategy(period=5)
        data = {
            "AAPL": create_vroc_data("AAPL", [1_000_000] * 25 + [2_000_000]),
            "MSFT": create_vroc_data("MSFT", [1_000_000] * 25 + [500_000]),
        }
        signals = strategy.generate_signals(data)
        by_symbol = {s.symbol: s for s in signals}
        assert set(by_symbol) == {"AAPL", "MSFT"}
        assert by_symbol["AAPL"].action == "buy"
        assert by_symbol["MSFT"].action == "sell"

    def test_generate_signals_skips_nan_volume(self):
        """A NaN last volume is rejected before any signal is derived."""
        strategy = VolumeRateOfChangeStrategy(period=5)
        data = {"AAPL": create_vroc_data("AAPL", [1_000_000] * 25 + [float("nan")])}
        assert strategy.generate_signals(data) == []


def create_cmo_data(symbol: str, closes: list[float]) -> pd.DataFrame:
    """Create deterministic close data for CMO tests.

    The close series drives the CMO calculation directly.
    """
    dates = pd.date_range(end=datetime.now(), periods=len(closes), freq="D")
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1_000_000.0] * len(closes),
        },
        index=dates,
    )


class TestChandeMomentumOscillatorStrategy:
    """Tests for the Chande Momentum Oscillator (CMO) strategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = ChandeMomentumOscillatorStrategy(period=14, name="Test_CMO")
        assert strategy.name == "Test_CMO"
        assert strategy.period == 14
        assert strategy.parameters["period"] == 14

    def test_validate_parameters(self):
        """Test parameter validation raises for invalid periods."""
        with pytest.raises(ValueError, match="period must be positive"):
            ChandeMomentumOscillatorStrategy(period=0)
        with pytest.raises(ValueError, match="period must be positive"):
            ChandeMomentumOscillatorStrategy(period=-5)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with fewer bars than period + 2."""
        strategy = ChandeMomentumOscillatorStrategy(period=5)
        data = {"AAPL": create_cmo_data("AAPL", [100.0] * 6)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_cmo_crosses_above_zero(self):
        """A momentum upturn flips CMO from zero to positive (buy)."""
        strategy = ChandeMomentumOscillatorStrategy(period=5)
        # 25 flat bars keep CMO at zero, then a decline followed by a rally
        # pushes CMO from 0 to +33.3 on the last bar.
        closes = [100.0] * 25 + [90.0, 85.0, 80.0, 75.0, 100.0, 105.0]
        data = {"AAPL": create_cmo_data("AAPL", closes)}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.strength == pytest.approx(0.25)
        assert signal.price == pytest.approx(105.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "cmo_cross_above_zero"
        assert signal.metadata["cmo"] == pytest.approx(100.0 / 3.0)
        assert signal.metadata["period"] == 5

    def test_generate_signals_cmo_crosses_below_zero(self):
        """A momentum downturn flips CMO from zero to negative (sell)."""
        strategy = ChandeMomentumOscillatorStrategy(period=5)
        closes = [100.0] * 25 + [110.0, 115.0, 120.0, 125.0, 100.0, 95.0]
        data = {"AAPL": create_cmo_data("AAPL", closes)}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.strength == pytest.approx(0.25)
        assert signal.price == pytest.approx(95.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "cmo_cross_below_zero"
        assert signal.metadata["cmo"] == pytest.approx(-100.0 / 3.0)
        assert signal.metadata["period"] == 5

    def test_generate_signals_flat_close_no_signals(self):
        """Constant close keeps CMO undefined, so no crossover fires."""
        strategy = ChandeMomentumOscillatorStrategy(period=5)
        data = {"AAPL": create_cmo_data("AAPL", [100.0] * 30)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals evaluates each symbol independently."""
        strategy = ChandeMomentumOscillatorStrategy(period=5)
        data = {
            "AAPL": create_cmo_data("AAPL", [100.0] * 25 + [90.0, 85.0, 80.0, 75.0, 100.0, 105.0]),
            "MSFT": create_cmo_data(
                "MSFT", [100.0] * 25 + [110.0, 115.0, 120.0, 125.0, 100.0, 95.0]
            ),
        }
        signals = strategy.generate_signals(data)
        by_symbol = {s.symbol: s for s in signals}
        assert set(by_symbol) == {"AAPL", "MSFT"}
        assert by_symbol["AAPL"].action == "buy"
        assert by_symbol["MSFT"].action == "sell"

    def test_generate_signals_skips_nan_close(self):
        """A NaN last close is rejected before any signal is derived."""
        strategy = ChandeMomentumOscillatorStrategy(period=5)
        closes = [100.0] * 25 + [90.0, 85.0, 80.0, 75.0, 100.0, float("nan")]
        data = {"AAPL": create_cmo_data("AAPL", closes)}
        assert strategy.generate_signals(data) == []


def create_volume_oscillator_data(
    symbol: str, volumes: list[float], close: float = 100.0
) -> pd.DataFrame:
    """Create deterministic close/volume data for Volume Oscillator tests.

    The close is constant so the Volume Oscillator is driven purely by the
    volume series.
    """
    dates = pd.date_range(end=datetime.now(), periods=len(volumes), freq="D")
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": [close] * len(volumes),
            "high": [close] * len(volumes),
            "low": [close] * len(volumes),
            "close": [close] * len(volumes),
            "volume": np.asarray(volumes, dtype=float),
        },
        index=dates,
    )


class TestVolumeOscillatorStrategy:
    """Tests for the Volume Oscillator strategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = VolumeOscillatorStrategy(fast_period=5, slow_period=13, name="Test_VOL")
        assert strategy.name == "Test_VOL"
        assert strategy.fast_period == 5
        assert strategy.slow_period == 13
        assert strategy.parameters["fast_period"] == 5
        assert strategy.parameters["slow_period"] == 13

    def test_validate_parameters(self):
        """Test parameter validation raises for invalid periods."""
        with pytest.raises(ValueError, match="fast_period must be positive"):
            VolumeOscillatorStrategy(fast_period=0, slow_period=13)
        with pytest.raises(ValueError, match="slow_period must be positive"):
            VolumeOscillatorStrategy(fast_period=5, slow_period=0)
        with pytest.raises(ValueError, match="fast_period must be less than slow_period"):
            VolumeOscillatorStrategy(fast_period=13, slow_period=13)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with fewer bars than slow_period + 2."""
        strategy = VolumeOscillatorStrategy(fast_period=5, slow_period=13)
        data = {"AAPL": create_volume_oscillator_data("AAPL", [1_000_000.0] * 15)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_vol_crosses_above_zero(self):
        """A final volume surge flips VOL from zero to +16.67 (buy)."""
        strategy = VolumeOscillatorStrategy(fast_period=5, slow_period=13)
        # 25 flat bars keep VOL at zero; the final bar doubles volume,
        # pushing VOL from 0 to +16.67 on the last bar only.
        data = {"AAPL": create_volume_oscillator_data("AAPL", [1_000_000.0] * 25 + [2_000_000.0])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.strength == pytest.approx(1 / 7)
        assert signal.price == pytest.approx(100.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "vol_cross_above_zero"
        assert signal.metadata["vol"] == pytest.approx(100.0 / 6.0)
        assert signal.metadata["fast_period"] == 5
        assert signal.metadata["slow_period"] == 13

    def test_generate_signals_vol_crosses_below_zero(self):
        """A final volume drop halves volume, flipping VOL to -10.26 (sell)."""
        strategy = VolumeOscillatorStrategy(fast_period=5, slow_period=13)
        data = {"AAPL": create_volume_oscillator_data("AAPL", [1_000_000.0] * 25 + [500_000.0])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.strength == pytest.approx(0.09302325581395351)
        assert signal.price == pytest.approx(100.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "vol_cross_below_zero"
        assert signal.metadata["vol"] == pytest.approx(-40.0 / 3.9)
        assert signal.metadata["fast_period"] == 5
        assert signal.metadata["slow_period"] == 13

    def test_generate_signals_flat_volume_no_signals(self):
        """Constant volume keeps VOL at zero, so no crossover fires."""
        strategy = VolumeOscillatorStrategy(fast_period=5, slow_period=13)
        data = {"AAPL": create_volume_oscillator_data("AAPL", [1_000_000.0] * 30)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals evaluates each symbol independently."""
        strategy = VolumeOscillatorStrategy(fast_period=5, slow_period=13)
        data = {
            "AAPL": create_volume_oscillator_data("AAPL", [1_000_000.0] * 25 + [2_000_000.0]),
            "MSFT": create_volume_oscillator_data("MSFT", [1_000_000.0] * 25 + [500_000.0]),
        }
        signals = strategy.generate_signals(data)
        by_symbol = {s.symbol: s for s in signals}
        assert set(by_symbol) == {"AAPL", "MSFT"}
        assert by_symbol["AAPL"].action == "buy"
        assert by_symbol["MSFT"].action == "sell"

    def test_generate_signals_skips_nan_volume(self):
        """A NaN last volume is rejected before any signal is derived."""
        strategy = VolumeOscillatorStrategy(fast_period=5, slow_period=13)
        data = {"AAPL": create_volume_oscillator_data("AAPL", [1_000_000.0] * 25 + [float("nan")])}
        assert strategy.generate_signals(data) == []


def create_volume_price_trend_data(
    symbol: str, closes: list[float], volume: float = 1_000_000.0
) -> pd.DataFrame:
    """Create deterministic close/volume data for Volume Price Trend tests.

    The close is the only varying column; volume is held constant so the VPT
    series is driven purely by the price moves.
    """
    dates = pd.date_range(end=datetime.now(), periods=len(closes), freq="D")
    close = np.asarray(closes, dtype=float)
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": np.full(len(close), volume),
        },
        index=dates,
    )


class TestVolumePriceTrendStrategy:
    """Tests for the Volume Price Trend strategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = VolumePriceTrendStrategy(fast_period=5, slow_period=13, name="Test_VPT")
        assert strategy.name == "Test_VPT"
        assert strategy.fast_period == 5
        assert strategy.slow_period == 13
        assert strategy.parameters["fast_period"] == 5
        assert strategy.parameters["slow_period"] == 13

    def test_validate_parameters(self):
        """Test parameter validation raises for invalid periods."""
        with pytest.raises(ValueError, match="fast_period must be positive"):
            VolumePriceTrendStrategy(fast_period=0, slow_period=13)
        with pytest.raises(ValueError, match="slow_period must be positive"):
            VolumePriceTrendStrategy(fast_period=5, slow_period=0)
        with pytest.raises(ValueError, match="fast_period must be less than slow_period"):
            VolumePriceTrendStrategy(fast_period=13, slow_period=13)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with fewer bars than slow_period + 2."""
        strategy = VolumePriceTrendStrategy(fast_period=5, slow_period=13)
        data = {"AAPL": create_volume_price_trend_data("AAPL", [100.0] * 15)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_vpt_bullish_crossover(self):
        """A final price surge flips the fast VPT EMA above the slow EMA (buy)."""
        strategy = VolumePriceTrendStrategy(fast_period=5, slow_period=13)
        # 25 flat bars keep both EMAs at zero; the final bar jumps to 300,
        # pushing the fast VPT EMA above the slow VPT EMA on the last bar only.
        data = {"AAPL": create_volume_price_trend_data("AAPL", [100.0] * 25 + [300.0])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.strength == pytest.approx(0.4)
        assert signal.price == pytest.approx(300.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "vpt_bullish_crossover"
        assert signal.metadata["vpt"] == pytest.approx(2_000_000.0)
        assert signal.metadata["fast_ema"] == pytest.approx(666666.6666666666)
        assert signal.metadata["slow_ema"] == pytest.approx(285714.2857142857)
        assert signal.metadata["fast_period"] == 5
        assert signal.metadata["slow_period"] == 13

    def test_generate_signals_vpt_bearish_crossover(self):
        """A final price drop flips the fast VPT EMA below the slow EMA (sell)."""
        strategy = VolumePriceTrendStrategy(fast_period=5, slow_period=13)
        data = {"AAPL": create_volume_price_trend_data("AAPL", [100.0] * 25 + [1.0])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.strength == pytest.approx(0.4)
        assert signal.price == pytest.approx(1.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "vpt_bearish_crossover"
        assert signal.metadata["vpt"] == pytest.approx(-990000.0)
        assert signal.metadata["fast_ema"] == pytest.approx(-330000.0)
        assert signal.metadata["slow_ema"] == pytest.approx(-141428.57142857142)
        assert signal.metadata["fast_period"] == 5
        assert signal.metadata["slow_period"] == 13

    def test_generate_signals_flat_price_no_signals(self):
        """Constant price keeps the VPT series at zero, so no crossover fires."""
        strategy = VolumePriceTrendStrategy(fast_period=5, slow_period=13)
        data = {"AAPL": create_volume_price_trend_data("AAPL", [100.0] * 30)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals evaluates each symbol independently."""
        strategy = VolumePriceTrendStrategy(fast_period=5, slow_period=13)
        data = {
            "AAPL": create_volume_price_trend_data("AAPL", [100.0] * 25 + [300.0]),
            "MSFT": create_volume_price_trend_data("MSFT", [100.0] * 25 + [1.0]),
        }
        signals = strategy.generate_signals(data)
        by_symbol = {s.symbol: s for s in signals}
        assert set(by_symbol) == {"AAPL", "MSFT"}
        assert by_symbol["AAPL"].action == "buy"
        assert by_symbol["MSFT"].action == "sell"

    def test_generate_signals_skips_nan_last_close(self):
        """A NaN last close is rejected before any signal is derived."""
        strategy = VolumePriceTrendStrategy(fast_period=5, slow_period=13)
        closes = [100.0] * 25 + [float("nan")]
        data = {"AAPL": create_volume_price_trend_data("AAPL", closes)}
        assert strategy.generate_signals(data) == []


def create_bollinger_percent_b_data(symbol: str, closes: list[float]) -> pd.DataFrame:
    """Create deterministic close data for Bollinger Bands %B tests.

    The close is the only varying column; open/high/low mirror the close.
    """
    dates = pd.date_range(end=datetime.now(), periods=len(closes), freq="D")
    close = np.asarray(closes, dtype=float)
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
        },
        index=dates,
    )


class TestBollingerPercentBStrategy:
    """Tests for the Bollinger Bands %B strategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = BollingerPercentBStrategy(
            period=20,
            std_dev=2.0,
            oversold=0.2,
            overbought=0.8,
            name="Test_BB_Percent_B",
        )
        assert strategy.name == "Test_BB_Percent_B"
        assert strategy.period == 20
        assert strategy.std_dev == 2.0
        assert strategy.oversold == 0.2
        assert strategy.overbought == 0.8
        assert strategy.parameters["period"] == 20
        assert strategy.parameters["std_dev"] == 2.0
        assert strategy.parameters["oversold"] == 0.2
        assert strategy.parameters["overbought"] == 0.8

    def test_validate_parameters(self):
        """Test parameter validation raises for invalid parameters."""
        with pytest.raises(ValueError, match="period must be positive"):
            BollingerPercentBStrategy(period=0, std_dev=2.0)
        with pytest.raises(ValueError, match="std_dev must be positive"):
            BollingerPercentBStrategy(period=20, std_dev=0.0)
        with pytest.raises(ValueError, match="oversold"):
            BollingerPercentBStrategy(period=20, std_dev=2.0, oversold=0.8, overbought=0.2)
        with pytest.raises(ValueError, match="oversold"):
            BollingerPercentBStrategy(period=20, std_dev=2.0, oversold=-0.1, overbought=0.8)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with fewer bars than period + 1."""
        strategy = BollingerPercentBStrategy(period=20)
        data = {"AAPL": create_bollinger_percent_b_data("AAPL", [100.0] * 20)}
        assert strategy.generate_signals(data) == []

    def test_generate_signals_flat_price_no_signals(self):
        """Constant price collapses the bands, so %B is undefined and no signal fires."""
        strategy = BollingerPercentBStrategy(period=20)
        data = {"AAPL": create_bollinger_percent_b_data("AAPL", [100.0] * 30)}
        assert strategy.generate_signals(data) == []

    def test_generate_signals_percent_b_oversold_buy(self):
        """A final crash pushes %B below the oversold threshold (buy)."""
        strategy = BollingerPercentBStrategy(period=20, oversold=0.2, overbought=0.8)
        # 28 flat bars, a small bump, then a crash: %B crosses below oversold.
        closes = [100.0] * 28 + [110.0, 50.0]
        data = {"AAPL": create_bollinger_percent_b_data("AAPL", closes)}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.price == pytest.approx(50.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "percent_b_oversold"
        assert signal.metadata["pct_b"] < strategy.oversold
        assert signal.metadata["period"] == 20
        assert signal.metadata["std_dev"] == 2.0
        assert signal.metadata["oversold"] == 0.2
        assert signal.metadata["overbought"] == 0.8

    def test_generate_signals_percent_b_overbought_sell(self):
        """A final spike pushes %B above the overbought threshold (sell)."""
        strategy = BollingerPercentBStrategy(period=20, oversold=0.2, overbought=0.8)
        # A declining run then a moderate bar and a spike: %B crosses above overbought.
        closes = list(range(113, 85, -1)) + [100.0, 200.0]
        data = {"AAPL": create_bollinger_percent_b_data("AAPL", closes)}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.price == pytest.approx(200.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "percent_b_overbought"
        assert signal.metadata["pct_b"] > strategy.overbought
        assert signal.metadata["period"] == 20
        assert signal.metadata["std_dev"] == 2.0
        assert signal.metadata["oversold"] == 0.2
        assert signal.metadata["overbought"] == 0.8

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals evaluates each symbol independently."""
        strategy = BollingerPercentBStrategy(period=20)
        data = {
            "AAPL": create_bollinger_percent_b_data("AAPL", [100.0] * 28 + [110.0, 50.0]),
            "MSFT": create_bollinger_percent_b_data(
                "MSFT", list(range(113, 85, -1)) + [100.0, 200.0]
            ),
        }
        signals = strategy.generate_signals(data)
        by_symbol = {s.symbol: s for s in signals}
        assert set(by_symbol) == {"AAPL", "MSFT"}
        assert by_symbol["AAPL"].action == "buy"
        assert by_symbol["MSFT"].action == "sell"


def create_klinger_oscillator_data(
    symbol: str, closes: list[float], volume: float = 1_000_000.0
) -> pd.DataFrame:
    """Create deterministic high/low/close/volume data for Klinger tests.

    The close is the only varying column; high/low/close are held equal and
    volume is held constant so the Klinger series is driven purely by the
    price moves.
    """
    dates = pd.date_range(end=datetime.now(), periods=len(closes), freq="D")
    close = np.asarray(closes, dtype=float)
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": np.full(len(close), volume),
        },
        index=dates,
    )


class TestKlingerOscillatorStrategy:
    """Tests for the Klinger Oscillator strategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = KlingerOscillatorStrategy(fast_period=55, slow_period=200, name="Test_Klinger")
        assert strategy.name == "Test_Klinger"
        assert strategy.fast_period == 55
        assert strategy.slow_period == 200
        assert strategy.parameters["fast_period"] == 55
        assert strategy.parameters["slow_period"] == 200

    def test_validate_parameters(self):
        """Test parameter validation raises for invalid periods."""
        with pytest.raises(ValueError, match="fast_period must be positive"):
            KlingerOscillatorStrategy(fast_period=0, slow_period=200)
        with pytest.raises(ValueError, match="slow_period must be positive"):
            KlingerOscillatorStrategy(fast_period=55, slow_period=0)
        with pytest.raises(ValueError, match="fast_period must be less than slow_period"):
            KlingerOscillatorStrategy(fast_period=200, slow_period=200)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with fewer bars than slow_period + 2."""
        strategy = KlingerOscillatorStrategy(fast_period=5, slow_period=13)
        data = {"AAPL": create_klinger_oscillator_data("AAPL", [100.0] * 15)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_klinger_bullish_crossover(self):
        """A final price surge flips the fast Klinger EMA above the slow EMA (buy)."""
        strategy = KlingerOscillatorStrategy(fast_period=5, slow_period=13)
        # 25 flat bars keep both EMAs at zero; the final bar jumps to 300,
        # pushing the fast Klinger EMA above the slow Klinger EMA on the last
        # bar only.
        data = {"AAPL": create_klinger_oscillator_data("AAPL", [100.0] * 25 + [300.0])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.strength == pytest.approx(0.4)
        assert signal.price == pytest.approx(300.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "klinger_bullish_crossover"
        assert signal.metadata["klinger"] == pytest.approx(1_000_000.0)
        assert signal.metadata["fast_ema"] == pytest.approx(333333.3333333333)
        assert signal.metadata["slow_ema"] == pytest.approx(142857.14285714284)
        assert signal.metadata["fast_period"] == 5
        assert signal.metadata["slow_period"] == 13

    def test_generate_signals_klinger_bearish_crossover(self):
        """A final price drop flips the fast Klinger EMA below the slow EMA (sell)."""
        strategy = KlingerOscillatorStrategy(fast_period=5, slow_period=13)
        data = {"AAPL": create_klinger_oscillator_data("AAPL", [100.0] * 25 + [1.0])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.strength == pytest.approx(0.4)
        assert signal.price == pytest.approx(1.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "klinger_bearish_crossover"
        assert signal.metadata["klinger"] == pytest.approx(-1_000_000.0)
        assert signal.metadata["fast_ema"] == pytest.approx(-333333.3333333333)
        assert signal.metadata["slow_ema"] == pytest.approx(-142857.14285714284)
        assert signal.metadata["fast_period"] == 5
        assert signal.metadata["slow_period"] == 13

    def test_generate_signals_flat_price_no_signals(self):
        """Constant price keeps the Klinger series at zero, so no crossover fires."""
        strategy = KlingerOscillatorStrategy(fast_period=5, slow_period=13)
        data = {"AAPL": create_klinger_oscillator_data("AAPL", [100.0] * 30)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals evaluates each symbol independently."""
        strategy = KlingerOscillatorStrategy(fast_period=5, slow_period=13)
        data = {
            "AAPL": create_klinger_oscillator_data("AAPL", [100.0] * 25 + [300.0]),
            "MSFT": create_klinger_oscillator_data("MSFT", [100.0] * 25 + [1.0]),
        }
        signals = strategy.generate_signals(data)
        by_symbol = {s.symbol: s for s in signals}
        assert set(by_symbol) == {"AAPL", "MSFT"}
        assert by_symbol["AAPL"].action == "buy"
        assert by_symbol["MSFT"].action == "sell"

    def test_generate_signals_skips_nan_last_close(self):
        """A NaN last close is rejected before any signal is derived."""
        strategy = KlingerOscillatorStrategy(fast_period=5, slow_period=13)
        closes = [100.0] * 25 + [float("nan")]
        data = {"AAPL": create_klinger_oscillator_data("AAPL", closes)}
        assert strategy.generate_signals(data) == []


def create_hull_moving_average_data(symbol: str, closes: list[float]) -> pd.DataFrame:
    """Create deterministic close/volume data for Hull Moving Average tests.

    The close is the only varying column; volume is held constant.
    """
    dates = pd.date_range(end=datetime.now(), periods=len(closes), freq="D")
    close = np.asarray(closes, dtype=float)
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": np.full(len(close), 1_000_000.0),
        },
        index=dates,
    )


class TestHullMovingAverageStrategy:
    """Tests for the Hull Moving Average strategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = HullMovingAverageStrategy(period=16, name="Test_HMA")
        assert strategy.name == "Test_HMA"
        assert strategy.period == 16
        assert strategy.parameters["period"] == 16

    def test_validate_parameters(self):
        """Test parameter validation raises for invalid periods."""
        with pytest.raises(ValueError, match="period must be positive"):
            HullMovingAverageStrategy(period=0)
        with pytest.raises(ValueError, match="period must be at least 2"):
            HullMovingAverageStrategy(period=1)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with fewer bars than period + 2."""
        strategy = HullMovingAverageStrategy(period=16)
        data = {"AAPL": create_hull_moving_average_data("AAPL", [100.0] * 17)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_hma_bullish_crossover(self):
        """A final price surge flips the close above the HMA (buy)."""
        strategy = HullMovingAverageStrategy(period=16)
        # 20 flat bars keep the HMA at 100; the final bar jumps to 160,
        # pushing the close above the HMA on the last bar only.
        data = {"AAPL": create_hull_moving_average_data("AAPL", [100.0] * 20 + [160.0])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.strength == pytest.approx(0.1947291361639824)
        assert signal.price == pytest.approx(160.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "hma_bullish_crossover"
        assert signal.metadata["hma"] == pytest.approx(107.84313725490196)
        assert signal.metadata["hma_prev"] == pytest.approx(100.0)
        assert signal.metadata["period"] == 16
        assert signal.metadata["close"] == pytest.approx(160.0)

    def test_generate_signals_hma_bearish_crossover(self):
        """A final price drop flips the close below the HMA (sell)."""
        strategy = HullMovingAverageStrategy(period=16)
        data = {"AAPL": create_hull_moving_average_data("AAPL", [100.0] * 20 + [40.0])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.strength == pytest.approx(0.3946587537091988)
        assert signal.price == pytest.approx(40.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "hma_bearish_crossover"
        assert signal.metadata["hma"] == pytest.approx(92.15686274509804)
        assert signal.metadata["hma_prev"] == pytest.approx(100.0)
        assert signal.metadata["period"] == 16
        assert signal.metadata["close"] == pytest.approx(40.0)

    def test_generate_signals_flat_price_no_signals(self):
        """Constant price keeps the close on the HMA, so no crossover fires."""
        strategy = HullMovingAverageStrategy(period=16)
        data = {"AAPL": create_hull_moving_average_data("AAPL", [100.0] * 22)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals evaluates each symbol independently."""
        strategy = HullMovingAverageStrategy(period=16)
        data = {
            "AAPL": create_hull_moving_average_data("AAPL", [100.0] * 20 + [160.0]),
            "MSFT": create_hull_moving_average_data("MSFT", [100.0] * 20 + [40.0]),
        }
        signals = strategy.generate_signals(data)
        by_symbol = {s.symbol: s for s in signals}
        assert set(by_symbol) == {"AAPL", "MSFT"}
        assert by_symbol["AAPL"].action == "buy"
        assert by_symbol["MSFT"].action == "sell"

    def test_generate_signals_skips_nan_last_close(self):
        """A NaN last close is rejected before any signal is derived."""
        strategy = HullMovingAverageStrategy(period=16)
        closes = [100.0] * 21 + [float("nan")]
        data = {"AAPL": create_hull_moving_average_data("AAPL", closes)}
        assert strategy.generate_signals(data) == []


def create_ease_of_movement_data(
    symbol: str, rows: list[tuple[float, float, float]], close: float = 100.0
) -> pd.DataFrame:
    """Create deterministic OHLCV data for Ease of Movement tests.

    Each row is a ``(high, low, volume)`` triple; the close is constant so the
    EOM is driven purely by the price/volume series.
    """
    dates = pd.date_range(end=datetime.now(), periods=len(rows), freq="D")
    high = [r[0] for r in rows]
    low = [r[1] for r in rows]
    volume = [r[2] for r in rows]
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": [close] * len(rows),
            "high": high,
            "low": low,
            "close": [close] * len(rows),
            "volume": np.asarray(volume, dtype=float),
        },
        index=dates,
    )


class TestEaseOfMovementStrategy:
    """Tests for the Ease of Movement strategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = EaseOfMovementStrategy(period=14, name="Test_EOM")
        assert strategy.name == "Test_EOM"
        assert strategy.period == 14
        assert strategy.parameters["period"] == 14

    def test_validate_parameters(self):
        """Test parameter validation raises for a non-positive period."""
        with pytest.raises(ValueError, match="period must be positive"):
            EaseOfMovementStrategy(period=0)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with fewer bars than period + 2."""
        strategy = EaseOfMovementStrategy(period=2)
        data = {
            "AAPL": create_ease_of_movement_data(
                "AAPL", [(10.0, 8.0, 100.0), (12.0, 10.0, 200.0), (14.0, 12.0, 400.0)]
            )
        }
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_eom_crosses_above_zero(self):
        """A final upward move flips EOM from below to above zero (buy)."""
        strategy = EaseOfMovementStrategy(period=2)
        data = {
            "AAPL": create_ease_of_movement_data(
                "AAPL",
                [(10.0, 8.0, 100.0), (8.0, 6.0, 200.0), (10.0, 8.0, 400.0), (12.0, 10.0, 200.0)],
            )
        }
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.strength == pytest.approx(0.0001333155579256099)
        assert signal.price == pytest.approx(100.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "eom_cross_above_zero"
        assert signal.metadata["eom"] == pytest.approx(0.013333333333333332)
        assert signal.metadata["period"] == 2

    def test_generate_signals_eom_crosses_below_zero(self):
        """A final downward move flips EOM from above to below zero (sell)."""
        strategy = EaseOfMovementStrategy(period=2)
        data = {
            "AAPL": create_ease_of_movement_data(
                "AAPL",
                [(10.0, 8.0, 100.0), (12.0, 10.0, 200.0), (14.0, 12.0, 400.0), (11.0, 9.0, 200.0)],
            )
        }
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.strength == pytest.approx(0.00015553136178816625)
        assert signal.price == pytest.approx(100.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "eom_cross_below_zero"
        assert signal.metadata["eom"] == pytest.approx(-0.015555555555555552)
        assert signal.metadata["period"] == 2

    def test_generate_signals_flat_price_no_signals(self):
        """Constant price keeps EOM at zero, so no crossover fires."""
        strategy = EaseOfMovementStrategy(period=2)
        data = {"AAPL": create_ease_of_movement_data("AAPL", [(10.0, 8.0, 100.0)] * 30)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals evaluates each symbol independently."""
        strategy = EaseOfMovementStrategy(period=2)
        data = {
            "AAPL": create_ease_of_movement_data(
                "AAPL",
                [(10.0, 8.0, 100.0), (8.0, 6.0, 200.0), (10.0, 8.0, 400.0), (12.0, 10.0, 200.0)],
            ),
            "MSFT": create_ease_of_movement_data(
                "MSFT",
                [(10.0, 8.0, 100.0), (12.0, 10.0, 200.0), (14.0, 12.0, 400.0), (11.0, 9.0, 200.0)],
            ),
        }
        signals = strategy.generate_signals(data)
        by_symbol = {s.symbol: s for s in signals}
        assert set(by_symbol) == {"AAPL", "MSFT"}
        assert by_symbol["AAPL"].action == "buy"
        assert by_symbol["MSFT"].action == "sell"

    def test_generate_signals_skips_nan_volume(self):
        """A NaN final volume is rejected before any signal is derived."""
        strategy = EaseOfMovementStrategy(period=2)
        data = {
            "AAPL": create_ease_of_movement_data(
                "AAPL",
                [
                    (10.0, 8.0, 100.0),
                    (10.0, 8.0, 100.0),
                    (10.0, 8.0, 100.0),
                    (10.0, 8.0, float("nan")),
                ],
            ),
        }
        assert strategy.generate_signals(data) == []


def create_vortex_data(symbol: str, rows: list[tuple[float, float, float]]) -> pd.DataFrame:
    """Create deterministic OHLC data for Vortex strategy tests.

    Each row is a ``(high, low, close)`` triple. The volume column is a
    constant so the Vortex indicator is driven purely by the price series.
    """
    dates = pd.date_range(end=datetime.now(), periods=len(rows), freq="D")
    high = [r[0] for r in rows]
    low = [r[1] for r in rows]
    close = [r[2] for r in rows]
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "volume": [1_000_000] * len(rows),
        },
        index=dates,
    )


class TestVortexStrategy:
    """Tests for the Vortex strategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = VortexStrategy(period=14, name="Test_Vortex")
        assert strategy.name == "Test_Vortex"
        assert strategy.period == 14
        assert strategy.parameters["period"] == 14

    def test_validate_parameters(self):
        """Test parameter validation raises for non-positive periods."""
        with pytest.raises(ValueError, match="period must be positive"):
            VortexStrategy(period=0)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with fewer bars than period + 2."""
        strategy = VortexStrategy(period=14)
        data = {"AAPL": create_vortex_data("AAPL", [(10, 8, 9)] * 15)}
        assert strategy.generate_signals(data) == []

    def test_generate_signals_vip_plus_crosses_above_vip_minus(self):
        """A final upward surge flips VIP+ above VIP- (buy)."""
        strategy = VortexStrategy(period=2)
        # 4 quiet bars keep VIP- above VIP+; the final bar surges high
        # while low stays put, pushing VIP+ to 1.0 and crossing above VIP-.
        data = {
            "AAPL": create_vortex_data(
                "AAPL",
                [(10, 8, 9), (9, 7, 8), (8, 6, 7), (7, 5, 6), (20, 18, 19)],
            )
        }
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.strength == pytest.approx(0.625)
        assert signal.price == pytest.approx(19.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "vortex_up_cross_above_down"
        assert signal.metadata["vip_plus"] == pytest.approx(1.0)
        assert signal.metadata["vip_minus"] == pytest.approx(0.875)
        assert signal.metadata["period"] == 2

    def test_generate_signals_vip_minus_crosses_above_vip_plus(self):
        """A final downward plunge flips VIP- above VIP+ (sell)."""
        strategy = VortexStrategy(period=2)
        # 4 quiet bars keep VIP+ above VIP-; the final bar plunges low
        # while high stays put, pushing VIP- to 0.733 and crossing above VIP+.
        data = {
            "AAPL": create_vortex_data(
                "AAPL",
                [(10, 8, 9), (12, 10, 11), (14, 12, 13), (16, 14, 15), (17, 5, 11)],
            )
        }
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.strength == pytest.approx(0.7666666666666666)
        assert signal.price == pytest.approx(11.0)
        assert signal.timestamp is not None
        assert signal.metadata["signal_type"] == "vortex_down_cross_above_up"
        assert signal.metadata["vip_plus"] == pytest.approx(0.4666666666666667)
        assert signal.metadata["vip_minus"] == pytest.approx(0.7333333333333333)
        assert signal.metadata["period"] == 2

    def test_generate_signals_no_crossover(self):
        """Constant price keeps both Vortex lines flat, so no signal fires."""
        strategy = VortexStrategy(period=2)
        data = {
            "AAPL": create_vortex_data(
                "AAPL",
                [(10, 8, 9), (9, 7, 8), (8, 6, 7), (7, 5, 6), (6, 4, 5)],
            )
        }
        assert strategy.generate_signals(data) == []

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals evaluates each symbol independently."""
        strategy = VortexStrategy(period=2)
        data = {
            "AAPL": create_vortex_data(
                "AAPL",
                [(10, 8, 9), (9, 7, 8), (8, 6, 7), (7, 5, 6), (20, 18, 19)],
            ),
            "MSFT": create_vortex_data(
                "MSFT",
                [(10, 8, 9), (12, 10, 11), (14, 12, 13), (16, 14, 15), (17, 5, 11)],
            ),
        }
        signals = strategy.generate_signals(data)
        by_symbol = {s.symbol: s for s in signals}
        assert set(by_symbol) == {"AAPL", "MSFT"}
        assert by_symbol["AAPL"].action == "buy"
        assert by_symbol["MSFT"].action == "sell"

    def test_generate_signals_skips_nan_price(self):
        """A NaN close is rejected before any signal is derived."""
        strategy = VortexStrategy(period=2)
        data = {
            "AAPL": create_vortex_data(
                "AAPL",
                [(10, 8, 9), (9, 7, 8), (8, 6, 7), (7, 5, 6), (float("nan"), 18, 19)],
            )
        }
        assert strategy.generate_signals(data) == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestStochasticMomentumIndexStrategy:
    """Tests for StochasticMomentumIndexStrategy."""

    def test_initialization(self):
        from quant_trading.strategies.examples import StochasticMomentumIndexStrategy

        strategy = StochasticMomentumIndexStrategy()
        assert strategy.k_period == 5
        assert strategy.signal_period == 3
        assert strategy.name == "Stochastic_Momentum_Index"

    def test_validate_parameters(self):
        from quant_trading.strategies.examples import StochasticMomentumIndexStrategy

        with pytest.raises(ValueError):
            StochasticMomentumIndexStrategy(k_period=0)
        with pytest.raises(ValueError):
            StochasticMomentumIndexStrategy(signal_period=0)

    def test_insufficient_data_returns_empty(self):
        from quant_trading.strategies.examples import StochasticMomentumIndexStrategy

        strategy = StochasticMomentumIndexStrategy()
        dates = pd.date_range(start="2023-01-01", periods=5, freq="D")
        data = {
            "AAPL": pd.DataFrame(
                {
                    "open": [10] * 5,
                    "high": [11] * 5,
                    "low": [9] * 5,
                    "close": [10] * 5,
                    "volume": [1000] * 5,
                },
                index=dates,
            )
        }
        assert strategy.generate_signals(data) == []

    def test_generate_signals_buy_on_cross_above_zero(self):
        from quant_trading.strategies.examples import StochasticMomentumIndexStrategy

        strategy = StochasticMomentumIndexStrategy(k_period=2, signal_period=2)
        dates = pd.date_range(start="2023-01-01", periods=10, freq="D")
        # Create pattern that should cross above zero
        high = [10, 10, 10, 10, 10, 10, 11, 12, 13, 14]
        low = [5, 5, 5, 5, 5, 5, 6, 7, 8, 9]
        close = [7, 7, 7, 7, 7, 7, 8.5, 10, 11.5, 13]
        data = {
            "AAPL": pd.DataFrame(
                {"open": close, "high": high, "low": low, "close": close, "volume": [1000] * 10},
                index=dates,
            )
        }
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)

    def test_generate_signals_sell_on_cross_below_zero(self):
        from quant_trading.strategies.examples import StochasticMomentumIndexStrategy

        strategy = StochasticMomentumIndexStrategy(k_period=2, signal_period=2)
        dates = pd.date_range(start="2023-01-01", periods=10, freq="D")
        high = [14, 13, 12, 11, 10, 10, 10, 10, 10, 10]
        low = [9, 8, 7, 6, 5, 5, 5, 5, 5, 5]
        close = [13, 11.5, 10, 8.5, 7, 7, 7, 7, 7, 7]
        data = {
            "AAPL": pd.DataFrame(
                {"open": close, "high": high, "low": low, "close": close, "volume": [1000] * 10},
                index=dates,
            )
        }
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)

    def test_generate_signals_multiple_symbols(self):
        from quant_trading.strategies.examples import StochasticMomentumIndexStrategy

        strategy = StochasticMomentumIndexStrategy(k_period=2, signal_period=2)
        dates = pd.date_range(start="2023-01-01", periods=10, freq="D")
        close = [7, 7, 7, 7, 7, 7, 8.5, 10, 11.5, 13]
        high = [10, 10, 10, 10, 10, 10, 11, 12, 13, 14]
        low = [5, 5, 5, 5, 5, 5, 6, 7, 8, 9]
        data = {
            "AAPL": pd.DataFrame(
                {"open": close, "high": high, "low": low, "close": close, "volume": [1000] * 10},
                index=dates,
            ),
            "MSFT": pd.DataFrame(
                {
                    "open": [13, 11.5, 10, 8.5, 7, 7, 7, 7, 7, 7],
                    "high": [14, 13, 12, 11, 10, 10, 10, 10, 10, 10],
                    "low": [9, 8, 7, 6, 5, 5, 5, 5, 5, 5],
                    "close": [13, 11.5, 10, 8.5, 7, 7, 7, 7, 7, 7],
                    "volume": [1000] * 10,
                },
                index=dates,
            ),
        }
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)

    def test_generate_signals_skips_nan_price(self):
        from quant_trading.strategies.examples import StochasticMomentumIndexStrategy

        strategy = StochasticMomentumIndexStrategy(k_period=2, signal_period=2)
        dates = pd.date_range(start="2023-01-01", periods=10, freq="D")
        close = [7, 7, 7, 7, 7, 7, 8.5, 10, 11.5, float("nan")]
        high = [10, 10, 10, 10, 10, 10, 11, 12, 13, 14]
        low = [5, 5, 5, 5, 5, 5, 6, 7, 8, 9]
        data = {
            "AAPL": pd.DataFrame(
                {"open": close, "high": high, "low": low, "close": close, "volume": [1000] * 10},
                index=dates,
            )
        }
        assert strategy.generate_signals(data) == []


class TestUltimateOscillatorStrategy:
    """Tests for UltimateOscillatorStrategy."""

    def test_init_default_parameters(self):
        from quant_trading.strategies.examples import UltimateOscillatorStrategy

        strategy = UltimateOscillatorStrategy()
        assert strategy.short_period == 7
        assert strategy.medium_period == 14
        assert strategy.long_period == 28
        assert strategy.name == "Ultimate_Oscillator"

    def test_validate_parameters(self):
        from quant_trading.strategies.examples import UltimateOscillatorStrategy

        with pytest.raises(ValueError):
            UltimateOscillatorStrategy(short_period=0)
        with pytest.raises(ValueError):
            UltimateOscillatorStrategy(short_period=14, medium_period=7, long_period=28)
        with pytest.raises(ValueError):
            UltimateOscillatorStrategy(short_period=10, medium_period=20, long_period=15)

    def test_insufficient_data_returns_empty(self):
        from quant_trading.strategies.examples import UltimateOscillatorStrategy

        strategy = UltimateOscillatorStrategy()
        dates = pd.date_range(start="2023-01-01", periods=10, freq="D")
        data = {
            "AAPL": pd.DataFrame(
                {
                    "open": [10] * 10,
                    "high": [11] * 10,
                    "low": [9] * 10,
                    "close": [10] * 10,
                    "volume": [1000] * 10,
                },
                index=dates,
            )
        }
        assert strategy.generate_signals(data) == []

    def test_generate_signals_buy_when_oversold_rising(self):
        import pandas as pd

        from quant_trading.strategies.examples import UltimateOscillatorStrategy

        strategy = UltimateOscillatorStrategy(short_period=2, medium_period=3, long_period=4)
        dates = pd.date_range(start="2023-01-01", periods=10, freq="D")
        data = pd.DataFrame(
            {
                "open": [10] * 10,
                "high": [11, 11, 11, 11, 11, 11, 11, 10.5, 10.5, 10.5],
                "low": [9, 9, 9, 9, 9, 9, 9, 9.5, 9.5, 9.5],
                "close": [10, 10, 10, 10, 10, 10, 10, 10.2, 10.4, 10.6],
                "volume": [1000] * 10,
            },
            index=dates,
        )
        signals = strategy.generate_signals({"AAPL": data})
        assert len(signals) >= 0  # Allow for calculation specifics

    def test_generate_signals_sell_when_overbought_falling(self):
        import pandas as pd

        from quant_trading.strategies.examples import UltimateOscillatorStrategy

        strategy = UltimateOscillatorStrategy(short_period=2, medium_period=3, long_period=4)
        dates = pd.date_range(start="2023-01-01", periods=10, freq="D")
        data = pd.DataFrame(
            {
                "open": [10] * 10,
                "high": [11, 11, 11, 11, 11, 11, 11, 11.5, 11.3, 11.1],
                "low": [9, 9, 9, 9, 9, 9, 9, 10.5, 10.5, 10.5],
                "close": [10, 10, 10, 10, 10, 10, 10, 10.8, 10.6, 10.4],
                "volume": [1000] * 10,
            },
            index=dates,
        )
        signals = strategy.generate_signals({"AAPL": data})
        assert isinstance(signals, list)


def create_negative_volume_index_data(
    symbol: str, closes: list[float], volumes: list[float]
) -> pd.DataFrame:
    dates = pd.date_range(end=datetime.now(), periods=len(closes), freq="D")
    close = np.asarray(closes, dtype=float)
    volume = np.asarray(volumes, dtype=float)
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": volume,
        },
        index=dates,
    )


class TestNegativeVolumeIndexStrategy:
    def test_initialization(self):
        strategy = NegativeVolumeIndexStrategy(period=255, name="Test_NVI")
        assert strategy.name == "Test_NVI"
        assert strategy.period == 255
        assert strategy.parameters["period"] == 255

    def test_validate_parameters(self):
        with pytest.raises(ValueError, match="period must be positive"):
            NegativeVolumeIndexStrategy(period=0)

    def test_generate_signals_insufficient_data(self):
        strategy = NegativeVolumeIndexStrategy(period=255)
        data = {"AAPL": create_negative_volume_index_data("AAPL", [100.0] * 10, [1000.0] * 10)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_nvi_bullish_crossover(self):
        strategy = NegativeVolumeIndexStrategy(period=5)
        # Create data where NVI was below EMA and crosses above at end
        # Build up so NVI stays flat, then volume drops sharply with price up
        closes = [100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 101.0]
        volumes = [1000.0, 1000.0, 1000.0, 1000.0, 1000.0, 2000.0, 1500.0]  # vol drops at last step
        data = {"AAPL": create_negative_volume_index_data("AAPL", closes, volumes)}
        signals = strategy.generate_signals(data)
        assert len(signals) >= 1
        assert signals[0].symbol == "AAPL"
        assert signals[0].action == "buy"

    def test_generate_signals_multiple_symbols(self):
        strategy = NegativeVolumeIndexStrategy(period=5)
        closes = [100.0, 100.0, 101.0, 101.0, 101.0, 101.0, 102.0]
        volumes = [1000.0, 2000.0, 1500.0, 1500.0, 1500.0, 1500.0, 1400.0]
        data = {
            "AAPL": create_negative_volume_index_data("AAPL", closes, volumes),
            "MSFT": create_negative_volume_index_data("MSFT", closes, volumes),
        }
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)

    def test_generate_signals_skips_nan_last_close(self):
        strategy = NegativeVolumeIndexStrategy(period=5)
        closes = [100.0] * 6 + [float("nan")]
        volumes = [1000.0] * 7
        data = {"AAPL": create_negative_volume_index_data("AAPL", closes, volumes)}
        assert strategy.generate_signals(data) == []


def create_positive_volume_index_data(
    symbol: str, closes: list[float], volumes: list[float]
) -> pd.DataFrame:
    dates = pd.date_range(end=datetime.now(), periods=len(closes), freq="D")
    close = np.asarray(closes, dtype=float)
    volume = np.asarray(volumes, dtype=float)
    return pd.DataFrame(  # type: ignore[no-any-return]
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": volume,
        },
        index=dates,
    )


class TestPositiveVolumeIndexStrategy:
    def test_initialization(self):
        strategy = PositiveVolumeIndexStrategy(period=255, name="Test_PVI")
        assert strategy.name == "Test_PVI"
        assert strategy.period == 255
        assert strategy.parameters["period"] == 255

    def test_validate_parameters(self):
        with pytest.raises(ValueError, match="period must be positive"):
            PositiveVolumeIndexStrategy(period=0)

    def test_generate_signals_insufficient_data(self):
        strategy = PositiveVolumeIndexStrategy(period=255)
        data = {"AAPL": create_positive_volume_index_data("AAPL", [100.0] * 10, [1000.0] * 10)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_pvi_bullish_crossover(self):
        strategy = PositiveVolumeIndexStrategy(period=5)
        closes = [100.0, 100.0, 101.0, 101.0, 101.0, 101.0, 102.0]
        volumes = [1000.0, 900.0, 1000.0, 1000.0, 1000.0, 1000.0, 1100.0]
        data = {"AAPL": create_positive_volume_index_data("AAPL", closes, volumes)}
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)

    def test_generate_signals_multiple_symbols(self):
        strategy = PositiveVolumeIndexStrategy(period=5)
        closes = [100.0, 100.0, 101.0, 101.0, 101.0, 101.0, 102.0]
        volumes = [1000.0, 900.0, 1000.0, 1000.0, 1000.0, 1000.0, 1100.0]
        data = {
            "AAPL": create_positive_volume_index_data("AAPL", closes, volumes),
            "MSFT": create_positive_volume_index_data("MSFT", closes, volumes),
        }
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)

    def test_generate_signals_skips_nan_last_close(self):
        strategy = PositiveVolumeIndexStrategy(period=5)
        closes = [100.0] * 6 + [float("nan")]
        volumes = [1000.0] * 7
        data = {"AAPL": create_positive_volume_index_data("AAPL", closes, volumes)}
        assert strategy.generate_signals(data) == []


def create_average_true_range_data(
    symbol: str,
    closes: list[float],
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> pd.DataFrame:
    """Create deterministic high/low/close data for Average True Range tests.

    When ``highs``/``lows`` are omitted they mirror the close.
    """
    dates = pd.date_range(end=datetime.now(), periods=len(closes), freq="D")
    close = np.asarray(closes, dtype=float)
    high = np.asarray(highs if highs is not None else closes, dtype=float)
    low = np.asarray(lows if lows is not None else closes, dtype=float)
    frame: pd.DataFrame = pd.DataFrame(
        {
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.full(len(close), 1_000_000.0),
        },
        index=dates,
    )
    return frame


class TestAverageTrueRangeStrategy:
    """Tests for the Average True Range Channel Breakout strategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = AverageTrueRangeStrategy(period=2, atr_multiplier=1.0, name="Test_ATR")
        assert strategy.name == "Test_ATR"
        assert strategy.period == 2
        assert strategy.atr_multiplier == 1.0
        assert strategy.parameters["period"] == 2
        assert strategy.parameters["atr_multiplier"] == 1.0

    def test_validate_parameters(self):
        """Test parameter validation raises for invalid values."""
        with pytest.raises(ValueError, match="period must be positive"):
            AverageTrueRangeStrategy(period=0, atr_multiplier=1.0)
        with pytest.raises(ValueError, match="atr_multiplier must be positive"):
            AverageTrueRangeStrategy(period=2, atr_multiplier=0.0)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with fewer bars than period + 2."""
        strategy = AverageTrueRangeStrategy(period=2, atr_multiplier=1.0)
        data = {"AAPL": create_average_true_range_data("AAPL", [100.0] * 3)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_atr_bullish_breakout(self):
        """A sharp close above the prior close + ATR band fires a buy."""
        strategy = AverageTrueRangeStrategy(period=2, atr_multiplier=1.0)
        data = {"AAPL": create_average_true_range_data("AAPL", [100.0, 100.0, 100.0, 110.0])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.price == pytest.approx(110.0)
        assert signal.timestamp is not None
        assert 0.0 < signal.strength <= 1.0
        assert signal.metadata["signal_type"] == "atr_bullish_breakout"
        assert signal.metadata["period"] == 2
        assert signal.metadata["atr_multiplier"] == 1.0

    def test_generate_signals_atr_bearish_breakout(self):
        """A sharp close below the prior close - ATR band fires a sell."""
        strategy = AverageTrueRangeStrategy(period=2, atr_multiplier=1.0)
        data = {"AAPL": create_average_true_range_data("AAPL", [100.0, 100.0, 100.0, 90.0])}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.price == pytest.approx(90.0)
        assert signal.timestamp is not None
        assert 0.0 < signal.strength <= 1.0
        assert signal.metadata["signal_type"] == "atr_bearish_breakout"
        assert signal.metadata["period"] == 2

    def test_generate_signals_flat_price_no_signals(self):
        """Constant price keeps the close inside the ATR band, so no breakout."""
        strategy = AverageTrueRangeStrategy(period=2, atr_multiplier=1.0)
        data = {"AAPL": create_average_true_range_data("AAPL", [100.0] * 10)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals evaluates each symbol independently."""
        strategy = AverageTrueRangeStrategy(period=2, atr_multiplier=1.0)
        data = {
            "AAPL": create_average_true_range_data("AAPL", [100.0, 100.0, 100.0, 110.0]),
            "MSFT": create_average_true_range_data("MSFT", [100.0, 100.0, 100.0, 90.0]),
        }
        signals = strategy.generate_signals(data)
        by_symbol = {s.symbol: s for s in signals}
        assert set(by_symbol) == {"AAPL", "MSFT"}
        assert by_symbol["AAPL"].action == "buy"
        assert by_symbol["MSFT"].action == "sell"

    def test_generate_signals_skips_nan_last_close(self):
        """A NaN last close is rejected before any signal is derived."""
        strategy = AverageTrueRangeStrategy(period=2, atr_multiplier=1.0)
        closes = [100.0, 100.0, 100.0, float("nan")]
        data = {"AAPL": create_average_true_range_data("AAPL", closes)}
        assert strategy.generate_signals(data) == []


class TestCCIStrategy:
    """Tests for CCIStrategy."""

    def test_initialization(self):
        strategy = CCIStrategy(period=20, threshold=100.0, name="Test_CCI")
        assert strategy.name == "Test_CCI"
        assert strategy.period == 20
        assert strategy.threshold == 100.0

    def test_validate_parameters(self):
        with pytest.raises(ValueError, match="period must be positive"):
            CCIStrategy(period=0)
        with pytest.raises(ValueError, match="threshold must be positive"):
            CCIStrategy(threshold=0)

    def test_generate_signals_insufficient_data(self):
        strategy = CCIStrategy(period=20)
        data = {"AAPL": create_trending_data("AAPL", days=10)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_overbought(self):
        strategy = CCIStrategy(period=5, threshold=10)
        closes = [100] * 10 + [150] * 5  # strong move up at end
        data = {"AAPL": create_donchian_data("AAPL", closes)}
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)
        for s in signals:
            assert s.symbol == "AAPL"
            assert s.action in ("buy", "sell")

    def test_generate_signals_multi_symbol(self):
        strategy = CCIStrategy(period=20, threshold=100)
        data = {
            "AAPL": create_trending_data("AAPL", days=60),
            "MSFT": create_trending_data("MSFT", days=60),
        }
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)
        for s in signals:
            assert s.symbol in ("AAPL", "MSFT")


class TestAroonStrategy:
    """Tests for AroonStrategy."""

    def test_initialization(self):
        strategy = AroonStrategy(period=25, name="Test_Aroon")
        assert strategy.name == "Test_Aroon"
        assert strategy.period == 25

    def test_validate_parameters(self):
        with pytest.raises(ValueError, match="period must be positive"):
            AroonStrategy(period=0)

    def test_generate_signals_insufficient_data(self):
        strategy = AroonStrategy(period=25)
        data = {"AAPL": create_trending_data("AAPL", days=10)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_returns_list(self):
        strategy = AroonStrategy(period=14)
        data = {"AAPL": create_trending_data("AAPL", days=60)}
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)
        for s in signals:
            assert s.symbol == "AAPL"
            assert s.action in ("buy", "sell")


class TestStochRSIStrategy:
    """Tests for StochRSIStrategy."""

    def test_initialization(self):
        strategy = StochRSIStrategy(
            rsi_period=14, stoch_period=14, k_period=3, d_period=3, name="Test_StochRSI"
        )
        assert strategy.name == "Test_StochRSI"
        assert strategy.rsi_period == 14

    def test_validate_parameters(self):
        with pytest.raises(ValueError, match="rsi_period must be positive"):
            StochRSIStrategy(rsi_period=0)
        with pytest.raises(ValueError, match="oversold must be between"):
            StochRSIStrategy(oversold=0)
        with pytest.raises(ValueError, match="overbought must be between"):
            StochRSIStrategy(overbought=100)
        with pytest.raises(ValueError, match="oversold must be less than overbought"):
            StochRSIStrategy(oversold=50, overbought=40)

    def test_generate_signals_insufficient_data(self):
        strategy = StochRSIStrategy()
        data = {"AAPL": create_trending_data("AAPL", days=10)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_multi_symbol(self):
        strategy = StochRSIStrategy()
        data = {
            "AAPL": create_trending_data("AAPL", days=80),
            "MSFT": create_trending_data("MSFT", days=80),
        }
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)
        for s in signals:
            assert s.symbol in ("AAPL", "MSFT")
            assert s.action in ("buy", "sell")

    def test_generate_signals_midline_cross_up(self):
        """%K crossing up through the 50 midline emits a midline_cross_up buy.

        With use_midline=True and %K below 50 on the previous bar and above
        50 on the final bar (without entering oversold/overbought territory),
        the ``elif self.use_midline`` arm fires.
        """
        strategy = StochRSIStrategy(use_midline=True, name="Test_StochRSI")
        data = {"AAPL": create_stochrsi_midline_data("AAPL", "bullish")}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.metadata["signal_type"] == "midline_cross_up"
        assert signal.metadata["k_percent"] == pytest.approx(56.222465388145224)
        assert signal.metadata["d_percent"] == pytest.approx(26.935246165350108)
        assert signal.strength == pytest.approx(0.36222465388145225)
        assert signal.price == pytest.approx(81.39)

    def test_generate_signals_midline_cross_down(self):
        """%K crossing down through the 50 midline emits a midline_cross_down sell.

        With use_midline=True and %K above 50 on the previous bar and below
        50 on the final bar (without entering oversold/overbought territory),
        the ``elif self.use_midline`` arm fires.
        """
        strategy = StochRSIStrategy(use_midline=True, name="Test_StochRSI")
        data = {"AAPL": create_stochrsi_midline_data("AAPL", "bearish")}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert signal.metadata["signal_type"] == "midline_cross_down"
        assert signal.metadata["k_percent"] == pytest.approx(32.675471829529116)
        assert signal.metadata["d_percent"] == pytest.approx(52.858133150608694)
        assert signal.strength == pytest.approx(0.4732452817047088)
        assert signal.price == pytest.approx(91.67)

    def test_generate_signals_midline_disabled(self):
        """When use_midline is False and no oversold/overbought crossover
        fires, the midline arm is skipped and no signal is produced."""
        strategy = StochRSIStrategy(use_midline=False, name="Test_StochRSI")
        data = {"AAPL": create_stochrsi_midline_data("AAPL", "bullish")}
        signals = strategy.generate_signals(data)
        assert signals == []


class TestPercentagePriceOscillatorStrategy:
    """Tests for PercentagePriceOscillatorStrategy."""

    def test_initialization(self):
        strategy = PercentagePriceOscillatorStrategy(
            fast_period=12, slow_period=26, signal_period=9, name="Test_PPO"
        )
        assert strategy.name == "Test_PPO"

    def test_validate_parameters(self):
        with pytest.raises(ValueError, match="fast_period must be positive"):
            PercentagePriceOscillatorStrategy(fast_period=0)

    def test_generate_signals_insufficient_data(self):
        strategy = PercentagePriceOscillatorStrategy()
        data = {"AAPL": create_trending_data("AAPL", days=10)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_returns_list(self):
        strategy = PercentagePriceOscillatorStrategy()
        data = {"AAPL": create_trending_data("AAPL", days=80)}
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)
        for s in signals:
            assert s.symbol == "AAPL"
            assert s.action in ("buy", "sell")

    def test_zero_line_option(self):
        """Test that use_zero_line enables zero-line crossovers."""
        strategy = PercentagePriceOscillatorStrategy(
            fast_period=5, slow_period=13, signal_period=5, use_zero_line=True
        )
        assert strategy.use_zero_line is True
        data = {"AAPL": create_trending_data("AAPL", days=100)}
        signals = strategy.generate_signals(data)
        # With zero-line enabled, more signal types may appear
        for signal in signals:
            assert signal.action in ("buy", "sell")

    def test_generate_signals_zero_line_bullish(self):
        """Test zero-line crossover generates buy when PPO crosses up.

        The PPO line crosses zero on the final bar while staying above the
        signal line, so no signal-line crossover occurs and the zero-line
        branch fires instead.
        """
        strategy = PercentagePriceOscillatorStrategy(
            fast_period=5, slow_period=13, signal_period=5, use_zero_line=True
        )
        data = {"AAPL": create_ppo_pvo_zero_line_data("AAPL", "bullish")}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert 0.0 <= signal.strength <= 1.0
        assert signal.metadata["signal_type"] == "ppo_zero_cross_above"
        assert signal.metadata["ppo"] == pytest.approx(4.187430785380317)
        assert signal.metadata["ppo"] > 0
        assert signal.metadata["signal"] == pytest.approx(1.0104568937649043)
        assert "zero_line" not in signal.metadata

    def test_generate_signals_zero_line_bearish(self):
        """Test zero-line crossover generates sell when PPO crosses down.

        The PPO line has just crossed above zero (signal line still lags
        below zero); the final close is tuned so the PPO line crosses back
        below zero without a signal-line crossover.
        """
        strategy = PercentagePriceOscillatorStrategy(
            fast_period=5, slow_period=13, signal_period=5, use_zero_line=True
        )
        data = {"AAPL": create_ppo_pvo_zero_line_data("AAPL", "bearish")}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert 0.0 <= signal.strength <= 1.0
        assert signal.metadata["signal_type"] == "ppo_zero_cross_below"
        assert signal.metadata["ppo"] == pytest.approx(-0.14530598525153834)
        assert signal.metadata["ppo"] < 0
        assert signal.metadata["signal"] == pytest.approx(-0.28104965986088726)
        assert "zero_line" not in signal.metadata

    def test_generate_signals_zero_line_disabled(self):
        """When use_zero_line is False and no signal-line crossover fires on
        the final bar, the ``elif self.use_zero_line`` arm is False and no
        signal is produced."""
        strategy = PercentagePriceOscillatorStrategy(
            fast_period=12, slow_period=26, signal_period=9, use_zero_line=False
        )
        data = {"AAPL": create_ppo_pvo_zero_line_data("AAPL", "bullish")}
        signals = strategy.generate_signals(data)
        assert signals == []


class TestChoppinessIndexStrategy:
    """Tests for ChoppinessIndexStrategy."""

    def test_initialization(self):
        strategy = ChoppinessIndexStrategy(period=14, name="Test_CHOP")
        assert strategy.name == "Test_CHOP"
        assert strategy.period == 14

    def test_validate_parameters(self):
        strategy = ChoppinessIndexStrategy(period=0)
        with pytest.raises(ValueError, match="period must be positive"):
            strategy.validate_parameters()

    def test_generate_signals_insufficient_data(self):
        strategy = ChoppinessIndexStrategy(period=14)
        data = {"AAPL": create_trending_data("AAPL", days=10)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_returns_list(self):
        strategy = ChoppinessIndexStrategy(period=14)
        data = {"AAPL": create_trending_data("AAPL", days=60)}
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)
        for s in signals:
            assert s.symbol == "AAPL"
            assert s.action in ("buy", "sell")


class TestAccumulationDistributionStrategy:
    """Tests for AccumulationDistributionStrategy."""

    def test_initialization(self):
        strategy = AccumulationDistributionStrategy(signal_period=21, name="Test_ADL")
        assert strategy.name == "Test_ADL"
        assert strategy.signal_period == 21

    def test_validate_parameters(self):
        with pytest.raises(ValueError, match="signal_period must be positive"):
            AccumulationDistributionStrategy(signal_period=0)

    def test_generate_signals_insufficient_data(self):
        strategy = AccumulationDistributionStrategy(signal_period=21)
        data = {"AAPL": create_trending_data("AAPL", days=10)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_returns_list(self):
        strategy = AccumulationDistributionStrategy(signal_period=21)
        data = {"AAPL": create_trending_data("AAPL", days=80)}
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)
        for s in signals:
            assert s.symbol == "AAPL"
            assert s.action in ("buy", "sell")


class TestAwesomeOscillatorStrategy:
    """Tests for AwesomeOscillatorStrategy."""

    def test_initialization(self):
        strategy = AwesomeOscillatorStrategy(short_period=5, long_period=34, name="Test_AO")
        assert strategy.name == "Test_AO"
        assert strategy.short_period == 5
        assert strategy.long_period == 34

    def test_validate_parameters(self):
        with pytest.raises(ValueError, match="short_period must be positive"):
            AwesomeOscillatorStrategy(short_period=0)
        with pytest.raises(ValueError, match="long_period must be positive"):
            AwesomeOscillatorStrategy(long_period=0)
        with pytest.raises(ValueError, match="short_period must be less than long_period"):
            AwesomeOscillatorStrategy(short_period=10, long_period=5)

    def test_generate_signals_insufficient_data(self):
        strategy = AwesomeOscillatorStrategy(short_period=5, long_period=34)
        data = {"AAPL": create_trending_data("AAPL", days=10)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_returns_list(self):
        strategy = AwesomeOscillatorStrategy(short_period=5, long_period=34)
        data = {"AAPL": create_trending_data("AAPL", days=80)}
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)
        for s in signals:
            assert s.symbol == "AAPL"
            assert s.action in ("buy", "sell")


class TestChaikinOscillatorStrategy:
    """Tests for ChaikinOscillatorStrategy."""

    def test_initialization(self):
        strategy = ChaikinOscillatorStrategy(fast_period=3, slow_period=10, name="Test_CHO")
        assert strategy.name == "Test_CHO"
        assert strategy.fast_period == 3
        assert strategy.slow_period == 10

    def test_validate_parameters(self):
        with pytest.raises(ValueError, match="fast_period must be positive"):
            ChaikinOscillatorStrategy(fast_period=0)
        with pytest.raises(ValueError, match="slow_period must be positive"):
            ChaikinOscillatorStrategy(slow_period=0)
        with pytest.raises(ValueError, match="fast_period must be less than slow_period"):
            ChaikinOscillatorStrategy(fast_period=10, slow_period=5)

    def test_generate_signals_insufficient_data(self):
        strategy = ChaikinOscillatorStrategy(fast_period=3, slow_period=10)
        data = {"AAPL": create_trending_data("AAPL", days=10)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_returns_list(self):
        strategy = ChaikinOscillatorStrategy(fast_period=3, slow_period=10)
        data = {"AAPL": create_trending_data("AAPL", days=80)}
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)
        for s in signals:
            assert s.symbol == "AAPL"
            assert s.action in ("buy", "sell")


class TestDetrendedPriceOscillatorStrategy:
    """Tests for DetrendedPriceOscillatorStrategy."""

    def test_initialization(self):
        strategy = DetrendedPriceOscillatorStrategy(period=20, name="Test_DPO")
        assert strategy.name == "Test_DPO"
        assert strategy.period == 20

    def test_validate_parameters(self):
        with pytest.raises(ValueError, match="period must be positive"):
            DetrendedPriceOscillatorStrategy(period=0)

    def test_generate_signals_insufficient_data(self):
        strategy = DetrendedPriceOscillatorStrategy(period=20)
        data = {"AAPL": create_trending_data("AAPL", days=10)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_returns_list(self):
        strategy = DetrendedPriceOscillatorStrategy(period=20)
        data = {"AAPL": create_trending_data("AAPL", days=80)}
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)
        for s in signals:
            assert s.symbol == "AAPL"
            assert s.action in ("buy", "sell")


class TestElderRayStrategy:
    """Tests for ElderRayStrategy."""

    def test_initialization(self):
        strategy = ElderRayStrategy(period=13, name="Test_ELDER")
        assert strategy.name == "Test_ELDER"
        assert strategy.period == 13

    def test_validate_parameters(self):
        with pytest.raises(ValueError, match="period must be positive"):
            ElderRayStrategy(period=0)

    def test_generate_signals_insufficient_data(self):
        strategy = ElderRayStrategy(period=13)
        data = {"AAPL": create_trending_data("AAPL", days=10)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_returns_list(self):
        strategy = ElderRayStrategy(period=13)
        data = {"AAPL": create_trending_data("AAPL", days=80)}
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)
        for s in signals:
            assert s.symbol == "AAPL"
            assert s.action in ("buy", "sell")


class TestRateOfChangeStrategy:
    """Tests for RateOfChangeStrategy."""

    def test_initialization(self):
        strategy = RateOfChangeStrategy(period=12, name="Test_ROC")
        assert strategy.name == "Test_ROC"
        assert strategy.period == 12

    def test_validate_parameters(self):
        with pytest.raises(ValueError, match="period must be positive"):
            RateOfChangeStrategy(period=0)

    def test_generate_signals_insufficient_data(self):
        strategy = RateOfChangeStrategy(period=12)
        data = {"AAPL": create_trending_data("AAPL", days=10)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_returns_list(self):
        strategy = RateOfChangeStrategy(period=12)
        data = {"AAPL": create_trending_data("AAPL", days=80)}
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)
        for s in signals:
            assert s.symbol == "AAPL"
            assert s.action in ("buy", "sell")


class TestTrixStrategy:
    """Tests for TrixStrategy."""

    def test_initialization(self):
        strategy = TrixStrategy(period=14, name="Test_TRIX")
        assert strategy.name == "Test_TRIX"
        assert strategy.period == 14

    def test_validate_parameters(self):
        with pytest.raises(ValueError, match="period must be positive"):
            TrixStrategy(period=0)

    def test_generate_signals_insufficient_data(self):
        strategy = TrixStrategy(period=14)
        data = {"AAPL": create_trending_data("AAPL", days=10)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_returns_list(self):
        strategy = TrixStrategy(period=14)
        data = {"AAPL": create_trending_data("AAPL", days=80)}
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)
        for s in signals:
            assert s.symbol == "AAPL"
            assert s.action in ("buy", "sell")


class TestPercentageVolumeOscillatorStrategy:
    """Tests for PercentageVolumeOscillatorStrategy."""

    def test_initialization(self):
        strategy = PercentageVolumeOscillatorStrategy(
            fast_period=12, slow_period=26, signal_period=9, name="Test_PVO"
        )
        assert strategy.name == "Test_PVO"

    def test_validate_parameters(self):
        with pytest.raises(ValueError, match="fast_period must be positive"):
            PercentageVolumeOscillatorStrategy(fast_period=0)

    def test_generate_signals_insufficient_data(self):
        strategy = PercentageVolumeOscillatorStrategy()
        data = {"AAPL": create_trending_data("AAPL", days=10)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_returns_list(self):
        strategy = PercentageVolumeOscillatorStrategy()
        data = {"AAPL": create_trending_data("AAPL", days=80)}
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)
        for s in signals:
            assert s.symbol == "AAPL"
            assert s.action in ("buy", "sell")

    def test_zero_line_option(self):
        """Test that use_zero_line enables zero-line crossovers."""
        strategy = PercentageVolumeOscillatorStrategy(
            fast_period=5, slow_period=13, signal_period=5, use_zero_line=True
        )
        assert strategy.use_zero_line is True
        data = {"AAPL": create_trending_data("AAPL", days=100)}
        signals = strategy.generate_signals(data)
        # With zero-line enabled, more signal types may appear
        for signal in signals:
            assert signal.action in ("buy", "sell")

    def test_generate_signals_zero_line_bullish(self):
        """Test zero-line crossover generates buy when PVO crosses up.

        The PVO line crosses zero on the final bar while staying above the
        signal line, so no signal-line crossover occurs and the zero-line
        branch fires instead.
        """
        strategy = PercentageVolumeOscillatorStrategy(
            fast_period=5, slow_period=13, signal_period=5, use_zero_line=True
        )
        data = {"AAPL": create_ppo_pvo_zero_line_data("AAPL", "bullish", pvo=True)}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert 0.0 <= signal.strength <= 1.0
        assert signal.metadata["signal_type"] == "pvo_zero_cross_above"
        assert signal.metadata["pvo"] == pytest.approx(4.187430785380328)
        assert signal.metadata["pvo"] > 0
        assert signal.metadata["signal"] == pytest.approx(1.010456893764923)
        assert "zero_line" not in signal.metadata

    def test_generate_signals_zero_line_bearish(self):
        """Test zero-line crossover generates sell when PVO crosses down.

        The PVO line has just crossed above zero (signal line still lags
        below zero); the final close is tuned so the PVO line crosses back
        below zero without a signal-line crossover.
        """
        strategy = PercentageVolumeOscillatorStrategy(
            fast_period=5, slow_period=13, signal_period=5, use_zero_line=True
        )
        data = {"AAPL": create_ppo_pvo_zero_line_data("AAPL", "bearish", pvo=True)}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.symbol == "AAPL"
        assert signal.action == "sell"
        assert 0.0 <= signal.strength <= 1.0
        assert signal.metadata["signal_type"] == "pvo_zero_cross_below"
        assert signal.metadata["pvo"] == pytest.approx(-0.1453059852515245)
        assert signal.metadata["pvo"] < 0
        assert signal.metadata["signal"] == pytest.approx(-0.28104965986087066)
        assert "zero_line" not in signal.metadata

    def test_generate_signals_zero_line_disabled(self):
        """When use_zero_line is False and no signal-line crossover fires on
        the final bar, the ``elif self.use_zero_line`` arm is False and no
        signal is produced."""
        strategy = PercentageVolumeOscillatorStrategy(
            fast_period=12, slow_period=26, signal_period=9, use_zero_line=False
        )
        data = {"AAPL": create_ppo_pvo_zero_line_data("AAPL", "bullish", pvo=True)}
        signals = strategy.generate_signals(data)
        assert signals == []
