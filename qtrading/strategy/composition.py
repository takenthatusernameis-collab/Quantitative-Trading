from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from qtrading.strategy import Order, OrderSide, SignalType


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
        filled_quantity = order.quantity * fill_ratio
        return self.calculate_costs(order, fill_price, filled_quantity)

    def should_partial_fill(self) -> bool:
        import random

        if self.config.partial_fill_probability <= 0:
            return False
        return random.random() < self.config.partial_fill_probability


class MultiStrategy:
    """Combine multiple strategies into a single strategy with signal aggregation."""

    def __init__(self):
        self.strategies: list = []

    def add_strategy(self, strategy) -> "MultiStrategy":
        self.strategies.append(strategy)
        return self

    def generate_signals(self, data):

        if data.empty:
            return []

        combined_signals = []
        for strategy in self.strategies:
            try:
                signals = strategy.generate_signals(data)
                combined_signals.extend(signals)
            except Exception:
                continue
        return combined_signals

    def get_weight(self, symbol: str) -> float:
        return 1.0 / len(self.strategies) if self.strategies else 0.0


def combine_signals(
    signals,
    method: str = "majority",
):
    """Combine multiple signals using specified method."""
    if not signals:
        return None

    if method == "majority":
        buys = sum(1 for s in signals if s.signal == SignalType.BUY)
        sells = sum(1 for s in signals if s.signal == SignalType.SELL)
        if buys > sells and buys > 0:
            return signals[0]
        if sells > buys and sells > 0:
            return signals[0]
    elif method == "unanimous":
        if all(s.signal == signals[0].signal for s in signals):
            return signals[0]
    elif method == "weighted":
        return signals[0] if signals else None
    return signals[0] if signals else None
