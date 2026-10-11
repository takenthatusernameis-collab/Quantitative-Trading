"""Portfolio and holding data structures."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from quant_trading.strategies.base import Position


@dataclass
class Holding:
    """Represents a holding in the portfolio."""

    symbol: str
    quantity: float = 0.0
    avg_cost: float = 0.0
    current_price: float = 0.0
    market_value: float = 0.0

    def __post_init__(self):
        if self.quantity > 0 and self.avg_cost > 0:
            self.market_value = self.quantity * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        if self.quantity == 0 or self.avg_cost == 0:
            return 0.0
        return self.quantity * (self.current_price - self.avg_cost)

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.avg_cost == 0:
            return 0.0
        return (self.current_price - self.avg_cost) / self.avg_cost

    def update_price(self, price: float) -> None:
        """Update current price and recalculate market value."""
        self.current_price = price
        self.market_value = self.quantity * price

    def to_position(self) -> Position:
        """Convert to a Position object."""
        return Position(
            symbol=self.symbol,
            quantity=self.quantity,
            avg_price=self.avg_cost,
            current_price=self.current_price,
            unrealized_pnl=self.unrealized_pnl,
        )


@dataclass
class Portfolio:
    """Portfolio state and operations."""

    cash: float = 0.0
    holdings: dict[str, Holding] = field(default_factory=dict)
    total_value: float = 0.0
    initial_capital: float = 0.0
    last_rebalance: datetime | None = None

    def __post_init__(self):
        if self.initial_capital == 0 and self.cash == 0:
            self.initial_capital = 0.0
        elif self.initial_capital == 0 and self.cash > 0:
            self.initial_capital = self.cash
        if self.total_value == 0:
            self.total_value = self.cash + self.get_holdings_value()

    def get_holdings_value(self) -> float:
        """Calculate total value of all holdings."""
        return sum(h.market_value for h in self.holdings.values())

    def get_position_value(self, symbol: str) -> float:
        """Get market value of a specific holding."""
        holding = self.holdings.get(symbol)
        return holding.market_value if holding else 0.0

    def get_position_pct(self, symbol: str) -> float:
        """Get position as percentage of portfolio."""
        if self.total_value <= 0:
            return 0.0
        return self.get_position_value(symbol) / self.total_value

    def add_holding(self, symbol: str, quantity: float, price: float) -> None:
        """Add or update a holding."""
        cost = quantity * price

        if symbol in self.holdings and self.holdings[symbol].quantity > 0:
            holding = self.holdings[symbol]
            total_qty = holding.quantity + quantity
            if total_qty != 0:
                new_avg_cost = (holding.avg_cost * holding.quantity + cost) / total_qty
            else:
                new_avg_cost = 0.0
            holding.quantity = total_qty
            holding.avg_cost = new_avg_cost
            holding.update_price(price)
        else:
            self.holdings[symbol] = Holding(
                symbol=symbol,
                quantity=quantity,
                avg_cost=price,
                current_price=price,
                market_value=quantity * price,
            )

        self.cash -= cost
        self.total_value = self.cash + self.get_holdings_value()

    def remove_holding(self, symbol: str, quantity: float, price: float) -> float:
        """Remove from a holding. Returns proceeds."""
        if symbol not in self.holdings:
            return 0.0

        holding = self.holdings[symbol]
        actual_qty = min(quantity, holding.quantity)
        proceeds = actual_qty * price

        holding.quantity -= actual_qty
        if holding.quantity <= 0:
            del self.holdings[symbol]
        else:
            holding.update_price(price)

        self.cash += proceeds
        self.total_value = self.cash + self.get_holdings_value()
        return proceeds

    def update_prices(self, prices: dict[str, float]) -> None:
        """Update prices for all holdings."""
        for symbol, price in prices.items():
            if symbol in self.holdings:
                self.holdings[symbol].update_price(price)
        self.total_value = self.cash + self.get_holdings_value()

    def get_positions(self) -> dict[str, Position]:
        """Get all positions as Position objects."""
        return {sym: h.to_position() for sym, h in self.holdings.items()}

    def get_allocation(self) -> dict[str, float]:
        """Get portfolio allocation percentages."""
        if self.total_value <= 0:
            return {}
        return {sym: h.market_value / self.total_value for sym, h in self.holdings.items()}

    def reset(self, capital: float) -> None:
        """Reset portfolio to initial state."""
        self.cash = capital
        self.holdings = {}
        self.total_value = capital
        self.initial_capital = capital
        self.last_rebalance = None

    def summary(self) -> dict[str, Any]:
        """Get portfolio summary."""
        return {
            "total_value": self.total_value,
            "cash": self.cash,
            "holdings_value": self.get_holdings_value(),
            "num_positions": len(self.holdings),
            "allocation": self.get_allocation(),
            "pnl": self.total_value - self.initial_capital,
            "pnl_pct": (
                (self.total_value - self.initial_capital) / self.initial_capital
                if self.initial_capital > 0
                else 0
            ),
        }
