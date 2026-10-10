import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from loguru import logger

from qtrading.config import get_settings
from qtrading.strategy import Order, OrderSide, OrderStatus, OrderType

if TYPE_CHECKING:
    from qtrading.execution.algorithms import (
        AlgorithmFactory,
        AlgorithmSlice,
        AlgorithmState,
        AlgorithmStateSnapshot,
        AlgorithmType,
        BaseExecutionAlgorithm,
        ExecutionAlgorithmConfig,
        ImplementationShortfallAlgorithm,
        POVAlgorithm,
        TWAPAlgorithm,
        VWAPAlgorithm,
    )
    from qtrading.execution.oms import (
        OMSOrder,
        OMSOrderState,
        OrderEvent,
        OrderManager,
    )
    from qtrading.execution.paper_engine import (
        LatencyConfig,
        PaperOrderBook,
        PaperTradingConfig,
        PaperTradingEngine,
        PartialFillConfig,
    )
    from qtrading.execution.smart_router import (
        RoutingDecision,
        RoutingStrategy,
        SimulatedVenueConnector,
        SmartOrderRouter,
        SmartOrderRouterConfig,
        VenueConfig,
        VenueConnector,
        VenueQuote,
        VenueType,
    )


class ExecutionMode(StrEnum):
    SIMULATION = "simulation"
    PAPER = "paper"
    LIVE = "live"


@dataclass
class ExecutionReport:
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    requested_quantity: Decimal
    filled_quantity: Decimal
    average_price: Decimal
    status: OrderStatus
    timestamp: datetime
    commission: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")
    exchange_order_id: str | None = None
    error_message: str | None = None


class ExecutionEngine(ABC):
    @abstractmethod
    async def submit_order(self, order: Order) -> ExecutionReport:
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        pass

    @abstractmethod
    async def get_order_status(self, order_id: str) -> ExecutionReport | None:
        pass

    @abstractmethod
    async def get_open_orders(self, symbol: str | None = None) -> list[ExecutionReport]:
        pass


class SimulationEngine(ExecutionEngine):
    def __init__(
        self,
        slippage_rate: Decimal = Decimal("0.0005"),
        commission_rate: Decimal = Decimal("0.001"),
    ):
        self.slippage_rate = slippage_rate
        self.commission_rate = commission_rate
        self.orders: dict[str, ExecutionReport] = {}
        self._price_feeds: dict[str, Decimal] = {}

    def update_price(self, symbol: str, price: Decimal) -> None:
        self._price_feeds[symbol] = price

    async def submit_order(self, order: Order) -> ExecutionReport:
        price = self._price_feeds.get(order.symbol)
        if price is None:
            return ExecutionReport(
                order_id=order.id,
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                requested_quantity=order.quantity,
                filled_quantity=Decimal("0"),
                average_price=Decimal("0"),
                status=OrderStatus.REJECTED,
                timestamp=datetime.now(),
                error_message=f"No price feed for {order.symbol}",
            )

        if order.order_type == OrderType.MARKET:
            fill_price = (
                price * (Decimal("1") + self.slippage_rate)
                if order.side == OrderSide.BUY
                else price * (Decimal("1") - self.slippage_rate)
            )
            filled_qty = order.quantity
        elif order.order_type == OrderType.LIMIT:
            if order.price is None:
                return ExecutionReport(
                    order_id=order.id,
                    symbol=order.symbol,
                    side=order.side,
                    order_type=order.order_type,
                    requested_quantity=order.quantity,
                    filled_quantity=Decimal("0"),
                    average_price=Decimal("0"),
                    status=OrderStatus.REJECTED,
                    timestamp=datetime.now(),
                    error_message="Limit price required",
                )
            if (
                order.side == OrderSide.BUY
                and price <= order.price
                or order.side == OrderSide.SELL
                and price >= order.price
            ):
                fill_price = order.price
                filled_qty = order.quantity
            else:
                return ExecutionReport(
                    order_id=order.id,
                    symbol=order.symbol,
                    side=order.side,
                    order_type=order.order_type,
                    requested_quantity=order.quantity,
                    filled_quantity=Decimal("0"),
                    average_price=Decimal("0"),
                    status=OrderStatus.OPEN,
                    timestamp=datetime.now(),
                )
        else:
            fill_price = price
            filled_qty = order.quantity

        commission = fill_price * filled_qty * self.commission_rate
        slippage = fill_price * filled_qty * self.slippage_rate

        report = ExecutionReport(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            requested_quantity=order.quantity,
            filled_quantity=filled_qty,
            average_price=fill_price,
            status=OrderStatus.FILLED,
            timestamp=datetime.now(),
            commission=commission,
            slippage=slippage,
        )

        self.orders[order.id] = report
        logger.info(f"Order filled: {order.id} @ {fill_price}")
        return report

    async def cancel_order(self, order_id: str) -> bool:
        if order_id in self.orders:
            order = self.orders[order_id]
            if order.status in (OrderStatus.OPEN, OrderStatus.PENDING):
                order.status = OrderStatus.CANCELLED
                return True
        return False

    async def get_order_status(self, order_id: str) -> ExecutionReport | None:
        return self.orders.get(order_id)

    async def get_open_orders(self, symbol: str | None = None) -> list[ExecutionReport]:
        orders = [
            o for o in self.orders.values() if o.status in (OrderStatus.OPEN, OrderStatus.PENDING)
        ]
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        return orders


class OrderRouter:
    def __init__(self, config_path: str | None = None):
        settings = get_settings(config_path)
        self.mode = ExecutionMode.SIMULATION
        self.timeout = settings.execution.timeout_seconds
        self.retry_attempts = settings.execution.retry_attempts
        self.retry_delay = settings.execution.retry_delay_seconds

        self.engine: ExecutionEngine = SimulationEngine(
            slippage_rate=Decimal(str(settings.backtest.slippage_rate)),
            commission_rate=Decimal(str(settings.backtest.commission_rate)),
        )
        self._callbacks: list[Callable[[ExecutionReport], Awaitable[None]]] = []

    def add_callback(self, callback: Callable[[ExecutionReport], Awaitable[None]]) -> None:
        self._callbacks.append(callback)

    async def submit_order(self, order: Order) -> ExecutionReport:
        for attempt in range(self.retry_attempts):
            try:
                report = await asyncio.wait_for(
                    self.engine.submit_order(order),
                    timeout=self.timeout,
                )
                for callback in self._callbacks:
                    await callback(report)
                return report
            except TimeoutError:
                logger.warning(f"Order {order.id} timeout on attempt {attempt + 1}")
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(self.retry_delay)
            except Exception as e:
                logger.error(f"Order {order.id} failed: {e}")
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(self.retry_delay)

        return ExecutionReport(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            requested_quantity=order.quantity,
            filled_quantity=Decimal("0"),
            average_price=Decimal("0"),
            status=OrderStatus.REJECTED,
            timestamp=datetime.now(),
            error_message="Max retries exceeded",
        )

    async def cancel_order(self, order_id: str) -> bool:
        return await self.engine.cancel_order(order_id)

    async def get_order_status(self, order_id: str) -> ExecutionReport | None:
        return await self.engine.get_order_status(order_id)

    async def get_open_orders(self, symbol: str | None = None) -> list[ExecutionReport]:
        return await self.engine.get_open_orders(symbol)

    def update_market_price(self, symbol: str, price: Decimal) -> None:
        if isinstance(self.engine, SimulationEngine):
            self.engine.update_price(symbol, price)

    def set_engine(self, engine: ExecutionEngine) -> None:
        self.engine = engine


class PortfolioManager:
    def __init__(self, initial_capital: Decimal):
        self.cash = initial_capital
        self.positions: dict[str, Decimal] = {}
        self.orders: dict[str, Order] = {}
        self.trade_history: list[ExecutionReport] = []

    def update_from_fill(self, report: ExecutionReport) -> None:
        if report.status != OrderStatus.FILLED:
            return

        self.trade_history.append(report)

        if report.side == OrderSide.BUY:
            cost = (
                report.average_price * report.filled_quantity + report.commission + report.slippage
            )
            self.cash -= cost
            self.positions[report.symbol] = (
                self.positions.get(report.symbol, Decimal("0")) + report.filled_quantity
            )
        else:
            proceeds = (
                report.average_price * report.filled_quantity - report.commission - report.slippage
            )
            self.cash += proceeds
            self.positions[report.symbol] = (
                self.positions.get(report.symbol, Decimal("0")) - report.filled_quantity
            )

            if self.positions[report.symbol] == 0:
                del self.positions[report.symbol]

    def get_portfolio_value(self, prices: dict[str, Decimal]) -> Decimal:
        value = self.cash
        for symbol, qty in self.positions.items():
            if symbol in prices:
                value += qty * prices[symbol]
        return value

    def get_available_cash(self) -> Decimal:
        return self.cash

    def get_position(self, symbol: str) -> Decimal:
        return self.positions.get(symbol, Decimal("0"))


from qtrading.execution.algorithms import (  # noqa: E402
    AlgorithmFactory,
    AlgorithmSlice,
    AlgorithmState,
    AlgorithmStateSnapshot,
    AlgorithmType,
    BaseExecutionAlgorithm,
    ExecutionAlgorithmConfig,
    ImplementationShortfallAlgorithm,
    POVAlgorithm,
    TWAPAlgorithm,
    VWAPAlgorithm,
)
from qtrading.execution.oms import (  # noqa: E402
    OMSOrder,
    OMSOrderState,
    OrderEvent,
    OrderManager,
)
from qtrading.execution.paper_engine import (  # noqa: E402
    LatencyConfig,
    PaperOrderBook,
    PaperTradingConfig,
    PaperTradingEngine,
    PartialFillConfig,
)
from qtrading.execution.smart_router import (  # noqa: E402
    RoutingDecision,
    RoutingStrategy,
    SimulatedVenueConnector,
    SmartOrderRouter,
    SmartOrderRouterConfig,
    VenueConfig,
    VenueConnector,
    VenueQuote,
    VenueType,
)

__all__ = [
    "ExecutionMode",
    "ExecutionReport",
    "ExecutionEngine",
    "SimulationEngine",
    "OrderRouter",
    "PortfolioManager",
    "PaperTradingConfig",
    "PaperTradingEngine",
    "PaperOrderBook",
    "LatencyConfig",
    "PartialFillConfig",
    "OrderManager",
    "OMSOrder",
    "OMSOrderState",
    "OrderEvent",
    "SmartOrderRouter",
    "SmartOrderRouterConfig",
    "VenueConfig",
    "VenueType",
    "RoutingStrategy",
    "VenueQuote",
    "RoutingDecision",
    "VenueConnector",
    "SimulatedVenueConnector",
    "BaseExecutionAlgorithm",
    "TWAPAlgorithm",
    "VWAPAlgorithm",
    "POVAlgorithm",
    "ImplementationShortfallAlgorithm",
    "AlgorithmFactory",
    "AlgorithmType",
    "AlgorithmState",
    "ExecutionAlgorithmConfig",
    "AlgorithmSlice",
    "AlgorithmStateSnapshot",
]
