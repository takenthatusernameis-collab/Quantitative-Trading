"""Real-time WebSocket data feed manager with reconnection handling."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from datetime import datetime
from decimal import Decimal

from loguru import logger

from qtrading.data.models import OHLCV, Exchange, Ticker, Timeframe


class RealTimeDataFeed:
    """Manages real-time WebSocket data feeds with reconnection handling."""

    def __init__(
        self,
        max_reconnect_attempts: int = 10,
        reconnect_delay: float = 5.0,
        backoff_multiplier: float = 1.5,
    ):
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self.backoff_multiplier = backoff_multiplier
        self._subscribed_symbols: dict[str, list[Callable]] = {}
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._exchange_instance = None
        self._reconnect_count: dict[str, int] = {}

    def set_exchange_instance(self, instance) -> None:
        """Set the underlying exchange instance."""
        self._exchange_instance = instance

    def subscribe_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        callback: Callable[[OHLCV], Awaitable[None]],
    ) -> None:
        """Subscribe to OHLCV WebSocket feed."""
        key = f"{symbol}_{timeframe.value}"
        if key not in self._subscribed_symbols:
            self._subscribed_symbols[key] = []
        self._subscribed_symbols[key].append(callback)

    def subscribe_ticker(
        self,
        symbol: str,
        callback: Callable[[Ticker], Awaitable[None]],
    ) -> None:
        """Subscribe to ticker WebSocket feed."""
        key = f"ticker_{symbol}"
        if key not in self._subscribed_symbols:
            self._subscribed_symbols[key] = []
        self._subscribed_symbols[key].append(callback)

    async def start(self) -> None:
        """Start all WebSocket subscriptions."""
        self._running = True
        for key in self._subscribed_symbols:
            task = asyncio.create_task(self._subscribe_loop(key))
            self._tasks.append(task)

    async def stop(self) -> None:
        """Stop all WebSocket subscriptions."""
        self._running = False
        for task in self._tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()

    async def _subscribe_loop(self, key: str) -> None:
        """Main subscription loop with reconnection handling."""
        while self._running:
            try:
                if key.startswith("ticker_"):
                    symbol = key[7:]
                    await self._watch_ticker(symbol)
                else:
                    parts = key.rsplit("_", 1)
                    if len(parts) == 2:
                        symbol, tf = parts
                        timeframe = Timeframe(tf)
                        await self._watch_ohlcv(symbol, timeframe)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Subscription error for {key}: {e}")
                count = self._reconnect_count.get(key, 0)
                if count >= self.max_reconnect_attempts:
                    logger.error(f"Max reconnection attempts reached for {key}")
                    break
                self._reconnect_count[key] = count + 1
                delay = self.reconnect_delay * (self.backoff_multiplier ** count)
                logger.info(f"Reconnecting to {key} in {delay:.1f}s (attempt {count + 1})")
                await asyncio.sleep(delay)

    async def _watch_ohlcv(self, symbol: str, timeframe: Timeframe) -> None:
        """Watch OHLCV WebSocket feed."""
        if self._exchange_instance is None or not hasattr(self._exchange_instance, "watch_ohlcv"):
            logger.warning(f"Exchange does not support watch_ohlcv for {symbol}")
            return

        while self._running:
            try:
                ohlcv_raw = await self._exchange_instance.watch_ohlcv(symbol, timeframe.value)
                exchange_id = getattr(self._exchange_instance, "id", "unknown")
                ohlcv = OHLCV(
                    timestamp=datetime.fromtimestamp(ohlcv_raw[0] / 1000),
                    open=Decimal(str(ohlcv_raw[1])),
                    high=Decimal(str(ohlcv_raw[2])),
                    low=Decimal(str(ohlcv_raw[3])),
                    close=Decimal(str(ohlcv_raw[4])),
                    volume=Decimal(str(ohlcv_raw[5])),
                    symbol=symbol,
                    timeframe=timeframe,
                    exchange=Exchange(exchange_id),
                )
                key = f"{symbol}_{timeframe.value}"
                for callback in self._subscribed_symbols.get(key, []):
                    try:
                        await callback(ohlcv)
                    except Exception as e:
                        logger.error(f"OHLCV callback error: {e}")
            except Exception as e:
                logger.error(f"watch_ohlcv error for {symbol}: {e}")
                break

    async def _watch_ticker(self, symbol: str) -> None:
        """Watch ticker WebSocket feed."""
        if self._exchange_instance is None or not hasattr(self._exchange_instance, "watch_ticker"):
            logger.warning(f"Exchange does not support watch_ticker for {symbol}")
            return

        while self._running:
            try:
                ticker_raw = await self._exchange_instance.watch_ticker(symbol)
                exchange_id = getattr(self._exchange_instance, "id", "unknown")
                last_val = ticker_raw.get("last")
                last_price = Decimal(str(last_val)) if last_val else Decimal("0")
                ticker = Ticker(
                    symbol=symbol,
                    bid=Decimal(str(ticker_raw["bid"])) if ticker_raw.get("bid") else Decimal("0"),
                    ask=Decimal(str(ticker_raw["ask"])) if ticker_raw.get("ask") else Decimal("0"),
                    last=last_price,
                    volume=Decimal(str(ticker_raw.get("baseVolume", 0))),
                    timestamp=datetime.fromtimestamp(ticker_raw["timestamp"] / 1000)
                    if ticker_raw.get("timestamp")
                    else datetime.now(),
                    exchange=Exchange(exchange_id),
                )
                key = f"ticker_{symbol}"
                for callback in self._subscribed_symbols.get(key, []):
                    try:
                        await callback(ticker)
                    except Exception as e:
                        logger.error(f"Ticker callback error: {e}")
            except Exception as e:
                logger.error(f"watch_ticker error for {symbol}: {e}")
                break
