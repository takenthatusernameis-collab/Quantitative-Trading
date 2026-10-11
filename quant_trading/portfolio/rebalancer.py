"""Portfolio rebalancing logic."""

from dataclasses import dataclass, field
from datetime import datetime

from quant_trading.portfolio.portfolio import Portfolio
from quant_trading.strategies.base import Signal


@dataclass
class RebalanceAction:
    """Represents a rebalancing action."""

    symbol: str
    action: str  # 'buy', 'sell', 'hold'
    quantity: float = 0.0
    reason: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


class Rebalancer:
    """Manages portfolio rebalancing based on signals and targets."""

    def __init__(
        self,
        portfolio: Portfolio,
        frequency: str = "monthly",
        target_allocation: dict[str, float] | None = None,
        rebalance_threshold: float = 0.05,  # Rebalance if deviation > 5%
    ):
        self.portfolio = portfolio
        self.frequency = frequency
        self.target_allocation = target_allocation or {}
        self.rebalance_threshold = rebalance_threshold
        self.last_rebalance: datetime | None = None
        self.rebalance_history: list[dict] = []

    def should_rebalance(self) -> bool:
        """Check if it's time to rebalance."""
        now = datetime.now()
        if self.last_rebalance is None:
            return True

        if self.frequency == "daily":
            return now.date() > self.last_rebalance.date()
        elif self.frequency == "weekly":
            return (now - self.last_rebalance).days >= 7
        elif self.frequency == "monthly":
            return now.month != self.last_rebalance.month or now.year != self.last_rebalance.year
        elif self.frequency == "quarterly":
            return (now - self.last_rebalance).days >= 90
        else:
            return False

    def calculate_target_values(self) -> dict[str, float]:
        """Calculate target values based on target allocation."""
        total_value = self.portfolio.total_value
        targets = {}
        for symbol, pct in self.target_allocation.items():
            targets[symbol] = total_value * pct
        return targets

    def generate_rebalance_actions(
        self,
        signals: list[Signal] | None = None,
        prices: dict[str, float] | None = None,
    ) -> list[RebalanceAction]:
        """Generate rebalancing actions based on target allocation."""
        actions = []
        targets = self.calculate_target_values()
        prices = prices or {}

        # Process target allocations
        for symbol in self.target_allocation:
            current_value = self.portfolio.get_position_value(symbol)
            target_value = targets[symbol]
            diff = target_value - current_value

            if self.portfolio.total_value <= 0:
                continue
            if abs(diff) / self.portfolio.total_value > self.rebalance_threshold:
                if diff > 0:
                    quantity = self._resolve_buy_quantity(symbol, diff, signals, prices)
                    if quantity > 0:
                        actions.append(
                            RebalanceAction(
                                symbol=symbol,
                                action="buy",
                                quantity=quantity,
                                reason="target_allocation",
                            )
                        )
                elif diff < 0:
                    quantity = self._resolve_sell_quantity(symbol, abs(diff))
                    if quantity > 0:
                        actions.append(
                            RebalanceAction(
                                symbol=symbol,
                                action="sell",
                                quantity=quantity,
                                reason="target_allocation",
                            )
                        )

        # Process signals for additional buys/sells
        if signals:
            for signal in signals:
                if signal.action == "buy" and signal.symbol not in self.target_allocation:
                    # Buy based on signal strength
                    target_value = (
                        self.portfolio.total_value * 0.05 * signal.strength
                    )  # 5% max per signal
                    current_value = self.portfolio.get_position_value(signal.symbol)
                    diff = target_value - current_value
                    if diff > 0 and signal.price:
                        actions.append(
                            RebalanceAction(
                                symbol=signal.symbol,
                                action="buy",
                                quantity=diff / signal.price,
                                reason=f"signal_{signal.metadata.get('signal_type', 'unknown')}",
                            )
                        )
                elif signal.action == "sell":
                    holding = self.portfolio.holdings.get(signal.symbol)
                    if holding and holding.quantity > 0:
                        actions.append(
                            RebalanceAction(
                                symbol=signal.symbol,
                                action="sell",
                                quantity=holding.quantity,
                                reason=f"signal_{signal.metadata.get('signal_type', 'sell')}",
                            )
                        )

        self.last_rebalance = datetime.now()
        self.rebalance_history.append(
            {
                "timestamp": self.last_rebalance,
                "actions": [a.symbol for a in actions],
                "portfolio_value": self.portfolio.total_value,
            }
        )

        return actions

    def _resolve_buy_quantity(
        self,
        symbol: str,
        diff: float,
        signals: list[Signal] | None,
        prices: dict[str, float],
    ) -> float:
        """Resolve a buy quantity for a symbol, guarding against zero prices."""
        if symbol in self.portfolio.holdings:
            price = self.portfolio.holdings[symbol].current_price
            if price and price > 0:
                return diff / price
        if symbol in prices and prices[symbol] > 0:
            return diff / prices[symbol]
        if signals:
            signal_prices = [s.price for s in signals if s.symbol == symbol and s.price]
            if signal_prices:
                avg_price = sum(signal_prices) / len(signal_prices)
                if avg_price > 0:
                    return diff / avg_price
        return 0.0

    def _resolve_sell_quantity(self, symbol: str, diff: float) -> float:
        """Resolve a sell quantity for a symbol, guarding against zero prices."""
        if symbol in self.portfolio.holdings:
            price = self.portfolio.holdings[symbol].current_price
            if price and price > 0:
                return diff / price
        return 0.0

    def set_target_allocation(self, allocation: dict[str, float]) -> None:
        """Set target allocation."""
        total = sum(allocation.values())
        if abs(total - 1.0) > 0.01:
            # Normalize
            allocation = {k: v / total for k, v in allocation.items()}
        self.target_allocation = allocation

    def get_current_deviation(self) -> dict[str, float]:
        """Get current deviation from target allocation."""
        current = self.portfolio.get_allocation()
        deviations = {}
        for symbol, target_pct in self.target_allocation.items():
            current_pct = current.get(symbol, 0.0)
            deviations[symbol] = current_pct - target_pct
        return deviations

    def needs_rebalance(self) -> bool:
        """Check if portfolio needs rebalancing based on deviations."""
        if not self.target_allocation:
            return False
        deviations = self.get_current_deviation()
        for dev in deviations.values():
            if abs(dev) > self.rebalance_threshold:
                return True
        return False
