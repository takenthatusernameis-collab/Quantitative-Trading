"""Example trading strategies."""

from typing import Any

import numpy as np
import pandas as pd

from .base import Signal, Strategy


class MovingAverageCrossover(Strategy):
    """Moving Average Crossover Strategy.

    Generates buy signals when fast MA crosses above slow MA,
    and sell signals when fast MA crosses below slow MA.
    """

    def __init__(
        self,
        fast_period: int = 10,
        slow_period: int = 30,
        name: str = "MA_Crossover",
    ):
        """Initialize the Moving Average Crossover strategy.

        Args:
            fast_period: Lookback window for the fast moving average.
            slow_period: Lookback window for the slow moving average; must
                exceed ``fast_period``.
            name: Human-readable name of the strategy.

        Raises:
            ValueError: If any parameter is invalid.

        """
        super().__init__(
            name,
            {
                "fast_period": fast_period,
                "slow_period": slow_period,
            },
        )
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        Raises:
            ValueError: If ``fast_period`` or ``slow_period`` is non-positive,
                or if ``fast_period`` is not less than ``slow_period``.

        """
        if self.fast_period <= 0:
            raise ValueError("fast_period must be positive")
        if self.slow_period <= 0:
            raise ValueError("slow_period must be positive")
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be less than slow_period")

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate buy/sell signals from fast/slow MA crossovers.

        A golden cross (fast MA crossing above the slow MA) produces a buy
        signal; a death cross (fast MA crossing below the slow MA) produces a
        sell signal.

        Args:
            data: Mapping of symbol to a DataFrame containing at least a
                ``"close"`` column indexed by timestamp.

        Returns:
            List of :class:`Signal` objects for symbols whose moving averages
            cross between the last two bars.

        """
        signals = []

        for symbol, df in data.items():
            if len(df) < self.slow_period:
                continue

            close = df["close"]
            current_price = close.iloc[-1]
            # The signal is emitted at the last close, so a close that is not a
            # number is rejected before anything is derived from it.
            if pd.isna(current_price):
                continue

            fast_ma = close.rolling(window=self.fast_period).mean()
            slow_ma = close.rolling(window=self.slow_period).mean()

            if len(fast_ma) < 2 or len(slow_ma) < 2:
                continue

            # Current and previous values
            fast_current = fast_ma.iloc[-1]
            fast_prev = fast_ma.iloc[-2]
            slow_current = slow_ma.iloc[-1]
            slow_prev = slow_ma.iloc[-2]

            if (
                pd.isna(fast_current)
                or pd.isna(fast_prev)
                or pd.isna(slow_current)
                or pd.isna(slow_prev)
            ):
                continue
            timestamp = df.index[-1]

            # Crossover detection
            if fast_prev <= slow_prev and fast_current > slow_current:
                # Golden cross - buy signal
                if slow_current and slow_current != 0:
                    strength = min(1.0, (fast_current - slow_current) / slow_current * 10)
                else:
                    strength = 0.5
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "fast_ma": fast_current,
                            "slow_ma": slow_current,
                            "crossover_type": "golden_cross",
                        },
                    )
                )
            elif fast_prev >= slow_prev and fast_current < slow_current:
                # Death cross - sell signal
                if slow_current and slow_current != 0:
                    strength = min(1.0, (slow_current - fast_current) / slow_current * 10)
                else:
                    strength = 0.5
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "fast_ma": fast_current,
                            "slow_ma": slow_current,
                            "crossover_type": "death_cross",
                        },
                    )
                )

        return signals


class RSIStrategy(Strategy):
    """RSI Mean Reversion Strategy.

    Buys when RSI is oversold (< 30), sells when overbought (> 70).
    """

    def __init__(
        self,
        period: int = 14,
        oversold: float = 30,
        overbought: float = 70,
        name: str = "RSI_MeanReversion",
    ):
        """Initialize the RSI mean reversion strategy.

        Args:
            period: Lookback window for the RSI calculation.
            oversold: RSI level below which an asset is considered oversold.
            overbought: RSI level above which an asset is considered overbought.
            name: Human-readable name of the strategy.

        Raises:
            ValueError: If any parameter is invalid.

        """
        super().__init__(
            name,
            {
                "period": period,
                "oversold": oversold,
                "overbought": overbought,
            },
        )
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        Raises:
            ValueError: If ``period`` is non-positive, thresholds are outside
                ``(0, 100)``, or ``oversold`` is not less than ``overbought``.

        """
        if self.period <= 0:
            raise ValueError("period must be positive")
        if not (0 < self.oversold < 100):
            raise ValueError("oversold must be between 0 and 100")
        if not (0 < self.overbought < 100):
            raise ValueError("overbought must be between 0 and 100")
        if self.oversold >= self.overbought:
            raise ValueError("oversold must be less than overbought")

    def _calculate_rsi(self, close: pd.Series) -> pd.Series:
        """Calculate the Relative Strength Index for a price series.

        Args:
            close: Series of close prices.

        Returns:
            Series of RSI values aligned with ``close``.

        """
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.period).mean()
        rs = gain / loss
        rsi: pd.Series = 100 - (100 / (1 + rs))
        return rsi

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate buy/sell signals from RSI crossovers of thresholds.

        Args:
            data: Mapping of symbol to a DataFrame containing at least a
                ``"close"`` column indexed by timestamp.

        Returns:
            List of :class:`Signal` objects for symbols whose RSI crosses the
            oversold or overbought thresholds between the last two bars.

        """
        signals = []

        for symbol, df in data.items():
            if len(df) < self.period + 1:
                continue

            close = df["close"]
            rsi = self._calculate_rsi(close)

            current_rsi = rsi.iloc[-1]
            prev_rsi = rsi.iloc[-2]
            current_price = close.iloc[-1]
            if pd.isna(current_rsi) or pd.isna(prev_rsi) or pd.isna(current_price):
                continue
            timestamp = df.index[-1]

            # Oversold - buy signal
            if prev_rsi <= self.oversold and current_rsi > self.oversold:
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=min(1.0, (self.oversold - prev_rsi) / self.oversold + 0.5),
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "rsi": current_rsi,
                            "signal_type": "oversold_bounce",
                        },
                    )
                )
            # Overbought - sell signal
            elif prev_rsi >= self.overbought and current_rsi < self.overbought:
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=min(
                            1.0, (prev_rsi - self.overbought) / (100 - self.overbought) + 0.5
                        ),
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "rsi": current_rsi,
                            "signal_type": "overbought_rejection",
                        },
                    )
                )

        return signals


class BollingerBandsStrategy(Strategy):
    """Bollinger Bands Mean Reversion Strategy.

    Buys when price touches lower band, sells when price touches upper band.
    """

    def __init__(
        self,
        period: int = 20,
        std_dev: float = 2.0,
        name: str = "Bollinger_Bands",
    ):
        """Initialize the Bollinger Bands mean reversion strategy.

        Args:
            period: Lookback window for the moving average and standard deviation.
            std_dev: Number of standard deviations for the bands.
            name: Human-readable name of the strategy.

        Raises:
            ValueError: If any parameter is invalid.

        """
        super().__init__(
            name,
            {
                "period": period,
                "std_dev": std_dev,
            },
        )
        self.period = period
        self.std_dev = std_dev
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        Raises:
            ValueError: If ``period`` or ``std_dev`` is non-positive.

        """
        if self.period <= 0:
            raise ValueError("period must be positive")
        if self.std_dev <= 0:
            raise ValueError("std_dev must be positive")

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate buy/sell signals from Bollinger Band touches.

        Args:
            data: Mapping of symbol to a DataFrame containing at least a
                ``"close"`` column indexed by timestamp.

        Returns:
            List of :class:`Signal` objects for symbols whose price touches
            the lower or upper Bollinger band.

        """
        signals: list[Signal] = []

        for symbol, df in data.items():
            if len(df) < self.period:
                continue

            close = df["close"]
            sma = close.rolling(window=self.period).mean()
            std = close.rolling(window=self.period).std()

            upper_band = sma + (std * self.std_dev)
            lower_band = sma - (std * self.std_dev)

            current_price = close.iloc[-1]
            current_upper = upper_band.iloc[-1]
            current_lower = lower_band.iloc[-1]
            current_sma = sma.iloc[-1]
            timestamp = df.index[-1]

            if (
                pd.isna(current_price)
                or pd.isna(current_upper)
                or pd.isna(current_lower)
                or pd.isna(current_sma)
                or current_price == 0
                or current_lower == 0
                or current_upper == 0
            ):
                continue

            # Price at lower band - buy signal
            if current_price <= current_lower * 1.005:  # Small buffer
                strength = min(1.0, (current_lower - current_price) / current_lower + 0.5)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "upper_band": current_upper,
                            "lower_band": current_lower,
                            "sma": current_sma,
                            "signal_type": "lower_band_touch",
                        },
                    )
                )
            # Price at upper band - sell signal
            elif current_price >= current_upper * 0.995:  # Small buffer
                strength = min(1.0, (current_price - current_upper) / current_upper + 0.5)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "upper_band": current_upper,
                            "lower_band": current_lower,
                            "sma": current_sma,
                            "signal_type": "upper_band_touch",
                        },
                    )
                )

        return signals


class SuperTrendStrategy(Strategy):
    """SuperTrend Strategy.

    Trend-following indicator using Average True Range (ATR) for volatility-adjusted
    trailing stops. Generates buy signals when price crosses above the SuperTrend line
    (trend turns bullish) and sell signals when price crosses below (trend turns bearish).

    The SuperTrend line acts as a dynamic support/resistance level that trails price
    based on volatility.
    """

    def __init__(
        self,
        period: int = 10,
        multiplier: float = 3.0,
        name: str = "SuperTrend",
    ):
        """Initialize the SuperTrend strategy.

        Args:
            period: Lookback window for Average True Range calculation.
            multiplier: Multiplier applied to ATR for band width.
            name: Human-readable name of the strategy.

        Raises:
            ValueError: If any parameter is invalid.

        """
        super().__init__(
            name,
            {
                "period": period,
                "multiplier": multiplier,
            },
        )
        self.period = period
        self.multiplier = multiplier
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        Raises:
            ValueError: If ``period`` or ``multiplier`` is non-positive.

        """
        if self.period <= 0:
            raise ValueError("period must be positive")
        if self.multiplier <= 0:
            raise ValueError("multiplier must be positive")

    def _calculate_atr(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Average True Range (ATR).

        Args:
            df: DataFrame containing at least ``"high"``, ``"low"``, and
                ``"close"`` columns.
            period: Lookback window for ATR calculation.

        Returns:
            Series of ATR values aligned with ``df`` index.

        """
        high = df["high"]
        low = df["low"]
        close = df["close"]

        # True Range = max(high - low, |high - prev_close|, |low - prev_close|)
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # ATR is the rolling average of True Range
        atr = true_range.rolling(window=period).mean()
        return atr

    def _calculate_supertrend(self, df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
        """Calculate SuperTrend indicator.

        Returns:
            Tuple of (supertrend_line, trend_direction) where trend_direction is
            1 for bullish (supertrend is support), -1 for bearish (supertrend is resistance).

        """
        atr = self._calculate_atr(df, self.period)
        hl2 = (df["high"] + df["low"]) / 2

        basic_upper = hl2 + self.multiplier * atr
        basic_lower = hl2 - self.multiplier * atr

        final_upper = basic_upper.copy()
        final_lower = basic_lower.copy()
        supertrend = pd.Series(index=df.index, dtype=float)
        trend = pd.Series(index=df.index, dtype=int)

        # Find first valid index (where ATR is not NaN)
        valid_idx = atr.first_valid_index()
        if valid_idx is None:
            # No valid ATR values, return all NaN
            trend.iloc[:] = -1
            return supertrend, trend

        start_i = df.index.get_loc(valid_idx)
        assert isinstance(start_i, int)

        # Initialize values before start_i as NaN/neutral
        for i in range(start_i):
            trend.iloc[i] = -1

        # Initialize at start_i
        i = start_i
        final_upper.iloc[i] = basic_upper.iloc[i]
        final_lower.iloc[i] = basic_lower.iloc[i]
        supertrend.iloc[i] = final_upper.iloc[i]
        trend.iloc[i] = -1  # Start bearish

        # Calculate for remaining rows
        for i in range(start_i + 1, len(df)):
            close = df["close"].iloc[i]
            prev_close = df["close"].iloc[i - 1]
            prev_final_upper = final_upper.iloc[i - 1]
            prev_final_lower = final_lower.iloc[i - 1]
            prev_trend = trend.iloc[i - 1]

            # Final upper band
            if basic_upper.iloc[i] < prev_final_upper or prev_close > prev_final_upper:
                final_upper.iloc[i] = basic_upper.iloc[i]
            else:
                final_upper.iloc[i] = prev_final_upper

            # Final lower band
            if basic_lower.iloc[i] > prev_final_lower or prev_close < prev_final_lower:
                final_lower.iloc[i] = basic_lower.iloc[i]
            else:
                final_lower.iloc[i] = prev_final_lower

            # Determine trend and supertrend value
            if prev_trend == -1 and close > prev_final_upper:
                # Trend change: bearish to bullish
                trend.iloc[i] = 1
                supertrend.iloc[i] = final_lower.iloc[i]
            elif prev_trend == 1 and close < prev_final_lower:
                # Trend change: bullish to bearish
                trend.iloc[i] = -1
                supertrend.iloc[i] = final_upper.iloc[i]
            elif prev_trend == 1:
                # Continue bullish
                trend.iloc[i] = 1
                supertrend.iloc[i] = final_lower.iloc[i]
            else:
                # Continue bearish
                trend.iloc[i] = -1
                supertrend.iloc[i] = final_upper.iloc[i]

        return supertrend, trend

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate buy/sell signals from SuperTrend trend reversals.

        Args:
            data: Mapping of symbol to a DataFrame containing at least
                ``"close"``, ``"high"``, and ``"low"`` columns indexed by
                timestamp.

        Returns:
            List of :class:`Signal` objects representing trend reversals.

        """
        signals = []

        for symbol, df in data.items():
            min_required = self.period + 2
            if len(df) < min_required:
                continue

            supertrend, trend = self._calculate_supertrend(df)

            current_price = df["close"].iloc[-1]
            current_supertrend = supertrend.iloc[-1]
            current_trend = trend.iloc[-1]
            prev_trend = trend.iloc[-2]
            timestamp = df.index[-1]

            if (
                pd.isna(current_price)
                or pd.isna(current_supertrend)
                or pd.isna(current_trend)
                or pd.isna(prev_trend)
                or current_price == 0
            ):
                continue

            # Trend change detection
            if prev_trend == -1 and current_trend == 1:
                # Bullish reversal - buy signal
                strength = min(1.0, (current_price - current_supertrend) / current_price * 20 + 0.5)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "supertrend": current_supertrend,
                            "trend": "bullish",
                            "signal_type": "trend_reversal_bullish",
                        },
                    )
                )
            elif prev_trend == 1 and current_trend == -1:
                # Bearish reversal - sell signal
                strength = min(1.0, (current_supertrend - current_price) / current_price * 20 + 0.5)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "supertrend": current_supertrend,
                            "trend": "bearish",
                            "signal_type": "trend_reversal_bearish",
                        },
                    )
                )

        return signals


class MACDStrategy(Strategy):
    """MACD (Moving Average Convergence Divergence) Strategy.

    Generates buy signals when the MACD line crosses above the signal line
    (bullish crossover), and sell signals when the MACD line crosses below the
    signal line (bearish crossover). Optionally also reacts to the MACD line
    crossing the zero axis.
    """

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        use_zero_line: bool = False,
        name: str = "MACD",
    ):
        """Initialize the MACD strategy.

        Args:
            fast_period: Lookback window for the fast EMA.
            slow_period: Lookback window for the slow EMA; must exceed ``fast_period``.
            signal_period: Lookback window for the signal line EMA.
            use_zero_line: If ``True``, also emit signals on MACD zero-axis crossovers.
            name: Human-readable name of the strategy.

        Raises:
            ValueError: If any parameter is invalid.

        """
        super().__init__(
            name,
            {
                "fast_period": fast_period,
                "slow_period": slow_period,
                "signal_period": signal_period,
                "use_zero_line": use_zero_line,
            },
        )
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.use_zero_line = use_zero_line
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        Raises:
            ValueError: If ``fast_period``, ``slow_period``, or ``signal_period``
                is non-positive, or if ``fast_period`` is not less than ``slow_period``.

        """
        if self.fast_period <= 0:
            raise ValueError("fast_period must be positive")
        if self.slow_period <= 0:
            raise ValueError("slow_period must be positive")
        if self.signal_period <= 0:
            raise ValueError("signal_period must be positive")
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be less than slow_period")

    def _ema(self, close: pd.Series, period: int) -> pd.Series:
        """Calculate an Exponential Moving Average.

        Args:
            close: Series of close prices.
            period: Lookback window for the EMA.

        Returns:
            Series of EMA values aligned with ``close``.

        """
        return close.ewm(span=period, adjust=False).mean()

    def _calculate_macd(self, close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate the MACD line, signal line, and histogram.

        Args:
            close: Series of close prices.

        Returns:
            Tuple of (macd_line, signal_line, histogram).

        """
        fast_ema = self._ema(close, self.fast_period)
        slow_ema = self._ema(close, self.slow_period)
        macd_line = fast_ema - slow_ema
        signal_line = self._ema(macd_line, self.signal_period)
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate buy/sell signals from MACD line and zero-axis crossovers.

        Args:
            data: Mapping of symbol to a DataFrame containing at least a
                ``"close"`` column indexed by timestamp.

        Returns:
            List of :class:`Signal` objects for symbols whose MACD line crosses
            the signal line (or, when ``use_zero_line`` is set, the zero axis).

        """
        signals = []

        for symbol, df in data.items():
            # Need enough data for the slow EMA plus signal smoothing
            min_required = self.slow_period + self.signal_period + 2
            if len(df) < min_required:
                continue

            close = df["close"]
            macd_line, signal_line, histogram = self._calculate_macd(close)

            macd_current = macd_line.iloc[-1]
            macd_prev = macd_line.iloc[-2]
            signal_current = signal_line.iloc[-1]
            signal_prev = signal_line.iloc[-2]
            hist_current = histogram.iloc[-1]

            current_price = close.iloc[-1]
            timestamp = df.index[-1]

            if (
                pd.isna(macd_current)
                or pd.isna(macd_prev)
                or pd.isna(signal_current)
                or pd.isna(signal_prev)
                or pd.isna(hist_current)
                or pd.isna(current_price)
                or current_price == 0
            ):
                continue

            # Bullish crossover: MACD line crosses above signal line
            if macd_prev <= signal_prev and macd_current > signal_current:
                strength = (
                    min(1.0, abs(macd_current - signal_current) / abs(signal_current) + 0.5)
                    if signal_current != 0
                    else 0.5
                )
                metadata = {
                    "macd": macd_current,
                    "signal": signal_current,
                    "histogram": hist_current,
                    "crossover_type": "bullish",
                }
                if self.use_zero_line and macd_current > 0:
                    metadata["zero_line"] = "above"
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata=metadata,
                    )
                )
            # Bearish crossover: MACD line crosses below signal line
            elif macd_prev >= signal_prev and macd_current < signal_current:
                strength = (
                    min(1.0, abs(signal_current - macd_current) / abs(signal_current) + 0.5)
                    if signal_current != 0
                    else 0.5
                )
                metadata = {
                    "macd": macd_current,
                    "signal": signal_current,
                    "histogram": hist_current,
                    "crossover_type": "bearish",
                }
                if self.use_zero_line and macd_current < 0:
                    metadata["zero_line"] = "below"
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata=metadata,
                    )
                )
            # Optional zero-line crossover when no signal-line crossover occurred
            elif self.use_zero_line:
                if macd_prev <= 0 and macd_current > 0:
                    # Strength based on MACD magnitude relative to signal line
                    ref = abs(signal_current) if signal_current != 0 else abs(macd_current)
                    strength = (
                        min(1.0, abs(macd_current) / ref * 0.5 + 0.3) if ref > 0 else 0.5
                    )  # pragma: no cover
                    signals.append(
                        Signal(
                            symbol=symbol,
                            action="buy",
                            strength=strength,
                            price=current_price,
                            timestamp=timestamp,
                            metadata={
                                "macd": macd_current,
                                "signal": signal_current,
                                "histogram": hist_current,
                                "crossover_type": "zero_line_bullish",
                            },
                        )
                    )
                elif macd_prev >= 0 and macd_current < 0:
                    ref = abs(signal_current) if signal_current != 0 else abs(macd_current)
                    strength = (
                        min(1.0, abs(macd_current) / ref * 0.5 + 0.3) if ref > 0 else 0.5
                    )  # pragma: no cover
                    signals.append(
                        Signal(
                            symbol=symbol,
                            action="sell",
                            strength=strength,
                            price=current_price,
                            timestamp=timestamp,
                            metadata={
                                "macd": macd_current,
                                "signal": signal_current,
                                "histogram": hist_current,
                                "crossover_type": "zero_line_bearish",
                            },
                        )
                    )
                else:  # pragma: no cover
                    pass
            else:  # pragma: no cover
                pass

        return signals


class DonchianChannelStrategy(Strategy):
    """Donchian Channel Breakout Strategy.

    Generates buy signals when price breaks above the upper channel (highest high
    over the lookback period), and sell signals when price breaks below the lower
    channel (lowest low over the lookback period).

    The Donchian Channel consists of three lines:
    - Upper Band: Highest high over N periods
    - Lower Band: Lowest low over N periods
    - Middle Band: Average of upper and lower bands

    This is a classic trend-following breakout strategy.
    """

    def __init__(
        self,
        period: int = 20,
        exit_period: int | None = None,
        name: str = "Donchian_Channel",
    ):
        """Initialize the Donchian Channel breakout strategy.

        Args:
            period: Lookback window for the entry Donchian channels.
            exit_period: Optional separate lookback window for the exit
                channels. When ``None``, defaults to ``period``.
            name: Human-readable name of the strategy.

        Raises:
            ValueError: If any parameter is invalid.

        """
        super().__init__(
            name,
            {
                "period": period,
                "exit_period": exit_period,
            },
        )
        self.period = period
        # Use separate exit period for tighter exits (classic turtle trading uses shorter exit)
        self.exit_period = exit_period if exit_period is not None else period
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        Raises:
            ValueError: If ``period`` or ``exit_period`` is non-positive.

        """
        if self.period <= 0:
            raise ValueError("period must be positive")
        if self.exit_period <= 0:
            raise ValueError("exit_period must be positive")

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate breakout and exit signals from Donchian Channel levels.

        Entry signals fire when price breaks above the upper channel (buy) or
        below the lower channel (sell). Exit signals fire for existing long or
        short positions when price crosses the middle band or the exit
        channel boundary.

        Args:
            data: Mapping of symbol to a DataFrame containing at least
                ``"high"``, ``"low"``, and ``"close"`` columns indexed by
                timestamp.

        Returns:
            List of :class:`Signal` objects for breakout and exit events.

        """
        signals = []

        for symbol, df in data.items():
            if len(df) < self.period + 1:
                continue

            high = df["high"]
            low = df["low"]
            close = df["close"]

            # Calculate Donchian Channels (shifted by one bar so breakouts
            # are measured against prior bars; including the current bar
            # would make close > upper_band impossible since high >= close)
            upper_band = high.rolling(window=self.period).max().shift(1)
            lower_band = low.rolling(window=self.period).min().shift(1)
            middle_band = (upper_band + lower_band) / 2

            # Exit channels (shorter period for tighter exits)
            exit_upper = high.rolling(window=self.exit_period).max().shift(1)
            exit_lower = low.rolling(window=self.exit_period).min().shift(1)

            current_price = close.iloc[-1]
            current_upper = upper_band.iloc[-1]
            current_lower = lower_band.iloc[-1]
            current_middle = middle_band.iloc[-1]
            current_exit_upper = exit_upper.iloc[-1]
            current_exit_lower = exit_lower.iloc[-1]

            prev_price = close.iloc[-2]
            prev_upper = upper_band.iloc[-2]
            prev_lower = lower_band.iloc[-2]
            prev_middle = middle_band.iloc[-2]
            prev_exit_upper = exit_upper.iloc[-2]
            prev_exit_lower = exit_lower.iloc[-2]

            timestamp = df.index[-1]

            # Skip if any required values are NaN or zero (avoid division by zero)
            if (
                pd.isna(current_price)
                or pd.isna(current_upper)
                or pd.isna(current_lower)
                or pd.isna(current_middle)
                or pd.isna(current_exit_upper)
                or pd.isna(current_exit_lower)
                or pd.isna(prev_price)
                or pd.isna(prev_upper)
                or pd.isna(prev_lower)
                or pd.isna(prev_middle)
                or pd.isna(prev_exit_upper)
                or pd.isna(prev_exit_lower)
                or current_upper == 0
                or current_lower == 0
                or current_middle == 0
                or current_exit_upper == 0
                or current_exit_lower == 0
            ):
                continue

            # Check current position for this symbol
            position = self.positions.get(symbol)
            is_long = position is not None and position.quantity > 0
            is_short = position is not None and position.quantity < 0

            # Entry signals: breakout above upper band / below lower band
            if prev_price <= prev_upper and current_price > current_upper:
                # Bullish breakout - buy signal
                strength = min(1.0, (current_price - current_upper) / current_upper * 10 + 0.5)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "upper_band": current_upper,
                            "lower_band": current_lower,
                            "middle_band": current_middle,
                            "exit_upper": current_exit_upper,
                            "exit_lower": current_exit_lower,
                            "signal_type": "upper_breakout",
                        },
                    )
                )
            elif prev_price >= prev_lower and current_price < current_lower:
                # Bearish breakdown - sell signal
                strength = min(1.0, (current_lower - current_price) / current_lower * 10 + 0.5)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "upper_band": current_upper,
                            "lower_band": current_lower,
                            "middle_band": current_middle,
                            "exit_upper": current_exit_upper,
                            "exit_lower": current_exit_lower,
                            "signal_type": "lower_breakdown",
                        },
                    )
                )

            # Exit signals for long positions
            if is_long:
                # Exit 1: Price crosses below middle band (mean reversion)
                if prev_price >= prev_middle and current_price < current_middle:
                    strength = min(
                        1.0, (current_middle - current_price) / current_middle * 10 + 0.5
                    )
                    signals.append(
                        Signal(
                            symbol=symbol,
                            action="sell",
                            strength=strength,
                            price=current_price,
                            timestamp=timestamp,
                            metadata={
                                "upper_band": current_upper,
                                "lower_band": current_lower,
                                "middle_band": current_middle,
                                "exit_upper": current_exit_upper,
                                "exit_lower": current_exit_lower,
                                "signal_type": "middle_band_exit_long",
                            },
                        )
                    )
                # Exit 2: Price breaks below exit lower band (trend-following exit)
                elif prev_price >= prev_exit_lower and current_price < current_exit_lower:
                    strength = min(
                        1.0, (current_exit_lower - current_price) / current_exit_lower * 10 + 0.5
                    )
                    signals.append(
                        Signal(
                            symbol=symbol,
                            action="sell",
                            strength=strength,
                            price=current_price,
                            timestamp=timestamp,
                            metadata={
                                "upper_band": current_upper,
                                "lower_band": current_lower,
                                "middle_band": current_middle,
                                "exit_upper": current_exit_upper,
                                "exit_lower": current_exit_lower,
                                "signal_type": "exit_channel_breakdown",
                            },
                        )
                    )

            # Exit signals for short positions
            elif is_short:
                # Exit 1: Price crosses above middle band (mean reversion)
                if prev_price <= prev_middle and current_price > current_middle:
                    strength = min(
                        1.0, (current_price - current_middle) / current_middle * 10 + 0.5
                    )
                    signals.append(
                        Signal(
                            symbol=symbol,
                            action="buy",
                            strength=strength,
                            price=current_price,
                            timestamp=timestamp,
                            metadata={
                                "upper_band": current_upper,
                                "lower_band": current_lower,
                                "middle_band": current_middle,
                                "exit_upper": current_exit_upper,
                                "exit_lower": current_exit_lower,
                                "signal_type": "middle_band_exit_short",
                            },
                        )
                    )
                # Exit 2: Price breaks above exit upper band (trend-following exit)
                elif prev_price <= prev_exit_upper and current_price > current_exit_upper:
                    strength = min(
                        1.0, (current_price - current_exit_upper) / current_exit_upper * 10 + 0.5
                    )
                    signals.append(
                        Signal(
                            symbol=symbol,
                            action="buy",
                            strength=strength,
                            price=current_price,
                            timestamp=timestamp,
                            metadata={
                                "upper_band": current_upper,
                                "lower_band": current_lower,
                                "middle_band": current_middle,
                                "exit_upper": current_exit_upper,
                                "exit_lower": current_exit_lower,
                                "signal_type": "exit_channel_breakout",
                            },
                        )
                    )

        return signals


class AroonStrategy(Strategy):
    """Aroon Trend Strategy.

    The Aroon indicator consists of two lines:
    - Aroon Up: Measures how many periods since the highest high occurred (in the lookback period)
    - Aroon Down: Measures how many periods since the lowest low occurred (in the lookback period)

    Aroon Up = ((period - periods since highest high) / period) * 100
    Aroon Down = ((period - periods since lowest low) / period) * 100

    Trading signals:
    - When Aroon Up crosses above Aroon Down: potential uptrend (buy signal)
    - When Aroon Down crosses above Aroon Up: potential downtrend (sell signal)
    - Extreme values (>70) indicate strong trends
    - Values near 0 indicate weak trends or consolidation
    """

    def __init__(
        self,
        period: int = 25,
        name: str = "Aroon",
    ):
        """Initialize the Aroon strategy.

        Args:
            period: Number of periods for Aroon calculation. Defaults to 25.
            name: Strategy name. Defaults to "Aroon".

        """
        super().__init__(
            name,
            {
                "period": period,
            },
        )
        self.period = period
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        Raises:
            ValueError: If any parameter is invalid.

        """
        if self.period <= 0:
            raise ValueError("period must be positive")

    def _calculate_aroon(self, high: pd.Series, low: pd.Series) -> tuple[pd.Series, pd.Series]:
        """Calculate Aroon Up and Aroon Down indicators.

        Returns:
            Tuple of (aroon_up, aroon_down) where:
            - aroon_up: ((period - periods since highest high) / period) * 100
            - aroon_down: ((period - periods since lowest low) / period) * 100

        """
        # Calculate periods since highest high and lowest low
        # Using rolling window to find the index of max/min within the period
        # Then calculate how many periods ago that was

        def periods_since_high(x: pd.Series) -> int:
            # Get the index of the maximum value (most recent if tie)
            # When all values are equal, we want the most recent (highest index)
            max_val = x.max()
            # Find the most recent index with the maximum value
            max_idx = len(x) - 1
            for i in range(len(x) - 1, -1, -1):
                if x.iloc[i] == max_val:
                    max_idx = i
                    break
            else:  # pragma: no cover
                pass
            return self.period - 1 - max_idx

        def periods_since_low(x: pd.Series) -> int:
            # Get the index of the minimum value (most recent if tie)
            # When all values are equal, we want the most recent (highest index)
            min_val = x.min()
            # Find the most recent index with the minimum value
            min_idx = len(x) - 1
            for i in range(len(x) - 1, -1, -1):
                if x.iloc[i] == min_val:
                    min_idx = i
                    break
            else:  # pragma: no cover
                pass
            return self.period - 1 - min_idx

        # Calculate rolling applications
        periods_since_high_series = high.rolling(window=self.period).apply(
            periods_since_high, raw=False
        )
        periods_since_low_series = low.rolling(window=self.period).apply(
            periods_since_low, raw=False
        )

        # Calculate Aroon values
        aroon_up = ((self.period - periods_since_high_series) / self.period) * 100
        aroon_down = ((self.period - periods_since_low_series) / self.period) * 100

        return aroon_up, aroon_down

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate trading signals based on Aroon indicator crossovers.

        Args:
            data: Dictionary mapping symbols to OHLCV DataFrames.

        Returns:
            List of trading signals.

        """
        signals = []

        for symbol, df in data.items():
            if len(df) < self.period + 1:
                continue

            high = df["high"]
            low = df["low"]
            close = df["close"]

            # Calculate Aroon indicators
            aroon_up, aroon_down = self._calculate_aroon(high, low)

            current_aroon_up = aroon_up.iloc[-1]
            current_aroon_down = aroon_down.iloc[-1]
            prev_aroon_up = aroon_up.iloc[-2]
            prev_aroon_down = aroon_down.iloc[-2]
            current_price = close.iloc[-1]
            timestamp = df.index[-1]

            # Skip if any values are NaN (insufficient data for calculation)
            if (
                pd.isna(current_aroon_up)
                or pd.isna(current_aroon_down)
                or pd.isna(prev_aroon_up)
                or pd.isna(prev_aroon_down)
            ):
                continue

            # Aroon Up crosses above Aroon Down - bullish signal (buy)
            if prev_aroon_up <= prev_aroon_down and current_aroon_up > current_aroon_down:
                # Strength based on how strong the crossover is and the Aroon Up value
                strength = min(1.0, (current_aroon_up - current_aroon_down) / 100 * 2 + 0.5)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "aroon_up": current_aroon_up,
                            "aroon_down": current_aroon_down,
                            "crossover_type": "bullish",
                        },
                    )
                )
            # Aroon Down crosses above Aroon Up - bearish signal (sell)
            elif prev_aroon_down <= prev_aroon_up and current_aroon_down > current_aroon_up:
                # Strength based on how strong the crossover is and the Aroon Down value
                strength = min(1.0, (current_aroon_down - current_aroon_up) / 100 * 2 + 0.5)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "aroon_up": current_aroon_up,
                            "aroon_down": current_aroon_down,
                            "crossover_type": "bearish",
                        },
                    )
                )

        return signals


class KeltnerChannelStrategy(Strategy):
    """Keltner Channel Strategy.

    The Keltner Channel is a volatility-based envelope set above and below an
    exponential moving average (EMA). The channels are typically set at a
    multiple of the Average True Range (ATR) above and below the EMA.

    Trading signals:
    - Buy when price closes above the upper channel (breakout)
    - Sell when price closes below the lower channel (breakdown)
    - Optional: Buy when price crosses above the middle EMA (trend change)
    - Optional: Sell when price crosses below the middle EMA (trend change)
    """

    def __init__(
        self,
        ema_period: int = 20,
        atr_period: int = 10,
        multiplier: float = 2.0,
        use_middle_cross: bool = False,
        name: str = "Keltner_Channel",
    ):
        """Initialize the Keltner Channel strategy.

        Args:
            ema_period: Period for EMA calculation. Defaults to 20.
            atr_period: Period for ATR calculation. Defaults to 10.
            multiplier: ATR multiplier for channel width. Defaults to 2.0.
            use_middle_cross: Whether to use middle EMA crossovers for signals.
                Defaults to False.
            name: Strategy name. Defaults to "Keltner_Channel".

        """
        super().__init__(
            name,
            {
                "ema_period": ema_period,
                "atr_period": atr_period,
                "multiplier": multiplier,
                "use_middle_cross": use_middle_cross,
            },
        )
        self.ema_period = ema_period
        self.atr_period = atr_period
        self.multiplier = multiplier
        self.use_middle_cross = use_middle_cross
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        Raises:
            ValueError: If any parameter is invalid.

        """
        if self.ema_period <= 0:
            raise ValueError("ema_period must be positive")
        if self.atr_period <= 0:
            raise ValueError("atr_period must be positive")
        if self.multiplier <= 0:
            raise ValueError("multiplier must be positive")

    def _ema(self, close: pd.Series, period: int) -> pd.Series:
        """Calculate Exponential Moving Average.

        Args:
            close: Closing price series.
            period: EMA period.

        Returns:
            EMA series.

        """
        return close.ewm(span=period, adjust=False).mean()

    def _atr(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Average True Range (ATR).

        Args:
            df: OHLC DataFrame.
            period: ATR period.

        Returns:
            ATR series.

        """
        high = df["high"]
        low = df["low"]
        close = df["close"]

        # True Range = max(high - low, |high - prev_close|, |low - prev_close|)
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # ATR is the rolling average of True Range
        atr = true_range.rolling(window=period).mean()
        return atr

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate trading signals based on Keltner Channel.

        Args:
            data: Dictionary mapping symbols to OHLCV DataFrames.

        Returns:
            List of trading signals.

        """
        signals: list[Signal] = []

        for symbol, df in data.items():
            # Need enough data for EMA and ATR calculations
            min_required = max(self.ema_period, self.atr_period) + 1
            if len(df) < min_required:
                continue

            close = df["close"]

            # Calculate EMA (middle line)
            ema = self._ema(close, self.ema_period)

            # Calculate ATR
            atr = self._atr(df, self.atr_period)

            # Calculate upper and lower channels
            upper_channel = ema + (self.multiplier * atr)
            lower_channel = ema - (self.multiplier * atr)

            current_price = close.iloc[-1]
            current_ema = ema.iloc[-1]
            current_upper = upper_channel.iloc[-1]
            current_lower = lower_channel.iloc[-1]
            prev_price = close.iloc[-2]
            prev_ema = ema.iloc[-2]
            prev_upper = upper_channel.iloc[-2]
            prev_lower = lower_channel.iloc[-2]
            timestamp = df.index[-1]

            # Skip if any required values are NaN or zero (avoid division by zero)
            if (
                pd.isna(current_price)
                or pd.isna(current_ema)
                or pd.isna(current_upper)
                or pd.isna(current_lower)
                or pd.isna(prev_price)
                or pd.isna(prev_ema)
                or pd.isna(prev_upper)
                or pd.isna(prev_lower)
                or current_ema == 0
                or current_upper == 0
                or current_lower == 0
            ):
                continue

            # Channel breakout signals
            if prev_price <= prev_upper and current_price > current_upper:
                # Buy signal: price broke above upper channel
                strength = min(1.0, (current_price - current_upper) / current_upper * 10 + 0.5)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "ema": current_ema,
                            "upper_channel": current_upper,
                            "lower_channel": current_lower,
                            "atr": atr.iloc[-1],
                            "signal_type": "upper_breakout",
                        },
                    )
                )
            elif prev_price >= prev_lower and current_price < current_lower:
                # Sell signal: price broke below lower channel
                strength = min(1.0, (current_lower - current_price) / current_lower * 10 + 0.5)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "ema": current_ema,
                            "upper_channel": current_upper,
                            "lower_channel": current_lower,
                            "atr": atr.iloc[-1],
                            "signal_type": "lower_breakout",
                        },
                    )
                )

            # Optional middle line crossover signals
            if self.use_middle_cross:
                if prev_price <= prev_ema and current_price > current_ema:
                    # Buy signal: price crossed above EMA
                    strength = min(1.0, (current_price - current_ema) / current_ema * 10 + 0.5)
                    signals.append(
                        Signal(
                            symbol=symbol,
                            action="buy",
                            strength=strength,
                            price=current_price,
                            timestamp=timestamp,
                            metadata={
                                "ema": current_ema,
                                "upper_channel": current_upper,
                                "lower_channel": current_lower,
                                "atr": atr.iloc[-1],
                                "signal_type": "middle_cross_up",
                            },
                        )
                    )
                elif prev_price >= prev_ema and current_price < current_ema:
                    # Sell signal: price crossed below EMA
                    strength = min(1.0, (current_ema - current_price) / current_ema * 10 + 0.5)
                    signals.append(
                        Signal(
                            symbol=symbol,
                            action="sell",
                            strength=strength,
                            price=current_price,
                            timestamp=timestamp,
                            metadata={
                                "ema": current_ema,
                                "upper_channel": current_upper,
                                "lower_channel": current_lower,
                                "atr": atr.iloc[-1],
                                "signal_type": "middle_cross_down",
                            },
                        )
                    )

        return signals


class StochasticOscillatorStrategy(Strategy):
    """Stochastic Oscillator Strategy.

    The Stochastic Oscillator compares a security's closing price to its price
    range over a given period. It consists of two lines:
    - %K (Fast Stochastic): The raw stochastic value
    - %D (Slow Stochastic): A moving average of %K (typically 3-period SMA)

    Trading signals:
    - Buy when %K crosses above %D in oversold territory (< 20)
    - Sell when %K crosses below %D in overbought territory (> 80)
    - Optional: Buy/sell on %K crossing the 50 level (mid-line)
    """

    def __init__(
        self,
        k_period: int = 14,
        d_period: int = 3,
        oversold: float = 20,
        overbought: float = 80,
        use_midline: bool = False,
        name: str = "Stochastic_Oscillator",
    ):
        """Initialize the Stochastic Oscillator strategy.

        Args:
            k_period: Period for %K calculation. Defaults to 14.
            d_period: Period for %D (SMA of %K). Defaults to 3.
            oversold: Oversold threshold. Defaults to 20.
            overbought: Overbought threshold. Defaults to 80.
            use_midline: Whether to use midline crossovers. Defaults to False.
            name: Strategy name. Defaults to "Stochastic_Oscillator".

        """
        super().__init__(
            name,
            {
                "k_period": k_period,
                "d_period": d_period,
                "oversold": oversold,
                "overbought": overbought,
                "use_midline": use_midline,
            },
        )
        self.k_period = k_period
        self.d_period = d_period
        self.oversold = oversold
        self.overbought = overbought
        self.use_midline = use_midline
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        Raises:
            ValueError: If any parameter is invalid.

        """
        if self.k_period <= 0:
            raise ValueError("k_period must be positive")
        if self.d_period <= 0:
            raise ValueError("d_period must be positive")
        if not (0 < self.oversold < 100):
            raise ValueError("oversold must be between 0 and 100")
        if not (0 < self.overbought < 100):
            raise ValueError("overbought must be between 0 and 100")
        if self.oversold >= self.overbought:
            raise ValueError("oversold must be less than overbought")

    def _calculate_stochastic(
        self, high: pd.Series, low: pd.Series, close: pd.Series
    ) -> tuple[pd.Series, pd.Series]:
        """Calculate %K and %D lines of the Stochastic Oscillator.

        Returns:
            Tuple of (k_percent, d_percent) where:
            - k_percent: Fast %K = 100 * (close - lowest low) / (highest high - lowest low)
            - d_percent: Slow %D = SMA of %K over d_period

        """
        lowest_low = low.rolling(window=self.k_period).min()
        highest_high = high.rolling(window=self.k_period).max()

        # %K calculation
        k_percent = 100 * (close - lowest_low) / (highest_high - lowest_low)

        # %D calculation (SMA of %K)
        d_percent = k_percent.rolling(window=self.d_period).mean()

        return k_percent, d_percent

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate trading signals based on Stochastic Oscillator.

        Args:
            data: Dictionary mapping symbols to OHLCV DataFrames.

        Returns:
            List of trading signals.

        """
        signals = []

        for symbol, df in data.items():
            min_required = self.k_period + self.d_period + 1
            if len(df) < min_required:
                continue

            high = df["high"]
            low = df["low"]
            close = df["close"]

            # Calculate Stochastic Oscillator
            k_percent, d_percent = self._calculate_stochastic(high, low, close)

            current_k = k_percent.iloc[-1]
            current_d = d_percent.iloc[-1]
            prev_k = k_percent.iloc[-2]
            prev_d = d_percent.iloc[-2]
            current_price = close.iloc[-1]
            timestamp = df.index[-1]

            # Skip if any values are NaN
            if pd.isna(current_k) or pd.isna(current_d) or pd.isna(prev_k) or pd.isna(prev_d):
                continue

            # Bullish crossover in oversold territory: %K crosses above %D when both are oversold
            if prev_k <= prev_d and current_k > current_d and current_k < self.oversold:
                strength = min(1.0, (self.oversold - current_k) / self.oversold + 0.5)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "k_percent": current_k,
                            "d_percent": current_d,
                            "signal_type": "oversold_crossover",
                        },
                    )
                )
            # Bearish crossover in overbought territory: %K crosses below %D when both are overbought
            elif prev_k >= prev_d and current_k < current_d and current_k > self.overbought:
                strength = min(1.0, (current_k - self.overbought) / (100 - self.overbought) + 0.5)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "k_percent": current_k,
                            "d_percent": current_d,
                            "signal_type": "overbought_crossover",
                        },
                    )
                )
            # Optional midline crossover signals
            elif self.use_midline:
                # Buy when %K crosses above 50
                if prev_k <= 50 and current_k > 50:
                    strength = min(1.0, abs(current_k - 50) / 50 * 0.5 + 0.3)
                    signals.append(
                        Signal(
                            symbol=symbol,
                            action="buy",
                            strength=strength,
                            price=current_price,
                            timestamp=timestamp,
                            metadata={
                                "k_percent": current_k,
                                "d_percent": current_d,
                                "signal_type": "midline_cross_up",
                            },
                        )
                    )
                # Sell when %K crosses below 50
                elif prev_k >= 50 and current_k < 50:
                    strength = min(1.0, abs(50 - current_k) / 50 * 0.5 + 0.3)
                    signals.append(
                        Signal(
                            symbol=symbol,
                            action="sell",
                            strength=strength,
                            price=current_price,
                            timestamp=timestamp,
                            metadata={
                                "k_percent": current_k,
                                "d_percent": current_d,
                                "signal_type": "midline_cross_down",
                            },
                        )
                    )

        return signals


class IchimokuCloudStrategy(Strategy):
    """Ichimoku Cloud Strategy.

    The Ichimoku Cloud (Ichimoku Kinko Hyo) is a collection of technical indicators
    that show support and resistance levels, momentum, and trend direction.
    It consists of five lines:
    1. Tenkan-sen (Conversion Line): (Highest High + Lowest Low) / 2 for the last 9 periods
    2. Kijun-sen (Base Line): (Highest High + Lowest Low) / 2 for the last 26 periods
    3. Senkou Span A (Leading Span A): (Tenkan-sen + Kijun-sen) / 2, plotted 26 periods ahead
    4. Senkou Span B (Leading Span B): (Highest High + Lowest Low) / 2 for the last 52 periods, plotted 26 periods ahead
    5. Chikou Span (Lagging Span): Close price plotted 26 periods behind

    Trading signals:
    - Buy when Tenkan-sen crosses above Kijun-sen and price is above the cloud
    - Sell when Tenkan-sen crosses below Kijun-sen and price is below the cloud
    """

    def __init__(
        self,
        tenkan_period: int = 9,
        kijun_period: int = 26,
        senkou_b_period: int = 52,
        name: str = "Ichimoku_Cloud",
    ):
        """Initialize the Ichimoku Cloud strategy.

        Args:
            tenkan_period: Period for Tenkan-sen. Defaults to 9.
            kijun_period: Period for Kijun-sen. Defaults to 26.
            senkou_b_period: Period for Senkou Span B. Defaults to 52.
            name: Strategy name. Defaults to "Ichimoku_Cloud".

        """
        super().__init__(
            name,
            {
                "tenkan_period": tenkan_period,
                "kijun_period": kijun_period,
                "senkou_b_period": senkou_b_period,
            },
        )
        self.tenkan_period = tenkan_period
        self.kijun_period = kijun_period
        self.senkou_b_period = senkou_b_period
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        Raises:
            ValueError: If any parameter is invalid.

        """
        if self.tenkan_period <= 0:
            raise ValueError("tenkan_period must be positive")
        if self.kijun_period <= 0:
            raise ValueError("kijun_period must be positive")
        if self.senkou_b_period <= 0:
            raise ValueError("senkou_b_period must be positive")

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate trading signals based on Ichimoku Cloud.

        Args:
            data: Dictionary mapping symbols to OHLCV DataFrames.

        Returns:
            List of trading signals.

        """
        signals = []

        for symbol, df in data.items():
            # We need enough data for the longest period and the forward shift
            min_required = max(self.senkou_b_period, self.kijun_period) + self.kijun_period
            if len(df) < min_required:
                continue

            high = df["high"]
            low = df["low"]
            close = df["close"]

            # Calculate Tenkan-sen (Conversion Line)
            tenkan_high = high.rolling(window=self.tenkan_period).max()
            tenkan_low = low.rolling(window=self.tenkan_period).min()
            tenkan_sen = (tenkan_high + tenkan_low) / 2

            # Calculate Kijun-sen (Base Line)
            kijun_high = high.rolling(window=self.kijun_period).max()
            kijun_low = low.rolling(window=self.kijun_period).min()
            kijun_sen = (kijun_high + kijun_low) / 2

            # Calculate Senkou Span A (Leading Span A)
            senkou_a = ((tenkan_sen + kijun_sen) / 2).shift(self.kijun_period)

            # Calculate Senkou Span B (Leading Span B)
            senkou_b_high = high.rolling(window=self.senkou_b_period).max()
            senkou_b_low = low.rolling(window=self.senkou_b_period).min()
            senkou_b = ((senkou_b_high + senkou_b_low) / 2).shift(self.kijun_period)

            current_price = close.iloc[-1]
            current_tenkan = tenkan_sen.iloc[-1]
            current_kijun = kijun_sen.iloc[-1]
            current_senkou_a = senkou_a.iloc[-1]
            current_senkou_b = senkou_b.iloc[-1]
            prev_tenkan = tenkan_sen.iloc[-2]
            prev_kijun = kijun_sen.iloc[-2]
            timestamp = df.index[-1]

            # Skip if any values are NaN or zero (avoid division by zero)
            if (
                pd.isna(current_price)
                or pd.isna(current_tenkan)
                or pd.isna(current_kijun)
                or pd.isna(current_senkou_a)
                or pd.isna(current_senkou_b)
                or pd.isna(prev_tenkan)
                or pd.isna(prev_kijun)
                or current_kijun == 0
            ):
                continue

            # Determine cloud boundaries (upper and lower)
            cloud_top = max(current_senkou_a, current_senkou_b)
            cloud_bottom = min(current_senkou_a, current_senkou_b)

            # Bullish signal: Tenkan crosses above Kijun AND price above cloud
            if (
                prev_tenkan <= prev_kijun
                and current_tenkan > current_kijun
                and current_price > cloud_top
            ):
                strength = min(1.0, (current_tenkan - current_kijun) / current_kijun * 10 + 0.5)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "tenkan_sen": current_tenkan,
                            "kijun_sen": current_kijun,
                            "senkou_span_a": current_senkou_a,
                            "senkou_span_b": current_senkou_b,
                            "cloud_top": cloud_top,
                            "cloud_bottom": cloud_bottom,
                            "signal_type": "tenkan_kijun_bullish_crossover",
                        },
                    )
                )
            # Bearish signal: Tenkan crosses below Kijun AND price below cloud
            elif (
                prev_tenkan >= prev_kijun
                and current_tenkan < current_kijun
                and current_price < cloud_bottom
            ):
                strength = min(1.0, (current_kijun - current_tenkan) / current_kijun * 10 + 0.5)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "tenkan_sen": current_tenkan,
                            "kijun_sen": current_kijun,
                            "senkou_span_a": current_senkou_a,
                            "senkou_span_b": current_senkou_b,
                            "cloud_top": cloud_top,
                            "cloud_bottom": cloud_bottom,
                            "signal_type": "tenkan_kijun_bearish_crossover",
                        },
                    )
                )

        return signals


class VWAPStrategy(Strategy):
    """Volume Weighted Average Price (VWAP) Strategy.

    The VWAP strategy generates signals based on price crossing the VWAP line.
    VWAP is calculated as the cumulative (typical price * volume) divided by
    cumulative volume, where typical price = (high + low + close) / 3.

    Trading signals:
    - Buy when price crosses above VWAP
    - Sell when price crosses below VWAP
    """

    def __init__(self, name: str = "VWAP"):
        """Initialize the VWAP strategy.

        Args:
            name: Strategy name. Defaults to "VWAP".

        """
        super().__init__(name, {})
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        VWAP strategy has no parameters to validate.
        """

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate trading signals based on VWAP crossovers.

        Args:
            data: Dictionary mapping symbols to OHLCV DataFrames.

        Returns:
            List of trading signals.

        """
        signals: list[Signal] = []

        for symbol, df in data.items():
            if len(df) < 2:
                continue

            # Calculate typical price and VWAP
            typical_price = (df["high"] + df["low"] + df["close"]) / 3
            vwap = (typical_price * df["volume"]).cumsum() / df["volume"].cumsum()

            # Current and previous values
            current_price = df["close"].iloc[-1]
            current_vwap = vwap.iloc[-1]
            prev_price = df["close"].iloc[-2]
            prev_vwap = vwap.iloc[-2]
            timestamp = df.index[-1]

            # Skip if VWAP is NaN or zero (insufficient data / degenerate input)
            if (
                pd.isna(current_vwap)
                or pd.isna(prev_vwap)
                or pd.isna(current_price)
                or pd.isna(prev_price)
                or current_vwap == 0
                or current_price == 0
            ):
                continue

            # Crossover detection
            if prev_price <= prev_vwap and current_price > current_vwap:
                # Price crossed above VWAP - buy signal
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=min(1.0, (current_price - current_vwap) / current_vwap * 10),
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "vwap": current_vwap,
                            "signal_type": "price_above_vwap",
                        },
                    )
                )
            elif prev_price >= prev_vwap and current_price < current_vwap:
                # Price crossed below VWAP - sell signal
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=min(1.0, (current_vwap - current_price) / current_vwap * 10),
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "vwap": current_vwap,
                            "signal_type": "price_below_vwap",
                        },
                    )
                )

        return signals


class ParabolicSARStrategy(Strategy):
    """Parabolic SAR (Stop and Reverse) Strategy.

    The Parabolic SAR is a trend-following indicator that provides entry and exit
    points based on a parabolic curve that trails price. It is particularly
    effective in trending markets.

    The SAR is calculated as:
        SAR_t = SAR_{t-1} + AF * (EP - SAR_{t-1})
    where:
        AF is the acceleration factor (starts at step, increases by step each time
            a new extreme point is reached, up to max_step)
        EP is the extreme point (highest high for long trend, lowest low for short trend)

    Trading signals:
        - Buy when price crosses above the SAR (trend changes to bullish)
        - Sell when price crosses below the SAR (trend changes to bearish)
    """

    def __init__(
        self,
        step: float = 0.02,
        max_step: float = 0.20,
        name: str = "Parabolic_SAR",
    ):
        """Initialize the Parabolic SAR strategy.

        Args:
            step: Initial step/acceleration factor. Defaults to 0.02.
            max_step: Maximum step/acceleration factor. Defaults to 0.20.
            name: Strategy name. Defaults to "Parabolic_SAR".

        """
        super().__init__(
            name,
            {
                "step": step,
                "max_step": max_step,
            },
        )
        self.step = step
        self.max_step = max_step
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        Raises:
            ValueError: If any parameter is invalid.

        """
        if self.step <= 0:
            raise ValueError("step must be positive")
        if self.max_step <= 0:
            raise ValueError("max_step must be positive")
        if self.step > self.max_step:
            raise ValueError("step must be less than or equal to max_step")

    def _calculate_sar(self, high: pd.Series, low: pd.Series) -> tuple[pd.Series, pd.Series]:
        """Calculate Parabolic SAR and trend.

        Returns:
            Tuple of (sar, trend) where:
                sar: Parabolic SAR values
                trend: 1 for bullish (SAR below price), -1 for bearish (SAR above price)

        """
        # Initialize arrays
        sar = pd.Series(index=high.index, dtype=float)
        trend = pd.Series(index=high.index, dtype=int)
        # Extreme point: highest high for long, lowest low for short
        ep = pd.Series(index=high.index, dtype=float)
        # Acceleration factor
        af = pd.Series(index=high.index, dtype=float)

        # Need at least two periods to initialize
        if len(high) < 2:
            # Not enough data, return all NaN
            sar.iloc[:] = np.nan
            trend.iloc[:] = 0
            ep.iloc[:] = np.nan
            af.iloc[:] = 0.0
            return sar, trend

        # Initialize for the first day
        # We'll assume the initial trend based on the first two periods
        if high.iloc[1] > high.iloc[0]:
            # Start with a long trend
            trend.iloc[0] = 1
            sar.iloc[0] = low.iloc[0]  # SAR starts at the low of the first period
            ep.iloc[0] = high.iloc[0]  # EP is the high of the first period
            af.iloc[0] = self.step
        else:
            # Start with a short trend
            trend.iloc[0] = -1
            sar.iloc[0] = high.iloc[0]  # SAR starts at the high of the first period
            ep.iloc[0] = low.iloc[0]  # EP is the low of the first period
            af.iloc[0] = self.step

        # Calculate for each subsequent period
        for i in range(1, len(high)):
            # Previous values
            prev_sar = sar.iloc[i - 1]
            prev_trend = trend.iloc[i - 1]
            prev_ep = ep.iloc[i - 1]
            prev_af = af.iloc[i - 1]

            # Current SAR
            sar.iloc[i] = prev_sar + prev_af * (prev_ep - prev_sar)

            # Check if we need to reverse the trend
            if prev_trend == 1:  # Currently long
                # SAR should be below the low
                if sar.iloc[i] > low.iloc[i]:
                    # Trend reversal to short
                    trend.iloc[i] = -1
                    sar.iloc[i] = prev_ep  # SAR becomes the previous EP
                    ep.iloc[i] = low.iloc[i]  # EP is the low of this period
                    af.iloc[i] = self.step  # Reset AF
                else:
                    # Continue long
                    trend.iloc[i] = 1
                    # Update EP if we have a new high
                    if high.iloc[i] > prev_ep:
                        ep.iloc[i] = high.iloc[i]
                        # Increase AF, but not beyond max_step
                        af.iloc[i] = min(prev_af + self.step, self.max_step)
                    else:
                        ep.iloc[i] = prev_ep
                        af.iloc[i] = prev_af
            else:  # Currently short
                # SAR should be above the high
                if sar.iloc[i] < high.iloc[i]:
                    # Trend reversal to long
                    trend.iloc[i] = 1
                    sar.iloc[i] = prev_ep  # SAR becomes the previous EP
                    ep.iloc[i] = high.iloc[i]  # EP is the high of this period
                    af.iloc[i] = self.step  # Reset AF
                else:
                    # Continue short
                    trend.iloc[i] = -1
                    # Update EP if we have a new low
                    if low.iloc[i] < prev_ep:
                        ep.iloc[i] = low.iloc[i]
                        # Increase AF, but not beyond max_step
                        af.iloc[i] = min(prev_af + self.step, self.max_step)
                    else:
                        ep.iloc[i] = prev_ep
                        af.iloc[i] = prev_af

        return sar, trend

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate trading signals based on Parabolic SAR trend reversals.

        Args:
            data: Dictionary mapping symbols to OHLCV DataFrames.

        Returns:
            List of trading signals.

        """
        signals = []

        for symbol, df in data.items():
            if len(df) < 2:
                continue

            high = df["high"]
            low = df["low"]
            close = df["close"]

            sar, trend = self._calculate_sar(high, low)

            current_price = close.iloc[-1]
            current_sar = sar.iloc[-1]
            current_trend = trend.iloc[-1]
            prev_trend = trend.iloc[-2] if len(trend) > 1 else current_trend
            timestamp = df.index[-1]

            # Skip if SAR is NaN or price is NaN/zero (insufficient data / degenerate input)
            if (
                pd.isna(current_sar)
                or pd.isna(current_trend)
                or pd.isna(prev_trend)
                or pd.isna(current_price)
                or current_price == 0
            ):
                continue

            # Check for trend reversal
            if current_trend != prev_trend:
                if current_trend == 1 and prev_trend == -1:
                    # Short to long reversal - bullish buy signal
                    strength = 1.0
                    signals.append(
                        Signal(
                            symbol=symbol,
                            action="buy",
                            strength=strength,
                            price=current_price,
                            timestamp=timestamp,
                            metadata={
                                "signal_type": "trend_reversal_bullish",
                                "trend": "bullish",
                                "sar": float(current_sar),
                                "current_trend": int(current_trend),
                                "prev_trend": int(prev_trend),
                            },
                        )
                    )
                # The fall-through of this elif is unreachable: _calculate_sar only
                # emits trend values of +1/-1, so a trend change always matches
                # exactly one of the two reversal patterns.
                elif current_trend == -1 and prev_trend == 1:  # pragma: no branch
                    # Long to short reversal - bearish sell signal
                    strength = 1.0
                    signals.append(
                        Signal(
                            symbol=symbol,
                            action="sell",
                            strength=strength,
                            price=current_price,
                            timestamp=timestamp,
                            metadata={
                                "signal_type": "trend_reversal_bearish",
                                "trend": "bearish",
                                "sar": float(current_sar),
                                "current_trend": int(current_trend),
                                "prev_trend": int(prev_trend),
                            },
                        )
                    )

        return signals


class EMACrossover(Strategy):
    """Exponential Moving Average (EMA) crossover strategy.

    Signals:
        - Buy when fast EMA crosses above slow EMA
        - Sell when fast EMA crosses below slow EMA

    Parameters:
        fast_period (int): Lookback window for the fast EMA (default: 12)
        slow_period (int): Lookback window for the slow EMA (default: 26)

    """

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        name: str = "EMA_Crossover",
        **kwargs: Any,
    ) -> None:
        """Initialize the EMA crossover strategy.

        Args:
            fast_period: Lookback window for the fast EMA.
            slow_period: Lookback window for the slow EMA; must exceed ``fast_period``.
            name: Strategy name.
            **kwargs: Additional arguments.

        Raises:
            ValueError: If parameters are invalid.

        """

        super().__init__(
            name,
            {
                "fast_period": fast_period,
                "slow_period": slow_period,
            },
        )
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters."""

        if not isinstance(self.fast_period, int) or self.fast_period < 1:
            raise ValueError("fast_period must be a positive integer")
        if not isinstance(self.slow_period, int) or self.slow_period < 1:
            raise ValueError("slow_period must be a positive integer")
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be less than slow_period")

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate buy/sell signals based on EMA crossover.

        Args:
            data: Dictionary mapping symbols to OHLCV DataFrames.

        Returns:
            List of trading signals.

        """
        signals = []

        for symbol, df in data.items():
            if len(df) < self.slow_period:
                continue

            close = df["close"]
            fast_ema = close.ewm(span=self.fast_period, min_periods=self.fast_period).mean()
            slow_ema = close.ewm(span=self.slow_period, min_periods=self.slow_period).mean()

            timestamp = df.index[-1]
            current_price = close.iloc[-1]
            current_fast = fast_ema.iloc[-1]
            current_slow = slow_ema.iloc[-1]
            prev_fast = fast_ema.iloc[-2] if len(fast_ema) > 1 else current_fast
            prev_slow = slow_ema.iloc[-2] if len(slow_ema) > 1 else current_slow

            if (
                pd.isna(current_fast)
                or pd.isna(current_slow)
                or pd.isna(prev_fast)
                or pd.isna(prev_slow)
                or pd.isna(current_price)
            ):
                continue

            # Buy when fast EMA crosses above slow EMA
            if prev_fast <= prev_slow and current_fast > current_slow:
                strength = (
                    min(1.0, (current_fast - current_slow) / current_price * 10.0 + 0.5)
                    if current_price
                    else 0.5
                )
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "fast_ema": current_fast,
                            "slow_ema": current_slow,
                            "signal_type": "ema_crossover_bullish",
                        },
                    )
                )
            # Sell when fast EMA crosses below slow EMA
            elif prev_fast >= prev_slow and current_fast < current_slow:
                strength = (
                    min(1.0, (current_slow - current_fast) / current_price * 10.0 + 0.5)
                    if current_price
                    else 0.5
                )
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "fast_ema": current_fast,
                            "slow_ema": current_slow,
                            "signal_type": "ema_crossover_bearish",
                        },
                    )
                )

        return signals


class MomentumStrategy(Strategy):
    """Momentum Strategy.

    A simple momentum-based strategy that generates signals based on price
    momentum relative to a lookback period. Buy signals are generated when
    momentum is positive and above a threshold, sell signals when momentum
    is negative.

    Momentum is calculated as:
        Momentum = (Close_t / Close_{t-n}) - 1

    Trading signals:
        - Buy when momentum > threshold (positive momentum)
        - Sell when momentum < -threshold (negative momentum)
    """

    def __init__(
        self,
        period: int = 10,
        threshold: float = 0.01,
        name: str = "Momentum",
    ):
        """Initialize the Momentum strategy.

        Args:
            period: Lookback period for momentum calculation. Defaults to 10.
            threshold: Threshold for signal generation. Defaults to 0.01 (1%).
            name: Strategy name. Defaults to "Momentum".

        Raises:
            ValueError: If parameters are invalid.

        """
        super().__init__(
            name,
            {
                "period": period,
                "threshold": threshold,
            },
        )
        self.period = period
        self.threshold = threshold
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        Raises:
            ValueError: If period is non-positive or threshold is negative.

        """
        if self.period <= 0:
            raise ValueError("period must be positive")
        if self.threshold < 0:
            raise ValueError("threshold must be non-negative")

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate trading signals based on momentum.

        Args:
            data: Dictionary mapping symbols to OHLCV DataFrames.

        Returns:
            List of trading signals.

        """
        signals: list[Signal] = []

        for symbol, df in data.items():
            if len(df) < self.period + 1:
                continue

            close = df["close"]
            current_price = close.iloc[-1]
            prev_price = close.iloc[-(self.period + 1)]
            timestamp = df.index[-1]

            if pd.isna(current_price) or pd.isna(prev_price) or prev_price == 0:
                continue

            momentum = (current_price / prev_price) - 1.0

            if momentum > self.threshold:
                strength = min(1.0, abs(momentum) / self.threshold)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "momentum": momentum,
                            "period": self.period,
                            "signal_type": "positive_momentum",
                        },
                    )
                )
            elif momentum < -self.threshold:
                strength = min(1.0, abs(momentum) / self.threshold)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "momentum": momentum,
                            "period": self.period,
                            "signal_type": "negative_momentum",
                        },
                    )
                )

        return signals


class ADXStrategy(Strategy):
    """Average Directional Index Strategy.

    Measures trend strength with the Average Directional Index (ADX) using
    Wilder's smoothing. The strategy buys when ADX is above the trend
    threshold and the positive directional index exceeds the negative one
    (bullish trend), and sells when ADX is above the threshold and the
    negative directional index exceeds the positive one (bearish trend).
    While ADX is at or below the threshold the market lacks a strong trend
    and no signal is emitted.

    The directional indicators are:

    * ``+DI``: smoothed upward directional movement over ``period`` bars.
    * ``-DI``: smoothed downward directional movement over ``period`` bars.
    * ``ADX``: smoothed average of the directional index ``DX = 100 * |
      +DI - -DI | / (+DI + -DI)``.
    """

    def __init__(
        self,
        period: int = 14,
        threshold: float = 25.0,
        name: str = "ADX",
    ):
        """Initialize the ADX strategy.

        Args:
            period: Lookback period for the directional indicators.
            threshold: ADX level above which a trend is considered strong.
            name: Human-readable name of the strategy.

        Raises:
            ValueError: If ``period`` is non-positive or ``threshold`` is not
                strictly between 0 and 100.

        """
        super().__init__(
            name,
            {
                "period": period,
                "threshold": threshold,
            },
        )
        self.period = period
        self.threshold = threshold
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        Raises:
            ValueError: If ``period`` is non-positive or ``threshold`` is not
                strictly between 0 and 100.

        """
        if self.period <= 0:
            raise ValueError("period must be positive")
        if not (0 < self.threshold < 100):
            raise ValueError("threshold must be between 0 and 100")

    def _calculate_adx(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate ADX, +DI, and -DI using Wilder's smoothing.

        Args:
            high: Series of high prices.
            low: Series of low prices.
            close: Series of close prices.

        Returns:
            Tuple of ``(adx, plus_di, minus_di)`` series aligned with the
            inputs. Values are undefined before enough history is available
            for the first ADX value.
        """
        period = self.period

        up_move = high.diff()
        down_move = low.shift(1) - low
        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

        previous_close = close.shift(1)
        true_range = pd.concat(
            [high - low, (high - previous_close).abs(), (low - previous_close).abs()],
            axis=1,
        ).max(axis=1)

        def wilder_smooth(values: pd.Series) -> pd.Series:
            smoothed: pd.Series = values.copy()
            smoothed.iloc[: period - 1] = np.nan
            smoothed.iloc[period - 1] = values.iloc[:period].sum()
            for index in range(period, len(values)):
                smoothed.iloc[index] = (
                    smoothed.iloc[index - 1]
                    - smoothed.iloc[index - 1] / period
                    + values.iloc[index]
                )
            return smoothed

        smoothed_tr = wilder_smooth(true_range)
        smoothed_plus_dm = wilder_smooth(plus_dm)
        smoothed_minus_dm = wilder_smooth(minus_dm)

        with np.errstate(divide="ignore", invalid="ignore"):
            plus_di = 100.0 * smoothed_plus_dm / smoothed_tr
            minus_di = 100.0 * smoothed_minus_dm / smoothed_tr
            dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di)

        plus_di = plus_di.fillna(0.0)
        minus_di = minus_di.fillna(0.0)
        dx = dx.fillna(0.0)

        adx = dx.copy()
        first_adx = 2 * period - 1
        if len(adx) > first_adx:
            adx.iloc[:first_adx] = np.nan
            adx.iloc[first_adx] = dx.iloc[period - 1 : 2 * period - 1].mean()
            for index in range(first_adx + 1, len(adx)):
                adx.iloc[index] = (adx.iloc[index - 1] * (period - 1) + dx.iloc[index]) / period

        return adx, plus_di, minus_di

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate trend-following signals from the ADX.

        Args:
            data: Mapping of symbol to an OHLCV DataFrame containing at
                least ``"high"``, ``"low"``, and ``"close"`` columns.

        Returns:
            List of :class:`Signal` objects. A buy signal is emitted when
            ADX exceeds the threshold with +DI above -DI; a sell signal when
            ADX exceeds the threshold with -DI above +DI. No signal is
            emitted while ADX is at or below the threshold.
        """
        signals: list[Signal] = []
        min_bars = 2 * self.period

        for symbol, df in data.items():
            if len(df) < min_bars:
                continue

            high = df["high"]
            low = df["low"]
            close = df["close"]
            adx, plus_di, minus_di = self._calculate_adx(high, low, close)

            current_adx = adx.iloc[-1]
            current_price = close.iloc[-1]
            if pd.isna(current_adx) or pd.isna(current_price):
                continue

            current_plus = plus_di.iloc[-1]
            current_minus = minus_di.iloc[-1]
            if pd.isna(current_plus) or pd.isna(current_minus):
                continue

            timestamp = df.index[-1]

            if current_adx <= self.threshold:
                continue

            strength = min(
                1.0,
                max(0.0, (current_adx - self.threshold) / (100.0 - self.threshold)),
            )
            metadata = {
                "adx": current_adx,
                "plus_di": current_plus,
                "minus_di": current_minus,
                "period": self.period,
                "threshold": self.threshold,
            }

            if current_plus > current_minus:
                metadata["signal_type"] = "bullish_trend"
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata=metadata,
                    )
                )
            elif current_minus > current_plus:
                metadata["signal_type"] = "bearish_trend"
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata=metadata,
                    )
                )

        return signals


class CCIStrategy(Strategy):
    """Commodity Channel Index strategy.

    The Commodity Channel Index (CCI) measures the deviation of the typical
    price from its simple moving average relative to the mean deviation.
    Values above ``+threshold`` indicate a strong bullish trend and values
    below ``-threshold`` indicate a strong bearish trend.
    """

    def __init__(
        self,
        period: int = 20,
        threshold: float = 100.0,
        name: str = "CCI",
    ):
        super().__init__(
            name,
            {
                "period": period,
                "threshold": threshold,
            },
        )
        self.period = period
        self.threshold = threshold
        self.validate_parameters()

    def validate_parameters(self) -> None:
        if self.period <= 0:
            raise ValueError("period must be positive")
        if self.threshold <= 0:
            raise ValueError("threshold must be positive")

    def _calculate_cci(self, high, low, close):
        typical = (high + low + close) / 3.0
        sma = typical.rolling(window=self.period).mean()
        mean_dev = typical.rolling(window=self.period).apply(
            lambda x: (np.abs(x - x.mean())).mean(), raw=True
        )
        cci = (typical - sma) / (0.015 * mean_dev)
        return cci

    def generate_signals(self, data):
        signals = []
        min_bars = self.period

        for symbol, df in data.items():
            if len(df) < min_bars:
                continue

            high = df["high"]
            low = df["low"]
            close = df["close"]
            cci = self._calculate_cci(high, low, close)

            current_cci = cci.iloc[-1]
            current_price = close.iloc[-1]
            if pd.isna(current_cci) or pd.isna(current_price):
                continue

            timestamp = df.index[-1]

            if current_cci > self.threshold:
                strength = min(1.0, (current_cci - self.threshold) / 100.0)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=max(0.0, strength),
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "cci": current_cci,
                            "period": self.period,
                            "threshold": self.threshold,
                            "signal_type": "bullish",
                        },
                    )
                )
            elif current_cci < -self.threshold:
                strength = min(1.0, (-current_cci - self.threshold) / 100.0)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=max(0.0, strength),
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "cci": current_cci,
                            "period": self.period,
                            "threshold": self.threshold,
                            "signal_type": "bearish",
                        },
                    )
                )

        return signals


class WilliamsRStrategy(Strategy):
    """Williams %R strategy.

    Williams %R is a momentum oscillator that measures where the close lies
    between the highest high and lowest low over a lookback period. Values
    range from -100 to 0: readings below ``oversold`` indicate an oversold
    market (buy), readings above ``overbought`` indicate an overbought
    market (sell).
    """

    def __init__(
        self,
        period: int = 14,
        overbought: float = -20.0,
        oversold: float = -80.0,
        name: str = "Williams %R",
    ):
        super().__init__(
            name,
            {
                "period": period,
                "overbought": overbought,
                "oversold": oversold,
            },
        )
        self.period = period
        self.overbought = overbought
        self.oversold = oversold
        self.validate_parameters()

    def validate_parameters(self) -> None:
        if self.period <= 0:
            raise ValueError("period must be positive")
        if not -100.0 < self.overbought < 0.0:
            raise ValueError("overbought must be between -100 and 0")
        if not -100.0 < self.oversold < 0.0:
            raise ValueError("oversold must be between -100 and 0")
        if self.oversold >= self.overbought:
            raise ValueError("oversold must be below overbought")

    def _calculate_williams_r(self, high, low, close):
        highest = high.rolling(window=self.period).max()
        lowest = low.rolling(window=self.period).min()
        denominator = highest - lowest
        williams_r = (highest - close) / denominator.replace(0, np.nan) * -100.0
        return williams_r

    def generate_signals(self, data):
        signals = []
        min_bars = self.period

        for symbol, df in data.items():
            if len(df) < min_bars:
                continue

            high = df["high"]
            low = df["low"]
            close = df["close"]
            williams_r = self._calculate_williams_r(high, low, close)

            current_williams_r = williams_r.iloc[-1]
            current_price = close.iloc[-1]
            if pd.isna(current_williams_r) or pd.isna(current_price):
                continue

            timestamp = df.index[-1]

            if current_williams_r < self.oversold:
                strength = min(1.0, (self.oversold - current_williams_r) / 100.0)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=max(0.0, strength),
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "williams_r": current_williams_r,
                            "period": self.period,
                            "overbought": self.overbought,
                            "oversold": self.oversold,
                            "signal_type": "oversold",
                        },
                    )
                )
            elif current_williams_r > self.overbought:
                strength = min(1.0, (current_williams_r - self.overbought) / 100.0)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=max(0.0, strength),
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "williams_r": current_williams_r,
                            "period": self.period,
                            "overbought": self.overbought,
                            "oversold": self.oversold,
                            "signal_type": "overbought",
                        },
                    )
                )

        return signals


class OBVStrategy(Strategy):
    """On-Balance Volume (OBV) Strategy.

    On-Balance Volume is a volume-based momentum indicator that cumulatively
    adds volume on up days and subtracts volume on down days:

    - OBV_t = OBV_{t-1} + volume_t when close_t > close_{t-1}
    - OBV_t = OBV_{t-1} - volume_t when close_t < close_{t-1}
    - OBV_t = OBV_{t-1} when close_t == close_{t-1}

    The strategy compares OBV to its signal line (a simple moving average of
    OBV over ``signal_period`` bars) and emits:

    - A buy signal when OBV crosses above its signal line (increasing buying
      pressure).
    - A sell signal when OBV crosses below its signal line (increasing selling
      pressure).
    """

    def __init__(self, signal_period: int = 20, name: str = "OBV"):
        """Initialize the On-Balance Volume strategy.

        Args:
            signal_period: Lookback window for the OBV signal line (SMA of
                OBV). Defaults to 20.
            name: Strategy name. Defaults to "OBV".

        Raises:
            ValueError: If ``signal_period`` is non-positive.

        """
        super().__init__(
            name,
            {
                "signal_period": signal_period,
            },
        )
        self.signal_period = signal_period
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        Raises:
            ValueError: If ``signal_period`` is non-positive.

        """
        if self.signal_period <= 0:
            raise ValueError("signal_period must be positive")

    def _calculate_obv(self, close: pd.Series, volume: pd.Series) -> pd.Series:
        """Calculate the On-Balance Volume series.

        Args:
            close: Series of close prices.
            volume: Series of volumes aligned with ``close``.

        Returns:
            Series of OBV values aligned with the inputs, starting at 0.

        """
        obv: pd.Series = pd.Series(index=close.index, dtype=float)
        obv.iloc[0] = 0.0
        for i in range(1, len(close)):
            if close.iloc[i] > close.iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] + volume.iloc[i]
            elif close.iloc[i] < close.iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] - volume.iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i - 1]
        return obv

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate buy/sell signals from OBV crossovers of its signal line.

        Args:
            data: Mapping of symbol to a DataFrame containing at least
                ``"close"`` and ``"volume"`` columns indexed by timestamp.

        Returns:
            List of :class:`Signal` objects for symbols whose OBV crosses its
            signal line between the last two bars.

        """
        signals: list[Signal] = []

        for symbol, df in data.items():
            if len(df) < self.signal_period + 1:
                continue

            close = df["close"]
            volume = df["volume"]

            obv = self._calculate_obv(close, volume)
            signal_line = obv.rolling(window=self.signal_period).mean()

            current_obv = obv.iloc[-1]
            current_signal = signal_line.iloc[-1]
            prev_obv = obv.iloc[-2]
            prev_signal = signal_line.iloc[-2]
            current_price = close.iloc[-1]
            timestamp = df.index[-1]

            if (
                pd.isna(current_obv)
                or pd.isna(current_signal)
                or pd.isna(prev_obv)
                or pd.isna(prev_signal)
                or pd.isna(current_price)
                or current_price == 0
            ):
                continue

            # OBV crosses above its signal line - rising buying pressure
            if prev_obv <= prev_signal and current_obv > current_signal:
                if current_signal != 0:
                    strength = min(
                        1.0,
                        abs(current_obv - current_signal) / abs(current_signal) + 0.5,
                    )
                else:
                    strength = 0.5
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "obv": current_obv,
                            "signal_line": current_signal,
                            "signal_period": self.signal_period,
                            "signal_type": "obv_cross_above",
                        },
                    )
                )
            # OBV crosses below its signal line - rising selling pressure
            elif prev_obv >= prev_signal and current_obv < current_signal:
                if current_signal != 0:
                    strength = min(
                        1.0,
                        abs(current_signal - current_obv) / abs(current_signal) + 0.5,
                    )
                else:
                    strength = 0.5
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "obv": current_obv,
                            "signal_line": current_signal,
                            "signal_period": self.signal_period,
                            "signal_type": "obv_cross_below",
                        },
                    )
                )

        return signals


class ChaikinMoneyFlowStrategy(Strategy):
    """Chaikin Money Flow Strategy.

    Chaikin Money Flow (CMF) is a volume-weighted momentum oscillator that
    measures buying and selling pressure over a lookback period:

    - Money Flow Multiplier = ((close - low) - (high - close)) / (high - low)
    - Money Flow Volume = Money Flow Multiplier * volume
    - CMF = sum(Money Flow Volume, period) / sum(volume, period)

    CMF oscillates between -1 and +1. Positive values indicate buying
    pressure (close in the upper part of the range on volume), negative values
    indicate selling pressure.

    Trading signals:
    - Buy when CMF crosses above zero (selling pressure turns to buying pressure).
    - Sell when CMF crosses below zero (buying pressure turns to selling pressure).
    """

    def __init__(self, period: int = 20, name: str = "Chaikin_Money_Flow"):
        """Initialize the Chaikin Money Flow strategy.

        Args:
            period: Lookback window for the CMF calculation. Defaults to 20.
            name: Strategy name. Defaults to "Chaikin_Money_Flow".

        Raises:
            ValueError: If ``period`` is non-positive.

        """
        super().__init__(
            name,
            {
                "period": period,
            },
        )
        self.period = period
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        Raises:
            ValueError: If ``period`` is non-positive.

        """
        if self.period <= 0:
            raise ValueError("period must be positive")

    def _calculate_cmf(self, df: pd.DataFrame) -> pd.Series:
        """Calculate the Chaikin Money Flow series.

        Args:
            df: DataFrame containing at least ``"high"``, ``"low"``,
                ``"close"``, and ``"volume"`` columns.

        Returns:
            Series of CMF values aligned with ``df`` index, bounded in [-1, 1].

        """
        high = df["high"]
        low = df["low"]
        close = df["close"]
        volume = df["volume"]

        high_minus_low = high - low
        money_flow_multiplier = ((close - low) - (high - close)) / high_minus_low.replace(0, np.nan)
        money_flow_volume = money_flow_multiplier * volume

        cmf: pd.Series = (
            money_flow_volume.rolling(window=self.period).sum()
            / volume.rolling(window=self.period).sum()
        )
        return cmf

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate buy/sell signals from CMF zero-line crossovers.

        Args:
            data: Mapping of symbol to a DataFrame containing at least
                ``"high"``, ``"low"``, ``"close"``, and ``"volume"`` columns
                indexed by timestamp.

        Returns:
            List of :class:`Signal` objects for symbols whose CMF crosses the
            zero line between the last two bars.

        """
        signals: list[Signal] = []

        for symbol, df in data.items():
            if len(df) < self.period + 1:
                continue

            close = df["close"]
            current_price = close.iloc[-1]
            # The signal is emitted at the last close, so a close that is not a
            # number is rejected before anything is derived from it.
            if pd.isna(current_price) or current_price == 0:
                continue

            cmf = self._calculate_cmf(df)
            current_cmf = cmf.iloc[-1]
            prev_cmf = cmf.iloc[-2]
            timestamp = df.index[-1]

            if pd.isna(current_cmf) or pd.isna(prev_cmf):
                continue

            # CMF crosses above zero - buying pressure takes over
            if prev_cmf <= 0 and current_cmf > 0:
                strength = min(1.0, abs(current_cmf) + 0.5)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "cmf": current_cmf,
                            "period": self.period,
                            "signal_type": "cmf_cross_above_zero",
                        },
                    )
                )
            # CMF crosses below zero - selling pressure takes over
            elif prev_cmf >= 0 and current_cmf < 0:
                strength = min(1.0, abs(current_cmf) + 0.5)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "cmf": current_cmf,
                            "period": self.period,
                            "signal_type": "cmf_cross_below_zero",
                        },
                    )
                )

        return signals


class ForceIndexStrategy(Strategy):
    """Force Index Strategy.

    The Force Index (FI) combines price change and volume to measure buying
    and selling pressure:

    - Force Index = (Close - Close_prev) * Volume
    - Often smoothed with an EMA over ``period`` days.

    Trading signals (common approach):
    - Buy when the smoothed Force Index crosses above zero (bullish pressure).
    - Sell when the smoothed Force Index crosses below zero (bearish pressure).
    """

    def __init__(self, period: int = 13, name: str = "Force_Index"):
        """Initialize the Force Index strategy.

        Args:
            period: Lookback window for EMA smoothing of Force Index.
                Defaults to 13.
            name: Strategy name. Defaults to "Force_Index".

        Raises:
            ValueError: If ``period`` is non-positive.
        """
        super().__init__(
            name,
            {
                "period": period,
            },
        )
        self.period = period
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        Raises:
            ValueError: If ``period`` is non-positive.
        """
        if self.period <= 0:
            raise ValueError("period must be positive")

    def _calculate_force_index(self, df: pd.DataFrame) -> pd.Series:
        """Calculate the smoothed Force Index series.

        Args:
            df: DataFrame containing at least ``"close"`` and ``"volume"``
                columns.

        Returns:
            Series of smoothed Force Index values aligned with ``df`` index.
        """
        close = df["close"]
        volume = df["volume"]
        force_index = (close - close.shift(1)) * volume
        # Use EMA smoothing (span = period)
        smoothed_force_index = force_index.ewm(span=self.period, adjust=False).mean()
        return smoothed_force_index

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate buy/sell signals from Force Index zero-line crossovers.

        Args:
            data: Mapping of symbol to a DataFrame containing at least
                ``"close"`` and ``"volume"`` columns indexed by timestamp.

        Returns:
            List of :class:`Signal` objects for symbols whose smoothed Force
            Index crosses the zero line between the last two bars.
        """
        signals: list[Signal] = []

        for symbol, df in data.items():
            if len(df) < self.period + 2:
                continue

            close = df["close"]
            current_price = close.iloc[-1]
            if pd.isna(current_price) or current_price == 0:
                continue

            force_index = self._calculate_force_index(df)
            current_fi = force_index.iloc[-1]
            prev_fi = force_index.iloc[-2]
            timestamp = df.index[-1]

            if pd.isna(current_fi) or pd.isna(prev_fi):
                continue

            # Cross above zero - bullish pressure
            if prev_fi <= 0 and current_fi > 0:
                strength = min(1.0, abs(float(current_fi)) / (abs(float(current_fi)) + 1.0))
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "force_index": float(current_fi),
                            "period": self.period,
                            "signal_type": "force_index_cross_above_zero",
                        },
                    )
                )
            # Cross below zero - bearish pressure
            elif prev_fi >= 0 and current_fi < 0:
                strength = min(1.0, abs(float(current_fi)) / (abs(float(current_fi)) + 1.0))
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "force_index": float(current_fi),
                            "period": self.period,
                            "signal_type": "force_index_cross_below_zero",
                        },
                    )
                )

        return signals


class MoneyFlowIndexStrategy(Strategy):
    """Money Flow Index (MFI) Strategy.

    The Money Flow Index is a volume-weighted momentum oscillator that
    combines typical price, money flow, and volume over a lookback period:

    - Typical Price = (high + low + close) / 3
    - Money Flow Multiplier = ((close - low) - (high - close)) / (high - low)
    - Money Flow Volume = Typical Price * Money Flow Multiplier * volume
    - Positive Money Flow = sum of Money Flow Volume on bars where close
      rose vs. the prior close
    - Negative Money Flow = sum of Money Flow Volume on bars where close
      fell vs. the prior close
    - MFI = 100 - (100 / (1 + Positive Money Flow / Negative Money Flow))

    MFI oscillates between 0 and 100. Values above 50 indicate buying
    pressure; values below 50 indicate selling pressure.

    Trading signals:
    - Buy when MFI crosses above 50 (selling pressure turns to buying).
    - Sell when MFI crosses below 50 (buying pressure turns to selling).
    """

    def __init__(self, period: int = 14, name: str = "Money_Flow_Index"):
        """Initialize the Money Flow Index strategy.

        Args:
            period: Lookback window for the MFI calculation. Defaults to 14.
            name: Strategy name. Defaults to "Money_Flow_Index".

        Raises:
            ValueError: If ``period`` is non-positive.
        """
        super().__init__(
            name,
            {
                "period": period,
            },
        )
        self.period = period
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        Raises:
            ValueError: If ``period`` is non-positive.
        """
        if self.period <= 0:
            raise ValueError("period must be positive")

    def _calculate_mfi(self, df: pd.DataFrame) -> pd.Series:
        """Calculate the Money Flow Index series.

        Args:
            df: DataFrame containing at least ``"high"``, ``"low"``,
                ``"close"``, and ``"volume"`` columns.

        Returns:
            Series of MFI values aligned with ``df`` index, bounded in [0, 100].
        """
        high = df["high"]
        low = df["low"]
        close = df["close"]
        volume = df["volume"]

        typical_price = (high + low + close) / 3.0
        high_minus_low = high - low
        money_flow_multiplier = ((close - low) - (high - close)) / high_minus_low.replace(0, np.nan)
        money_flow_volume = typical_price * money_flow_multiplier * volume

        prior_close = close.shift(1)
        positive_money_flow = (
            money_flow_volume.where(close > prior_close, 0.0).rolling(window=self.period).sum()
        )
        negative_money_flow = (
            money_flow_volume.where(close < prior_close, 0.0).rolling(window=self.period).sum()
        )

        money_flow_ratio = positive_money_flow / negative_money_flow
        mfi: pd.Series = 100.0 - (100.0 / (1.0 + money_flow_ratio))
        return mfi

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate buy/sell signals from MFI 50-line crossovers.

        Args:
            data: Mapping of symbol to a DataFrame containing at least
                ``"high"``, ``"low"``, ``"close"``, and ``"volume"`` columns
                indexed by timestamp.

        Returns:
            List of :class:`Signal` objects for symbols whose MFI crosses the
            50 line between the last two bars.
        """
        signals: list[Signal] = []

        for symbol, df in data.items():
            if len(df) < self.period + 1:
                continue

            close = df["close"]
            current_price = close.iloc[-1]
            # The signal is emitted at the last close, so a close that is not a
            # number is rejected before anything is derived from it.
            if pd.isna(current_price) or current_price == 0:
                continue

            mfi = self._calculate_mfi(df)
            current_mfi = mfi.iloc[-1]
            prev_mfi = mfi.iloc[-2]
            timestamp = df.index[-1]

            if pd.isna(current_mfi) or pd.isna(prev_mfi):
                continue

            # MFI crosses above 50 - buying pressure takes over
            if prev_mfi <= 50 and current_mfi > 50:
                strength = min(1.0, abs(float(current_mfi) - 50.0) / 50.0)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "mfi": float(current_mfi),
                            "period": self.period,
                            "signal_type": "mfi_cross_above_50",
                        },
                    )
                )
            # MFI crosses below 50 - selling pressure takes over
            elif prev_mfi >= 50 and current_mfi < 50:
                strength = min(1.0, abs(float(current_mfi) - 50.0) / 50.0)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "mfi": float(current_mfi),
                            "period": self.period,
                            "signal_type": "mfi_cross_below_50",
                        },
                    )
                )

        return signals


class ElderRayStrategy(Strategy):
    """Elder Ray Index Strategy.

    Elder Ray Index (Bull/Bear Power) measures buying and selling pressure:

    - EMA = EMA(close, period)
    - Bull Power = high - EMA
    - Bear Power = low - EMA

    Trading signals:
    - Buy when Bull Power crosses above zero (bulls take control).
    - Sell when Bear Power crosses below zero (bears take control).
    """

    def __init__(self, period: int = 13, name: str = "Elder_Ray"):
        super().__init__(name, {"period": period})
        self.period = period
        self.validate_parameters()

    def validate_parameters(self) -> None:
        if self.period <= 0:
            raise ValueError("period must be positive")

    def _calculate(self, df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
        close = df["close"]
        high = df["high"]
        low = df["low"]
        ema = close.ewm(span=self.period, adjust=False).mean()
        bull_power = high - ema
        bear_power = low - ema
        return bull_power, bear_power

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals: list[Signal] = []
        for symbol, df in data.items():
            if len(df) < self.period + 2:
                continue
            close = df["close"]
            current_price = close.iloc[-1]
            if pd.isna(current_price) or current_price == 0:
                continue
            bull_power, bear_power = self._calculate(df)
            curr_bull = bull_power.iloc[-1]
            prev_bull = bull_power.iloc[-2]
            curr_bear = bear_power.iloc[-1]
            prev_bear = bear_power.iloc[-2]
            timestamp = df.index[-1]
            if pd.isna(curr_bull) or pd.isna(prev_bull) or pd.isna(curr_bear) or pd.isna(prev_bear):
                continue
            if prev_bull <= 0 and curr_bull > 0:
                strength = min(1.0, abs(float(curr_bull)) / (abs(float(curr_bull)) + 1.0))
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "bull_power": float(curr_bull),
                            "period": self.period,
                            "signal_type": "elder_ray_bull_cross",
                        },
                    )
                )
            elif prev_bear >= 0 and curr_bear < 0:
                strength = min(1.0, abs(float(curr_bear)) / (abs(float(curr_bear)) + 1.0))
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "bear_power": float(curr_bear),
                            "period": self.period,
                            "signal_type": "elder_ray_bear_cross",
                        },
                    )
                )
        return signals


class RateOfChangeStrategy(Strategy):
    """Rate of Change (ROC) Strategy.

    ROC measures the percentage change in price over a period:

    - ROC = (close - close[n]) / close[n] * 100

    Trading signals:
    - Buy when ROC crosses above zero (momentum turns positive).
    - Sell when ROC crosses below zero (momentum turns negative).
    """

    def __init__(self, period: int = 12, name: str = "Rate_Of_Change"):
        super().__init__(name, {"period": period})
        self.period = period
        self.validate_parameters()

    def validate_parameters(self) -> None:
        if self.period <= 0:
            raise ValueError("period must be positive")

    def _calculate(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        return (close - close.shift(self.period)) / close.shift(self.period) * 100.0

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals: list[Signal] = []
        for symbol, df in data.items():
            if len(df) < self.period + 2:
                continue
            close = df["close"]
            current_price = close.iloc[-1]
            if pd.isna(current_price) or current_price == 0:
                continue
            roc = self._calculate(df)
            curr_roc = roc.iloc[-1]
            prev_roc = roc.iloc[-2]
            timestamp = df.index[-1]
            if pd.isna(curr_roc) or pd.isna(prev_roc):
                continue
            if prev_roc <= 0 and curr_roc > 0:
                strength = min(1.0, abs(float(curr_roc)) / (abs(float(curr_roc)) + 100.0))
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "roc": float(curr_roc),
                            "period": self.period,
                            "signal_type": "roc_cross_above_zero",
                        },
                    )
                )
            elif prev_roc >= 0 and curr_roc < 0:
                strength = min(1.0, abs(float(curr_roc)) / (abs(float(curr_roc)) + 100.0))
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "roc": float(curr_roc),
                            "period": self.period,
                            "signal_type": "roc_cross_below_zero",
                        },
                    )
                )
        return signals


class VolumeRateOfChangeStrategy(Strategy):
    """Volume Rate of Change (VROC) Strategy.

    The Volume Rate of Change measures the percent change in volume over a
    lookback period, so it flags unusual volume surges or drying up without
    reference to price:

    - VROC = (volume - volume[n]) / volume[n] * 100, where n = ``period``

    VROC oscillates around zero. A positive value means volume is expanding
    relative to ``period`` bars ago; a negative value means volume is
    contracting.

    Trading signals:
    - Buy when VROC crosses above zero (volume expansion begins).
    - Sell when VROC crosses below zero (volume contraction begins).
    """

    def __init__(self, period: int = 14, name: str = "Volume_Rate_Of_Change"):
        """Initialize the Volume Rate of Change strategy.

        Args:
            period: Lookback window for the VROC calculation. Defaults to 14.
            name: Strategy name. Defaults to "Volume_Rate_Of_Change".

        Raises:
            ValueError: If ``period`` is non-positive.
        """
        super().__init__(
            name,
            {
                "period": period,
            },
        )
        self.period = period
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        Raises:
            ValueError: If ``period`` is non-positive.
        """
        if self.period <= 0:
            raise ValueError("period must be positive")

    def _calculate_vroc(self, df: pd.DataFrame) -> pd.Series:
        """Calculate the Volume Rate of Change series.

        Args:
            df: DataFrame containing at least a ``"volume"`` column.

        Returns:
            Series of VROC values aligned with ``df`` index, expressed as a
            percentage.
        """
        volume = df["volume"]
        prior_volume = volume.shift(self.period)
        vroc: pd.Series = (volume - prior_volume) / prior_volume.replace(0, np.nan) * 100.0
        return vroc

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate buy/sell signals from VROC zero-line crossovers.

        Args:
            data: Mapping of symbol to a DataFrame containing at least a
                ``"volume"`` and ``"close"`` column indexed by timestamp.

        Returns:
            List of :class:`Signal` objects for symbols whose VROC crosses the
            zero line between the last two bars.
        """
        signals: list[Signal] = []

        for symbol, df in data.items():
            if len(df) < self.period + 2:
                continue

            close = df["close"]
            current_price = close.iloc[-1]
            # The signal is emitted at the last close, so a close that is not a
            # number is rejected before anything is derived from it.
            if pd.isna(current_price) or current_price == 0:
                continue

            vroc = self._calculate_vroc(df)
            current_vroc = vroc.iloc[-1]
            prev_vroc = vroc.iloc[-2]
            timestamp = df.index[-1]

            if pd.isna(current_vroc) or pd.isna(prev_vroc):
                continue

            # VROC crosses above zero - volume expansion begins
            if prev_vroc <= 0 and current_vroc > 0:
                strength = min(1.0, abs(float(current_vroc)) / (abs(float(current_vroc)) + 100.0))
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "vroc": float(current_vroc),
                            "period": self.period,
                            "signal_type": "vroc_cross_above_zero",
                        },
                    )
                )
            # VROC crosses below zero - volume contraction begins
            elif prev_vroc >= 0 and current_vroc < 0:
                strength = min(1.0, abs(float(current_vroc)) / (abs(float(current_vroc)) + 100.0))
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "vroc": float(current_vroc),
                            "period": self.period,
                            "signal_type": "vroc_cross_below_zero",
                        },
                    )
                )

        return signals


class ChandeMomentumOscillatorStrategy(Strategy):
    """Chande Momentum Oscillator (CMO) Strategy.

    The Chande Momentum Oscillator measures momentum as the ratio of net
    upward price movement to total price movement over a lookback period:

    - CMO = (sum_up - sum_down) / (sum_up + sum_down) * 100

    where ``sum_up`` is the sum of positive close-to-close changes and
    ``sum_down`` is the sum of the magnitudes of negative changes over
    ``period`` bars. CMO oscillates between +100 (pure upside) and -100
    (pure downside), crossing zero when momentum changes direction.

    Trading signals:
    - Buy when CMO crosses above zero (momentum turns positive).
    - Sell when CMO crosses below zero (momentum turns negative).
    """

    def __init__(self, period: int = 14, name: str = "Chande_Momentum_Oscillator"):
        """Initialize the Chande Momentum Oscillator strategy.

        Args:
            period: Lookback window for the CMO calculation. Defaults to 14.
            name: Strategy name. Defaults to "Chande_Momentum_Oscillator".

        Raises:
            ValueError: If ``period`` is non-positive.
        """
        super().__init__(
            name,
            {
                "period": period,
            },
        )
        self.period = period
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        Raises:
            ValueError: If ``period`` is non-positive.
        """
        if self.period <= 0:
            raise ValueError("period must be positive")

    def _calculate_cmo(self, df: pd.DataFrame) -> pd.Series:
        """Calculate the Chande Momentum Oscillator series.

        Args:
            df: DataFrame containing at least a ``"close"`` column.

        Returns:
            Series of CMO values aligned with ``df`` index, expressed as a
            percentage between +100 and -100.
        """
        close = df["close"]
        delta = close.diff()
        up = delta.clip(lower=0.0)
        down = (-delta).clip(lower=0.0)
        sum_up = up.rolling(self.period).sum()
        sum_down = down.rolling(self.period).sum()
        denominator = sum_up + sum_down
        cmo: pd.Series = (sum_up - sum_down) / denominator.replace(0, np.nan) * 100.0
        return cmo

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate buy/sell signals from CMO zero-line crossovers.

        Args:
            data: Mapping of symbol to a DataFrame containing at least a
                ``"close"`` column indexed by timestamp.

        Returns:
            List of :class:`Signal` objects for symbols whose CMO crosses the
            zero line between the last two bars.
        """
        signals: list[Signal] = []

        for symbol, df in data.items():
            if len(df) < self.period + 2:
                continue

            close = df["close"]
            current_price = close.iloc[-1]
            if pd.isna(current_price) or current_price == 0:
                continue

            cmo = self._calculate_cmo(df)
            current_cmo = cmo.iloc[-1]
            prev_cmo = cmo.iloc[-2]
            timestamp = df.index[-1]

            if pd.isna(current_cmo) or pd.isna(prev_cmo):
                continue

            # CMO crosses above zero - momentum turns positive
            if prev_cmo <= 0 and current_cmo > 0:
                strength = min(1.0, abs(float(current_cmo)) / (abs(float(current_cmo)) + 100.0))
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "cmo": float(current_cmo),
                            "period": self.period,
                            "signal_type": "cmo_cross_above_zero",
                        },
                    )
                )
            # CMO crosses below zero - momentum turns negative
            elif prev_cmo >= 0 and current_cmo < 0:
                strength = min(1.0, abs(float(current_cmo)) / (abs(float(current_cmo)) + 100.0))
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "cmo": float(current_cmo),
                            "period": self.period,
                            "signal_type": "cmo_cross_below_zero",
                        },
                    )
                )

        return signals


class VolumeOscillatorStrategy(Strategy):
    """Volume Oscillator Strategy.

    The Volume Oscillator is the difference between a fast and a slow
    exponential moving average of volume, expressed as a percentage of the
    slow volume EMA:

    - VOL = (fast_vol_ema - slow_vol_ema) / slow_vol_ema * 100

    where ``fast_vol_ema`` and ``slow_vol_ema`` are EMAs of the ``volume``
    column over ``fast_period`` and ``slow_period`` bars respectively. It
    oscillates around zero: a positive value means recent volume is expanding
    relative to the longer-term volume trend, a negative value means volume is
    contracting.

    Trading signals:
    - Buy when VOL crosses above zero (volume expansion accelerating).
    - Sell when VOL crosses below zero (volume contraction accelerating).
    """

    def __init__(
        self,
        fast_period: int = 5,
        slow_period: int = 13,
        name: str = "Volume_Oscillator",
    ):
        """Initialize the Volume Oscillator strategy.

        Args:
            fast_period: Lookback window for the fast volume EMA.
            slow_period: Lookback window for the slow volume EMA; must
                exceed ``fast_period``.
            name: Human-readable name of the strategy.

        Raises:
            ValueError: If any parameter is invalid.

        """
        super().__init__(
            name,
            {
                "fast_period": fast_period,
                "slow_period": slow_period,
            },
        )
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        Raises:
            ValueError: If ``fast_period`` or ``slow_period`` is non-positive,
                or if ``fast_period`` is not less than ``slow_period``.

        """
        if self.fast_period <= 0:
            raise ValueError("fast_period must be positive")
        if self.slow_period <= 0:
            raise ValueError("slow_period must be positive")
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be less than slow_period")

    def _calculate_vol(self, df: pd.DataFrame) -> pd.Series:
        """Calculate the Volume Oscillator series.

        Args:
            df: DataFrame containing at least a ``"volume"`` column.

        Returns:
            Series of VOL values aligned with ``df`` index, expressed as a
            percentage.

        """
        volume = df["volume"]
        fast_ema = volume.ewm(span=self.fast_period, adjust=False).mean()
        slow_ema = volume.ewm(span=self.slow_period, adjust=False).mean()
        vol: pd.Series = (fast_ema - slow_ema) / slow_ema.replace(0, np.nan) * 100.0
        return vol

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate buy/sell signals from Volume Oscillator zero-line crossovers.

        Args:
            data: Mapping of symbol to a DataFrame containing at least a
                ``"volume"`` and ``"close"`` column indexed by timestamp.

        Returns:
            List of :class:`Signal` objects for symbols whose Volume
            Oscillator crosses the zero line between the last two bars.

        """
        signals: list[Signal] = []

        for symbol, df in data.items():
            if len(df) < self.slow_period + 2:
                continue

            close = df["close"]
            current_price = close.iloc[-1]
            # The signal is emitted at the last close, so a close that is not a
            # number is rejected before anything is derived from it.
            if pd.isna(current_price) or current_price == 0:
                continue

            vol = self._calculate_vol(df)
            current_vol = vol.iloc[-1]
            prev_vol = vol.iloc[-2]
            timestamp = df.index[-1]

            if pd.isna(current_vol) or pd.isna(prev_vol):
                continue

            # VOL crosses above zero - volume expansion begins
            if prev_vol <= 0 and current_vol > 0:
                strength = min(1.0, abs(float(current_vol)) / (abs(float(current_vol)) + 100.0))
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "vol": float(current_vol),
                            "fast_period": self.fast_period,
                            "slow_period": self.slow_period,
                            "signal_type": "vol_cross_above_zero",
                        },
                    )
                )
            # VOL crosses below zero - volume contraction begins
            elif prev_vol >= 0 and current_vol < 0:
                strength = min(1.0, abs(float(current_vol)) / (abs(float(current_vol)) + 100.0))
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "vol": float(current_vol),
                            "fast_period": self.fast_period,
                            "slow_period": self.slow_period,
                            "signal_type": "vol_cross_below_zero",
                        },
                    )
                )

        return signals


class ChaikinOscillatorStrategy(Strategy):
    """Chaikin Oscillator Strategy.

    The Chaikin Oscillator is the difference between a fast and a slow
    exponential moving average of the Accumulation/Distribution Line (ADL):

    - CHO = EMA(ADL, fast_period) - EMA(ADL, slow_period)

    It measures the momentum of the ADL. Trading signals:
    - Buy when CHO crosses above zero (accumulation momentum).
    - Sell when CHO crosses below zero (distribution momentum).
    """

    def __init__(
        self,
        fast_period: int = 3,
        slow_period: int = 10,
        name: str = "Chaikin_Oscillator",
    ):
        super().__init__(
            name,
            {"fast_period": fast_period, "slow_period": slow_period},
        )
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.validate_parameters()

    def validate_parameters(self) -> None:
        if self.fast_period <= 0:
            raise ValueError("fast_period must be positive")
        if self.slow_period <= 0:
            raise ValueError("slow_period must be positive")
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be less than slow_period")

    def _calculate_adl(self, df: pd.DataFrame) -> pd.Series:
        high = df["high"]
        low = df["low"]
        close = df["close"]
        volume = df["volume"]
        hl_range = (high - low).replace(0, np.nan)
        mfv = ((close - low) - (high - close)) / hl_range * volume
        mfv = mfv.fillna(0.0)
        adl: pd.Series = mfv.cumsum()
        return adl

    def _calculate_cho(self, df: pd.DataFrame) -> pd.Series:
        adl = self._calculate_adl(df)
        fast_ema = adl.ewm(span=self.fast_period, adjust=False).mean()
        slow_ema = adl.ewm(span=self.slow_period, adjust=False).mean()
        return fast_ema - slow_ema

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals: list[Signal] = []
        for symbol, df in data.items():
            if len(df) < self.slow_period + 2:
                continue
            close = df["close"]
            current_price = close.iloc[-1]
            if pd.isna(current_price) or current_price == 0:
                continue
            cho = self._calculate_cho(df)
            current_cho = cho.iloc[-1]
            prev_cho = cho.iloc[-2]
            timestamp = df.index[-1]
            if pd.isna(current_cho) or pd.isna(prev_cho):
                continue
            if prev_cho <= 0 and current_cho > 0:
                strength = min(1.0, abs(float(current_cho)) / (abs(float(current_cho)) + 1.0))
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "cho": float(current_cho),
                            "fast_period": self.fast_period,
                            "slow_period": self.slow_period,
                            "signal_type": "cho_cross_above_zero",
                        },
                    )
                )
            elif prev_cho >= 0 and current_cho < 0:
                strength = min(1.0, abs(float(current_cho)) / (abs(float(current_cho)) + 1.0))
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "cho": float(current_cho),
                            "fast_period": self.fast_period,
                            "slow_period": self.slow_period,
                            "signal_type": "cho_cross_below_zero",
                        },
                    )
                )
        return signals



class AwesomeOscillatorStrategy(Strategy):
    def __init__(self, short_period=5, long_period=34, name="Awesome_Oscillator"):
        super().__init__(name, {"short_period": short_period, "long_period": long_period})
        self.short_period = short_period
        self.long_period = long_period
        self.validate_parameters()

    def validate_parameters(self):
        if self.short_period <= 0:
            raise ValueError("short_period must be positive")
        if self.long_period <= 0:
            raise ValueError("long_period must be positive")
        if self.short_period >= self.long_period:
            raise ValueError("short_period must be less than long_period")

    def _calculate_ao(self, df):
        median_price = (df["high"] + df["low"]) / 2.0
        short_sma = median_price.rolling(window=self.short_period).mean()
        long_sma = median_price.rolling(window=self.long_period).mean()
        return short_sma - long_sma

    def generate_signals(self, data):
        signals = []
        for symbol, df in data.items():
            if len(df) < self.long_period + 2:
                continue
            close = df["close"]
            current_price = close.iloc[-1]
            if pd.isna(current_price) or current_price == 0:
                continue
            ao = self._calculate_ao(df)
            current_ao = ao.iloc[-1]
            prev_ao = ao.iloc[-2]
            timestamp = df.index[-1]
            if pd.isna(current_ao) or pd.isna(prev_ao):
                continue
            if prev_ao <= 0 and current_ao > 0:
                strength = min(1.0, abs(float(current_ao)) / (abs(float(current_ao)) + 1.0))
                signals.append(Signal(symbol=symbol, action="buy", strength=strength, price=current_price, timestamp=timestamp, metadata={"ao": float(current_ao), "short_period": self.short_period, "long_period": self.long_period, "signal_type": "ao_cross_above_zero"}))
            elif prev_ao >= 0 and current_ao < 0:
                strength = min(1.0, abs(float(current_ao)) / (abs(float(current_ao)) + 1.0))
                signals.append(Signal(symbol=symbol, action="sell", strength=strength, price=current_price, timestamp=timestamp, metadata={"ao": float(current_ao), "short_period": self.short_period, "long_period": self.long_period, "signal_type": "ao_cross_below_zero"}))
        return signals

class VortexStrategy(Strategy):
    """Vortex Strategy.

    The Vortex Indicator compares upward and downward movement over a lookback
    period, normalized by the True Range so the two lines are directly
    comparable. It consists of two lines:

    - ``VIP+`` (Vortex Up): sum of |current high - previous low| over the
      period, divided by the sum of True Range over the period.
    - ``VIP-`` (Vortex Down): sum of |current low - previous high| over the
      period, divided by the sum of True Range over the period.

    Both lines are bounded in ``[0, 1]`` and their sum is at most 1 when the
    ranges are disjoint. Trading signals:

    - Buy when VIP+ crosses above VIP- (upward trend emerging).
    - Sell when VIP- crosses above VIP+ (downward trend emerging).
    """

    def __init__(
        self,
        period: int = 14,
        name: str = "Vortex",
    ):
        """Initialize the Vortex strategy.

        Args:
            period: Lookback window for the Vortex calculation.
            name: Human-readable name of the strategy.

        Raises:
            ValueError: If ``period`` is non-positive.

        """
        super().__init__(name, {"period": period})
        self.period = period
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters.

        Raises:
            ValueError: If ``period`` is non-positive.

        """
        if self.period <= 0:
            raise ValueError("period must be positive")

    def _calculate_vortex(self, df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
        """Calculate the Vortex Up (VIP+) and Vortex Down (VIP-) lines.

        Args:
            df: DataFrame containing at least ``"high"``, ``"low"``, and
                ``"close"`` columns.

        Returns:
            Tuple of ``(vip_plus, vip_minus)`` series aligned with ``df``
            index. Values are NaN until ``period`` bars of history are
            available.

        """
        high = df["high"]
        low = df["low"]
        close = df["close"]

        prev_high = high.shift(1)
        prev_low = low.shift(1)
        prev_close = close.shift(1)

        # Positive and negative vortex movement
        vm_plus = (high - prev_low).abs()
        vm_minus = (low - prev_high).abs()

        # True Range = max(high - low, |high - prev_close|, |low - prev_close|)
        true_range = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)

        sum_vm_plus = vm_plus.rolling(window=self.period).sum()
        sum_vm_minus = vm_minus.rolling(window=self.period).sum()
        sum_tr = true_range.rolling(window=self.period).sum()

        with np.errstate(divide="ignore", invalid="ignore"):
            vip_plus = sum_vm_plus / sum_tr.replace(0, np.nan)
            vip_minus = sum_vm_minus / sum_tr.replace(0, np.nan)

        return vip_plus, vip_minus

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """Generate buy/sell signals from Vortex line crossovers.

        Args:
            data: Mapping of symbol to a DataFrame containing at least
                ``"high"``, ``"low"``, and ``"close"`` columns indexed by
                timestamp.

        Returns:
            List of :class:`Signal` objects for symbols whose Vortex Up and
            Down lines cross between the last two bars.

        """
        signals: list[Signal] = []

        for symbol, df in data.items():
            if len(df) < self.period + 2:
                continue

            vip_plus, vip_minus = self._calculate_vortex(df)

            current_plus = vip_plus.iloc[-1]
            current_minus = vip_minus.iloc[-1]
            prev_plus = vip_plus.iloc[-2]
            prev_minus = vip_minus.iloc[-2]
            current_price = df["close"].iloc[-1]
            timestamp = df.index[-1]

            if (
                pd.isna(current_plus)
                or pd.isna(current_minus)
                or pd.isna(prev_plus)
                or pd.isna(prev_minus)
                or pd.isna(current_price)
                or current_price == 0
            ):
                continue

            # Vortex Up crosses above Vortex Down - bullish signal
            if prev_plus <= prev_minus and current_plus > current_minus:
                strength = min(1.0, (current_plus - current_minus) + 0.5)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "vip_plus": float(current_plus),
                            "vip_minus": float(current_minus),
                            "period": self.period,
                            "signal_type": "vortex_up_cross_above_down",
                        },
                    )
                )
            # Vortex Down crosses above Vortex Up - bearish signal
            elif prev_minus <= prev_plus and current_minus > current_plus:
                strength = min(1.0, (current_minus - current_plus) + 0.5)
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "vip_plus": float(current_plus),
                            "vip_minus": float(current_minus),
                            "period": self.period,
                            "signal_type": "vortex_down_cross_above_up",
                        },
                    )
                )

        return signals

class TrixStrategy(Strategy):
    """TRIX (Triple Exponential Average) Strategy.

    TRIX measures the rate of change of a triple exponentially smoothed
    moving average of the close price:

    - EMA1 = EMA(close, period)
    - EMA2 = EMA(EMA1, period)
    - EMA3 = EMA(EMA2, period)
    - TRIX = (EMA3 - EMA3_prev) / EMA3_prev * 100

    Trading signals:
    - Buy when TRIX crosses above zero (momentum turning positive).
    - Sell when TRIX crosses below zero (momentum turning negative).
    """

    def __init__(self, period: int = 14, name: str = "TRIX"):
        super().__init__(name, {"period": period})
        self.period = period
        self.validate_parameters()

    def validate_parameters(self) -> None:
        if self.period <= 0:
            raise ValueError("period must be positive")

    def _calculate_trix(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        ema1 = close.ewm(span=self.period, adjust=False).mean()
        ema2 = ema1.ewm(span=self.period, adjust=False).mean()
        ema3 = ema2.ewm(span=self.period, adjust=False).mean()
        trix: pd.Series = ema3.pct_change() * 100.0
        return trix

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals: list[Signal] = []
        for symbol, df in data.items():
            if len(df) < self.period * 3 + 2:
                continue
            close = df["close"]
            current_price = close.iloc[-1]
            if pd.isna(current_price) or current_price == 0:
                continue
            trix = self._calculate_trix(df)
            current_trix = trix.iloc[-1]
            prev_trix = trix.iloc[-2]
            timestamp = df.index[-1]
            if pd.isna(current_trix) or pd.isna(prev_trix):
                continue
            if prev_trix <= 0 and current_trix > 0:
                strength = min(1.0, abs(float(current_trix)) / (abs(float(current_trix)) + 1.0))
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "trix": float(current_trix),
                            "period": self.period,
                            "signal_type": "trix_cross_above_zero",
                        },
                    )
                )
            elif prev_trix >= 0 and current_trix < 0:
                strength = min(1.0, abs(float(current_trix)) / (abs(float(current_trix)) + 1.0))
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=strength,
                        price=current_price,
                        timestamp=timestamp,
                        metadata={
                            "trix": float(current_trix),
                            "period": self.period,
                            "signal_type": "trix_cross_below_zero",
                        },
                    )
                )
        return signals
