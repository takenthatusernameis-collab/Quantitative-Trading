import asyncio
import contextlib
import random
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from loguru import logger

from qtrading.execution.oms import OrderManager
from qtrading.execution.smart_router import SmartOrderRouter
from qtrading.strategy import Order, OrderSide, OrderStatus, OrderType


class AlgorithmType(StrEnum):
    TWAP = "twap"
    VWAP = "vwap"
    POV = "pov"
    IMPLEMENTATION_SHORTFALL = "implementation_shortfall"


class AlgorithmState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class ExecutionAlgorithmConfig:
    algorithm_type: AlgorithmType
    symbol: str
    side: OrderSide
    total_quantity: Decimal
    start_time: datetime
    end_time: datetime
    limit_price: Decimal | None = None
    max_participation_rate: Decimal = Decimal("0.1")
    min_order_size: Decimal = Decimal("0.001")
    max_order_size: Decimal | None = None
    num_slices: int = 10
    randomize_sizes: bool = True
    randomize_timing: bool = True
    urgency: Decimal = Decimal("0.5")
    metadata: dict = field(default_factory=dict)


@dataclass
class AlgorithmSlice:
    slice_id: str
    quantity: Decimal
    scheduled_time: datetime
    limit_price: Decimal | None
    status: str = "pending"
    order_id: str | None = None
    filled_quantity: Decimal = Decimal("0")
    average_price: Decimal | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class AlgorithmStateSnapshot:
    algorithm_id: str
    state: AlgorithmState
    total_quantity: Decimal
    filled_quantity: Decimal
    remaining_quantity: Decimal
    average_price: Decimal | None
    slices_completed: int
    slices_total: int
    start_time: datetime
    end_time: datetime
    current_time: datetime
    participation_rate: Decimal
    metadata: dict = field(default_factory=dict)


class BaseExecutionAlgorithm(ABC):
    def __init__(
        self,
        config: ExecutionAlgorithmConfig,
        router: SmartOrderRouter,
        oms: OrderManager | None = None,
    ):
        self.config = config
        self.router = router
        self.oms = oms
        self.algorithm_id = f"algo_{config.algorithm_type.value}_{int(datetime.now().timestamp())}"
        self.state = AlgorithmState.PENDING
        self.slices: list[AlgorithmSlice] = []
        self.filled_quantity = Decimal("0")
        self.average_price: Decimal | None = None
        self.total_commission = Decimal("0")
        self.total_slippage = Decimal("0")
        self._running = False
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._callbacks: list = []

    def add_callback(self, callback: Callable[[AlgorithmStateSnapshot], None]) -> None:
        self._callbacks.append(callback)

    def _notify_state_change(self) -> None:
        snapshot = self.get_state_snapshot()
        for callback in self._callbacks:
            try:
                callback(snapshot)
            except Exception as e:
                logger.error(f"Algorithm callback error: {e}")

    @abstractmethod
    def generate_slices(self) -> list[AlgorithmSlice]:
        pass

    async def start(self) -> bool:
        async with self._lock:
            if self.state != AlgorithmState.PENDING:
                return False

            self.slices = self.generate_slices()
            self.state = AlgorithmState.RUNNING
            self._running = True
            self._notify_state_change()

            self._task = asyncio.create_task(self._run())
            logger.info(f"Started {self.config.algorithm_type.value} algorithm {self.algorithm_id}")
            return True

    async def pause(self) -> bool:
        async with self._lock:
            if self.state != AlgorithmState.RUNNING:
                return False
            self.state = AlgorithmState.PAUSED
            self._notify_state_change()
            return True

    async def resume(self) -> bool:
        async with self._lock:
            if self.state != AlgorithmState.PAUSED:
                return False
            self.state = AlgorithmState.RUNNING
            self._notify_state_change()
            return True

    async def cancel(self) -> bool:
        async with self._lock:
            if self.state in (AlgorithmState.COMPLETED, AlgorithmState.CANCELLED, AlgorithmState.ERROR):
                return False

            self.state = AlgorithmState.CANCELLED
            self._running = False

            for slice_ in self.slices:
                if slice_.status in ("pending", "submitted") and slice_.order_id:
                    await self.router.cancel_order(slice_.order_id)
                    slice_.status = "cancelled"

            if self._task:
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task

            self._notify_state_change()
            return True

    async def _run(self) -> None:
        try:
            await self._execute_slices()
            async with self._lock:
                if self.state == AlgorithmState.RUNNING:
                    self.state = AlgorithmState.COMPLETED
                    self._notify_state_change()
        except asyncio.CancelledError:
            async with self._lock:
                self.state = AlgorithmState.CANCELLED
                self._notify_state_change()
            raise
        except Exception as e:
            logger.error(f"Algorithm {self.algorithm_id} error: {e}")
            async with self._lock:
                self.state = AlgorithmState.ERROR
                self._notify_state_change()

    @abstractmethod
    async def _execute_slices(self) -> None:
        pass

    async def _execute_slice(self, slice_: AlgorithmSlice) -> None:
        slice_.status = "submitted"

        order = Order(
            id=slice_.slice_id,
            symbol=self.config.symbol,
            side=self.config.side,
            order_type=OrderType.LIMIT if slice_.limit_price else OrderType.MARKET,
            quantity=slice_.quantity,
            price=slice_.limit_price,
        )

        try:
            results = await self.router.route_order(order)
            if results:
                result = results[0]
                slice_.order_id = result.get("exchange_order_id")
                slice_.status = "filled" if result["status"] == OrderStatus.FILLED else "partial"
                slice_.filled_quantity = result["filled_quantity"]
                slice_.average_price = result["average_price"]

                self.filled_quantity += result["filled_quantity"]
                self.total_commission += result.get("commission", Decimal("0"))

                if self.average_price is None:
                    self.average_price = result["average_price"]
                elif result["filled_quantity"] > 0:
                    self.average_price = (
                        (self.average_price * (self.filled_quantity - result["filled_quantity"])) +
                        (result["average_price"] * result["filled_quantity"])
                    ) / self.filled_quantity

                if self.oms and slice_.order_id:
                    await self.oms.update_fill(
                        slice_.order_id,
                        result["filled_quantity"],
                        result["average_price"],
                        result.get("commission", Decimal("0")),
                    )

            self._notify_state_change()

        except Exception as e:
            logger.error(f"Error executing slice {slice_.slice_id}: {e}")
            slice_.status = "error"
            slice_.metadata["error"] = str(e)
            self._notify_state_change()

    def get_state_snapshot(self) -> AlgorithmStateSnapshot:
        completed = sum(1 for s in self.slices if s.status == "filled")
        return AlgorithmStateSnapshot(
            algorithm_id=self.algorithm_id,
            state=self.state,
            total_quantity=self.config.total_quantity,
            filled_quantity=self.filled_quantity,
            remaining_quantity=self.config.total_quantity - self.filled_quantity,
            average_price=self.average_price,
            slices_completed=completed,
            slices_total=len(self.slices),
            start_time=self.config.start_time,
            end_time=self.config.end_time,
            current_time=datetime.now(),
            participation_rate=self.filled_quantity / self.config.total_quantity if self.config.total_quantity > 0 else Decimal("0"),
        )

    def get_slice_status(self) -> list[dict]:
        return [
            {
                "slice_id": s.slice_id,
                "quantity": str(s.quantity),
                "scheduled_time": s.scheduled_time.isoformat(),
                "status": s.status,
                "order_id": s.order_id,
                "filled_quantity": str(s.filled_quantity),
                "average_price": str(s.average_price) if s.average_price else None,
            }
            for s in self.slices
        ]


class TWAPAlgorithm(BaseExecutionAlgorithm):
    def generate_slices(self) -> list[AlgorithmSlice]:
        duration = (self.config.end_time - self.config.start_time).total_seconds()
        if duration <= 0:
            return []

        slice_duration = duration / self.config.num_slices
        base_qty = self.config.total_quantity / Decimal(str(self.config.num_slices))
        slices = []

        for i in range(self.config.num_slices):
            scheduled = self.config.start_time + timedelta(seconds=i * slice_duration)
            if self.config.randomize_timing and i < self.config.num_slices - 1:
                jitter = random.uniform(-slice_duration * 0.1, slice_duration * 0.1)
                scheduled += timedelta(seconds=jitter)

            qty = base_qty
            if self.config.randomize_sizes:
                variation = Decimal(str(random.uniform(0.8, 1.2)))
                qty = (base_qty * variation).quantize(Decimal("0.00000001"))
                if qty < self.config.min_order_size:
                    qty = self.config.min_order_size

            slices.append(AlgorithmSlice(
                slice_id=f"{self.algorithm_id}_slice_{i}",
                quantity=qty,
                scheduled_time=scheduled,
                limit_price=self.config.limit_price,
            ))

        total = sum(s.quantity for s in slices)
        if total != self.config.total_quantity:
            diff = self.config.total_quantity - total
            slices[-1].quantity += diff

        return slices

    async def _execute_slices(self) -> None:
        for slice_ in self.slices:
            if not self._running:
                break

            now = datetime.now()
            if slice_.scheduled_time > now:
                wait_time = (slice_.scheduled_time - now).total_seconds()
                if wait_time > 0:
                    await asyncio.sleep(min(wait_time, 60))

            if not self._running:
                break

            await self._execute_slice(slice_)


class VWAPAlgorithm(BaseExecutionAlgorithm):
    def __init__(
        self,
        config: ExecutionAlgorithmConfig,
        router: SmartOrderRouter,
        oms: OrderManager | None = None,
        volume_profile: list[tuple[datetime, Decimal]] | None = None,
    ):
        super().__init__(config, router, oms)
        self.volume_profile = volume_profile or []

    def generate_slices(self) -> list[AlgorithmSlice]:
        if not self.volume_profile:
            return TWAPAlgorithm(self.config, self.router, self.oms).generate_slices()

        total_volume = sum(v for _, v in self.volume_profile)
        if total_volume == 0:
            return TWAPAlgorithm(self.config, self.router, self.oms).generate_slices()

        slices = []
        for i, (timestamp, volume) in enumerate(self.volume_profile):
            if timestamp < self.config.start_time or timestamp > self.config.end_time:
                continue

            participation = volume / total_volume
            qty = self.config.total_quantity * Decimal(str(participation))

            if qty < self.config.min_order_size:
                qty = self.config.min_order_size
            if self.config.max_order_size and qty > self.config.max_order_size:
                qty = self.config.max_order_size

            slices.append(AlgorithmSlice(
                slice_id=f"{self.algorithm_id}_slice_{i}",
                quantity=qty,
                scheduled_time=timestamp,
                limit_price=self.config.limit_price,
            ))

        total = sum(s.quantity for s in slices)
        if total != self.config.total_quantity and slices:
            diff = self.config.total_quantity - total
            slices[-1].quantity += diff

        return slices

    async def _execute_slices(self) -> None:
        for slice_ in self.slices:
            if not self._running:
                break

            now = datetime.now()
            if slice_.scheduled_time > now:
                wait_time = (slice_.scheduled_time - now).total_seconds()
                if wait_time > 0:
                    await asyncio.sleep(min(wait_time, 60))

            if not self._running:
                break

            await self._execute_slice(slice_)


class POVAlgorithm(BaseExecutionAlgorithm):
    def __init__(
        self,
        config: ExecutionAlgorithmConfig,
        router: SmartOrderRouter,
        oms: OrderManager | None = None,
        volume_feed: Any = None,
    ):
        super().__init__(config, router, oms)
        self.volume_feed = volume_feed
        self._last_volume = Decimal("0")
        self._interval = 60

    def generate_slices(self) -> list[AlgorithmSlice]:
        duration = (self.config.end_time - self.config.start_time).total_seconds()
        num_intervals = max(int(duration / self._interval), 1)
        base_qty = self.config.total_quantity / Decimal(str(num_intervals))
        slices = []

        for i in range(num_intervals):
            scheduled = self.config.start_time + timedelta(seconds=i * self._interval)
            qty = base_qty

            if self.config.randomize_sizes:
                variation = Decimal(str(random.uniform(0.8, 1.2)))
                qty = (base_qty * variation).quantize(Decimal("0.00000001"))
                if qty < self.config.min_order_size:
                    qty = self.config.min_order_size

            slices.append(AlgorithmSlice(
                slice_id=f"{self.algorithm_id}_slice_{i}",
                quantity=qty,
                scheduled_time=scheduled,
                limit_price=self.config.limit_price,
            ))

        total = sum(s.quantity for s in slices)
        if total != self.config.total_quantity and slices:
            diff = self.config.total_quantity - total
            slices[-1].quantity += diff

        return slices

    async def _execute_slices(self) -> None:
        for slice_ in self.slices:
            if not self._running:
                break

            now = datetime.now()
            if slice_.scheduled_time > now:
                wait_time = (slice_.scheduled_time - now).total_seconds()
                if wait_time > 0:
                    await asyncio.sleep(min(wait_time, self._interval))

            if not self._running:
                break

            await self._execute_pov_slice(slice_)

    async def _execute_pov_slice(self, slice_: AlgorithmSlice) -> None:
        if self.volume_feed:
            try:
                current_volume = await self.volume_feed.get_volume(self.config.symbol)
                if current_volume and current_volume > 0:
                    participation = min(self.config.max_participation_rate, slice_.quantity / current_volume)
                    adjusted_qty = current_volume * participation
                    slice_.quantity = min(adjusted_qty, slice_.quantity)
            except Exception as e:
                logger.warning(f"Volume feed error: {e}")

        if slice_.quantity < self.config.min_order_size:
            slice_.status = "skipped"
            self._notify_state_change()
            return

        await self._execute_slice(slice_)


class ImplementationShortfallAlgorithm(BaseExecutionAlgorithm):
    def __init__(
        self,
        config: ExecutionAlgorithmConfig,
        router: SmartOrderRouter,
        oms: OrderManager | None = None,
        risk_aversion: Decimal = Decimal("1.0"),
        volatility: Decimal = Decimal("0.02"),
    ):
        super().__init__(config, router, oms)
        self.risk_aversion = risk_aversion
        self.volatility = volatility

    def generate_slices(self) -> list[AlgorithmSlice]:
        duration = (self.config.end_time - self.config.start_time).total_seconds()
        if duration <= 0:
            return []

        tau = self.config.urgency
        optimal_slices = max(int(self.config.num_slices * float(tau)), 1)
        slice_duration = duration / optimal_slices

        self.risk_aversion * self.volatility * Decimal(str(duration / 86400))
        base_qty = self.config.total_quantity / Decimal(str(optimal_slices))

        front_load = float(self.config.urgency)
        slices = []

        for i in range(optimal_slices):
            scheduled = self.config.start_time + timedelta(seconds=i * slice_duration)
            if self.config.randomize_timing and i < optimal_slices - 1:
                jitter = random.uniform(-slice_duration * 0.05, slice_duration * 0.05)
                scheduled += timedelta(seconds=jitter)

            progress = i / optimal_slices
            urgency_factor = 1.0 - front_load * progress
            qty = base_qty * Decimal(str(urgency_factor))

            if qty < self.config.min_order_size:
                qty = self.config.min_order_size
            if self.config.max_order_size and qty > self.config.max_order_size:
                qty = self.config.max_order_size

            slices.append(AlgorithmSlice(
                slice_id=f"{self.algorithm_id}_slice_{i}",
                quantity=qty,
                scheduled_time=scheduled,
                limit_price=self.config.limit_price,
                metadata={"urgency_factor": urgency_factor},
            ))

        total = sum(s.quantity for s in slices)
        if total != self.config.total_quantity and slices:
            diff = self.config.total_quantity - total
            slices[-1].quantity += diff

        return slices

    async def _execute_slices(self) -> None:
        for slice_ in self.slices:
            if not self._running:
                break

            now = datetime.now()
            if slice_.scheduled_time > now:
                wait_time = (slice_.scheduled_time - now).total_seconds()
                if wait_time > 0:
                    await asyncio.sleep(min(wait_time, 60))

            if not self._running:
                break

            await self._execute_slice(slice_)


class AlgorithmFactory:
    @staticmethod
    def create(
        algorithm_type: AlgorithmType,
        config: ExecutionAlgorithmConfig,
        router: SmartOrderRouter,
        oms: OrderManager | None = None,
        **kwargs: Any,
    ) -> BaseExecutionAlgorithm:
        if algorithm_type == AlgorithmType.TWAP:
            return TWAPAlgorithm(config, router, oms)
        elif algorithm_type == AlgorithmType.VWAP:
            return VWAPAlgorithm(config, router, oms, kwargs.get("volume_profile"))
        elif algorithm_type == AlgorithmType.POV:
            return POVAlgorithm(config, router, oms, kwargs.get("volume_feed"))
        elif algorithm_type == AlgorithmType.IMPLEMENTATION_SHORTFALL:
            return ImplementationShortfallAlgorithm(
                config, router, oms,
                kwargs.get("risk_aversion", Decimal("1.0")),
                kwargs.get("volatility", Decimal("0.02")),
            )
        else:
            raise ValueError(f"Unknown algorithm type: {algorithm_type}")
