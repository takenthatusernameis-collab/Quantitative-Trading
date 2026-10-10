import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import ccxt.async_support as ccxt
from loguru import logger

from qtrading.data.models import (
    OHLCV,
    DataCache,
    DataSource,
    Exchange,
    OrderBook,
    Ticker,
    Timeframe,
)


class CCXTDataSource(DataSource):
    def __init__(
        self,
        exchange: Exchange,
        api_key: str | None = None,
        api_secret: str | None = None,
        password: str | None = None,
        sandbox: bool = False,
        cache: DataCache | None = None,
    ):
        self.exchange = exchange
        self.cache = cache
        self._exchange_instance = None
        self._config = {
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }
        if api_key:
            self._config["apiKey"] = api_key
        if api_secret:
            self._config["secret"] = api_secret
        if password:
            self._config["password"] = password
        if sandbox:
            self._config["options"]["defaultType"] = "future"

    async def _get_exchange(self):
        if self._exchange_instance is None:
            exchange_class = getattr(ccxt, self.exchange.value)
            self._exchange_instance = exchange_class(self._config)
            await self._exchange_instance.load_markets()
        return self._exchange_instance

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> list[OHLCV]:
        if self.cache:
            cached = self.cache.load(symbol, timeframe, self.exchange, since)
            if cached and (limit is None or len(cached) >= limit):
                return cached[-limit:] if limit else cached

        exchange = await self._get_exchange()
        since_ms = int(since.timestamp() * 1000) if since else None

        try:
            raw_ohlcv = await exchange.fetch_ohlcv(
                symbol, timeframe.value, since=since_ms, limit=limit
            )
        except Exception as e:
            logger.error(f"Failed to fetch OHLCV for {symbol} on {self.exchange}: {e}")
            raise

        ohlcv_list = [
            OHLCV(
                timestamp=datetime.fromtimestamp(candle[0] / 1000, tz=UTC),
                open=Decimal(str(candle[1])),
                high=Decimal(str(candle[2])),
                low=Decimal(str(candle[3])),
                close=Decimal(str(candle[4])),
                volume=Decimal(str(candle[5])),
                symbol=symbol,
                timeframe=timeframe,
                exchange=self.exchange,
            )
            for candle in raw_ohlcv
        ]

        if self.cache and ohlcv_list:
            self.cache.save(ohlcv_list)

        return ohlcv_list

    async def fetch_ticker(self, symbol: str) -> Ticker:
        exchange = await self._get_exchange()
        try:
            ticker = await exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.error(f"Failed to fetch ticker for {symbol} on {self.exchange}: {e}")
            raise

        return Ticker(
            symbol=symbol,
            bid=Decimal(str(ticker["bid"])) if ticker["bid"] else Decimal("0"),
            ask=Decimal(str(ticker["ask"])) if ticker["ask"] else Decimal("0"),
            last=Decimal(str(ticker["last"])) if ticker["last"] else Decimal("0"),
            volume=Decimal(str(ticker["baseVolume"])) if ticker["baseVolume"] else Decimal("0"),
            timestamp=datetime.fromtimestamp(ticker["timestamp"] / 1000, tz=UTC)
            if ticker["timestamp"]
            else datetime.now(UTC),
            exchange=self.exchange,
        )

    async def fetch_order_book(self, symbol: str, limit: int = 20) -> OrderBook:
        exchange = await self._get_exchange()
        try:
            order_book = await exchange.fetch_order_book(symbol, limit)
        except Exception as e:
            logger.error(f"Failed to fetch order book for {symbol} on {self.exchange}: {e}")
            raise

        return OrderBook(
            symbol=symbol,
            bids=[(Decimal(str(b[0])), Decimal(str(b[1]))) for b in order_book["bids"]],
            asks=[(Decimal(str(a[0])), Decimal(str(a[1]))) for a in order_book["asks"]],
            timestamp=datetime.fromtimestamp(order_book["timestamp"] / 1000, tz=UTC)
            if order_book["timestamp"]
            else datetime.now(UTC),
            exchange=self.exchange,
        )

    async def subscribe_ohlcv(self, symbol: str, timeframe: Timeframe, callback) -> None:
        exchange = await self._get_exchange()
        if not hasattr(exchange, "watch_ohlcv"):
            raise NotImplementedError(f"{self.exchange} does not support WebSocket OHLCV")

        while True:
            try:
                ohlcv = await exchange.watch_ohlcv(symbol, timeframe.value)
                candle = OHLCV(
                    timestamp=datetime.fromtimestamp(ohlcv[0] / 1000, tz=UTC),
                    open=Decimal(str(ohlcv[1])),
                    high=Decimal(str(ohlcv[2])),
                    low=Decimal(str(ohlcv[3])),
                    close=Decimal(str(ohlcv[4])),
                    volume=Decimal(str(ohlcv[5])),
                    symbol=symbol,
                    timeframe=timeframe,
                    exchange=self.exchange,
                )
                await callback(candle)
            except Exception as e:
                logger.error(f"WebSocket error for {symbol}: {e}")
                await asyncio.sleep(5)

    async def subscribe_ticker(self, symbol: str, callback) -> None:
        exchange = await self._get_exchange()
        if not hasattr(exchange, "watch_ticker"):
            raise NotImplementedError(f"{self.exchange} does not support WebSocket ticker")

        while True:
            try:
                ticker = await exchange.watch_ticker(symbol)
                ticker_obj = Ticker(
                    symbol=symbol,
                    bid=Decimal(str(ticker["bid"])) if ticker["bid"] else Decimal("0"),
                    ask=Decimal(str(ticker["ask"])) if ticker["ask"] else Decimal("0"),
                    last=Decimal(str(ticker["last"])) if ticker["last"] else Decimal("0"),
                    volume=Decimal(str(ticker["baseVolume"]))
                    if ticker["baseVolume"]
                    else Decimal("0"),
                    timestamp=datetime.fromtimestamp(ticker["timestamp"] / 1000, tz=UTC)
                    if ticker["timestamp"]
                    else datetime.now(UTC),
                    exchange=self.exchange,
                )
                await callback(ticker_obj)
            except Exception as e:
                logger.error(f"WebSocket error for {symbol}: {e}")
                await asyncio.sleep(5)

    def get_supported_symbols(self) -> list[str]:
        return []

    def get_supported_timeframes(self) -> list[Timeframe]:
        return list(Timeframe)

    async def close(self):
        if self._exchange_instance:
            await self._exchange_instance.close()
            self._exchange_instance = None


class DataManager:
    def __init__(self, config_path: str | None = None):
        from qtrading.config import get_settings

        self.settings = get_settings(config_path)
        self.sources: dict[Exchange, CCXTDataSource] = {}
        self.cache = DataCache(self.settings.data.cache_dir)

    def get_source(self, exchange: Exchange) -> CCXTDataSource:
        if exchange not in self.sources:
            self.sources[exchange] = CCXTDataSource(exchange, cache=self.cache)
        return self.sources[exchange]

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        exchange: Exchange,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> list[OHLCV]:
        source = self.get_source(exchange)
        return await source.fetch_ohlcv(symbol, timeframe, since, limit)

    async def fetch_ticker(self, symbol: str, exchange: Exchange) -> Ticker:
        source = self.get_source(exchange)
        return await source.fetch_ticker(symbol)

    async def fetch_order_book(self, symbol: str, exchange: Exchange, limit: int = 20) -> OrderBook:
        source = self.get_source(exchange)
        return await source.fetch_order_book(symbol, limit)

    async def close_all(self):
        for source in self.sources.values():
            await source.close()
        self.sources.clear()
