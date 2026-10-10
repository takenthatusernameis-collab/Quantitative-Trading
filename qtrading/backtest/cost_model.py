from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from qtrading.strategy import Order, OrderSide


class CostModelType(StrEnum):
    FIXED = "fixed"
    PERCENTAGE = "percentage"
    TIERED = "tiered"
    DYNAMIC = "dynamic"


@dataclass
class TieredCost:
    threshold: Decimal
    rate: Decimal


@dataclass
class TransactionCostConfig:
    model_type: CostModelType = CostModelType.PERCENTAGE
    commission_rate: Decimal = Decimal("0.001")
    min_commission: Decimal = Decimal("0")
    slippage_rate: Decimal = Decimal("0.0005")
    latency_seconds: float = 0.0
    partial_fill_probability: float = 0.0
    tiered_rates: list[TieredCost] = field(default_factory=list)


@dataclass
class TransactionCost:
    order: Order
    fill_price: Decimal
    filled_quantity: Decimal
    commission: Decimal
    slippage: Decimal
    latency_cost: Decimal
    total_cost: Decimal
    is_partial_fill: bool = False


class TransactionCostModel:
    """Models transaction costs including commission, slippage, latency, and partial fills."""

    def __init__(self, config: TransactionCostConfig | None = None):
        self.config = config or TransactionCostConfig()

    def calculate_commission(
        self,
        fill_price: Decimal,
        quantity: Decimal,
    ) -> Decimal:
        if self.config.model_type == CostModelType.FIXED:
            return self.config.commission_rate

        if self.config.model_type == CostModelType.TIERED and self.config.tiered_rates:
            trade_value = fill_price * quantity
            rate = self.config.commission_rate
            for tier in self.config.tiered_rates:
                if trade_value >= tier.threshold:
                    rate = tier.rate
            commission = trade_value * rate
        else:
            commission = fill_price * quantity * self.config.commission_rate

        return max(commission, self.config.min_commission)

    def calculate_slippage(
        self,
        fill_price: Decimal,
        quantity: Decimal,
        side: OrderSide,
        volatility: Decimal | None = None,
    ) -> Decimal:
        slippage_rate = self.config.slippage_rate

        if volatility is not None and volatility > 0:
            dynamic_rate = slippage_rate * (Decimal("1") + volatility)
            slippage_rate = min(dynamic_rate, Decimal("0.1"))

        return fill_price * quantity * slippage_rate

    def calculate_latency_cost(
        self,
        fill_price: Decimal,
        quantity: Decimal,
    ) -> Decimal:
        if self.config.latency_seconds <= 0:
            return Decimal("0")
        latency_hours = Decimal(str(self.config.latency_seconds / 3600))
        return fill_price * quantity * Decimal("0.0001") * latency_hours

    def calculate_costs(
        self,
        order: Order,
        fill_price: Decimal,
        filled_quantity: Decimal | None = None,
        volatility: Decimal | None = None,
    ) -> TransactionCost:
        quantity = filled_quantity if filled_quantity is not None else order.quantity
        is_partial = filled_quantity is not None and filled_quantity < order.quantity

        commission = self.calculate_commission(fill_price, quantity)
        slippage = self.calculate_slippage(fill_price, quantity, order.side, volatility)
        latency_cost = self.calculate_latency_cost(fill_price, quantity)
        total_cost = commission + slippage + latency_cost

        return TransactionCost(
            order=order,
            fill_price=fill_price,
            filled_quantity=quantity,
            commission=commission,
            slippage=slippage,
            latency_cost=latency_cost,
            total_cost=total_cost,
            is_partial_fill=is_partial,
        )

    def apply_partial_fill(
        self,
        order: Order,
        fill_price: Decimal,
        fill_ratio: Decimal,
    ) -> TransactionCost:
        """Apply a partial fill ratio to an order."""
        filled_quantity = order.quantity * fill_ratio
        return self.calculate_costs(order, fill_price, filled_quantity)

    def should_partial_fill(self) -> bool:
        import random

        if self.config.partial_fill_probability <= 0:
            return False
        return random.random() < self.config.partial_fill_probability


class CostAggregator:
    """Aggregates transaction costs across multiple orders."""

    def __init__(self):
        self.total_commission = Decimal("0")
        self.total_slippage = Decimal("0")
        self.total_latency_cost = Decimal("0")
        self.total_cost = Decimal("0")
        self.order_count = 0
        self.partial_fill_count = 0

    def add_cost(self, cost: TransactionCost) -> None:
        self.total_commission += cost.commission
        self.total_slippage += cost.slippage
        self.total_latency_cost += cost.latency_cost
        self.total_cost += cost.total_cost
        self.order_count += 1
        if cost.is_partial_fill:
            self.partial_fill_count += 1

    def get_summary(self) -> dict:
        return {
            "total_commission": self.total_commission,
            "total_slippage": self.total_slippage,
            "total_latency_cost": self.total_latency_cost,
            "total_cost": self.total_cost,
            "order_count": self.order_count,
            "partial_fill_count": self.partial_fill_count,
            "avg_cost_per_order": self.total_cost / self.order_count
            if self.order_count > 0
            else Decimal("0"),
        }


def create_cost_model(config: TransactionCostConfig | None = None) -> TransactionCostModel:
    return TransactionCostModel(config)


def create_tiered_cost_model(
    commission_rate: Decimal = Decimal("0.001"),
    slippage_rate: Decimal = Decimal("0.0005"),
    tiers: list[tuple[Decimal, Decimal]] | None = None,
) -> TransactionCostModel:
    tiered_rates = [TieredCost(threshold=t[0], rate=t[1]) for t in (tiers or [])]
    config = TransactionCostConfig(
        model_type=CostModelType.TIERED,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        tiered_rates=tiered_rates,
    )
    return TransactionCostModel(config)
