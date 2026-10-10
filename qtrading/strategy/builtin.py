import pandas as pd

from qtrading.strategy import (
    Position,
    Signal,
    SignalType,
    Strategy,
    StrategyContext,
    StrategyParams,
    StrategyRegistry,
)


@StrategyRegistry.register("sma_crossover")
class SMACrossoverStrategy(Strategy):
    def __init__(self, params: StrategyParams):
        super().__init__(params)
        self.fast_period = params.parameters.get("fast_period", 10)
        self.slow_period = params.parameters.get("slow_period", 30)
        self.position_size = params.parameters.get("position_size", 0.1)

    async def initialize(self, context: StrategyContext) -> None:
        pass

    async def on_bar(self, context: StrategyContext) -> list[Signal]:
        signals = []
        for symbol in self.params.symbols:
            df = context.get_ohlcv(symbol, max(self.fast_period, self.slow_period) + 10)
            if df is None or len(df) < self.slow_period:
                continue

            close = df["close"].astype(float)
            fast_sma = close.rolling(self.fast_period).mean()
            slow_sma = close.rolling(self.slow_period).mean()

            current_fast = fast_sma.iloc[-1]
            current_slow = slow_sma.iloc[-1]
            prev_fast = fast_sma.iloc[-2]
            prev_slow = slow_sma.iloc[-2]

            current_price = context.get_price(symbol)
            if current_price is None:
                continue

            position = context.positions.get(symbol)
            has_position = position is not None and position.quantity != 0

            if prev_fast <= prev_slow and current_fast > current_slow and not has_position:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    strength=1.0,
                    timestamp=context.current_time,
                    price=current_price,
                    metadata={
                        "strategy": "sma_crossover",
                        "fast": current_fast,
                        "slow": current_slow
                    }
                ))
            elif (
                prev_fast >= prev_slow
                and current_fast < current_slow
                and has_position
                and position.side == "long"
            ):
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.CLOSE_LONG,
                    strength=1.0,
                    timestamp=context.current_time,
                    price=current_price,
                    metadata={
                        "strategy": "sma_crossover",
                        "fast": current_fast,
                        "slow": current_slow
                    }
                ))

        self.signals.extend(signals)
        return signals

    async def on_tick(self, context: StrategyContext, ticker) -> list[Signal]:
        return []

    async def on_order_fill(self, context: StrategyContext, order) -> None:
        pass

    async def on_position_change(self, context: StrategyContext, position: Position) -> None:
        pass


@StrategyRegistry.register("bollinger_bands")
class BollingerBandsStrategy(Strategy):
    def __init__(self, params: StrategyParams):
        super().__init__(params)
        self.period = params.parameters.get("period", 20)
        self.std_dev = params.parameters.get("std_dev", 2.0)
        self.position_size = params.parameters.get("position_size", 0.1)

    async def initialize(self, context: StrategyContext) -> None:
        pass

    async def on_bar(self, context: StrategyContext) -> list[Signal]:
        signals = []
        for symbol in self.params.symbols:
            df = context.get_ohlcv(symbol, self.period + 10)
            if df is None or len(df) < self.period:
                continue

            close = df["close"].astype(float)
            sma = close.rolling(self.period).mean().iloc[-1]
            std = close.rolling(self.period).std().iloc[-1]
            current_price = context.get_price(symbol)
            if current_price is None:
                continue

            upper_band = sma + (self.std_dev * std)
            lower_band = sma - (self.std_dev * std)
            current_price_float = float(current_price)

            position = context.positions.get(symbol)
            has_long = position is not None and position.quantity > 0
            has_short = position is not None and position.quantity < 0

            if current_price_float < lower_band and not has_long:
                strength = min((lower_band - current_price_float) / lower_band, 2.0)
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    strength=strength,
                    timestamp=context.current_time,
                    price=current_price,
                    metadata={
                        "strategy": "bollinger_bands",
                        "price": current_price_float,
                        "upper": upper_band,
                        "lower": lower_band,
                        "sma": sma
                    }
                ))
            elif current_price_float > upper_band and not has_short:
                strength = min((current_price_float - upper_band) / upper_band, 2.0)
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    strength=strength,
                    timestamp=context.current_time,
                    price=current_price,
                    metadata={
                        "strategy": "bollinger_bands",
                        "price": current_price_float,
                        "upper": upper_band,
                        "lower": lower_band,
                        "sma": sma
                    }
                ))
            elif has_long and current_price_float > sma:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.CLOSE_LONG,
                    strength=1.0,
                    timestamp=context.current_time,
                    price=current_price,
                    metadata={
                        "strategy": "bollinger_bands",
                        "price": current_price_float,
                        "sma": sma
                    }
                ))
            elif has_short and current_price_float < sma:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.CLOSE_SHORT,
                    strength=1.0,
                    timestamp=context.current_time,
                    price=current_price,
                    metadata={
                        "strategy": "bollinger_bands",
                        "price": current_price_float,
                        "sma": sma
                    }
                ))

        self.signals.extend(signals)
        return signals

    async def on_tick(self, context: StrategyContext, ticker) -> list[Signal]:
        return []

    async def on_order_fill(self, context: StrategyContext, order) -> None:
        pass

    async def on_position_change(self, context: StrategyContext, position: Position) -> None:
        pass


@StrategyRegistry.register("macd")
class MACDStrategy(Strategy):
    def __init__(self, params: StrategyParams):
        super().__init__(params)
        self.fast_period = params.parameters.get("fast_period", 12)
        self.slow_period = params.parameters.get("slow_period", 26)
        self.signal_period = params.parameters.get("signal_period", 9)
        self.position_size = params.parameters.get("position_size", 0.1)

    def _calculate_macd(self, close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
        fast_ema = close.ewm(span=self.fast_period, adjust=False).mean()
        slow_ema = close.ewm(span=self.slow_period, adjust=False).mean()
        macd_line = fast_ema - slow_ema
        signal_line = macd_line.ewm(span=self.signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    async def initialize(self, context: StrategyContext) -> None:
        pass

    async def on_bar(self, context: StrategyContext) -> list[Signal]:
        signals = []
        for symbol in self.params.symbols:
            df = context.get_ohlcv(symbol, self.slow_period + self.signal_period + 10)
            if df is None or len(df) < self.slow_period + self.signal_period:
                continue

            close = df["close"].astype(float)
            macd_line, signal_line, histogram = self._calculate_macd(close)

            current_macd = macd_line.iloc[-1]
            current_signal = signal_line.iloc[-1]
            current_histogram = histogram.iloc[-1]
            prev_macd = macd_line.iloc[-2]
            prev_signal = signal_line.iloc[-2]

            current_price = context.get_price(symbol)
            if current_price is None:
                continue

            position = context.positions.get(symbol)
            has_long = position is not None and position.quantity > 0
            has_short = position is not None and position.quantity < 0

            if prev_macd <= prev_signal and current_macd > current_signal and not has_long:
                    strength = min(abs(current_histogram) / (abs(current_signal) + 1e-10), 2.0)
                    signals.append(Signal(
                        symbol=symbol,
                        signal_type=SignalType.BUY,
                        strength=strength,
                        timestamp=context.current_time,
                        price=current_price,
                        metadata={
                            "strategy": "macd",
                            "macd": current_macd,
                            "signal": current_signal,
                            "histogram": current_histogram
                        }
                    ))
            elif prev_macd >= prev_signal and current_macd < current_signal:
                if has_long:
                    signals.append(Signal(
                        symbol=symbol,
                        signal_type=SignalType.CLOSE_LONG,
                        strength=1.0,
                        timestamp=context.current_time,
                        price=current_price,
                        metadata={
                            "strategy": "macd",
                            "macd": current_macd,
                            "signal": current_signal,
                            "histogram": current_histogram
                        }
                    ))
                elif not has_short:
                    strength = min(abs(current_histogram) / (abs(current_signal) + 1e-10), 2.0)
                    signals.append(Signal(
                        symbol=symbol,
                        signal_type=SignalType.SELL,
                        strength=strength,
                        timestamp=context.current_time,
                        price=current_price,
                        metadata={
                            "strategy": "macd",
                            "macd": current_macd,
                            "signal": current_signal,
                            "histogram": current_histogram
                        }
                    ))

        self.signals.extend(signals)
        return signals

    async def on_tick(self, context: StrategyContext, ticker) -> list[Signal]:
        return []

    async def on_order_fill(self, context: StrategyContext, order) -> None:
        pass

    async def on_position_change(self, context: StrategyContext, position: Position) -> None:
        pass


@StrategyRegistry.register("momentum")
class MomentumStrategy(Strategy):
    def __init__(self, params: StrategyParams):
        super().__init__(params)
        self.lookback = params.parameters.get("lookback", 20)
        self.holding_period = params.parameters.get("holding_period", 10)
        self.position_size = params.parameters.get("position_size", 0.1)
        self._entry_bars: dict[str, int] = {}

    async def initialize(self, context: StrategyContext) -> None:
        pass

    async def on_bar(self, context: StrategyContext) -> list[Signal]:
        signals = []
        for symbol in self.params.symbols:
            df = context.get_ohlcv(symbol, self.lookback + 10)
            if df is None or len(df) < self.lookback:
                continue

            close = df["close"].astype(float)
            current_price = context.get_price(symbol)
            if current_price is None:
                continue

            current_price_float = float(current_price)
            price_lookback_ago = close.iloc[-self.lookback]
            momentum = (current_price_float - price_lookback_ago) / price_lookback_ago

            position = context.positions.get(symbol)
            has_long = position is not None and position.quantity > 0
            has_short = position is not None and position.quantity < 0

            if symbol not in self._entry_bars:
                self._entry_bars[symbol] = 0

            if momentum > 0.02 and not has_long and not has_short:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    strength=min(abs(momentum) * 10, 2.0),
                    timestamp=context.current_time,
                    price=current_price,
                    metadata={
                        "strategy": "momentum",
                        "momentum": momentum,
                        "lookback": self.lookback
                    }
                ))
                self._entry_bars[symbol] = 0
            elif momentum < -0.02 and not has_short and not has_long:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    strength=min(abs(momentum) * 10, 2.0),
                    timestamp=context.current_time,
                    price=current_price,
                    metadata={
                        "strategy": "momentum",
                        "momentum": momentum,
                        "lookback": self.lookback
                    }
                ))
                self._entry_bars[symbol] = 0
            elif has_long:
                self._entry_bars[symbol] += 1
                if self._entry_bars[symbol] >= self.holding_period or momentum < 0:
                    signals.append(Signal(
                        symbol=symbol,
                        signal_type=SignalType.CLOSE_LONG,
                        strength=1.0,
                        timestamp=context.current_time,
                        price=current_price,
                        metadata={
                            "strategy": "momentum",
                            "momentum": momentum,
                            "bars_held": self._entry_bars[symbol]
                        }
                    ))
                    self._entry_bars[symbol] = 0
            elif has_short:
                self._entry_bars[symbol] += 1
                if self._entry_bars[symbol] >= self.holding_period or momentum > 0:
                    signals.append(Signal(
                        symbol=symbol,
                        signal_type=SignalType.CLOSE_SHORT,
                        strength=1.0,
                        timestamp=context.current_time,
                        price=current_price,
                        metadata={
                            "strategy": "momentum",
                            "momentum": momentum,
                            "bars_held": self._entry_bars[symbol]
                        }
                    ))
                    self._entry_bars[symbol] = 0

        self.signals.extend(signals)
        return signals

    async def on_tick(self, context: StrategyContext, ticker) -> list[Signal]:
        return []

    async def on_order_fill(self, context: StrategyContext, order) -> None:
        pass

    async def on_position_change(self, context: StrategyContext, position: Position) -> None:
        pass


@StrategyRegistry.register("mean_reversion")
class MeanReversionStrategy(Strategy):
    def __init__(self, params: StrategyParams):
        super().__init__(params)
        self.lookback = params.parameters.get("lookback", 20)
        self.entry_zscore = params.parameters.get("entry_zscore", 2.0)
        self.exit_zscore = params.parameters.get("exit_zscore", 0.5)
        self.position_size = params.parameters.get("position_size", 0.1)

    async def initialize(self, context: StrategyContext) -> None:
        pass

    async def on_bar(self, context: StrategyContext) -> list[Signal]:
        signals = []
        for symbol in self.params.symbols:
            df = context.get_ohlcv(symbol, self.lookback + 10)
            if df is None or len(df) < self.lookback:
                continue

            close = df["close"].astype(float)
            mean = close.rolling(self.lookback).mean().iloc[-1]
            std = close.rolling(self.lookback).std().iloc[-1]
            current_price = float(context.get_price(symbol)) if context.get_price(symbol) else 0

            if std == 0:
                continue

            zscore = (current_price - mean) / std
            position = context.positions.get(symbol)
            has_long = position is not None and position.quantity > 0
            has_short = position is not None and position.quantity < 0

            if zscore < -self.entry_zscore and not has_long:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    strength=min(abs(zscore) / self.entry_zscore, 2.0),
                    timestamp=context.current_time,
                    price=context.get_price(symbol),
                    metadata={
                        "strategy": "mean_reversion",
                        "zscore": zscore,
                        "mean": mean,
                        "std": std
                    }
                ))
            elif zscore > self.entry_zscore and not has_short:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    strength=min(abs(zscore) / self.entry_zscore, 2.0),
                    timestamp=context.current_time,
                    price=context.get_price(symbol),
                    metadata={
                        "strategy": "mean_reversion",
                        "zscore": zscore,
                        "mean": mean,
                        "std": std
                    }
                ))
            elif has_long and zscore > -self.exit_zscore:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.CLOSE_LONG,
                    strength=1.0,
                    timestamp=context.current_time,
                    price=context.get_price(symbol),
                    metadata={
                        "strategy": "mean_reversion",
                        "zscore": zscore
                    }
                ))
            elif has_short and zscore < self.exit_zscore:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.CLOSE_SHORT,
                    strength=1.0,
                    timestamp=context.current_time,
                    price=context.get_price(symbol),
                    metadata={
                        "strategy": "mean_reversion",
                        "zscore": zscore
                    }
                ))

        self.signals.extend(signals)
        return signals

    async def on_tick(self, context: StrategyContext, ticker) -> list[Signal]:
        return []

    async def on_order_fill(self, context: StrategyContext, order) -> None:
        pass

    async def on_position_change(self, context: StrategyContext, position: Position) -> None:
        pass


@StrategyRegistry.register("rsi_strategy")
class RSIStrategy(Strategy):
    def __init__(self, params: StrategyParams):
        super().__init__(params)
        self.period = params.parameters.get("period", 14)
        self.overbought = params.parameters.get("overbought", 70)
        self.oversold = params.parameters.get("oversold", 30)
        self.position_size = params.parameters.get("position_size", 0.1)

    def _calculate_rsi(self, close: pd.Series, period: int) -> pd.Series:
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    async def initialize(self, context: StrategyContext) -> None:
        pass

    async def on_bar(self, context: StrategyContext) -> list[Signal]:
        signals = []
        for symbol in self.params.symbols:
            df = context.get_ohlcv(symbol, self.period + 10)
            if df is None or len(df) < self.period:
                continue

            close = df["close"].astype(float)
            rsi = self._calculate_rsi(close, self.period).iloc[-1]
            current_price = context.get_price(symbol)
            if current_price is None:
                continue

            position = context.positions.get(symbol)
            has_long = position is not None and position.quantity > 0
            has_short = position is not None and position.quantity < 0

            if rsi < self.oversold and not has_long:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    strength=(self.oversold - rsi) / self.oversold,
                    timestamp=context.current_time,
                    price=current_price,
                    metadata={"strategy": "rsi", "rsi": rsi}
                ))
            elif rsi > self.overbought and not has_short:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    strength=(rsi - self.overbought) / (100 - self.overbought),
                    timestamp=context.current_time,
                    price=current_price,
                    metadata={"strategy": "rsi", "rsi": rsi}
                ))
            elif has_long and rsi > 50:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.CLOSE_LONG,
                    strength=1.0,
                    timestamp=context.current_time,
                    price=current_price,
                    metadata={"strategy": "rsi", "rsi": rsi}
                ))
            elif has_short and rsi < 50:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.CLOSE_SHORT,
                    strength=1.0,
                    timestamp=context.current_time,
                    price=current_price,
                    metadata={"strategy": "rsi", "rsi": rsi}
                ))

        self.signals.extend(signals)
        return signals

    async def on_tick(self, context: StrategyContext, ticker) -> list[Signal]:
        return []

    async def on_order_fill(self, context: StrategyContext, order) -> None:
        pass

    async def on_position_change(self, context: StrategyContext, position: Position) -> None:
        pass
