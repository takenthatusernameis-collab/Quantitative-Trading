"""Portfolio and holding data structures.

Examples:
    Create a portfolio, add a holding, and inspect its value::

        from quant_trading.portfolio.portfolio import Portfolio

        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 150.0)
        portfolio.update_prices({"AAPL": 160.0})
        assert portfolio.get_position_value("AAPL") == 16000.0
        assert portfolio.get_position_pct("AAPL") > 0.0

    Reset the portfolio to a fresh cash balance::

        portfolio.reset(200000.0)
        assert portfolio.cash == 200000.0
        assert len(portfolio.holdings) == 0

    Produce a serializable summary of portfolio state::

        summary = portfolio.summary()
        assert summary["num_positions"] == 0
        assert summary["pnl"] == 0.0

"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from quant_trading.strategies.base import Position


@dataclass
class Holding:
    """Represents a holding in the portfolio.

    Attributes:
        symbol: Ticker symbol of the held asset.
        quantity: Number of units held (positive for long, negative for short).
        avg_cost: Average cost basis per unit.
        current_price: Latest market price per unit.
        market_value: Current market value (quantity * current_price).

    Examples:
        Create a holding and inspect its unrealized PnL::

            from quant_trading.portfolio.portfolio import Holding

            holding = Holding(
                symbol="AAPL", quantity=100, avg_cost=100.0, current_price=150.0
            )
            assert holding.unrealized_pnl == 5000.0
            assert holding.unrealized_pnl_pct == 0.5

    """

    symbol: str
    quantity: float = 0.0
    avg_cost: float = 0.0
    current_price: float = 0.0
    market_value: float = 0.0

    def __post_init__(self) -> None:
        """Derive market value from quantity and current price when initialized."""
        if self.quantity > 0 and self.avg_cost > 0:
            self.market_value = self.quantity * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        """Unrealized profit and loss for this holding."""
        if self.quantity == 0 or self.avg_cost == 0:
            return 0.0
        return self.quantity * (self.current_price - self.avg_cost)

    @property
    def unrealized_pnl_pct(self) -> float:
        """Unrealized profit and loss as a percentage of average cost."""
        if self.avg_cost == 0:
            return 0.0
        return (self.current_price - self.avg_cost) / self.avg_cost

    def update_price(self, price: float) -> None:
        """Update current price and recalculate market value.

        Args:
            price: New current price per unit.

        """
        self.current_price = price
        self.market_value = self.quantity * price

    def to_position(self) -> Position:
        """Convert to a Position object.

        Returns:
            Position mirroring this holding's symbol, quantity, prices, and PnL.

        """
        return Position(
            symbol=self.symbol,
            quantity=self.quantity,
            avg_price=self.avg_cost,
            current_price=self.current_price,
            unrealized_pnl=self.unrealized_pnl,
        )


@dataclass
class Portfolio:
    """Portfolio state and operations.

    Attributes:
        cash: Available cash balance.
        holdings: Symbol-keyed dictionary of Holding objects.
        total_value: Total portfolio value (cash plus holdings market value).
        initial_capital: Starting capital used as the PnL reference.
        last_rebalance: Timestamp of the last rebalance, if any.

    Examples:
        Create a portfolio and track a position through a price update::

            from quant_trading.portfolio.portfolio import Portfolio

            portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
            portfolio.add_holding("AAPL", 100, 100.0)
            portfolio.update_prices({"AAPL": 120.0})
            assert portfolio.holdings["AAPL"].market_value == 12000.0
            assert portfolio.summary()["num_positions"] == 1

    """

    cash: float = 0.0
    holdings: dict[str, Holding] = field(default_factory=dict)
    total_value: float = 0.0
    initial_capital: float = 0.0
    last_rebalance: datetime | None = None

    def __post_init__(self) -> None:
        """Derive initial capital and total value when not explicitly provided."""
        if self.initial_capital == 0 and self.cash == 0:
            self.initial_capital = 0.0
        elif self.initial_capital == 0 and self.cash > 0:
            self.initial_capital = self.cash
        if self.total_value == 0:
            self.total_value = self.cash + self.get_holdings_value()

    def get_holdings_value(self) -> float:
        """Calculate total value of all holdings.

        Returns:
            Sum of market values across every holding in the portfolio.

        """
        return sum(h.market_value for h in self.holdings.values())

    def get_position_value(self, symbol: str) -> float:
        """Get market value of a specific holding.

        Args:
            symbol: Symbol of the holding to look up.

        Returns:
            Market value of the holding, or 0.0 when the symbol is absent.

        """
        holding = self.holdings.get(symbol)
        return holding.market_value if holding else 0.0

    def get_position_pct(self, symbol: str) -> float:
        """Get position as percentage of portfolio.

        Args:
            symbol: Symbol of the holding to evaluate.

        Returns:
            Position market value divided by total portfolio value, or 0.0
            when total value is non-positive.

        """
        if self.total_value <= 0:
            return 0.0
        return self.get_position_value(symbol) / self.total_value

    def add_holding(
        self,
        symbol: str,
        quantity: float,
        price: float,
        commission: float = 0.0,
        slippage: float = 0.0,
    ) -> None:
        """Add or update a holding.

        Args:
            symbol: Symbol of the holding to add or increase.
            quantity: Quantity to add (use a negative quantity to reduce).
            price: Execution price per unit.
            commission: Commission rate applied to the trade.
            slippage: Slippage rate applied to the trade.

        Entry fees (commission + slippage) are capitalized into the average
        cost basis of long positions: a new long position is costed at
        ``price * (1 + commission + slippage)``, and lots added to an existing
        long are averaged at their fee-inclusive cost. Reductions of a long
        leave the remaining basis untouched. Short positions keep the execution
        price as their basis.

        Returns:
            None.

        """
        cost = quantity * price

        if symbol in self.holdings and self.holdings[symbol].quantity > 0 and quantity > 0:
            holding = self.holdings[symbol]
            total_qty = holding.quantity + quantity
            if total_qty != 0:
                new_avg_cost = (
                    holding.avg_cost * holding.quantity
                    + price * (1 + commission + slippage) * quantity
                ) / total_qty
            else:  # pragma: no cover  (both quantities are positive, so total_qty is never 0)
                new_avg_cost = 0.0
            holding.quantity = total_qty
            holding.avg_cost = new_avg_cost
            holding.update_price(price)
            self.cash -= cost * (1 + commission + slippage)
        elif symbol in self.holdings and self.holdings[symbol].quantity > 0 and quantity < 0:
            holding = self.holdings[symbol]
            total_qty = holding.quantity + quantity
            if total_qty <= 0:
                del self.holdings[symbol]
            else:
                holding.quantity = total_qty
                holding.avg_cost = holding.avg_cost
                holding.update_price(price)
            self.cash += abs(cost) * (1 - commission - slippage)
        else:
            entry_price = price * (1 + commission + slippage) if quantity > 0 else price
            self.holdings[symbol] = Holding(
                symbol=symbol,
                quantity=quantity,
                avg_cost=entry_price,
                current_price=price,
                market_value=quantity * price,
            )
            if quantity > 0:
                self.cash -= cost * (1 + commission + slippage)
            else:
                self.cash += abs(cost) * (1 - commission - slippage)
        self.total_value = self.cash + self.get_holdings_value()

    def remove_holding(
        self,
        symbol: str,
        quantity: float,
        price: float,
        commission: float = 0.0,
        slippage: float = 0.0,
    ) -> float:
        """Remove from a holding. Returns proceeds.

        Args:
            symbol: Symbol of the holding to reduce.
            quantity: Quantity to remove (capped at the current holding size).
            price: Execution price per unit.
            commission: Commission rate applied to the trade.
            slippage: Slippage rate applied to the trade.

        Returns:
            Proceeds from the sale (actual quantity removed times price), or
            0.0 when the symbol is not held.

        """
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

        self.cash += proceeds * (1 - commission - slippage)
        self.total_value = self.cash + self.get_holdings_value()
        return proceeds * (1 - commission - slippage)

    def update_prices(self, prices: dict[str, float]) -> None:
        """Update prices for all holdings.

        Args:
            prices: Symbol-keyed map of new market prices. Unknown symbols
                are ignored.

        Returns:
            None.

        """
        for symbol, price in prices.items():
            if symbol in self.holdings:
                self.holdings[symbol].update_price(price)
        self.total_value = self.cash + self.get_holdings_value()

    def get_positions(self) -> dict[str, Position]:
        """Get all positions as Position objects.

        Returns:
            Symbol-keyed Position objects for every current holding.

        """
        return {sym: h.to_position() for sym, h in self.holdings.items()}

    def get_allocation(self) -> dict[str, float]:
        """Get portfolio allocation percentages.

        Returns:
            Symbol-keyed market-value fractions of total portfolio value, or
            an empty dictionary when total value is non-positive.

        """
        if self.total_value <= 0:
            return {}
        return {sym: h.market_value / self.total_value for sym, h in self.holdings.items()}

    def reset(self, capital: float) -> None:
        """Reset portfolio to initial state.

        Args:
            capital: New cash balance, also set as initial capital and total
                value.

        Returns:
            None.

        """
        self.cash = capital
        self.holdings = {}
        self.total_value = capital
        self.initial_capital = capital
        self.last_rebalance = None

    def summary(self) -> dict[str, Any]:
        """Get portfolio summary.

        Returns:
            Dictionary with total_value, cash, holdings_value, num_positions,
            allocation, pnl, and pnl_pct keys.

        """
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
