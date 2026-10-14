"""Tests for AroonStrategy."""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from quant_trading.strategies.examples import AroonStrategy


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


def create_aroon_bullish_data(symbol: str, days: int = 50) -> pd.DataFrame:
    """Create mock price data that produces an Aroon bullish crossover at the end.

    Creates a period of declining prices (high Aroon Down), then a sharp reversal
    to new highs (high Aroon Up) to trigger the bullish crossover on the most recent bar.
    """
    dates = pd.date_range(end=datetime.now(), periods=days, freq="D")
    # First (days-2) days: establish the trend
    # Last 2 days: the crossover happens between t-2 and t-1, signal generated at t
    prices = []
    for i in range(days):
        if i < days - 2:
            # Establish initial downtrend to create high Aroon Down
            prices.append(100 - i * 0.3)
        else:
            # The last 2 days are where the crossover happens
            # We want:
            # - t-2: Aroon Up low, Aroon Down high (so Up <= Down)
            # - t-1: Aroon Up high, Aroon Down low (so Up > Down) - this is where crossover is detected

            # Calculate how far we are into the last 2 days (0, 1)
            days_into_last_2 = i - (days - 2)

            if days_into_last_2 == 0:
                # This is bar t-2: start with low Up, high Down
                base_value = 100 - (days - 2) * 0.3  # Continue the downtrend to establish baseline
                prices.append(base_value)  # Low Up, High Down
            else:  # days_into_last_2 == 1 (this is bar t-1, the most recent complete bar)
                # This is where the sharp reversal happens to create the crossover
                base_value = 100 - (days - 2) * 0.3  # Start from same baseline
                prices.append(
                    base_value + 40.0
                )  # Large uptick to create crossover: High Up, Lower Down

    df = pd.DataFrame(
        {
            "open": np.array(prices) * (1 + np.random.uniform(-0.002, 0.002, days)),
            "high": np.array(prices) * (1 + np.random.uniform(0, 0.005, days)),
            "low": np.array(prices) * (1 - np.random.uniform(0, 0.005, days)),
            "close": prices,
            "volume": np.full(days, 1_000_000),
        },
        index=dates,
    )
    return df


def create_aroon_bearish_data(symbol: str, days: int = 50) -> pd.DataFrame:
    """Create mock price data that produces an Aroon bearish crossover at the end.

    Creates a period of advancing prices (high Aroon Up), then a sharp reversal
    to new lows (high Aroon Down) to trigger the bearish crossover on the most recent bar.
    """
    dates = pd.date_range(end=datetime.now(), periods=days, freq="D")
    # First (days-2) days: establish the trend
    # Last 2 days: the crossover happens between t-2 and t-1, signal generated at t
    prices = []
    for i in range(days):
        if i < days - 2:
            # Establish initial uptrend to create high Aroon Up
            prices.append(100 + i * 0.3)
        else:
            # The last 2 days are where the crossover happens
            # We want:
            # - t-2: Aroon Up high, Aroon Down low (so Down <= Up)
            # - t-1: Aroon Up low, Aroon Down high (so Down > Up) - this is where crossover is detected

            # Calculate how far we are into the last 2 days (0, 1)
            days_into_last_2 = i - (days - 2)

            if days_into_last_2 == 0:
                # This is bar t-2: start with high Up, low Down
                base_value = 100 + (days - 2) * 0.3  # Continue the uptrend to establish baseline
                prices.append(base_value)  # High Up, Low Down
            else:  # days_into_last_2 == 1 (this is bar t-1, the most recent complete bar)
                # This is where the sharp reversal happens to create the crossover
                base_value = 100 + (days - 2) * 0.3  # Start from same baseline
                prices.append(
                    base_value - 40.0
                )  # Large downtick to create crossover: Low Up, High Down

    df = pd.DataFrame(
        {
            "open": np.array(prices) * (1 + np.random.uniform(-0.002, 0.002, days)),
            "high": np.array(prices) * (1 + np.random.uniform(0, 0.005, days)),
            "low": np.array(prices) * (1 - np.random.uniform(0, 0.005, days)),
            "close": prices,
            "volume": np.full(days, 1_000_000),
        },
        index=dates,
    )
    return df


class TestAroonStrategy:
    """Tests for AroonStrategy."""

    def test_initialization(self):
        """Test strategy initialization."""
        strategy = AroonStrategy(period=25, name="Test_Aroon")
        assert strategy.name == "Test_Aroon"
        assert strategy.period == 25
        assert strategy.parameters["period"] == 25

    def test_validate_parameters(self):
        """Test parameter validation."""
        with pytest.raises(ValueError, match="period must be positive"):
            AroonStrategy(period=0)
        with pytest.raises(ValueError, match="period must be positive"):
            AroonStrategy(period=-5)

    def test_generate_signals_insufficient_data(self):
        """Test generate_signals with insufficient data."""
        strategy = AroonStrategy(period=25)
        data = {"AAPL": create_trending_data("AAPL", days=20)}  # Less than period
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_generate_signals_bullish_crossover(self):
        """Test generate_signals detects Aroon bullish crossover (buy signal)."""
        strategy = AroonStrategy(period=25)
        data = {"AAPL": create_aroon_bullish_data("AAPL", days=50)}
        signals = strategy.generate_signals(data)

        # Should have at least one signal due to the designed crossover
        assert len(signals) >= 1
        for signal in signals:
            assert signal.symbol == "AAPL"
            assert signal.action in ("buy", "sell")
            assert 0.0 <= signal.strength <= 1.0
            assert signal.price is not None
            assert signal.timestamp is not None
            if signal.action == "buy":
                assert signal.metadata.get("crossover_type") == "bullish"
                assert "aroon_up" in signal.metadata
                assert "aroon_down" in signal.metadata

    def test_generate_signals_bearish_crossover(self):
        """Test generate_signals detects Aroon bearish crossover (sell signal)."""
        strategy = AroonStrategy(period=25)
        data = {"AAPL": create_aroon_bearish_data("AAPL", days=50)}
        signals = strategy.generate_signals(data)

        assert len(signals) >= 1
        for signal in signals:
            assert signal.symbol == "AAPL"
            assert signal.action in ("buy", "sell")
            assert 0.0 <= signal.strength <= 1.0
            if signal.action == "sell":
                assert signal.metadata.get("crossover_type") == "bearish"

    def test_generate_signals_multiple_symbols(self):
        """Test generate_signals with multiple symbols."""
        strategy = AroonStrategy(period=25)
        data = {
            "AAPL": create_aroon_bullish_data("AAPL", days=50),
            "MSFT": create_aroon_bearish_data("MSFT", days=50),
        }
        signals = strategy.generate_signals(data)
        symbols = {s.symbol for s in signals}
        assert symbols.issubset({"AAPL", "MSFT"})

    def test_aroon_calculation(self):
        """Test Aroon calculation internally."""
        strategy = AroonStrategy(period=5)
        # Create simple test data
        high = pd.Series([10, 12, 11, 13, 15, 14, 16])  # Highest at index 4 and 6
        low = pd.Series([8, 9, 7, 8, 6, 5, 4])  # Lowest at index 6

        aroon_up, aroon_down = strategy._calculate_aroon(high, low)

        # For the last value (index 6):
        # Highest high in last 5 periods (indices 2-6): 16 at index 6 (0 periods ago)
        # Aroon Up = ((5-0)/5)*100 = 100
        # Lowest low in last 5 periods (indices 2-6): 4 at index 6 (0 periods ago)
        # Aroon Down = ((5-0)/5)*100 = 100
        assert aroon_up.iloc[-1] == 100.0
        assert aroon_down.iloc[-1] == 100.0

        # For index 5:
        # Highest high in last 5 periods (indices 1-5): 15 at index 4 (1 period ago)
        # Aroon Up = ((5-1)/5)*100 = 80
        # Lowest low in last 5 periods (indices 1-5): 5 at index 5 (0 periods ago)
        # Aroon Down = ((5-0)/5)*100 = 100
        assert aroon_up.iloc[-2] == 80.0
        assert aroon_down.iloc[-2] == 100.0

    def test_aroon_calculation_edge_case(self):
        """Test Aroon calculation with all same values."""
        strategy = AroonStrategy(period=5)
        high = pd.Series([10, 10, 10, 10, 10, 10, 10])
        low = pd.Series([10, 10, 10, 10, 10, 10, 10])

        aroon_up, aroon_down = strategy._calculate_aroon(high, low)

        # First 4 values (period-1) will be NaN due to insufficient data for rolling window
        # Starting from index 4 (5th element), we should have 100.0 values
        # When all values are equal, the most recent index is used
        # So for any period, highest high and lowest low are at the most recent bar
        # Aroon Up = ((period-0)/period)*100 = 100
        # Aroon Down = ((period-0)/period)*100 = 100
        expected_up = pd.Series([np.nan, np.nan, np.nan, np.nan, 100.0, 100.0, 100.0])
        expected_down = pd.Series([np.nan, np.nan, np.nan, np.nan, 100.0, 100.0, 100.0])
        pd.testing.assert_series_equal(aroon_up, expected_up)
        pd.testing.assert_series_equal(aroon_down, expected_down)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_generate_signals_nan_aroon_skipped():
    """generate_signals skips symbols whose Aroon values are NaN (line 979)."""
    strategy = AroonStrategy(period=5)
    # Exactly period+1 rows, but with NaN highs so rolling Aroon is NaN.
    df = create_trending_data("AAPL", days=6)
    df["high"] = float("nan")
    df["low"] = float("nan")
    signals = strategy.generate_signals({"AAPL": df})
    assert signals == []


def test_generate_signals_no_crossover():
    """generate_signals produces no signal when neither Aroon crossover fires
    (the bearish `elif` at line 994 is False, so control falls through to the
    return at line 948)."""
    strategy = AroonStrategy(period=25)
    # A steady uptrend: Aroon Up stays high, Aroon Down stays low, so neither
    # the bullish `if` nor the bearish `elif` condition is satisfied on the final bar.
    df = create_aroon_bullish_data("AAPL", days=50)
    signals = strategy.generate_signals({"AAPL": df.iloc[:-1]})
    assert signals == []


def test_aroon_calculation_nan_in_window():
    """A NaN inside the rolling window yields NaN Aroon values (the inner loop
    never matches, so the `for` completes without `break`)."""
    strategy = AroonStrategy(period=5)
    high = pd.Series([10.0, 12.0, 11.0, 13.0, float("nan"), 15.0, 14.0])
    low = pd.Series([8.0, 9.0, 7.0, 8.0, float("nan"), 5.0, 4.0])

    aroon_up, aroon_down = strategy._calculate_aroon(high, low)

    assert pd.isna(aroon_up.iloc[-1])
    assert pd.isna(aroon_down.iloc[-1])
