"""Portfolio and holding data structures.

>>> from quant_trading.portfolio.portfolio import Portfolio
>>> portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
>>> portfolio.add_holding("AAPL", 100, 150.0)
>>> portfolio.update_prices({"AAPL": 160.0})
>>> portfolio.get_position_value("AAPL")
16000.0
>>> portfolio.get_position_pct("AAPL") > 0.0
True

Reset the portfolio to a fresh cash balance::

>>> portfolio.reset(200000.0)
>>> portfolio.cash
200000.0
>>> len(portfolio.holdings)
0

Produce a serializable summary of portfolio state::

>>> summary = portfolio.summary()
>>> summary["num_positions"]
0
>>> summary["pnl"]
0.0

"""

from dataclasses import dataclass, field
from datetime import datetime
from math import copysign
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

            >>> from quant_trading.portfolio.portfolio import Holding
            >>> holding = Holding(
            ...     symbol="AAPL", quantity=100, avg_cost=100.0, current_price=150.0
            ... )
            >>> holding.unrealized_pnl
            5000.0
            >>> holding.unrealized_pnl_pct
            0.5

        A short with the same prices is the mirror image: its PnL and its
        percentage are the negation of the long's::

            >>> holding = Holding(
            ...     symbol="AAPL", quantity=-100, avg_cost=100.0, current_price=150.0
            ... )
            >>> holding.unrealized_pnl
            -5000.0
            >>> holding.unrealized_pnl_pct
            -0.5

        A zero-quantity holding reports 0.0 for both::

            >>> holding = Holding(symbol="AAPL", quantity=0, avg_cost=100.0, current_price=150.0)
            >>> holding.unrealized_pnl
            0.0
            >>> holding.unrealized_pnl_pct
            0.0

    """

    symbol: str
    quantity: float = 0.0
    avg_cost: float = 0.0
    current_price: float = 0.0
    market_value: float = 0.0

    def __post_init__(self) -> None:
        """Derive market value from quantity and current price when initialized.

        The market value of a position is always ``quantity *
        current_price``, for longs and for shorts alike, so it is derived
        here rather than left to the caller. A zero-quantity holding has no
        market value and keeps the ``0.0`` default.
        """
        if self.quantity != 0:
            self.market_value = self.quantity * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        """Unrealized profit and loss for this holding."""
        if self.quantity == 0 or self.avg_cost == 0:
            return 0.0
        return self.quantity * (self.current_price - self.avg_cost)

    @property
    def unrealized_pnl_pct(self) -> float:
        """Unrealized profit and loss as a percentage of cost basis.

        The percentage carries the sign of the position's PnL, so a long and a
        short with the same prices are mirror images: their ``unrealized_pnl``
        and ``unrealized_pnl_pct`` are negations of each other. A
        zero-quantity holding (or one with a zero cost basis) reports 0.0.

        The relation ``unrealized_pnl == abs(quantity) * abs(avg_cost) *
        unrealized_pnl_pct`` holds for every holding.
        """
        if self.quantity == 0 or self.avg_cost == 0:
            return 0.0
        return copysign(1.0, self.quantity) * (self.current_price - self.avg_cost) / self.avg_cost

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

    def to_dict(self) -> dict[str, Any]:
        """Serialize holding to a dictionary."""
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "avg_cost": self.avg_cost,
            "current_price": self.current_price,
            "market_value": self.market_value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Holding":
        """Deserialize holding from a dictionary."""
        return cls(
            symbol=data["symbol"],
            quantity=data.get("quantity", 0.0),
            avg_cost=data.get("avg_cost", 0.0),
            current_price=data.get("current_price", 0.0),
            market_value=data.get("market_value", 0.0),
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

            >>> from quant_trading.portfolio.portfolio import Portfolio
            >>> portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
            >>> portfolio.add_holding("AAPL", 100, 100.0)
            >>> portfolio.update_prices({"AAPL": 120.0})
            >>> portfolio.holdings["AAPL"].market_value
            12000.0
            >>> portfolio.summary()["num_positions"]
            1

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

    def get_position(self, symbol: str) -> Position | None:
        """Get a single holding as a Position object.

        Args:
            symbol: Ticker symbol of the position to look up.

        Returns:
            The Position for the symbol, or None when the symbol is not held.

        """
        holding = self.holdings.get(symbol)
        return holding.to_position() if holding else None

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
        """Add to, reduce, or open a holding.

        Args:
            symbol: Symbol of the holding to add to or reduce.
            quantity: Signed quantity to trade. A positive quantity buys and a
                negative quantity sells.
            price: Execution price per unit.
            commission: Commission rate applied to the trade.
            slippage: Slippage rate applied to the trade.

        Entry fees (commission + slippage) are capitalized into the average
        cost basis of long positions: a new long position is costed at
        ``price * (1 + commission + slippage)``, and lots added to an existing
        long are averaged at their fee-inclusive cost. Reductions of a long
        leave the remaining basis untouched. Short positions keep the execution
        price as their basis, and lots added to an existing short are averaged
        at the raw execution price.

        A trade in the opposite direction to the open position reduces it. The
        executed quantity is capped at the size of the position, so a reduction
        can never open or flip a position, and a fully offset position is
        removed from the portfolio instead of being left behind with a zero
        quantity. A zero quantity is a no-op and never creates a position.

        Returns:
            None.

        """
        holding = self.holdings.get(symbol)

        if quantity == 0:
            # A zero-sized trade must not create a position.
            self.total_value = self.cash + self.get_holdings_value()
            return

        if holding is None or holding.quantity == 0:
            # Open a new position, replacing a stale zero-quantity entry.
            entry_price = price * (1 + commission + slippage) if quantity > 0 else price
            self.holdings[symbol] = Holding(
                symbol=symbol,
                quantity=quantity,
                avg_cost=entry_price,
                current_price=price,
                market_value=quantity * price,
            )
            executed = quantity
        elif (holding.quantity > 0) == (quantity > 0):
            # Add to the open position and average its cost basis.
            if quantity > 0:
                total_qty = holding.quantity + quantity
                holding.avg_cost = (
                    holding.avg_cost * holding.quantity
                    + price * (1 + commission + slippage) * quantity
                ) / total_qty
            else:
                total_qty = holding.quantity + quantity
                holding.avg_cost = (
                    holding.avg_cost * abs(holding.quantity) + price * abs(quantity)
                ) / abs(total_qty)
            holding.quantity = total_qty
            holding.update_price(price)
            executed = quantity
        else:
            # Reduce the open position. The executed quantity is capped at the
            # size of the position, so a reduction can never open or flip a
            # position, and the remaining basis is left untouched.
            size = min(abs(quantity), abs(holding.quantity))
            executed = -copysign(size, holding.quantity)
            remaining = holding.quantity + executed
            if remaining == 0:
                del self.holdings[symbol]
            else:
                holding.quantity = remaining
                holding.update_price(price)

        if executed > 0:
            # A buy debits cash, fees included.
            self.cash -= executed * price * (1 + commission + slippage)
        else:
            # A sell credits cash, fees deducted.
            self.cash += abs(executed) * price * (1 - commission - slippage)

        self.total_value = self.cash + self.get_holdings_value()

    def remove_holding(
        self,
        symbol: str,
        quantity: float,
        price: float,
        commission: float = 0.0,
        slippage: float = 0.0,
    ) -> float:
        """Remove from a holding. Returns the cash effect of the sale.

        Args:
            symbol: Symbol of the holding to reduce.
            quantity: Quantity to remove (capped at the current holding size).
            price: Execution price per unit.
            commission: Commission rate applied to the trade.
            slippage: Slippage rate applied to the trade.

        Returns:
            Net cash effect of the trade: the proceeds of a sale for a long
            position, the (negative) cost of covering for a short position, or
            0.0 when the symbol is not held.

        """
        holding = self.holdings.get(symbol)
        if holding is None:
            return 0.0

        size = min(abs(quantity), abs(holding.quantity))
        gross = size * price
        if holding.quantity > 0:
            # Selling a long position credits cash.
            holding.quantity -= size
            cash_effect = gross * (1 - commission - slippage)
        else:
            # Covering a short position costs cash.
            holding.quantity += size
            cash_effect = -gross * (1 + commission + slippage)

        if holding.quantity == 0:
            del self.holdings[symbol]
        else:
            holding.update_price(price)

        self.cash += cash_effect
        self.total_value = self.cash + self.get_holdings_value()
        return cash_effect

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

    def get_allocation(self, use_absolute: bool = False) -> dict[str, float]:
        """Get portfolio allocation percentages.

        Args:
            use_absolute: When True, use absolute market values so short
                positions contribute positively to gross exposure. When False
                (default), use signed market values (net allocation), where
                shorts appear as negative weights.

        Returns:
            Symbol-keyed market-value fractions of total portfolio value, or
            an empty dictionary when total value is non-positive.

        """
        if self.total_value <= 0:
            return {}
        if use_absolute:
            return {sym: abs(h.market_value) / self.total_value for sym, h in self.holdings.items()}
        return {sym: h.market_value / self.total_value for sym, h in self.holdings.items()}

    def get_net_allocation(self) -> dict[str, float]:
        """Get net allocation (signed weights; shorts are negative)."""
        return self.get_allocation(use_absolute=False)

    def get_gross_allocation(self) -> dict[str, float]:
        """Get gross allocation (absolute weights; shorts contribute positively)."""
        return self.get_allocation(use_absolute=True)

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

    def to_dict(self) -> dict[str, Any]:
        """Serialize portfolio to a dictionary."""
        last_rebalance_serialized: str | Any | None = None
        if self.last_rebalance is not None:
            if hasattr(self.last_rebalance, "isoformat"):
                last_rebalance_serialized = self.last_rebalance.isoformat()
            else:
                last_rebalance_serialized = self.last_rebalance
        return {
            "cash": self.cash,
            "holdings": {sym: h.to_dict() for sym, h in self.holdings.items()},
            "total_value": self.total_value,
            "initial_capital": self.initial_capital,
            "last_rebalance": last_rebalance_serialized,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Portfolio":
        """Deserialize portfolio from a dictionary."""
        last_rebalance_raw = data.get("last_rebalance")
        last_rebalance: datetime | None = None
        if isinstance(last_rebalance_raw, str) and last_rebalance_raw:
            try:
                last_rebalance = datetime.fromisoformat(last_rebalance_raw)
            except (ValueError, TypeError):
                last_rebalance = None
        elif isinstance(last_rebalance_raw, datetime):
            last_rebalance = last_rebalance_raw
        portfolio = cls(
            cash=data.get("cash", 0.0),
            initial_capital=data.get("initial_capital", data.get("cash", 0.0)),
        )
        portfolio.total_value = data.get("total_value", portfolio.cash)
        portfolio.last_rebalance = last_rebalance
        portfolio.holdings = {}
        holdings_data = data.get("holdings", {}) or {}
        for sym, hdata in holdings_data.items():
            holding = Holding.from_dict(hdata)
            portfolio.holdings[sym] = holding
        return portfolio
