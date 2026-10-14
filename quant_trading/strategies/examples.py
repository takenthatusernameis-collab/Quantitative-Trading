"""Example trading strategies."""

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
        if self.fast_period <= 0:
            raise ValueError("fast_period must be positive")
        if self.slow_period <= 0:
            raise ValueError("slow_period must be positive")
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be less than slow_period")

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        for symbol, df in data.items():
            if len(df) < self.slow_period:
                continue

            close = df["close"]
            fast_ma = close.rolling(window=self.fast_period).mean()
            slow_ma = close.rolling(window=self.slow_period).mean()

            # Current and previous values
            fast_current = fast_ma.iloc[-1]
            fast_prev = fast_ma.iloc[-2]
            slow_current = slow_ma.iloc[-1]
            slow_prev = slow_ma.iloc[-2]

            current_price = close.iloc[-1]
            timestamp = df.index[-1]

            # Crossover detection
            if fast_prev <= slow_prev and fast_current > slow_current:
                # Golden cross - buy signal
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="buy",
                        strength=min(1.0, (fast_current - slow_current) / slow_current * 10),
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
                signals.append(
                    Signal(
                        symbol=symbol,
                        action="sell",
                        strength=min(1.0, (slow_current - fast_current) / slow_current * 10),
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
        """Validate strategy parameters."""
        if self.period <= 0:
            raise ValueError("period must be positive")
        if not (0 < self.oversold < 100):
            raise ValueError("oversold must be between 0 and 100")
        if not (0 < self.overbought < 100):
            raise ValueError("overbought must be between 0 and 100")
        if self.oversold >= self.overbought:
            raise ValueError("oversold must be less than overbought")

    def _calculate_rsi(self, close: pd.Series) -> pd.Series:
        """Calculate RSI indicator."""
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.period).mean()
        rs = gain / loss
        rsi: pd.Series = 100 - (100 / (1 + rs))
        return rsi

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        for symbol, df in data.items():
            if len(df) < self.period + 1:
                continue

            close = df["close"]
            rsi = self._calculate_rsi(close)

            current_rsi = rsi.iloc[-1]
            prev_rsi = rsi.iloc[-2]
            current_price = close.iloc[-1]
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
        """Validate strategy parameters."""
        if self.period <= 0:
            raise ValueError("period must be positive")
        if self.std_dev <= 0:
            raise ValueError("std_dev must be positive")

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

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
        """Validate strategy parameters."""
        if self.period <= 0:
            raise ValueError("period must be positive")
        if self.multiplier <= 0:
            raise ValueError("multiplier must be positive")

    def _calculate_atr(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Average True Range (ATR)."""
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
        """Validate strategy parameters."""
        if self.fast_period <= 0:
            raise ValueError("fast_period must be positive")
        if self.slow_period <= 0:
            raise ValueError("slow_period must be positive")
        if self.signal_period <= 0:
            raise ValueError("signal_period must be positive")
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be less than slow_period")

    def _ema(self, close: pd.Series, period: int) -> pd.Series:
        """Calculate Exponential Moving Average."""
        return close.ewm(span=period, adjust=False).mean()

    def _calculate_macd(self, close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate MACD line, signal line, and histogram.

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

            # Bullish crossover: MACD line crosses above signal line
            if macd_prev <= signal_prev and macd_current > signal_current:
                strength = min(1.0, abs(macd_current - signal_current) / abs(signal_current) + 0.5)
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
                strength = min(1.0, abs(signal_current - macd_current) / abs(signal_current) + 0.5)
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
                    strength = min(1.0, abs(macd_current) / ref * 0.5 + 0.3) if ref > 0 else 0.5
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
                    strength = min(1.0, abs(macd_current) / ref * 0.5 + 0.3) if ref > 0 else 0.5
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
        """Validate strategy parameters."""
        if self.period <= 0:
            raise ValueError("period must be positive")
        if self.exit_period <= 0:
            raise ValueError("exit_period must be positive")

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
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
        super().__init__(
            name,
            {
                "period": period,
            },
        )
        self.period = period
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate strategy parameters."""
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

        def periods_since_high(x):
            # Get the index of the maximum value (most recent if tie)
            # When all values are equal, we want the most recent (highest index)
            max_val = x.max()
            # Find the most recent index with the maximum value
            max_idx = len(x) - 1
            for i in range(len(x) - 1, -1, -1):
                if x.iloc[i] == max_val:
                    max_idx = i
                    break
            return self.period - 1 - max_idx

        def periods_since_low(x):
            # Get the index of the minimum value (most recent if tie)
            # When all values are equal, we want the most recent (highest index)
            min_val = x.min()
            # Find the most recent index with the minimum value
            min_idx = len(x) - 1
            for i in range(len(x) - 1, -1, -1):
                if x.iloc[i] == min_val:
                    min_idx = i
                    break
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
