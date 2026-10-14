"""Tests for example trading strategies."""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from quant_trading.strategies.examples import (
    BollingerBandsStrategy,
    DonchianChannelStrategy,
    KeltnerChannelStrategy,
    MACDStrategy,
    MovingAverageCrossover,
    RSIStrategy,
    SuperTrendStrategy,
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
    return df


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
    return df


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
    return df


def create_donchian_data(symbol: str, closes: list[float]) -> pd.DataFrame:
    """Create deterministic OHLC data from explicit close prices.

    High/low carry a small 0.1% wick so high >= close >= low holds.
    Explicit closes make Donchian breakout/breakdown scenarios
    reproducible, unlike randomized data whose bands rarely align
    with the final bar.
    """
    close = np.asarray(closes, dtype=float)
    dates = pd.date_range(end=datetime.now(), periods=len(close), freq="D")
    return pd.DataFrame(
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
    low_raw = close * 0.999   # Temporary low for TR calculation

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
        np.maximum(open_prices, close)
    )
    low_prices = np.minimum(
        lower_band * (1 - np.random.uniform(0, noise_factor, len(close))),
        np.minimum(open_prices, close)
    )

    # Ensure high >= close >= low
    high_prices = np.maximum(high_prices, np.maximum(open_prices, close))
    low_prices = np.minimum(low_prices, np.minimum(open_prices, close))

    return pd.DataFrame(
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
    return df


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
    return df


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
    return pd.DataFrame(
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
        strategy = MACDStrategy(fast_period=12, slow_period=26, signal_period=9, use_zero_line=False)
        # Steady rising prices keep MACD and signal in parallel with no crossover.
        data = {"AAPL": create_donchian_data("AAPL", [100.0] * 30 + list(range(100, 170)))}
        signals = strategy.generate_signals(data)
        assert signals == []


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
        data_b = [100.0] * 20 + [80.0]   # Breakdown
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
