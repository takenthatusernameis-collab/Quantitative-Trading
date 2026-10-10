import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from loguru import logger

from qtrading.execution.oms import OrderManager
from qtrading.strategy import Order, OrderSide, OrderStatus, OrderType


class VenueType(StrEnum):
    EXCHANGE = "exchange"
    DARK_POOL = "dark_pool"
    OTC = "otc"
    INTERNAL = "internal"


class RoutingStrategy(StrEnum):
    BEST_PRICE = "best_price"
    PRO_RATA = "pro_rata"
    WEIGHTED = "weighted"
    SMART = "smart"


@dataclass
class VenueConfig:
    name: str
    venue_type: VenueType = VenueType.EXCHANGE
    enabled: bool = True
    priority: int = 100
    fee_rate: Decimal = Decimal("0.001")
    rebate_rate: Decimal = Decimal("0")
    min_order_size: Decimal = Decimal("0")
    max_order_size: Decimal = Decimal("1000000")
    supported_symbols: list[str] = field(default_factory=list)
    supported_order_types: list[OrderType] = field(default_factory=lambda: [OrderType.MARKET, OrderType.LIMIT])
    latency_ms: int = 10
    metadata: dict = field(default_factory=dict)


@dataclass
class VenueQuote:
    venue: str
    symbol: str
    bid: Decimal
    ask: Decimal
    bid_size: Decimal
    ask_size: Decimal
    timestamp: datetime
    metadata: dict = field(default_factory=dict)

    @property
    def mid_price(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid

    @property
    def spread_bps(self) -> Decimal:
        if self.mid_price == 0:
            return Decimal("0")
        return (self.spread / self.mid_price) * Decimal("10000")


@dataclass
class RoutingDecision:
    venue: str
    quantity: Decimal
    price: Decimal | None
    order_type: OrderType
    reasoning: str
    metadata: dict = field(default_factory=dict)


@dataclass
class SmartOrderRouterConfig:
    default_strategy: RoutingStrategy = RoutingStrategy.SMART
    max_venues_per_order: int = 3
    min_fill_rate: Decimal = Decimal("0.01")
    enable_sor: bool = True
    enable_internalization: bool = True
    price_improvement_threshold_bps: Decimal = Decimal("5")
    venue_configs: dict[str, VenueConfig] = field(default_factory=dict)


class VenueConnector:
    def __init__(self, config: VenueConfig):
        self.config = config
        self._connected = False
        self._last_quote: VenueQuote | None = None
        self._quote_callbacks: list = []

    async def connect(self) -> bool:
        self._connected = True
        logger.info(f"Connected to venue {self.config.name}")
        return True

    async def disconnect(self) -> bool:
        self._connected = False
        logger.info(f"Disconnected from venue {self.config.name}")
        return True

    def is_connected(self) -> bool:
        return self._connected

    def update_quote(self, quote: VenueQuote) -> None:
        self._last_quote = quote
        for callback in self._quote_callbacks:
            try:
                callback(quote)
            except Exception as e:
                logger.error(f"Quote callback error for {self.config.name}: {e}")

    def get_quote(self) -> VenueQuote | None:
        return self._last_quote

    def add_quote_callback(self, callback: Callable[[VenueQuote], None]) -> None:
        self._quote_callbacks.append(callback)

    async def submit_order(self, order: Order) -> dict:
        raise NotImplementedError

    async def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError

    async def get_order_status(self, order_id: str) -> dict | None:
        raise NotImplementedError


class SimulatedVenueConnector(VenueConnector):
    def __init__(self, config: VenueConfig):
        super().__init__(config)
        self.orders: dict[str, dict] = {}
        self._order_counter = 0

    async def submit_order(self, order: Order) -> dict:
        self._order_counter += 1
        exchange_order_id = f"{self.config.name}_{int(datetime.now().timestamp() * 1000)}_{self._order_counter}"

        quote = self._last_quote
        if quote is None:
            return {
                "order_id": order.id,
                "exchange_order_id": exchange_order_id,
                "status": OrderStatus.REJECTED,
                "filled_quantity": Decimal("0"),
                "average_price": Decimal("0"),
                "error_message": "No quote available",
            }

        if order.order_type == OrderType.MARKET:
            if order.side == OrderSide.BUY:
                fill_price = quote.ask * (Decimal("1") + self.config.fee_rate)
                available_qty = quote.ask_size
            else:
                fill_price = quote.bid * (Decimal("1") - self.config.fee_rate)
                available_qty = quote.bid_size

            fill_qty = min(order.quantity, available_qty)
            status = OrderStatus.FILLED if fill_qty >= order.quantity else OrderStatus.PARTIALLY_FILLED
        else:
            fill_price = order.price or Decimal("0")
            fill_qty = order.quantity
            status = OrderStatus.FILLED

        commission = fill_price * fill_qty * self.config.fee_rate

        self.orders[exchange_order_id] = {
            "order_id": order.id,
            "exchange_order_id": exchange_order_id,
            "symbol": order.symbol,
            "side": order.side,
            "order_type": order.order_type,
            "quantity": order.quantity,
            "price": order.price,
            "filled_quantity": fill_qty,
            "average_price": fill_price,
            "status": status,
            "commission": commission,
            "timestamp": datetime.now(),
        }

        return {
            "order_id": order.id,
            "exchange_order_id": exchange_order_id,
            "status": status,
            "filled_quantity": fill_qty,
            "average_price": fill_price,
            "commission": commission,
        }

    async def cancel_order(self, order_id: str) -> bool:
        if order_id in self.orders:
            order = self.orders[order_id]
            if order["status"] in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED):
                order["status"] = OrderStatus.CANCELLED
                return True
        return False

    async def get_order_status(self, order_id: str) -> dict | None:
        return self.orders.get(order_id)


class SmartOrderRouter:
    def __init__(self, config: SmartOrderRouterConfig | None = None):
        self.config = config or SmartOrderRouterConfig()
        self.venues: dict[str, VenueConnector] = {}
        self.venue_configs: dict[str, VenueConfig] = {}
        self.quotes: dict[str, VenueQuote] = {}
        self._lock = asyncio.Lock()
        self._order_manager: OrderManager | None = None

        for _name, venue_config in self.config.venue_configs.items():
            self.add_venue(venue_config)

    def set_order_manager(self, oms: OrderManager) -> None:
        self._order_manager = oms

    def add_venue(self, config: VenueConfig) -> None:
        self.venue_configs[config.name] = config
        connector = SimulatedVenueConnector(config)
        connector.add_quote_callback(self._on_quote_update)
        self.venues[config.name] = connector

    def _on_quote_update(self, quote: VenueQuote) -> None:
        self.quotes[f"{quote.venue}:{quote.symbol}"] = quote

    async def connect_all(self) -> dict[str, bool]:
        results = {}
        for name, venue in self.venues.items():
            results[name] = await venue.connect()
        return results

    async def disconnect_all(self) -> dict[str, bool]:
        results = {}
        for name, venue in self.venues.items():
            results[name] = await venue.disconnect()
        return results

    def update_venue_quote(self, venue: str, symbol: str, bid: Decimal, ask: Decimal, bid_size: Decimal, ask_size: Decimal) -> None:
        quote = VenueQuote(
            venue=venue,
            symbol=symbol,
            bid=bid,
            ask=ask,
            bid_size=bid_size,
            ask_size=ask_size,
            timestamp=datetime.now(),
        )
        self.quotes[f"{venue}:{symbol}"] = quote

    def get_best_quote(self, symbol: str, side: OrderSide) -> VenueQuote | None:
        relevant_quotes = [
            q for k, q in self.quotes.items()
            if k.endswith(f":{symbol}") and self.venue_configs.get(q.venue, VenueConfig(name="")).enabled
        ]
        if not relevant_quotes:
            return None

        if side == OrderSide.BUY:
            return min(relevant_quotes, key=lambda q: q.ask)
        else:
            return max(relevant_quotes, key=lambda q: q.bid)

    def get_all_quotes(self, symbol: str) -> list[VenueQuote]:
        return [
            q for k, q in self.quotes.items()
            if k.endswith(f":{symbol}") and self.venue_configs.get(q.venue, VenueConfig(name="")).enabled
        ]

    def calculate_routing(
        self,
        order: Order,
        strategy: RoutingStrategy | None = None,
    ) -> list[RoutingDecision]:
        strategy = strategy or self.config.default_strategy
        quotes = self.get_all_quotes(order.symbol)

        if not quotes:
            return []

        enabled_venues = [v for v in self.venue_configs.values() if v.enabled]
        venue_quotes = {q.venue: q for q in quotes if q.venue in [v.name for v in enabled_venues]}

        if not venue_quotes:
            return []

        decisions = []

        if strategy == RoutingStrategy.BEST_PRICE:
            decisions = self._route_best_price(order, venue_quotes)
        elif strategy == RoutingStrategy.PRO_RATA:
            decisions = self._route_pro_rata(order, venue_quotes)
        elif strategy == RoutingStrategy.WEIGHTED:
            decisions = self._route_weighted(order, venue_quotes)
        elif strategy == RoutingStrategy.SMART:
            decisions = self._route_smart(order, venue_quotes)

        return decisions[: self.config.max_venues_per_order]

    def _route_best_price(self, order: Order, venue_quotes: dict[str, VenueQuote]) -> list[RoutingDecision]:
        if order.side == OrderSide.BUY:
            best_venue = min(venue_quotes.keys(), key=lambda v: venue_quotes[v].ask)
            best_quote = venue_quotes[best_venue]
            price = best_quote.ask if order.order_type == OrderType.MARKET else order.price
        else:
            best_venue = max(venue_quotes.keys(), key=lambda v: venue_quotes[v].bid)
            best_quote = venue_quotes[best_venue]
            price = best_quote.bid if order.order_type == OrderType.MARKET else order.price

        return [RoutingDecision(
            venue=best_venue,
            quantity=order.quantity,
            price=price,
            order_type=order.order_type,
            reasoning="Best price across venues",
        )]

    def _route_pro_rata(self, order: Order, venue_quotes: dict[str, VenueQuote]) -> list[RoutingDecision]:
        total_liquidity = Decimal("0")
        for quote in venue_quotes.values():
            if order.side == OrderSide.BUY:
                total_liquidity += quote.ask_size
            else:
                total_liquidity += quote.bid_size

        if total_liquidity == 0:
            return []

        decisions = []
        for venue, quote in venue_quotes.items():
            venue_liquidity = quote.ask_size if order.side == OrderSide.BUY else quote.bid_size

            if venue_liquidity == 0:
                continue

            allocation = order.quantity * (venue_liquidity / total_liquidity)
            price = quote.ask if order.side == OrderSide.BUY else quote.bid
            if order.order_type == OrderType.LIMIT and order.price:
                price = order.price

            decisions.append(RoutingDecision(
                venue=venue,
                quantity=allocation,
                price=price,
                order_type=order.order_type,
                reasoning=f"Pro-rata allocation based on liquidity ({venue_liquidity/total_liquidity*100:.1f}%)",
            ))

        return decisions

    def _route_weighted(self, order: Order, venue_quotes: dict[str, VenueQuote]) -> list[RoutingDecision]:
        weights = {}
        total_weight = Decimal("0")

        for venue, quote in venue_quotes.items():
            config = self.venue_configs.get(venue, VenueConfig(name=""))
            if order.side == OrderSide.BUY:
                liquidity_score = quote.ask_size
                price_score = Decimal("1") / quote.ask if quote.ask > 0 else Decimal("0")
            else:
                liquidity_score = quote.bid_size
                price_score = quote.bid

            fee_penalty = Decimal("1") - config.fee_rate
            priority_weight = Decimal("1") / Decimal(str(config.priority))

            weight = liquidity_score * price_score * fee_penalty * priority_weight
            weights[venue] = weight
            total_weight += weight

        if total_weight == 0:
            return []

        decisions = []
        for venue, weight in weights.items():
            quote = venue_quotes[venue]
            allocation = order.quantity * (weight / total_weight)
            price = quote.ask if order.side == OrderSide.BUY else quote.bid
            if order.order_type == OrderType.LIMIT and order.price:
                price = order.price

            decisions.append(RoutingDecision(
                venue=venue,
                quantity=allocation,
                price=price,
                order_type=order.order_type,
                reasoning=f"Weighted allocation (weight: {weight/total_weight*100:.1f}%)",
            ))

        return decisions

    def _route_smart(self, order: Order, venue_quotes: dict[str, VenueQuote]) -> list[RoutingDecision]:
        best_quote = self.get_best_quote(order.symbol, order.side)
        if not best_quote:
            return []

        primary_venue = best_quote.venue
        decisions = []

        remaining_qty = order.quantity
        for venue, quote in venue_quotes.items():
            if remaining_qty <= 0:
                break

            config = self.venue_configs.get(venue, VenueConfig(name=""))

            if order.side == OrderSide.BUY:
                available = quote.ask_size
                venue_price = quote.ask
            else:
                available = quote.bid_size
                venue_price = quote.bid

            if order.order_type == OrderType.LIMIT and order.price:
                venue_price = order.price

            max_fill = min(remaining_qty, available, config.max_order_size)
            if max_fill < config.min_order_size:
                continue

            if venue == primary_venue:
                fill_qty = max_fill
            else:
                price_diff = abs(venue_price - (best_quote.ask if order.side == OrderSide.BUY else best_quote.bid))
                price_diff_bps = (price_diff / best_quote.mid_price) * Decimal("10000")
                if price_diff_bps > self.config.price_improvement_threshold_bps:
                    continue
                fill_qty = min(max_fill, remaining_qty * Decimal("0.3"))

            if fill_qty > 0:
                decisions.append(RoutingDecision(
                    venue=venue,
                    quantity=fill_qty,
                    price=venue_price,
                    order_type=order.order_type,
                    reasoning="Smart routing: primary venue gets priority, secondary venues for price improvement",
                    metadata={
                        "is_primary": venue == primary_venue,
                        "price_diff_bps": float(price_diff_bps) if venue != primary_venue else 0,
                    },
                ))
                remaining_qty -= fill_qty

        return decisions

    async def route_order(
        self,
        order: Order,
        strategy: RoutingStrategy | None = None,
    ) -> list[dict]:
        decisions = self.calculate_routing(order, strategy)
        results = []

        for decision in decisions:
            venue = self.venues.get(decision.venue)
            if not venue or not venue.is_connected():
                results.append({
                    "venue": decision.venue,
                    "status": OrderStatus.REJECTED,
                    "error_message": "Venue not connected",
                })
                continue

            venue_order = Order(
                id=order.id,
                symbol=order.symbol,
                side=order.side,
                order_type=decision.order_type,
                quantity=decision.quantity,
                price=decision.price,
                stop_price=order.stop_price,
            )

            try:
                result = await venue.submit_order(venue_order)
                result["venue"] = decision.venue
                result["routing_decision"] = {
                    "quantity": str(decision.quantity),
                    "price": str(decision.price) if decision.price else None,
                    "reasoning": decision.reasoning,
                }
                results.append(result)

                if self._order_manager:
                    await self._order_manager.submit_order(order.id, result.get("exchange_order_id"))
                    if result["status"] == OrderStatus.FILLED or result["status"] == OrderStatus.PARTIALLY_FILLED:
                        await self._order_manager.update_fill(
                            order.id,
                            result["filled_quantity"],
                            result["average_price"],
                            result.get("commission", Decimal("0")),
                        )

            except Exception as e:
                logger.error(f"Error routing to {decision.venue}: {e}")
                results.append({
                    "venue": decision.venue,
                    "status": OrderStatus.REJECTED,
                    "error_message": str(e),
                })

        return results

    async def cancel_order(self, order_id: str, venue: str | None = None) -> bool:
        if venue:
            connector = self.venues.get(venue)
            if connector:
                return await connector.cancel_order(order_id)
            return False

        for connector in self.venues.values():
            if await connector.cancel_order(order_id):
                return True
        return False

    def get_venue_status(self) -> dict[str, dict]:
        return {
            name: {
                "connected": venue.is_connected(),
                "config": {
                    "name": config.name,
                    "type": config.venue_type.value,
                    "enabled": config.enabled,
                    "priority": config.priority,
                    "fee_rate": str(config.fee_rate),
                },
            }
            for name, config in self.venue_configs.items()
            if (venue := self.venues.get(name))
        }
