from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum, StrEnum
from typing import Optional

import pandas as pd
from pydantic import BaseModel, Field


class SignalType(StrEnum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(StrEnum):
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Signal:
    symbol: str
    signal_type: SignalType
    strength: float
    timestamp: datetime
    price: Decimal | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Order:
    id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Decimal | None = None
    stop_price: Decimal | None = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: Decimal = Decimal("0")
    average_fill_price: Decimal | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    exchange: str | None = None
    strategy_id: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    side: str
    timestamp: datetime
    strategy_id: str | None = None


class StrategyParams(BaseModel):
    name: str
    symbols: list[str] = Field(default_factory=list)
    timeframes: list[str] = Field(default_factory=list)
    parameters: dict = Field(default_factory=dict)


class StrategyContext:
    def __init__(
        self,
        current_time: datetime,
        portfolio_value: Decimal,
        positions: dict[str, Position],
        available_capital: Decimal,
        market_data: dict[str, pd.DataFrame],
    ):
        self.current_time = current_time
        self.portfolio_value = portfolio_value
        self.positions = positions
        self.available_capital = available_capital
        self.market_data = market_data

    def get_price(self, symbol: str) -> Decimal | None:
        if symbol in self.market_data and not self.market_data[symbol].empty:
            return Decimal(str(self.market_data[symbol].iloc[-1]["close"]))
        return None

    def get_ohlcv(self, symbol: str, lookback: int = 100) -> pd.DataFrame | None:
        if symbol in self.market_data:
            df = self.market_data[symbol]
            return df.tail(lookback) if len(df) >= lookback else df
        return None


class Strategy(ABC):
    def __init__(self, params: StrategyParams):
        self.params = params
        self.signals: list[Signal] = []
        self.orders: list[Order] = []
        self._initialized = False

    @abstractmethod
    async def initialize(self, context: StrategyContext) -> None:
        pass

    @abstractmethod
    async def on_bar(self, context: StrategyContext) -> list[Signal]:
        pass

    @abstractmethod
    async def on_tick(self, context: StrategyContext, ticker) -> list[Signal]:
        pass

    @abstractmethod
    async def on_order_fill(self, context: StrategyContext, order: Order) -> None:
        pass

    @abstractmethod
    async def on_position_change(self, context: StrategyContext, position: Position) -> None:
        pass

    async def run(self, context: StrategyContext) -> list[Signal]:
        if not self._initialized:
            await self.initialize(context)
            self._initialized = True
        return await self.on_bar(context)

    def get_signals(self) -> list[Signal]:
        return self.signals.copy()

    def clear_signals(self) -> None:
        self.signals.clear()


class StrategyRegistry:
    _strategies: dict[str, type[Strategy]] = {}

    @classmethod
    def register(cls, name: str, strategy_class: type[Strategy] = None) -> None:
        if strategy_class is None:
            def decorator(cls_):
                cls._strategies[name] = cls_
                return cls_
            return decorator
        cls._strategies[name] = strategy_class

    @classmethod
    def get(cls, name: str) -> type[Strategy] | None:
        return cls._strategies.get(name)

    @classmethod
    def list_strategies(cls) -> list[str]:
        return list(cls._strategies.keys())

    @classmethod
    def create(cls, name: str, params: StrategyParams) -> Strategy:
        strategy_class = cls.get(name)
        if strategy_class is None:
            raise ValueError(f"Strategy '{name}' not found")
        return strategy_class(params)
