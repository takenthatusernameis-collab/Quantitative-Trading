from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

import pandas as pd


class Timeframe(StrEnum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"

    def to_seconds(self) -> int:
        """Convert timeframe to seconds."""
        mapping = {
            Timeframe.M1: 60,
            Timeframe.M5: 300,
            Timeframe.M15: 900,
            Timeframe.M30: 1800,
            Timeframe.H1: 3600,
            Timeframe.H4: 14400,
            Timeframe.D1: 86400,
            Timeframe.W1: 604800,
        }
        return mapping.get(self, 0)


class Exchange(StrEnum):
    BINANCE = "binance"
    BYBIT = "bybit"
    COINBASE = "coinbase"
    KRAKEN = "kraken"


@dataclass(frozen=True)
class OHLCV:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    symbol: str
    timeframe: Timeframe
    exchange: Exchange


@dataclass(frozen=True)
class Ticker:
    symbol: str
    bid: Decimal
    ask: Decimal
    last: Decimal
    volume: Decimal
    timestamp: datetime
    exchange: Exchange

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / 2


@dataclass(frozen=True)
class OrderBook:
    symbol: str
    bids: list[tuple[Decimal, Decimal]]
    asks: list[tuple[Decimal, Decimal]]
    timestamp: datetime
    exchange: Exchange

    @property
    def best_bid(self) -> Decimal:
        return self.bids[0][0] if self.bids else Decimal("0")

    @property
    def best_ask(self) -> Decimal:
        return self.asks[0][0] if self.asks else Decimal("0")

    @property
    def spread(self) -> Decimal:
        return self.best_ask - self.best_bid


class DataSource(ABC):
    @abstractmethod
    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> list[OHLCV]:
        pass

    @abstractmethod
    async def fetch_ticker(self, symbol: str) -> Ticker:
        pass

    @abstractmethod
    async def fetch_order_book(self, symbol: str, limit: int = 20) -> OrderBook:
        pass

    @abstractmethod
    async def subscribe_ohlcv(self, symbol: str, timeframe: Timeframe, callback) -> None:
        pass

    @abstractmethod
    async def subscribe_ticker(self, symbol: str, callback) -> None:
        pass

    @abstractmethod
    def get_supported_symbols(self) -> list[str]:
        pass

    @abstractmethod
    def get_supported_timeframes(self) -> list[Timeframe]:
        pass


class DataCache:
    def __init__(self, cache_dir: str = "./data/cache"):
        from pathlib import Path
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, symbol: str, timeframe: Timeframe, exchange: Exchange):
        safe_symbol = symbol.replace("/", "_")
        return self.cache_dir / f"{exchange.value}_{safe_symbol}_{timeframe.value}.parquet"

    def save(self, data: list[OHLCV]) -> None:
        if not data:
            return
        df = pd.DataFrame([{
            "timestamp": ohlcv.timestamp,
            "open": float(ohlcv.open),
            "high": float(ohlcv.high),
            "low": float(ohlcv.low),
            "close": float(ohlcv.close),
            "volume": float(ohlcv.volume),
            "symbol": ohlcv.symbol,
            "timeframe": ohlcv.timeframe.value,
            "exchange": ohlcv.exchange.value,
        } for ohlcv in data])
        cache_path = self._get_cache_path(data[0].symbol, data[0].timeframe, data[0].exchange)
        df.to_parquet(cache_path, index=False)

    def load(
        self,
        symbol: str,
        timeframe: Timeframe,
        exchange: Exchange,
        since: datetime | None = None,
    ) -> list[OHLCV]:
        cache_path = self._get_cache_path(symbol, timeframe, exchange)
        if not cache_path.exists():
            return []
        df = pd.read_parquet(cache_path)
        if since:
            df = df[df["timestamp"] >= since]
        return [
            OHLCV(
                timestamp=row["timestamp"],
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=Decimal(str(row["volume"])),
                symbol=row["symbol"],
                timeframe=Timeframe(row["timeframe"]),
                exchange=Exchange(row["exchange"]),
            )
            for _, row in df.iterrows()
        ]

    def clear(self, symbol: str, timeframe: Timeframe, exchange: Exchange) -> None:
        cache_path = self._get_cache_path(symbol, timeframe, exchange)
        if cache_path.exists():
            cache_path.unlink()
