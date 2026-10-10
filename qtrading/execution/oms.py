import asyncio
import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Generator

from loguru import logger

from qtrading.strategy import OrderSide, OrderType


class OMSOrderState(StrEnum):
    CREATED = "created"
    VALIDATED = "validated"
    ROUTED = "routed"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    PARTIAL_FILL = "partial_fill"
    FILLED = "filled"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class OrderEvent:
    event_id: str
    order_id: str
    timestamp: datetime
    state: OMSOrderState
    previous_state: OMSOrderState | None
    data: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class OMSOrder:
    order_id: str
    client_order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Decimal | None
    stop_price: Decimal | None
    time_in_force: str = "GTC"
    state: OMSOrderState = OMSOrderState.CREATED
    filled_quantity: Decimal = Decimal("0")
    average_fill_price: Decimal | None = None
    commission: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    exchange: str | None = None
    exchange_order_id: str | None = None
    strategy_id: str | None = None
    parent_order_id: str | None = None
    metadata: dict = field(default_factory=dict)
    events: list[OrderEvent] = field(default_factory=list)

    def add_event(self, state: OMSOrderState, data: dict | None = None, metadata: dict | None = None) -> OrderEvent:
        event = OrderEvent(
            event_id=str(uuid.uuid4()),
            order_id=self.order_id,
            timestamp=datetime.now(),
            state=state,
            previous_state=self.state,
            data=data or {},
            metadata=metadata or {},
        )
        self.events.append(event)
        self.state = state
        self.updated_at = datetime.now()
        return event


class OrderManager:
    def __init__(self, db_path: str = "./data/oms.db"):
        self.db_path = db_path
        self.orders: dict[str, OMSOrder] = {}
        self._lock = asyncio.Lock()
        self._init_db()

    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS oms_orders (
                    order_id TEXT PRIMARY KEY,
                    client_order_id TEXT UNIQUE NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    quantity TEXT NOT NULL,
                    price TEXT,
                    stop_price TEXT,
                    time_in_force TEXT DEFAULT 'GTC',
                    state TEXT NOT NULL,
                    filled_quantity TEXT DEFAULT '0',
                    average_fill_price TEXT,
                    commission TEXT DEFAULT '0',
                    slippage TEXT DEFAULT '0',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    exchange TEXT,
                    exchange_order_id TEXT,
                    strategy_id TEXT,
                    parent_order_id TEXT,
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS oms_events (
                    event_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    state TEXT NOT NULL,
                    previous_state TEXT,
                    data TEXT,
                    metadata TEXT,
                    FOREIGN KEY (order_id) REFERENCES oms_orders(order_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_oms_orders_client_id ON oms_orders(client_order_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_oms_orders_symbol ON oms_orders(symbol)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_oms_orders_state ON oms_orders(state)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_oms_events_order_id ON oms_events(order_id)
            """)

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _order_to_row(self, order: OMSOrder) -> dict:
        return {
            "order_id": order.order_id,
            "client_order_id": order.client_order_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "quantity": str(order.quantity),
            "price": str(order.price) if order.price else None,
            "stop_price": str(order.stop_price) if order.stop_price else None,
            "time_in_force": order.time_in_force,
            "state": order.state.value,
            "filled_quantity": str(order.filled_quantity),
            "average_fill_price": str(order.average_fill_price) if order.average_fill_price else None,
            "commission": str(order.commission),
            "slippage": str(order.slippage),
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
            "exchange": order.exchange,
            "exchange_order_id": order.exchange_order_id,
            "strategy_id": order.strategy_id,
            "parent_order_id": order.parent_order_id,
            "metadata": json.dumps(order.metadata),
        }

    def _row_to_order(self, row: sqlite3.Row) -> OMSOrder:
        order = OMSOrder(
            order_id=row["order_id"],
            client_order_id=row["client_order_id"],
            symbol=row["symbol"],
            side=OrderSide(row["side"]),
            order_type=OrderType(row["order_type"]),
            quantity=Decimal(row["quantity"]),
            price=Decimal(row["price"]) if row["price"] else None,
            stop_price=Decimal(row["stop_price"]) if row["stop_price"] else None,
            time_in_force=row["time_in_force"],
            state=OMSOrderState(row["state"]),
            filled_quantity=Decimal(row["filled_quantity"]),
            average_fill_price=Decimal(row["average_fill_price"]) if row["average_fill_price"] else None,
            commission=Decimal(row["commission"]),
            slippage=Decimal(row["slippage"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            exchange=row["exchange"],
            exchange_order_id=row["exchange_order_id"],
            strategy_id=row["strategy_id"],
            parent_order_id=row["parent_order_id"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
        return order

    async def create_order(
        self,
        client_order_id: str,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: Decimal,
        price: Decimal | None = None,
        stop_price: Decimal | None = None,
        time_in_force: str = "GTC",
        exchange: str | None = None,
        strategy_id: str | None = None,
        parent_order_id: str | None = None,
        metadata: dict | None = None,
    ) -> OMSOrder:
        async with self._lock:
            order_id = str(uuid.uuid4())
            order = OMSOrder(
                order_id=order_id,
                client_order_id=client_order_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                stop_price=stop_price,
                time_in_force=time_in_force,
                exchange=exchange,
                strategy_id=strategy_id,
                parent_order_id=parent_order_id,
                metadata=metadata or {},
            )
            order.add_event(OMSOrderState.CREATED)

            self.orders[order_id] = order
            self._persist_order(order)

            logger.info(f"Created order {order_id} (client: {client_order_id})")
            return order

    def _persist_order(self, order: OMSOrder) -> None:
        with self._get_connection() as conn:
            row = self._order_to_row(order)
            conn.execute("""
                INSERT OR REPLACE INTO oms_orders VALUES (
                    :order_id, :client_order_id, :symbol, :side, :order_type,
                    :quantity, :price, :stop_price, :time_in_force, :state,
                    :filled_quantity, :average_fill_price, :commission, :slippage,
                    :created_at, :updated_at, :exchange, :exchange_order_id,
                    :strategy_id, :parent_order_id, :metadata
                )
            """, row)

            for event in order.events:
                conn.execute("""
                    INSERT OR IGNORE INTO oms_events VALUES (
                        :event_id, :order_id, :timestamp, :state, :previous_state, :data, :metadata
                    )
                """, {
                    "event_id": event.event_id,
                    "order_id": event.order_id,
                    "timestamp": event.timestamp.isoformat(),
                    "state": event.state.value,
                    "previous_state": event.previous_state.value if event.previous_state else None,
                    "data": json.dumps(event.data),
                    "metadata": json.dumps(event.metadata),
                })

    async def validate_order(self, order_id: str) -> bool:
        async with self._lock:
            order = self.orders.get(order_id)
            if not order:
                return False

            if order.state != OMSOrderState.CREATED:
                order.add_event(OMSOrderState.REJECTED, {"reason": "Invalid state for validation"})
                self._persist_order(order)
                return False

            if order.quantity <= 0:
                order.add_event(OMSOrderState.REJECTED, {"reason": "Invalid quantity"})
                self._persist_order(order)
                return False

            if order.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT) and order.price is None:
                order.add_event(OMSOrderState.REJECTED, {"reason": "Price required for limit order"})
                self._persist_order(order)
                return False

            order.add_event(OMSOrderState.VALIDATED)
            self._persist_order(order)
            return True

    async def route_order(self, order_id: str, exchange: str) -> bool:
        async with self._lock:
            order = self.orders.get(order_id)
            if not order:
                return False

            if order.state != OMSOrderState.VALIDATED:
                return False

            order.exchange = exchange
            order.add_event(OMSOrderState.ROUTED, {"exchange": exchange})
            self._persist_order(order)
            return True

    async def submit_order(self, order_id: str, exchange_order_id: str | None = None) -> bool:
        async with self._lock:
            order = self.orders.get(order_id)
            if not order:
                return False

            if order.state not in (OMSOrderState.VALIDATED, OMSOrderState.ROUTED):
                return False

            if exchange_order_id:
                order.exchange_order_id = exchange_order_id
            order.add_event(OMSOrderState.SUBMITTED, {"exchange_order_id": exchange_order_id})
            self._persist_order(order)
            return True

    async def acknowledge_order(self, order_id: str, exchange_order_id: str) -> bool:
        async with self._lock:
            order = self.orders.get(order_id)
            if not order:
                return False

            if order.state != OMSOrderState.SUBMITTED:
                return False

            order.exchange_order_id = exchange_order_id
            order.add_event(OMSOrderState.ACKNOWLEDGED, {"exchange_order_id": exchange_order_id})
            self._persist_order(order)
            return True

    async def update_fill(
        self,
        order_id: str,
        filled_quantity: Decimal,
        fill_price: Decimal,
        commission: Decimal = Decimal("0"),
        slippage: Decimal = Decimal("0"),
    ) -> bool:
        async with self._lock:
            order = self.orders.get(order_id)
            if not order:
                return False

            new_filled = order.filled_quantity + filled_quantity
            if new_filled > order.quantity:
                return False

            if order.filled_quantity == Decimal("0"):
                order.average_fill_price = fill_price
            else:
                avg_price = order.average_fill_price or Decimal("0")
                order.average_fill_price = (
                    (avg_price * order.filled_quantity) + (fill_price * filled_quantity)
                ) / new_filled

            order.filled_quantity = new_filled
            order.commission += commission
            order.slippage += slippage
            order.updated_at = datetime.now()

            if order.filled_quantity >= order.quantity:
                order.add_event(OMSOrderState.FILLED, {
                    "filled_quantity": str(filled_quantity),
                    "fill_price": str(fill_price),
                    "commission": str(commission),
                    "slippage": str(slippage),
                })
            else:
                order.add_event(OMSOrderState.PARTIAL_FILL, {
                    "filled_quantity": str(filled_quantity),
                    "fill_price": str(fill_price),
                    "commission": str(commission),
                    "slippage": str(slippage),
                })

            self._persist_order(order)
            return True

    async def request_cancel(self, order_id: str) -> bool:
        async with self._lock:
            order = self.orders.get(order_id)
            if not order:
                return False

            if order.state not in (OMSOrderState.SUBMITTED, OMSOrderState.ACKNOWLEDGED, OMSOrderState.PARTIAL_FILL):
                return False

            order.add_event(OMSOrderState.CANCEL_REQUESTED)
            self._persist_order(order)
            return True

    async def cancel_order(self, order_id: str) -> bool:
        async with self._lock:
            order = self.orders.get(order_id)
            if not order:
                return False

            if order.state not in (OMSOrderState.SUBMITTED, OMSOrderState.ACKNOWLEDGED, OMSOrderState.PARTIAL_FILL, OMSOrderState.CANCEL_REQUESTED):
                return False

            order.add_event(OMSOrderState.CANCELLED, {"filled_quantity": str(order.filled_quantity)})
            self._persist_order(order)
            return True

    async def reject_order(self, order_id: str, reason: str) -> bool:
        async with self._lock:
            order = self.orders.get(order_id)
            if not order:
                return False

            order.add_event(OMSOrderState.REJECTED, {"reason": reason})
            self._persist_order(order)
            return True

    async def expire_order(self, order_id: str) -> bool:
        async with self._lock:
            order = self.orders.get(order_id)
            if not order:
                return False

            if order.state in (OMSOrderState.FILLED, OMSOrderState.CANCELLED, OMSOrderState.REJECTED):
                return False

            order.add_event(OMSOrderState.EXPIRED)
            self._persist_order(order)
            return True

    async def get_order(self, order_id: str) -> OMSOrder | None:
        async with self._lock:
            return self.orders.get(order_id)

    async def get_order_by_client_id(self, client_order_id: str) -> OMSOrder | None:
        async with self._lock:
            for order in self.orders.values():
                if order.client_order_id == client_order_id:
                    return order
            return None

    async def get_orders_by_state(self, state: OMSOrderState) -> list[OMSOrder]:
        async with self._lock:
            return [o for o in self.orders.values() if o.state == state]

    async def get_orders_by_symbol(self, symbol: str) -> list[OMSOrder]:
        async with self._lock:
            return [o for o in self.orders.values() if o.symbol == symbol]

    async def get_open_orders(self, symbol: str | None = None) -> list[OMSOrder]:
        open_states = {OMSOrderState.SUBMITTED, OMSOrderState.ACKNOWLEDGED, OMSOrderState.PARTIAL_FILL}
        async with self._lock:
            orders = [o for o in self.orders.values() if o.state in open_states]
            if symbol:
                orders = [o for o in orders if o.symbol == symbol]
            return orders

    async def load_from_db(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM oms_orders")
            count = 0
            for row in cursor:
                order = self._row_to_order(row)
                cursor2 = conn.execute("SELECT * FROM oms_events WHERE order_id = ? ORDER BY timestamp", (order.order_id,))
                for event_row in cursor2:
                    event = OrderEvent(
                        event_id=event_row["event_id"],
                        order_id=event_row["order_id"],
                        timestamp=datetime.fromisoformat(event_row["timestamp"]),
                        state=OMSOrderState(event_row["state"]),
                        previous_state=OMSOrderState(event_row["previous_state"]) if event_row["previous_state"] else None,
                        data=json.loads(event_row["data"]) if event_row["data"] else {},
                        metadata=json.loads(event_row["metadata"]) if event_row["metadata"] else {},
                    )
                    order.events.append(event)
                self.orders[order.order_id] = order
                count += 1
            return count

    async def get_order_history(self, order_id: str) -> list[OrderEvent]:
        async with self._lock:
            order = self.orders.get(order_id)
            return order.events if order else []

    async def get_all_orders(self, limit: int = 100, offset: int = 0) -> list[OMSOrder]:
        async with self._lock:
            orders = list(self.orders.values())
            orders.sort(key=lambda o: o.created_at, reverse=True)
            return orders[offset:offset + limit]
