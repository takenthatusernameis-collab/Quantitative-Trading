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
        super().__init__(name, {
            "fast_period": fast_period,
            "slow_period": slow_period,
        })
        self.fast_period = fast_period
        self.slow_period = slow_period

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        for symbol, df in data.items():
            if len(df) < self.slow_period:
                continue

            close = df['close']
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
                signals.append(Signal(
                    symbol=symbol,
                    action='buy',
                    strength=min(1.0, (fast_current - slow_current) / slow_current * 10),
                    price=current_price,
                    timestamp=timestamp,
                    metadata={
                        'fast_ma': fast_current,
                        'slow_ma': slow_current,
                        'crossover_type': 'golden_cross',
                    }
                ))
            elif fast_prev >= slow_prev and fast_current < slow_current:
                # Death cross - sell signal
                signals.append(Signal(
                    symbol=symbol,
                    action='sell',
                    strength=min(1.0, (slow_current - fast_current) / slow_current * 10),
                    price=current_price,
                    timestamp=timestamp,
                    metadata={
                        'fast_ma': fast_current,
                        'slow_ma': slow_current,
                        'crossover_type': 'death_cross',
                    }
                ))

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
        super().__init__(name, {
            "period": period,
            "oversold": oversold,
            "overbought": overbought,
        })
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def _calculate_rsi(self, close: pd.Series) -> pd.Series:
        """Calculate RSI indicator."""
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        for symbol, df in data.items():
            if len(df) < self.period + 1:
                continue

            close = df['close']
            rsi = self._calculate_rsi(close)

            current_rsi = rsi.iloc[-1]
            prev_rsi = rsi.iloc[-2]
            current_price = close.iloc[-1]
            timestamp = df.index[-1]

            # Oversold - buy signal
            if prev_rsi <= self.oversold and current_rsi > self.oversold:
                signals.append(Signal(
                    symbol=symbol,
                    action='buy',
                    strength=min(1.0, (self.oversold - prev_rsi) / self.oversold + 0.5),
                    price=current_price,
                    timestamp=timestamp,
                    metadata={
                        'rsi': current_rsi,
                        'signal_type': 'oversold_bounce',
                    }
                ))
            # Overbought - sell signal
            elif prev_rsi >= self.overbought and current_rsi < self.overbought:
                signals.append(Signal(
                    symbol=symbol,
                    action='sell',
                    strength=min(1.0, (prev_rsi - self.overbought) / (100 - self.overbought) + 0.5),
                    price=current_price,
                    timestamp=timestamp,
                    metadata={
                        'rsi': current_rsi,
                        'signal_type': 'overbought_rejection',
                    }
                ))

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
        super().__init__(name, {
            "period": period,
            "std_dev": std_dev,
        })
        self.period = period
        self.std_dev = std_dev

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        for symbol, df in data.items():
            if len(df) < self.period:
                continue

            close = df['close']
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
                signals.append(Signal(
                    symbol=symbol,
                    action='buy',
                    strength=strength,
                    price=current_price,
                    timestamp=timestamp,
                    metadata={
                        'upper_band': current_upper,
                        'lower_band': current_lower,
                        'sma': current_sma,
                        'signal_type': 'lower_band_touch',
                    }
                ))
            # Price at upper band - sell signal
            elif current_price >= current_upper * 0.995:  # Small buffer
                strength = min(1.0, (current_price - current_upper) / current_upper + 0.5)
                signals.append(Signal(
                    symbol=symbol,
                    action='sell',
                    strength=strength,
                    price=current_price,
                    timestamp=timestamp,
                    metadata={
                        'upper_band': current_upper,
                        'lower_band': current_lower,
                        'sma': current_sma,
                        'signal_type': 'upper_band_touch',
                    }
                ))

        return signals