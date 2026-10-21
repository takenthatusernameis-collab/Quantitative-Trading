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

    Apply the generated actions to the portfolio::

        executions = rebalancer.execute_actions(actions, prices={"AAPL": 150.0})
        assert all(e.executed_quantity >= 0 for e in executions)

"""

from dataclasses import dataclass, field
from datetime import datetime
from math import copysign
from typing import Any

from quant_trading.portfolio.portfolio import Portfolio
from quant_trading.risk.manager import RiskManager
from quant_trading.strategies.base import Signal

# Relative cushion kept when a buy is sized against the available cash.  It
# keeps floating point rounding from pushing the cash balance below zero.
_CASH_SAFETY_MARGIN = 1e-9


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


@dataclass
class RebalanceExecution:
    """The outcome of applying a single :class:`RebalanceAction` to a portfolio.

    Attributes:
        symbol: Ticker symbol the action applied to.
        action: Order direction of the action (``"buy"``, ``"sell"`` or
            ``"hold"``).
        requested_quantity: Quantity the action asked for, as an absolute
            number of units.
        executed_quantity: Units actually traded. It is 0.0 for a ``"hold"``
            action and for an action that could not be executed, and it is
            capped at the size of the open position when the action trades
            against one.
        price: Price per unit resolved for the action, or 0.0 when no price
            could be resolved.
        cash_effect: Change in the portfolio's cash balance caused by the
            action (negative for a buy, positive for a sale).
        reason: The reason carried by the action.
        timestamp: Time the action was applied (defaults to now).

    Examples:
        Record the execution of a buy action::

            from quant_trading.portfolio.rebalancer import RebalanceExecution

            execution = RebalanceExecution(
                symbol="AAPL",
                action="buy",
                requested_quantity=10.0,
                executed_quantity=10.0,
                price=150.0,
                cash_effect=-1500.0,
            )
            assert execution.executed_quantity == 10.0

    """

    symbol: str
    action: str
    requested_quantity: float = 0.0
    executed_quantity: float = 0.0
    price: float = 0.0
    cash_effect: float = 0.0
    reason: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class _RebalancePlan:
    """Cash and position state a planned batch of actions expects.

    The planner walks the actions in the order they will be executed and keeps
    track of the cash that is still available and of the positions the
    portfolio is expected to hold once the batch is done.  A buy is therefore
    never sized against cash that an earlier action of the same batch already
    committed.

    Attributes:
        cash: Cash the batch may still spend.
        fee_rate: Combined commission and slippage rate of the batch.
        positions: Signed quantity the batch expects to hold per symbol.
    """

    cash: float
    fee_rate: float = 0.0
    positions: dict[str, float] = field(default_factory=dict)


class Rebalancer:
    """Manages portfolio rebalancing based on signals and targets.

    The rebalancer compares a portfolio's current allocation against a set of
    target allocations and emits :class:`RebalanceAction` objects describing
    the trades required to close the gap. It can also react to trading
    :class:`~quant_trading.strategies.base.Signal` objects for symbols that
    are not part of the target allocation.

    The emitted actions can be applied to the managed portfolio with
    :meth:`execute_actions`, which reports what each action actually traded.

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
        risk_manager: Optional :class:`~quant_trading.risk.manager.RiskManager`
            used to size buys against the position and loss limits before
            actions are emitted. When ``None`` (the default) no risk checks
            are applied.

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
        rebalance_threshold: float = 0.05,
        risk_manager: RiskManager | None = None,
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
            risk_manager: Optional risk manager used to check buy sizes
                against the position and loss limits before actions are
                emitted. When ``None`` no risk checks are applied.

        """
        self.portfolio = portfolio
        self.frequency = frequency
        self.target_allocation = target_allocation or {}
        self.rebalance_threshold = rebalance_threshold
        self.risk_manager = risk_manager
        self.last_rebalance: datetime | None = None
        self.rebalance_history: list[dict[str, Any]] = []

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

    def _portfolio_value_at_prices(self, prices: dict[str, float]) -> float:
        """Total value of the portfolio with every position marked at a price.

        The cash is added to the market value of every open position, with
        each position valued at the price it is traded at. The result is the
        value of the portfolio in the price space the trades are planned in,
        so the targets, the deviations and the trades that close them are all
        measured against the same value.

        Args:
            prices: Symbol-keyed price map used to mark the positions.

        Returns:
            The total value of the portfolio at the given prices.

        """
        total = self.portfolio.cash
        for symbol, holding in self.portfolio.holdings.items():
            total += holding.quantity * self._resolve_execution_price(symbol, prices)
        return total

    def calculate_target_values(self, prices: dict[str, float] | None = None) -> dict[str, float]:
        """Calculate target market values for every symbol in the allocation.

        Each target is the product of the portfolio's current total value and
        the symbol's target allocation fraction.

        Args:
            prices: Optional symbol-keyed price map. When given, the total
                value of the portfolio is computed with every position marked
                at that price, so the targets live in the same price space as
                the trades that are planned from them.

        Returns:
            Symbol-keyed target market values. Empty when no target
            allocation is configured.

        """
        total_value = self._portfolio_value_at_prices(prices or {})
        targets = {}
        for symbol, pct in self.target_allocation.items():
            targets[symbol] = total_value * pct
        return targets

    def generate_rebalance_actions(
        self,
        signals: list[Signal] | None = None,
        prices: dict[str, float] | None = None,
        commission: float = 0.0,
        slippage: float = 0.0,
    ) -> list[RebalanceAction]:
        """Generate rebalancing actions to move the portfolio to its targets.

        Two sources of actions are considered:

        1. **Target allocations** - for every symbol in
           :attr:`target_allocation`, a buy or sell action is emitted when the
           current deviation exceeds :attr:`rebalance_threshold`.
        2. **Trading signals** - buy signals for symbols outside the target
           allocation are sized to 5% of portfolio value times signal strength;
           sell signals liquidate the full holdings of the signaled symbol.

        Every trade is sized at the price it is planned at, and the deviation
        it closes is measured at that same price, so the trade releases
        exactly the dollars the deviation measured and the position lands on
        its target.

        The actions are **affordable**: a buy is sized against the cash the
        portfolio actually has, net of the fees, and against the cash that the
        earlier actions of the same batch have not committed yet.  A buy that
        cannot be paid for in full is reduced to what the remaining cash can
        buy, and a buy that cannot be paid for at all is dropped.  A sell
        releases cash that the buys later in the batch can use.

        The actions are planned in the order they are returned, so a buy is
        only sized against the cash that is available at that point of the
        sequence: a sell that comes later in the list cannot fund a buy that
        comes before it.

        The fees are part of the sizing, so the same ``commission`` and
        ``slippage`` must be passed to :meth:`execute_actions` that are passed
        here.  Passing the execution fees to this method is what keeps the
        cash balance of the portfolio non-negative.

        After computing the actions the rebalancer records the run in
        :attr:`rebalance_history` and updates :attr:`last_rebalance`.

        Args:
            signals: Optional list of :class:`~quant_trading.strategies.base.Signal`
                objects to act on.
            prices: Optional symbol-keyed price map used to resolve buy
                quantities when the portfolio has no holding for a symbol.
            commission: Commission rate the actions will be executed with.
            slippage: Slippage rate the actions will be executed with.

        Returns:
            List of :class:`RebalanceAction` objects to execute. May be empty
            when no deviation or signal warrants a trade.

        """
        actions = []
        prices = prices or {}
        total_value = self._portfolio_value_at_prices(prices)
        targets = self.calculate_target_values(prices)
        plan = _RebalancePlan(
            cash=self.portfolio.cash,
            fee_rate=commission + slippage,
            positions={
                symbol: holding.quantity for symbol, holding in self.portfolio.holdings.items()
            },
        )

        # Process target allocations
        for symbol in self.target_allocation:
            if total_value <= 0:
                continue
            # The price the trade is planned at is the price the deviation is
            # measured at, so the trade closes exactly the dollars the
            # deviation measured and the position lands on its target.
            price = self._resolve_plan_price(symbol, prices, signals)
            if price <= 0:
                # Without a price neither the deviation nor the quantity of a
                # trade can be determined, so the symbol is left alone.
                continue
            current_value = self._planned_position_value(plan, symbol, price)
            target_value = targets[symbol]
            diff = target_value - current_value

            if abs(diff) / total_value > self.rebalance_threshold:
                if diff > 0:
                    quantity = self._resolve_buy_quantity(symbol, diff, signals, prices, price)
                    quantity = self._risk_adjust_buy(plan, symbol, quantity, price, total_value)
                    if quantity > 0:
                        quantity = self._plan_buy(plan, symbol, quantity, price)
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
                    quantity = self._resolve_sell_quantity(symbol, abs(diff), price)
                    if quantity > 0:
                        self._plan_sell(plan, symbol, quantity, price)
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
                    # Buy based on signal strength: the position is topped up
                    # to 5% of the portfolio value times the strength of the
                    # signal.
                    price = self._resolve_plan_price(signal.symbol, prices, signals)
                    if price <= 0:
                        # Without a price the position cannot be sized.
                        continue
                    target_value = total_value * 0.05 * signal.strength  # 5% max per signal
                    # The value the batch has already committed to the symbol
                    # counts towards the current value, so a second signal for
                    # the same symbol tops the position up to its target
                    # instead of buying another slice on top of it.
                    current_value = self._planned_position_value(plan, signal.symbol, price)
                    diff = target_value - current_value
                    if diff > 0 and signal.price:
                        quantity = self._resolve_buy_quantity(
                            signal.symbol, diff, signals, prices, price
                        )
                        quantity = self._risk_adjust_buy(
                            plan,
                            signal.symbol,
                            quantity,
                            price,
                            total_value,
                        )
                        if quantity > 0:
                            quantity = self._plan_buy(plan, signal.symbol, quantity, price)
                            if quantity > 0:
                                actions.append(
                                    RebalanceAction(
                                        symbol=signal.symbol,
                                        action="buy",
                                        quantity=quantity,
                                        reason=f"signal_{signal.metadata.get('signal_type', 'unknown')}",
                                    )
                                )
                elif signal.action == "sell":
                    holding = self.portfolio.holdings.get(signal.symbol)
                    if holding and holding.quantity != 0:
                        price = self._resolve_execution_price(signal.symbol, prices)
                        quantity = abs(holding.quantity)
                        self._plan_sell(plan, signal.symbol, quantity, price)
                        actions.append(
                            RebalanceAction(
                                symbol=signal.symbol,
                                action="sell",
                                quantity=quantity,
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

    def execute_actions(
        self,
        actions: list[RebalanceAction],
        prices: dict[str, float] | None = None,
        commission: float = 0.0,
        slippage: float = 0.0,
    ) -> list[RebalanceExecution]:
        """Apply rebalancing actions to the managed portfolio.

        Each action is translated into a trade on :attr:`portfolio`:

        * a ``"buy"`` buys ``quantity`` units, opening a long position or
          adding to the one already held (and covering an open short);
        * a ``"sell"`` sells ``quantity`` units, reducing an open long or
          covering an open short;
        * a ``"hold"`` does nothing.

        The portfolio caps a trade against an open position at the size of that
        position, so an action can never open or flip a position, and a fully
        offset position is removed from the portfolio. The execution reports
        what was actually traded, which may be less than the quantity the
        action asked for.

        The execution price of an action is taken from the ``prices`` map when
        it holds a positive price for the symbol, and otherwise from the
        current price of the holding. An action with no resolvable price, a
        zero quantity, or a ``"hold"`` direction is skipped and reported with
        an executed quantity of 0.0.

        After the actions are applied the run is recorded in
        :attr:`rebalance_history` and :attr:`last_rebalance` is updated.

        Args:
            actions: Actions to apply, typically the list returned by
                :meth:`generate_rebalance_actions`.
            prices: Optional symbol-keyed price map used to resolve the
                execution price of each action.
            commission: Commission rate applied to every trade.
            slippage: Slippage rate applied to every trade.

        Returns:
            One :class:`RebalanceExecution` per action, in the order the
            actions were given.

        Raises:
            ValueError: If an action carries an unrecognized direction.

        """
        prices = prices or {}
        executions: list[RebalanceExecution] = []

        for action in actions:
            if action.action not in ("buy", "sell", "hold"):
                raise ValueError(f"Unknown rebalance action: {action.action!r}")

            quantity = abs(action.quantity)
            price = self._resolve_execution_price(action.symbol, prices)
            position_before = self._position_of(action.symbol)
            cash_before = self.portfolio.cash

            if quantity > 0 and price > 0:
                if action.action == "buy":
                    self.portfolio.add_holding(action.symbol, quantity, price, commission, slippage)
                elif action.action == "sell":
                    self.portfolio.remove_holding(
                        action.symbol, quantity, price, commission, slippage
                    )

            position_after = self._position_of(action.symbol)
            executions.append(
                RebalanceExecution(
                    symbol=action.symbol,
                    action=action.action,
                    requested_quantity=quantity,
                    executed_quantity=abs(position_after - position_before),
                    price=price,
                    cash_effect=self.portfolio.cash - cash_before,
                    reason=action.reason,
                )
            )

        self.last_rebalance = datetime.now()
        self.portfolio.last_rebalance = self.last_rebalance
        self.rebalance_history.append(
            {
                "timestamp": self.last_rebalance,
                "actions": [e.symbol for e in executions],
                "portfolio_value": self.portfolio.total_value,
                "executions": [
                    {
                        "symbol": e.symbol,
                        "action": e.action,
                        "requested_quantity": e.requested_quantity,
                        "executed_quantity": e.executed_quantity,
                        "price": e.price,
                        "cash_effect": e.cash_effect,
                        "reason": e.reason,
                    }
                    for e in executions
                ],
            }
        )

        return executions

    def _resolve_execution_price(self, symbol: str, prices: dict[str, float]) -> float:
        """Resolve the price an action is executed at.

        The ``prices`` map wins when it holds a positive price for the symbol,
        and the current price of the holding is used otherwise.

        Args:
            symbol: Symbol the action applies to.
            prices: Symbol-keyed price map.

        Returns:
            The execution price, or 0.0 when no positive price is available.

        """
        return self._resolve_plan_price(symbol, prices)

    def _resolve_plan_price(
        self,
        symbol: str,
        prices: dict[str, float],
        signals: list[Signal] | None = None,
    ) -> float:
        """Resolve the price a planned trade is sized at.

        The precedence matches the execution price resolution -- the ``prices``
        map first, then the current price of the holding -- so that a planned
        trade is priced exactly like the trade it produces.  When neither is
        available the average price of the matching signals is used.

        Args:
            symbol: Symbol the trade applies to.
            prices: Symbol-keyed price map.
            signals: Optional signals for the symbol, used as a price source.

        Returns:
            The price, or 0.0 when no positive price is available.

        """
        price = prices.get(symbol)
        if price is not None and price > 0:
            return price
        holding = self.portfolio.holdings.get(symbol)
        if holding is not None and holding.current_price > 0:
            return holding.current_price
        if signals:
            signal_prices = [s.price for s in signals if s.symbol == symbol and s.price]
            if signal_prices:
                avg_price = sum(signal_prices) / len(signal_prices)
                if avg_price > 0:
                    return avg_price
        return 0.0

    def _position_of(self, symbol: str) -> float:
        """Return the signed quantity currently held in a symbol.

        Args:
            symbol: Symbol to look up.

        Returns:
            The quantity held, or 0.0 when the symbol is not held.

        """
        holding = self.portfolio.holdings.get(symbol)
        return holding.quantity if holding is not None else 0.0

    def _plan_buy(
        self,
        plan: _RebalancePlan,
        symbol: str,
        quantity: float,
        price: float,
    ) -> float:
        """Size a planned buy so that the batch stays solvent.

        The buy is reduced to what the remaining cash can pay for, fees
        included, and a buy that covers an open short is capped at the size of
        that short exactly like the execution is.

        Args:
            plan: Cash and position state of the batch being planned.
            symbol: Symbol being bought.
            quantity: Quantity the plan would like to buy.
            price: Price the buy is planned at.

        Returns:
            The quantity that can actually be bought, or 0.0 when nothing can
            be afforded.

        """
        position = plan.positions.get(symbol, 0.0)
        if position < 0:
            # The buy covers an open short; it cannot flip it.
            quantity = min(quantity, -position)

        affordable = plan.cash * (1.0 - _CASH_SAFETY_MARGIN) / (price * (1.0 + plan.fee_rate))
        quantity = min(quantity, affordable)
        if quantity <= 0:
            return 0.0

        plan.cash -= quantity * price * (1.0 + plan.fee_rate)
        plan.positions[symbol] = position + quantity
        return quantity

    def _risk_adjust_buy(
        self,
        plan: _RebalancePlan,
        symbol: str,
        quantity: float,
        price: float,
        total_value: float,
    ) -> float:
        """Size a buy down so the resulting position stays within risk limits.

        Applies the position limit (the smaller of the maximum position
        fraction and the maximum position dollar value) and halts buying when
        the portfolio's drawdown (loss) limit has been breached. A buy that
        would exceed the position limit is reduced to the largest quantity
        that still fits; a buy with no room left is dropped entirely.
        Available cash is enforced separately by :meth:`_plan_buy`.

        Args:
            plan: Cash and position state of the batch being planned.
            symbol: Symbol being bought.
            quantity: Quantity the plan would like to buy.
            price: Price the buy is planned at.
            total_value: Current total portfolio value.

        Returns:
            The risk-adjusted quantity to buy, or 0.0 when the buy is not
            permitted.

        """
        if self.risk_manager is None or not self.risk_manager.risk_enabled:
            return quantity

        drawdown_limit = self.risk_manager.portfolio_limit.max_drawdown
        if (
            drawdown_limit > 0
            and self.risk_manager.portfolio_risk.current_drawdown <= -drawdown_limit
        ):
            return 0.0

        limit = self.risk_manager.position_limit
        current_position = plan.positions.get(symbol, 0.0)
        max_position_value = min(limit.max_size * total_value, limit.max_value)
        room = max_position_value - current_position * price
        if room <= 0:
            return 0.0
        return min(quantity, room / price)

    def _plan_sell(
        self,
        plan: _RebalancePlan,
        symbol: str,
        quantity: float,
        price: float,
    ) -> None:
        """Book the cash a planned sell releases.

        A sell of a long position credits the cash the sale brings in, fees
        deducted.  A sell against an open short covers it and therefore costs
        cash.  Only the part of the position that is actually sold is booked,
        exactly like the execution does.

        Args:
            plan: Cash and position state of the batch being planned.
            symbol: Symbol being sold.
            quantity: Quantity the plan would like to sell.
            price: Price the sell is planned at.

        Returns:
            None.

        """
        if price <= 0:
            return  # pragma: no cover - price is always > 0 when _plan_sell is called

        position = plan.positions.get(symbol, 0.0)
        size = min(quantity, abs(position))
        if size <= 0:
            return

        if position > 0:
            plan.cash += size * price * (1.0 - plan.fee_rate)
        else:
            plan.cash -= size * price * (1.0 + plan.fee_rate)
        plan.positions[symbol] = position - copysign(size, position)

    def _planned_position_value(self, plan: _RebalancePlan, symbol: str, price: float) -> float:
        """Value of the position the batch expects to hold, at the given price.

        The batch's own trades are part of the position, so a symbol the batch
        has already bought is valued with the quantity the plan expects to
        hold, not with the quantity the portfolio holds. The position is
        valued at the price the batch trades it at, so the deviation that is
        measured and the trade that closes it live in the same price space.

        Args:
            plan: Cash and position state of the batch being planned.
            symbol: Symbol to value.
            price: Price the position is valued at.

        Returns:
            The market value of the position (negative for a short position),
            or 0.0 when the batch holds nothing in the symbol.

        """
        return plan.positions.get(symbol, 0.0) * price

    def _resolve_buy_quantity(
        self,
        symbol: str,
        diff: float,
        signals: list[Signal] | None,
        prices: dict[str, float],
        price: float | None = None,
    ) -> float:
        """Resolve a buy quantity for a symbol, guarding against zero prices.

        The price used to convert a dollar ``diff`` into a quantity is taken
        from the first available source in order: the ``prices`` map, the
        portfolio's existing holding, and finally the average price of matching
        signals.  The order matches the execution price resolution, so a
        planned buy is priced like the trade it produces.

        Args:
            symbol: Symbol being bought.
            diff: Dollar amount to buy (target value minus current value).
            signals: Optional signals for the symbol, used as a price source.
            prices: Optional symbol-keyed price map.
            price: Price the buy is planned at. When given it is used as is,
                so the quantity is derived from the same price the deviation
                was measured at.

        Returns:
            Quantity to buy, or 0.0 when no positive price could be resolved.

        """
        if price is None:
            price = self._resolve_plan_price(symbol, prices, signals)
        if price > 0:
            return diff / price
        return 0.0

    def _resolve_sell_quantity(self, symbol: str, diff: float, price: float | None = None) -> float:
        """Resolve a sell quantity for a symbol, guarding against zero prices.

        The quantity is derived from the price the sell is planned at, so the
        trade releases exactly the dollar amount the deviation measured. When
        no price is given the current price of the holding is used.

        Args:
            symbol: Symbol being sold.
            diff: Dollar amount to sell (absolute value of the deviation).
            price: Price the sell is planned at, or ``None`` to fall back to
                the current price of the holding.

        Returns:
            Quantity to sell, or 0.0 when the symbol is not held or the price
            is non-positive.

        """
        if symbol not in self.portfolio.holdings:
            return 0.0
        if price is not None and price > 0:
            return diff / price
        mark = self.portfolio.holdings[symbol].current_price
        if mark and mark > 0:
            return diff / mark
        return 0.0

    def set_target_allocation(self, allocation: dict[str, float]) -> None:
        """Set the target allocation, normalizing it to sum to 1.0.

        Args:
            allocation: Symbol-keyed target fractions of total portfolio value.
                When the fractions do not sum to 1.0 (within a 0.01 tolerance)
                they are rescaled so they do. An empty allocation clears the
                targets.

        Returns:
            None.

        Raises:
            ValueError: If the fractions sum to zero, because they cannot be
                rescaled to sum to 1.0.

        """
        total = sum(allocation.values())
        if allocation and abs(total - 1.0) > 0.01:
            if total == 0:
                raise ValueError("Target allocation fractions must not sum to zero")
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
