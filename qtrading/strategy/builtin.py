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

            if prev_fast <= prev_slow and current_fast > current_slow:
                if not has_position:
                    signals.append(Signal(
                        symbol=symbol,
                        signal_type=SignalType.BUY,
                        strength=1.0,
                        timestamp=context.current_time,
                        price=current_price,
                        metadata={"strategy": "sma_crossover", "fast": current_fast, "slow": current_slow}
                    ))
            elif prev_fast >= prev_slow and current_fast < current_slow:
                if has_position and position.side == "long":
                    signals.append(Signal(
                        symbol=symbol,
                        signal_type=SignalType.CLOSE_LONG,
                        strength=1.0,
                        timestamp=context.current_time,
                        price=current_price,
                        metadata={"strategy": "sma_crossover", "fast": current_fast, "slow": current_slow}
                    ))

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
                    metadata={"strategy": "mean_reversion", "zscore": zscore, "mean": mean, "std": std}
                ))
            elif zscore > self.entry_zscore and not has_short:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    strength=min(abs(zscore) / self.entry_zscore, 2.0),
                    timestamp=context.current_time,
                    price=context.get_price(symbol),
                    metadata={"strategy": "mean_reversion", "zscore": zscore, "mean": mean, "std": std}
                ))
            elif has_long and zscore > -self.exit_zscore:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.CLOSE_LONG,
                    strength=1.0,
                    timestamp=context.current_time,
                    price=context.get_price(symbol),
                    metadata={"strategy": "mean_reversion", "zscore": zscore}
                ))
            elif has_short and zscore < self.exit_zscore:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.CLOSE_SHORT,
                    strength=1.0,
                    timestamp=context.current_time,
                    price=context.get_price(symbol),
                    metadata={"strategy": "mean_reversion", "zscore": zscore}
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
