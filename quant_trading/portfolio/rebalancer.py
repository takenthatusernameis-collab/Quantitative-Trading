"""Portfolio rebalancing logic.

This module translates a portfolio's current allocation and a set of trading
signals into concrete :class:`RebalanceAction` objects that should be
executed to bring the portfolio back to its target allocation.

Examples:
    Generate buy and sell actions for a target allocation::

        from quant_trading.portfolio.portfolio import Portfolio
        from quant_trading.portfolio.rebalancer import Rebalancer
        from quant_trading.strategies.base import Signal

        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        rebalancer = Rebalancer(
            portfolio,
            frequency="monthly",
            target_allocation={"AAPL": 0.6, "MSFT": 0.4},
        )
        actions = rebalancer.generate_rebalance_actions()
        assert all(a.reason == "target_allocation" for a in actions)

    React to a sell signal for an unallocated symbol::

        sell_signal = Signal(symbol="AAPL", action="sell", price=150.0)
        actions = rebalancer.generate_rebalance_actions(signals=[sell_signal])
        assert actions[0].action == "sell"

"""

from dataclasses import dataclass, field
from datetime import datetime

from quant_trading.portfolio.portfolio import Portfolio
from quant_trading.strategies.base import Signal


@dataclass
class RebalanceAction:
    """A single rebalancing action produced by :class:`Rebalancer`.

    Each action describes one order that should be executed to move the
    portfolio toward its target allocation or to react to a trading signal.

    Attributes:
        symbol: Ticker symbol the action applies to.
        action: Order direction, one of ``"buy"``, ``"sell"``, or ``"hold"``.
        quantity: Absolute quantity to trade (always non-negative; the
            :attr:`action` field determines whether it is a buy or a sell).
        reason: Short explanation for the action, such as
            ``"target_allocation"`` or ``"signal_<type>"``.
        timestamp: Time the action was generated (defaults to now).

    Examples:
        Create a buy action for a target allocation::

            from quant_trading.portfolio.rebalancer import RebalanceAction

            action = RebalanceAction(
                symbol="AAPL", action="buy", quantity=10, reason="target_allocation"
            )
            assert action.quantity == 10

        Create a sell action driven by a signal::

            sell = RebalanceAction(symbol="AAPL", action="sell", quantity=5)
            assert sell.reason == ""

    """

    symbol: str
    action: str  # 'buy', 'sell', 'hold'
    quantity: float = 0.0
    reason: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


class Rebalancer:
    """Manages portfolio rebalancing based on signals and targets.

    The rebalancer compares a portfolio's current allocation against a set of
    target allocations and emits :class:`RebalanceAction` objects describing
    the trades required to close the gap. It can also react to trading
    :class:`~quant_trading.strategies.base.Signal` objects for symbols that
    are not part of the target allocation.

    Attributes:
        portfolio: The :class:`~quant_trading.portfolio.portfolio.Portfolio`
            being managed.
        frequency: Rebalancing cadence, one of ``"daily"``, ``"weekly"``,
            ``"monthly"``, or ``"quarterly"``.
        target_allocation: Symbol-keyed target fractions of total portfolio
            value (e.g. ``{"AAPL": 0.6, "MSFT": 0.4}``).
        rebalance_threshold: Minimum deviation (as a fraction of total
            portfolio value) that triggers a rebalance; trades smaller than
            this are skipped.
        last_rebalance: Timestamp of the most recent rebalance, or ``None``
            if the rebalancer has not run yet.
        rebalance_history: List of dicts recording each rebalance's
            timestamp, affected symbols, and portfolio value.

    Examples:
        Create a rebalancer and check whether it is time to rebalance::

            from quant_trading.portfolio.portfolio import Portfolio
            from quant_trading.portfolio.rebalancer import Rebalancer

            portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
            rebalancer = Rebalancer(
                portfolio,
                frequency="monthly",
                target_allocation={"AAPL": 0.6, "MSFT": 0.4},
            )
            assert rebalancer.should_rebalance() is True

    """

    def __init__(
        self,
        portfolio: Portfolio,
        frequency: str = "monthly",
        target_allocation: dict[str, float] | None = None,
        rebalance_threshold: float = 0.05,  # Rebalance if deviation > 5%
    ):
        """Initialize the rebalancer.

        Args:
            portfolio: The portfolio to manage.
            frequency: Rebalancing cadence (``"daily"``, ``"weekly"``,
                ``"monthly"``, or ``"quarterly"``).
            target_allocation: Symbol-keyed target fractions of total portfolio
                value. Defaults to an empty dict when ``None``.
            rebalance_threshold: Minimum deviation (as a fraction of total
                portfolio value) that triggers a rebalance.

        """
        self.portfolio = portfolio
        self.frequency = frequency
        self.target_allocation = target_allocation or {}
        self.rebalance_threshold = rebalance_threshold
        self.last_rebalance: datetime | None = None
        self.rebalance_history: list[dict] = []

    def should_rebalance(self) -> bool:
        """Check if it is time to rebalance based on the configured frequency.

        The first call always returns ``True`` (since no prior rebalance has
        been recorded). Subsequent calls compare the elapsed time since
        :attr:`last_rebalance` against the cadence implied by
        :attr:`frequency`.

        Returns:
            True if enough time has elapsed since the last rebalance (or if
            no rebalance has occurred yet), False otherwise. An unrecognized
            :attr:`frequency` value also returns False.

        """
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
        """Calculate target market values for every symbol in the allocation.

        Each target is the product of the portfolio's current total value and
        the symbol's target allocation fraction.

        Returns:
            Symbol-keyed target market values. Empty when no target
            allocation is configured.

        """
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
        """Generate rebalancing actions to move the portfolio to its targets.

        Two sources of actions are considered:

        1. **Target allocations** - for every symbol in
           :attr:`target_allocation`, a buy or sell action is emitted when the
           current deviation exceeds :attr:`rebalance_threshold`.
        2. **Trading signals** - buy signals for symbols outside the target
           allocation are sized to 5% of portfolio value times signal strength;
           sell signals liquidate the full holdings of the signaled symbol.

        After computing the actions the rebalancer records the run in
        :attr:`rebalance_history` and updates :attr:`last_rebalance`.

        Args:
            signals: Optional list of :class:`~quant_trading.strategies.base.Signal`
                objects to act on.
            prices: Optional symbol-keyed price map used to resolve buy
                quantities when the portfolio has no holding for a symbol.

        Returns:
            List of :class:`RebalanceAction` objects to execute. May be empty
            when no deviation or signal warrants a trade.

        """
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
        """Resolve a buy quantity for a symbol, guarding against zero prices.

        The price used to convert a dollar ``diff`` into a quantity is taken
        from the first available source in order: the portfolio's existing
        holding, the ``prices`` map, and finally the average price of matching
        signals.

        Args:
            symbol: Symbol being bought.
            diff: Dollar amount to buy (target value minus current value).
            signals: Optional signals for the symbol, used as a price source.
            prices: Optional symbol-keyed price map.

        Returns:
            Quantity to buy, or 0.0 when no positive price could be resolved.

        """
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
        """Resolve a sell quantity for a symbol, guarding against zero prices.

        Args:
            symbol: Symbol being sold.
            diff: Dollar amount to sell (absolute value of the deviation).

        Returns:
            Quantity to sell (``diff`` divided by the holding's current
            price), or 0.0 when the symbol is not held or the price is
            non-positive.

        """
        if symbol in self.portfolio.holdings:
            price = self.portfolio.holdings[symbol].current_price
            if price and price > 0:
                return diff / price
        return 0.0

    def set_target_allocation(self, allocation: dict[str, float]) -> None:
        """Set the target allocation, normalizing it to sum to 1.0.

        Args:
            allocation: Symbol-keyed target fractions of total portfolio value.
                When the fractions do not sum to 1.0 (within a 0.01 tolerance)
                they are rescaled so they do.

        Returns:
            None.

        """
        total = sum(allocation.values())
        if abs(total - 1.0) > 0.01:
            # Normalize
            allocation = {k: v / total for k, v in allocation.items()}
        self.target_allocation = allocation

    def get_current_deviation(self) -> dict[str, float]:
        """Get the deviation of each symbol from its target allocation.

        Args:
            None.

        Returns:
            Symbol-keyed differences (current fraction minus target
            fraction) for every symbol in :attr:`target_allocation`.

        """
        current = self.portfolio.get_allocation()
        deviations = {}
        for symbol, target_pct in self.target_allocation.items():
            current_pct = current.get(symbol, 0.0)
            deviations[symbol] = current_pct - target_pct
        return deviations

    def needs_rebalance(self) -> bool:
        """Check if the portfolio needs rebalancing based on deviations.

        Returns:
            True if any symbol's absolute deviation from its target
            allocation exceeds :attr:`rebalance_threshold`, False otherwise.
            Returns False when no target allocation is configured.

        """
        if not self.target_allocation:
            return False
        deviations = self.get_current_deviation()
        for dev in deviations.values():
            if abs(dev) > self.rebalance_threshold:
                return True
        return False
