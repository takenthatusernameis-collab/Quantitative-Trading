import asyncio
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from loguru import logger

from qtrading.strategy import Order, OrderSide, OrderStatus, OrderType


class OrderBookSide(StrEnum):
    BID = "bid"
    ASK = "ask"


@dataclass
class OrderBookLevel:
    price: Decimal
    quantity: Decimal
    orders: list[str] = field(default_factory=list)


@dataclass
class PaperOrderBook:
    symbol: str
    bids: dict[Decimal, OrderBookLevel] = field(default_factory=dict)
    asks: dict[Decimal, OrderBookLevel] = field(default_factory=dict)
    last_update: datetime = field(default_factory=datetime.now)
    sequence: int = 0

    def get_best_bid(self) -> Decimal | None:
        if not self.bids:
            return None
        return max(self.bids.keys())

    def get_best_ask(self) -> Decimal | None:
        if not self.asks:
            return None
        return min(self.asks.keys())

    def get_spread(self) -> Decimal | None:
        bid = self.get_best_bid()
        ask = self.get_best_ask()
        if bid is None or ask is None:
            return None
        return ask - bid

    def get_mid_price(self) -> Decimal | None:
        bid = self.get_best_bid()
        ask = self.get_best_ask()
        if bid is None or ask is None:
            return None
        return (bid + ask) / Decimal("2")

    def add_level(self, side: OrderBookSide, price: Decimal, quantity: Decimal, order_id: str) -> None:
        book = self.bids if side == OrderBookSide.BID else self.asks
        if price not in book:
            book[price] = OrderBookLevel(price=price, quantity=Decimal("0"))
        book[price].quantity += quantity
        book[price].orders.append(order_id)
        self.sequence += 1
        self.last_update = datetime.now()

    def remove_level(self, side: OrderBookSide, price: Decimal, quantity: Decimal, order_id: str) -> bool:
        book = self.bids if side == OrderBookSide.BID else self.asks
        if price not in book:
            return False
        level = book[price]
        level.quantity -= quantity
        if order_id in level.orders:
            level.orders.remove(order_id)
        if level.quantity <= 0:
            del book[price]
        self.sequence += 1
        self.last_update = datetime.now()
        return True

    def get_depth(self, side: OrderBookSide, levels: int = 10) -> list[tuple[Decimal, Decimal]]:
        book = self.bids if side == OrderBookSide.BID else self.asks
        prices = sorted(book.keys(), reverse=(side == OrderBookSide.BID))
        return [(p, book[p].quantity) for p in prices[:levels]]


@dataclass
class LatencyConfig:
    base_latency_ms: int = 10
    jitter_ms: int = 5
    queue_latency_ms: int = 2
    network_latency_ms: int = 3


@dataclass
class PartialFillConfig:
    enabled: bool = True
    min_fill_rate: Decimal = Decimal("0.1")
    max_fill_rate: Decimal = Decimal("1.0")
    fill_probability: Decimal = Decimal("0.3")


@dataclass
class PaperTradingConfig:
    latency: LatencyConfig = field(default_factory=LatencyConfig)
    partial_fill: PartialFillConfig = field(default_factory=PartialFillConfig)
    slippage_rate: Decimal = Decimal("0.0005")
    commission_rate: Decimal = Decimal("0.001")
    maker_commission_rate: Decimal = Decimal("0.0005")
    taker_commission_rate: Decimal = Decimal("0.001")
    initial_balances: dict[str, Decimal] = field(default_factory=dict)
    max_order_size_pct: Decimal = Decimal("0.1")
    enable_order_book: bool = True
    tick_size: Decimal = Decimal("0.01")
    lot_size: Decimal = Decimal("0.00001")


@dataclass
class InternalOrderState:
    order: Order
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: Decimal = Decimal("0")
    average_fill_price: Decimal | None = None
    commission: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")
    error_message: str | None = None
    history: list[dict] = field(default_factory=list)


class PaperTradingEngine:
    def __init__(self, config: PaperTradingConfig | None = None):
        self.config = config or PaperTradingConfig()
        self.order_books: dict[str, PaperOrderBook] = {}
        self.orders: dict[str, InternalOrderState] = {}
        self.balances: dict[str, Decimal] = self.config.initial_balances.copy()
        self.positions: dict[str, Decimal] = {}
        self.trade_history: list[dict] = []
        self._order_counter = 0
        self._lock = asyncio.Lock()
        self._callbacks: list = []

        if not self.balances:
            self.balances["USDT"] = Decimal("100000")
            self.balances["BTC"] = Decimal("0")
            self.balances["ETH"] = Decimal("0")

    def add_callback(self, callback: Callable[[Any], None]) -> None:
        self._callbacks.append(callback)

    def _generate_order_id(self) -> str:
        self._order_counter += 1
        return f"paper_{int(time.time() * 1000)}_{self._order_counter}"

    async def _simulate_latency(self) -> None:
        latency = self.config.latency.base_latency_ms + random.randint(
            0, self.config.latency.jitter_ms
        )
        await asyncio.sleep(latency / 1000)

    def _get_or_create_order_book(self, symbol: str) -> PaperOrderBook:
        if symbol not in self.order_books:
            self.order_books[symbol] = PaperOrderBook(symbol=symbol)
        return self.order_books[symbol]

    def update_market_data(self, symbol: str, bids: list[tuple[Decimal, Decimal]], asks: list[tuple[Decimal, Decimal]]) -> None:
        book = self._get_or_create_order_book(symbol)
        book.bids.clear()
        book.asks.clear()
        for price, qty in bids:
            book.add_level(OrderBookSide.BID, price, qty, "")
        for price, qty in asks:
            book.add_level(OrderBookSide.ASK, price, qty, "")
        book.last_update = datetime.now()

    def update_price(self, symbol: str, price: Decimal) -> None:
        book = self._get_or_create_order_book(symbol)
        spread = price * Decimal("0.0002")
        book.add_level(OrderBookSide.BID, price - spread / 2, Decimal("10"), "")
        book.add_level(OrderBookSide.ASK, price + spread / 2, Decimal("10"), "")

    async def submit_order(self, order: Order) -> dict:
        await self._simulate_latency()

        order_id = order.id or self._generate_order_id()

        book = self._get_or_create_order_book(order.symbol)
        mid_price = book.get_mid_price()
        if mid_price is None:
            return self._create_rejection(order_id, order, "No market data available")

        if order.side == OrderSide.BUY:
            required_quote = order.quantity * mid_price * (Decimal("1") + self.config.slippage_rate)
            available = self.balances.get("USDT", Decimal("0"))
            if required_quote > available:
                return self._create_rejection(order_id, order, "Insufficient balance")
        else:
            base_asset = order.symbol.split("/")[0]
            available = self.balances.get(base_asset, Decimal("0"))
            if order.quantity > available:
                return self._create_rejection(order_id, order, "Insufficient balance")

        internal_state = InternalOrderState(order=order)
        internal_state.history.append({
            "status": OrderStatus.PENDING,
            "timestamp": datetime.now(),
            "filled_qty": Decimal("0"),
            "avg_price": Decimal("0"),
        })
        self.orders[order_id] = internal_state

        if order.order_type == OrderType.MARKET:
            return await self._execute_market_order(order_id, internal_state, book)
        elif order.order_type == OrderType.LIMIT:
            return await self._execute_limit_order(order_id, internal_state, book)
        else:
            return self._create_rejection(order_id, order, f"Unsupported order type: {order.order_type}")

    async def _execute_market_order(self, order_id: str, state: InternalOrderState, book: PaperOrderBook) -> dict:
        order = state.order
        side_book = book.asks if order.side == OrderSide.BUY else book.bids
        if not side_book:
            return self._create_rejection(order_id, order, "No liquidity available")

        prices = sorted(side_book.keys())
        remaining_qty = order.quantity
        total_filled = Decimal("0")
        total_cost = Decimal("0")
        commission = Decimal("0")
        slippage_cost = Decimal("0")

        for price in prices:
            if remaining_qty <= 0:
                break
            level = side_book[price]
            available_qty = level.quantity

            if self.config.partial_fill.enabled and random.random() < float(self.config.partial_fill.fill_probability):
                fill_rate = self.config.partial_fill.min_fill_rate + (
                    self.config.partial_fill.max_fill_rate - self.config.partial_fill.min_fill_rate
                ) * Decimal(str(random.random()))
                fill_qty = min(remaining_qty, available_qty * fill_rate)
            else:
                fill_qty = min(remaining_qty, available_qty)

            if fill_qty <= 0:
                continue

            fill_price = price
            if order.side == OrderSide.BUY:
                fill_price = price * (Decimal("1") + self.config.slippage_rate)
            else:
                fill_price = price * (Decimal("1") - self.config.slippage_rate)

            fill_cost = fill_price * fill_qty
            fill_commission = fill_cost * self.config.taker_commission_rate
            fill_slippage = fill_cost * self.config.slippage_rate

            book.remove_level(
                OrderBookSide.ASK if order.side == OrderSide.BUY else OrderBookSide.BID,
                price,
                fill_qty,
                order_id,
            )

            remaining_qty -= fill_qty
            total_filled += fill_qty
            total_cost += fill_cost
            commission += fill_commission
            slippage_cost += fill_slippage

            self._record_fill(order_id, fill_qty, fill_price, fill_commission, fill_slippage)

            if remaining_qty <= 0:
                break

        if total_filled > 0:
            avg_price = total_cost / total_filled
            status = OrderStatus.FILLED if remaining_qty <= 0 else OrderStatus.PARTIALLY_FILLED
        else:
            avg_price = Decimal("0")
            status = OrderStatus.REJECTED

        self._update_balances_and_positions(order, total_filled, avg_price, commission, slippage_cost)
        self._update_order_status(order_id, status, total_filled, avg_price, commission, slippage_cost)

        return self._create_report(order_id, order, total_filled, avg_price, status, commission, slippage_cost)

    async def _execute_limit_order(self, order_id: str, state: InternalOrderState, book: PaperOrderBook) -> dict:
        order = state.order
        if order.price is None:
            return self._create_rejection(order_id, order, "Limit price required")

        if order.side == OrderSide.BUY:
            best_ask = book.get_best_ask()
            if best_ask and order.price >= best_ask:
                return await self._execute_market_order(order_id, state, book)
            book.add_level(OrderBookSide.BID, order.price, order.quantity, order_id)
        else:
            best_bid = book.get_best_bid()
            if best_bid and order.price <= best_bid:
                return await self._execute_market_order(order_id, state, book)
            book.add_level(OrderBookSide.ASK, order.price, order.quantity, order_id)

        self._update_order_status(order_id, OrderStatus.OPEN, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"))

        return self._create_report(order_id, order, Decimal("0"), order.price, OrderStatus.OPEN, Decimal("0"), Decimal("0"))

    def _create_rejection(self, order_id: str, order: Order, reason: str) -> dict:
        self._update_order_status(order_id, OrderStatus.REJECTED, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), reason)
        return {
            "order_id": order_id,
            "symbol": order.symbol,
            "side": order.side,
            "order_type": order.order_type,
            "requested_quantity": order.quantity,
            "filled_quantity": Decimal("0"),
            "average_price": Decimal("0"),
            "status": OrderStatus.REJECTED,
            "timestamp": datetime.now(),
            "commission": Decimal("0"),
            "slippage": Decimal("0"),
            "error_message": reason,
        }

    def _record_fill(self, order_id: str, qty: Decimal, price: Decimal, commission: Decimal, slippage: Decimal) -> None:
        order = self.orders[order_id].order
        trade = {
            "order_id": order_id,
            "symbol": order.symbol,
            "side": order.side,
            "quantity": qty,
            "price": price,
            "commission": commission,
            "slippage": slippage,
            "timestamp": datetime.now(),
        }
        self.trade_history.append(trade)

    def _update_balances_and_positions(self, order: Order, filled_qty: Decimal, avg_price: Decimal, commission: Decimal, slippage: Decimal) -> None:
        base, quote = order.symbol.split("/")

        if order.side == OrderSide.BUY:
            cost = avg_price * filled_qty + commission + slippage
            self.balances[quote] = self.balances.get(quote, Decimal("0")) - cost
            self.balances[base] = self.balances.get(base, Decimal("0")) + filled_qty
            self.positions[order.symbol] = self.positions.get(order.symbol, Decimal("0")) + filled_qty
        else:
            proceeds = avg_price * filled_qty - commission - slippage
            self.balances[quote] = self.balances.get(quote, Decimal("0")) + proceeds
            self.balances[base] = self.balances.get(base, Decimal("0")) - filled_qty
            self.positions[order.symbol] = self.positions.get(order.symbol, Decimal("0")) - filled_qty

        if self.positions.get(order.symbol, Decimal("0")) == 0:
            self.positions.pop(order.symbol, None)

    def _update_order_status(
        self,
        order_id: str,
        status: OrderStatus,
        filled_qty: Decimal,
        avg_price: Decimal,
        commission: Decimal,
        slippage: Decimal,
        error: str | None = None,
    ) -> None:
        if order_id not in self.orders:
            return
        state = self.orders[order_id]
        state.status = status
        state.filled_quantity = filled_qty
        state.average_fill_price = avg_price if filled_qty > 0 else None
        state.commission = commission
        state.slippage = slippage
        state.error_message = error
        state.history.append({
            "status": status,
            "timestamp": datetime.now(),
            "filled_qty": filled_qty,
            "avg_price": avg_price,
            "commission": commission,
            "slippage": slippage,
            "error": error,
        })

    def _create_report(
        self,
        order_id: str,
        order: Order,
        filled_qty: Decimal,
        avg_price: Decimal,
        status: OrderStatus,
        commission: Decimal,
        slippage: Decimal,
        error: str | None = None,
    ) -> dict:
        return {
            "order_id": order_id,
            "symbol": order.symbol,
            "side": order.side,
            "order_type": order.order_type,
            "requested_quantity": order.quantity,
            "filled_quantity": filled_qty,
            "average_price": avg_price,
            "status": status,
            "timestamp": datetime.now(),
            "commission": commission,
            "slippage": slippage,
            "error_message": error,
        }

    async def cancel_order(self, order_id: str) -> bool:
        await self._simulate_latency()

        if order_id not in self.orders:
            return False

        state = self.orders[order_id]
        order = state.order
        if state.status not in (OrderStatus.OPEN, OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED):
            return False

        book = self._get_or_create_order_book(order.symbol)
        if order.order_type == OrderType.LIMIT and order.price:
            book.remove_level(
                OrderBookSide.BID if order.side == OrderSide.BUY else OrderBookSide.ASK,
                order.price,
                order.quantity - state.filled_quantity,
                order_id,
            )

        self._update_order_status(order_id, OrderStatus.CANCELLED, state.filled_quantity, state.average_fill_price or Decimal("0"), Decimal("0"), Decimal("0"))
        return True

    async def get_order_status(self, order_id: str) -> dict | None:
        if order_id not in self.orders:
            return None
        state = self.orders[order_id]
        order = state.order
        return {
            "order_id": order_id,
            "symbol": order.symbol,
            "side": order.side,
            "order_type": order.order_type,
            "requested_quantity": order.quantity,
            "filled_quantity": state.filled_quantity,
            "average_price": state.average_fill_price or Decimal("0"),
            "status": state.status,
            "timestamp": state.history[-1]["timestamp"] if state.history else datetime.now(),
            "history": state.history,
        }

    async def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        open_orders: list[dict] = []
        for order_id, state in self.orders.items():
            if state.status in (OrderStatus.OPEN, OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED):
                if symbol is None or state.order.symbol == symbol:
                    status = await self.get_order_status(order_id)
                    if status is not None:
                        open_orders.append(status)
        return open_orders

    def get_balance(self, asset: str) -> Decimal:
        return self.balances.get(asset, Decimal("0"))

    def get_all_balances(self) -> dict[str, Decimal]:
        return self.balances.copy()

    def get_position(self, symbol: str) -> Decimal:
        return self.positions.get(symbol, Decimal("0"))

    def get_all_positions(self) -> dict[str, Decimal]:
        return self.positions.copy()

    def get_portfolio_value(self, prices: dict[str, Decimal]) -> Decimal:
        value = self.balances.get("USDT", Decimal("0"))
        for symbol, qty in self.positions.items():
            if symbol in prices:
                value += qty * prices[symbol]
        return value

    def get_order_book(self, symbol: str, depth: int = 10) -> dict:
        book = self._get_or_create_order_book(symbol)
        return {
            "symbol": symbol,
            "bids": book.get_depth(OrderBookSide.BID, depth),
            "asks": book.get_depth(OrderBookSide.ASK, depth),
            "spread": book.get_spread(),
            "mid_price": book.get_mid_price(),
            "timestamp": book.last_update,
            "sequence": book.sequence,
        }

    def get_trade_history(self, symbol: str | None = None, limit: int = 100) -> list[dict]:
        trades = self.trade_history
        if symbol:
            trades = [t for t in trades if t["symbol"] == symbol]
        return trades[-limit:]


class PaperTradingEngineV2:
    def __init__(self, config: PaperTradingConfig | None = None):
        self.config = config or PaperTradingConfig()
        self.engine = PaperTradingEngine(config)
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        self._running = True
        logger.info("Paper trading engine started")

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("Paper trading engine stopped")

    def __getattr__(self, name: str) -> Any:
        return getattr(self.engine, name)
