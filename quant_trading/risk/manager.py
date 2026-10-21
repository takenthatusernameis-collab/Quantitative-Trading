"""Risk management orchestration.

Examples:
    Create a risk manager and check a trading signal::

        from quant_trading.risk.manager import RiskManager
        from quant_trading.strategies.base import Signal

        rm = RiskManager(initial_capital=100000.0, max_position_size=0.1)
        signal = Signal(symbol="AAPL", action="buy", price=150.0, strength=1.0)
        result = rm.check_signal(signal, portfolio_value=100000.0)
        assert result.passed in (True, False)

"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from quant_trading.risk.limits import CheckResult, PortfolioLimit, PositionLimit
from quant_trading.risk.metrics import RiskMetrics, calculate_all_metrics
from quant_trading.strategies.base import Position, Signal


@dataclass
class PortfolioRisk:
    """Current portfolio risk state.

    Attributes:
        total_market_value: Total market value of portfolio (cash + positions).
        cash: Available cash balance.
        positions_value: Market value of all positions.
        leverage: Gross portfolio leverage ratio (sum of the absolute market
            values of the positions / total_value).
        current_drawdown: Current drawdown from peak (0.0 = at peak, negative
            while the portfolio is below its peak).
        peak_value: Peak portfolio value observed.

    Examples:
        pr = PortfolioRisk(total_market_value=100000.0, cash=50000.0, positions_value=50000.0)
        assert pr.total_value == 100000.0

    """

    total_market_value: float = 0.0
    cash: float = 0.0
    positions_value: float = 0.0
    leverage: float = 0.0
    current_drawdown: float = 0.0
    peak_value: float = 0.0

    @property
    def total_value(self) -> float:
        """Total portfolio value.

        Returns:
            Equal to ``total_market_value``.

        """
        return self.total_market_value


class RiskManager:
    """Manages risk for trading operations.

    Attributes:
        initial_capital: Starting capital.
        risk_free_rate: Annual risk-free rate used for risk-adjusted metrics.
        position_limit: Position limit configuration.
        portfolio_limit: Portfolio limit configuration.
        portfolio_risk: Current portfolio risk state.
        positions: Current positions by symbol.
        equity_curve: History of total portfolio values.
        peak_value: Peak value observed in equity curve.
        risk_metrics: Last computed risk metrics (if any).
        risk_enabled: Whether risk checks are enabled.
        history: Historical risk snapshots.
        trailing_stop_pct: Distance of the trailing stop from the best price
            the position has reached, as a fraction (``0.0`` disables it).
        trailing_stop_activation_pct: How far a position must move in its
            favour before its trailing stop starts to trail.

    Examples:
        rm = RiskManager(initial_capital=50000.0, max_position_size=0.2)
        assert rm.initial_capital == 50000.0
        assert rm.risk_enabled

    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        max_position_size: float = 0.1,
        max_portfolio_risk: float = 0.02,
        max_drawdown: float = 0.20,
        max_positions: int = 20,
        stop_loss_pct: float = 0.05,
        take_profit_pct: float = 0.15,
        risk_free_rate: float = 0.02,
        max_leverage: float = 1.0,
        trailing_stop_pct: float = 0.0,
        trailing_stop_activation_pct: float = 0.0,
    ):
        """Initialize risk manager.

        Args:
            initial_capital: Initial capital for risk calculations.
            max_position_size: Maximum position size as fraction of portfolio.
            max_portfolio_risk: Maximum fraction of the portfolio value that may
                be at risk at any time.
            max_drawdown: Maximum drawdown before halt (fraction).
            max_positions: Maximum number of positions allowed.
            stop_loss_pct: Default stop loss percentage.
            take_profit_pct: Default take profit percentage.
            risk_free_rate: Annual risk-free rate used for risk-adjusted
                metrics (Sharpe/Sortino/alpha). Defaults to 0.02 to match
                the rest of the framework.
            max_leverage: Maximum gross exposure as a multiple of the portfolio
                value (1.0 = fully invested with no borrowing).
            trailing_stop_pct: Distance of the trailing stop from the best
                price the position has reached, as a fraction. Trailing stops
                are disabled when this is ``0.0`` (the default).
            trailing_stop_activation_pct: How far a position must move in its
                favour, as a fraction of the entry price, before its trailing
                stop starts to trail. ``0.0`` (the default) activates the
                trailing stop as soon as the position is at its entry price.

        Returns:
            None.

        """
        self.initial_capital = initial_capital
        self.risk_free_rate = risk_free_rate
        self.position_limit = PositionLimit(
            max_size=max_position_size,
            max_value=initial_capital * max_position_size,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
        )
        self.portfolio_limit = PortfolioLimit(
            max_positions=max_positions,
            max_position_size=max_position_size,
            max_portfolio_risk=max_portfolio_risk,
            max_drawdown=max_drawdown,
            max_leverage=max_leverage,
            stop_loss_pct=stop_loss_pct,
        )

        self.portfolio_risk = PortfolioRisk(
            total_market_value=initial_capital,
            cash=initial_capital,
            peak_value=initial_capital,
        )
        self.positions: dict[str, Position] = {}
        self.equity_curve: list[float] = [initial_capital]
        self.peak_value = initial_capital
        self.risk_metrics: RiskMetrics | None = None
        self.risk_enabled = True
        self.history: list[dict[str, Any]] = []
        self.trailing_stop_pct = trailing_stop_pct
        self.trailing_stop_activation_pct = trailing_stop_activation_pct
        self._trailing_stops: dict[str, float] = {}
        self._trailing_highs: dict[str, float] = {}
        self._trailing_lows: dict[str, float] = {}

    def update_portfolio_value(self, positions: dict[str, Position], cash: float) -> None:
        """Update portfolio value and track equity curve.

        Args:
            positions: Current positions by symbol.
            cash: Current cash balance.

        Returns:
            None.

        Examples:
            Update portfolio after a trade execution::

                from quant_trading.strategies.base import Position

                rm = RiskManager(initial_capital=50000.0)
                positions = {"AAPL": Position("AAPL", 100, 150.0, 152.0)}
                rm.update_portfolio_value(positions, 35000.0)
                assert rm.portfolio_risk.positions_value > 0.0

        """
        self.positions = positions
        positions_value = sum(p.market_value for p in positions.values())
        total_value = cash + positions_value

        # A position that is no longer held cannot carry a trailing stop, and
        # the price of the positions that are still held is fed to the
        # trailing stop tracker so its stop keeps following the market.
        for symbol in self._tracked_trailing_symbols():
            if symbol not in positions:
                self._clear_trailing_state(symbol)
        for symbol, position in positions.items():
            self.update_trailing_stop(symbol, position.current_price)

        # The peak is updated first so the drawdown is measured against the
        # peak the portfolio is actually at. Measuring against the previous
        # peak would report a positive drawdown at a new high.
        peak_value = max(self.peak_value, total_value)

        self.portfolio_risk = PortfolioRisk(
            total_market_value=total_value,
            cash=cash,
            positions_value=positions_value,
            leverage=(
                sum(abs(p.market_value) for p in positions.values()) / total_value
                if total_value > 0
                else 0
            ),
            current_drawdown=((total_value - peak_value) / peak_value if peak_value > 0 else 0),
            peak_value=peak_value,
        )

        self.equity_curve.append(total_value)
        self.peak_value = peak_value

        self.history.append(
            {
                "timestamp": datetime.now(),
                "total_value": total_value,
                "cash": cash,
                "positions_value": positions_value,
                "drawdown": self.portfolio_risk.current_drawdown,
            }
        )

    def sync_position(self, symbol: str, position: Position | None) -> None:
        """Refresh the manager's view of a single position.

        The portfolio snapshot is otherwise only refreshed by
        :meth:`update_portfolio_value`, which a caller naturally calls once
        per update cycle. A caller that executes several trades between two
        such refreshes can keep the snapshot current with this method, so a
        risk check performed after the first trade already sees the exposure
        that trade created instead of the exposure of the previous cycle.

        Only the position view is refreshed. The totals held in
        ``portfolio_risk`` and the equity curve are not recomputed; call
        :meth:`update_portfolio_value` for a full refresh.

        Args:
            symbol: Symbol whose position changed.
            position: The new position, or None when the position was closed.

        Returns:
            None.

        Examples:
            Keep the snapshot current while a batch of trades is executed::

                from quant_trading.risk.manager import RiskManager
                from quant_trading.strategies.base import Position

                rm = RiskManager(initial_capital=100000.0, max_leverage=0.5)
                rm.sync_position("AAPL", Position("AAPL", 100, 150.0, 150.0))
                assert "AAPL" in rm.positions

        """
        if position is None:
            self.positions.pop(symbol, None)
            self._clear_trailing_state(symbol)
            return

        previous = self.positions.get(symbol)
        if previous is not None and previous.quantity * position.quantity < 0:
            # The position flipped direction, so the trailing stop tracked for
            # the old direction no longer applies to the new one.
            self._clear_trailing_state(symbol)

        self.positions[symbol] = position
        self.update_trailing_stop(symbol, position.current_price)

    def check_signal(self, signal: Signal, portfolio_value: float | None = None) -> CheckResult:
        """Check if a trading signal passes risk limits.

        The position limits are measured against the manager's current
        position view, which is refreshed by :meth:`update_portfolio_value`
        and kept up to date with :meth:`sync_position` as trades are
        executed.

        A signal that adds exposure is measured against the exposure the
        position would carry once the trade is done: the trade brings the
        position to its target, so the position size limit is checked on the
        target when the position is below it and on the exposure the position
        already carries when it is above it. The portfolio risk budget and
        the leverage limit are increased by the increment alone, so a
        position that is already part of the way to its target is not
        charged for exposure it already carries.

        A ``"buy"`` signal against an open short covers that short. Covering
        reduces the gross exposure of the portfolio, so it cannot breach any
        of the position limits and only the presence of a price is checked. A
        ``"short"`` signal is gated exactly like a ``"buy"`` signal, because
        both add gross exposure.

        Args:
            signal: Trading signal to evaluate.
            portfolio_value: Current portfolio value. The manager's internal
                portfolio value is used when this is ``None``; any explicit
                value overrides it, including ``0.0`` (a wiped-out portfolio,
                which is rejected below).

        Returns:
            CheckResult with pass/fail and any violations.

        Examples:
            Buy signal is rejected when position size limits are violated::

                from quant_trading.risk.manager import RiskManager
                from quant_trading.strategies.base import Signal

                rm = RiskManager(initial_capital=100000.0, max_position_size=0.1)
                signal = Signal(symbol="AAPL", action="buy", price=150.0, strength=2.0)
                result = rm.check_signal(signal)
                assert result.passed in (True, False)

        """
        result = CheckResult(passed=True)

        if not self.risk_enabled:
            return result

        value = (
            self.portfolio_risk.total_market_value if portfolio_value is None else portfolio_value
        )
        if value <= 0:
            result.add_violation("Portfolio value is zero or negative")
            return result

        if signal.action == "buy":
            position = self.positions.get(signal.symbol)
            if signal.price is None:
                result.add_violation("Buy signal has no price")
                return result
            if position is not None and position.quantity < 0:
                # The buy covers an open short. Covering reduces the gross
                # exposure, so no position limit can be breached by it.
                return result
            current_gross = abs(position.quantity) * signal.price if position else 0.0
            self._check_exposure_increase(
                result,
                label="Buy",
                target_value=signal.strength * value * self.position_limit.max_size,
                current_gross=current_gross,
                portfolio_value=value,
            )

        elif signal.action == "sell":
            position = self.positions.get(signal.symbol)
            if position is None or position.quantity == 0:
                result.add_violation("Sell signal for position with no holdings")
            elif position.quantity < 0:
                result.add_violation("Sell signal for position with an open short")

        elif signal.action == "short":
            position = self.positions.get(signal.symbol)
            if position is not None and position.quantity > 0:
                result.add_violation("Short signal for position with long holdings")
                return result
            if signal.price is None:
                result.add_violation("Short signal has no price")
                return result
            current_gross = abs(position.quantity) * signal.price if position else 0.0
            self._check_exposure_increase(
                result,
                label="Short",
                target_value=signal.strength * value * self.position_limit.max_size,
                current_gross=current_gross,
                portfolio_value=value,
            )

        return result

    def _check_exposure_increase(
        self,
        result: CheckResult,
        label: str,
        target_value: float,
        current_gross: float,
        portfolio_value: float,
    ) -> None:
        """Check the limits that bound an increase of the gross exposure.

        The trade is measured on its gross exposure, so a short is limited
        exactly like a long of the same size. The position size is checked on
        the gross exposure the symbol would carry after the trade, the
        portfolio risk budget on the risk the trade adds, and the leverage
        limit on the gross exposure the trade adds to the portfolio.

        A trade brings the position to its target, so the exposure the symbol
        carries afterwards is the target itself when the position is below it,
        and the exposure it already carries when it is above it. The risk
        budget and the leverage limit are increased by the increment alone
        (the target less the exposure the symbol already carries), not by the
        whole target: the exposure the position already has is already
        counted in the current portfolio risk and in the current leverage.

        Args:
            result: Check result that collects the violations.
            label: Name of the signal used in the violation messages.
            target_value: Dollar value of the exposure the signal targets.
            current_gross: Gross exposure the symbol already carries.
            portfolio_value: Current portfolio value.

        Returns:
            None.

        """
        post_trade_size = max(current_gross, target_value)
        increment = max(0.0, target_value - current_gross)

        if post_trade_size > self.position_limit.max_value:
            result.add_violation(
                f"{label} signal would exceed max position value: ${post_trade_size:,.2f} > ${self.position_limit.max_value:,.2f}"
            )

        position_pct = post_trade_size / portfolio_value if portfolio_value > 0 else 0
        if position_pct > self.position_limit.max_size:
            result.add_violation(
                f"{label} signal would exceed max position size: {position_pct:.2%} > {self.position_limit.max_size:.2%}"
            )

        # Gate the trade on the portfolio risk budget and the leverage limit,
        # so a strategy cannot keep opening positions until the post-hoc
        # portfolio check reports a breach. The trade adds the increment of
        # gross exposure and increment * stop_loss_pct of risk.
        current_risk = self.portfolio_limit.portfolio_risk_pct(self.positions, portfolio_value)
        new_risk = current_risk + (increment * self.portfolio_limit.stop_loss_pct / portfolio_value)
        if new_risk > self.portfolio_limit.max_portfolio_risk:
            result.add_violation(
                f"{label} signal would exceed max portfolio risk: {new_risk:.2%} > {self.portfolio_limit.max_portfolio_risk:.2%}"
            )

        current_gross_exposure = self.portfolio_limit.leverage(self.positions, portfolio_value)
        new_leverage = current_gross_exposure + (increment / portfolio_value)
        if new_leverage > self.portfolio_limit.max_leverage:
            result.add_violation(
                f"{label} signal would exceed max leverage: {new_leverage:.2f}x > {self.portfolio_limit.max_leverage:.2f}x"
            )

    def check_portfolio(self) -> CheckResult:
        """Check overall portfolio risk limits.

        Returns:
            CheckResult with pass/fail and any violations.

        Examples:
            Check portfolio constraints after updating values::

                rm = RiskManager(initial_capital=100000.0, max_positions=20)
                rm.update_portfolio_value({}, 100000.0)
                result = rm.check_portfolio()
                assert result.passed

        """
        result = CheckResult(passed=True)

        if not self.risk_enabled:
            return result

        violations = self.portfolio_limit.check(
            self.positions,
            self.portfolio_risk.total_market_value,
            self.peak_value,
        )
        for v in violations:
            result.add_violation(v)

        return result

    def calculate_metrics(
        self,
        market_returns: pd.Series | None = None,
        periods_per_year: int = 252,
        risk_free_rate: float | None = None,
    ) -> RiskMetrics:
        """Calculate current risk metrics from equity curve.

        Args:
            market_returns: Optional benchmark returns for beta/alpha.
            periods_per_year: Number of periods per year used for annualization
                (default 252 for daily data).
            risk_free_rate: Annual risk-free rate used for risk-adjusted
                metrics. Defaults to the manager's configured rate.

        Returns:
            Computed RiskMetrics object.

        """
        equity_series = pd.Series(self.equity_curve)
        self.risk_metrics = calculate_all_metrics(
            equity_series,
            market_returns=market_returns,
            risk_free_rate=self.risk_free_rate if risk_free_rate is None else risk_free_rate,
            periods_per_year=periods_per_year,
        )
        return self.risk_metrics

    def is_short_position(self, symbol: str) -> bool:
        """Whether the tracked position for a symbol is a short.

        The direction of a position is the sign of its quantity: a positive
        quantity is a long, a negative quantity is a short. A symbol without
        a position, or with a flat one, is not a short.

        Args:
            symbol: Symbol to query.

        Returns:
            True when the position is a short, False otherwise.

        Examples:
            A short position is recognised by its negative quantity::

                from quant_trading.risk.manager import RiskManager
                from quant_trading.strategies.base import Position

                rm = RiskManager()
                rm.sync_position("AAPL", Position("AAPL", -100, 150.0, 150.0))
                assert rm.is_short_position("AAPL")

        """
        position = self.positions.get(symbol)
        return position is not None and position.quantity < 0

    def get_position_stop_loss(self, symbol: str) -> float | None:
        """Get stop loss price for a position.

        The level is direction aware. For a long position the stop sits
        below the average entry price (``avg_price * (1 - stop_loss_pct)``);
        for a short position it sits above it
        (``avg_price * (1 + stop_loss_pct)``), because a short loses when the
        price rises. If a trailing stop is active and is tighter (better) than
        the fixed stop, it will be used.

        Args:
            symbol: Symbol to query.

        Returns:
            Stop loss price, or None if no position/invalid price.

        """
        position = self.positions.get(symbol)
        if position is None or position.avg_price <= 0:
            return None
        if position.quantity < 0:
            fixed_stop = position.avg_price * (1 + self.position_limit.stop_loss_pct)
        else:
            fixed_stop = position.avg_price * (1 - self.position_limit.stop_loss_pct)

        trailing_stop = self.get_trailing_stop(symbol)
        if trailing_stop is None:
            return fixed_stop
        if position.quantity < 0:
            # A short is stopped out above its entry price, so the lower of
            # the two levels is the tighter one.
            return min(fixed_stop, trailing_stop)
        # A long is stopped out below its entry price, so the higher of the
        # two levels is the tighter one.
        return max(fixed_stop, trailing_stop)

    def get_trailing_stop(self, symbol: str) -> float | None:
        """Get the trailing stop price tracked for a position.

        A trailing stop follows the price of a position once it has moved far
        enough in its favour. It sits ``trailing_stop_pct`` away from the best
        price the position has reached since it was opened: below the highest
        price for a long, above the lowest price for a short. The stop only
        ratchets in the favourable direction, so it never gives back ground it
        has already locked in.

        Trailing stops are only tracked when ``trailing_stop_pct`` is greater
        than zero; they are disabled by default.

        Args:
            symbol: Symbol to query.

        Returns:
            Trailing stop price, or None when no trailing stop is active for
            the symbol.

        Examples:
            A trailing stop follows the best price of a long position::

                from quant_trading.risk.manager import RiskManager
                from quant_trading.strategies.base import Position

                rm = RiskManager(trailing_stop_pct=0.05)
                rm.sync_position("AAPL", Position("AAPL", 100, 100.0, 100.0))
                rm.update_trailing_stop("AAPL", 120.0)
                assert rm.get_trailing_stop("AAPL") == 114.0

        """
        return self._trailing_stops.get(symbol)

    def update_trailing_stop(self, symbol: str, price: float) -> float | None:
        """Feed a market price into the trailing stop tracker.

        The tracker records the best price the position has reached and
        moves the trailing stop accordingly. The stop only ratchets in the
        favourable direction: for a long it never moves down, for a short it
        never moves up.

        The trailing stop only starts to trail once the position has moved
        ``trailing_stop_activation_pct`` in its favour, measured from the
        average entry price. Before that the position keeps the trailing stop
        it already has.

        Args:
            symbol: Symbol whose position is tracked.
            price: Latest market price of the symbol.

        Returns:
            The trailing stop price after the update, or None when trailing
            stops are disabled or the symbol has no position.

        Examples:
            The trailing stop of a short follows the lowest price it reached::

                from quant_trading.risk.manager import RiskManager
                from quant_trading.strategies.base import Position

                rm = RiskManager(trailing_stop_pct=0.05)
                rm.sync_position("AAPL", Position("AAPL", -100, 100.0, 100.0))
                rm.update_trailing_stop("AAPL", 80.0)
                assert rm.get_trailing_stop("AAPL") == 84.0

        """
        if self.trailing_stop_pct <= 0 or price <= 0:
            return None

        position = self.positions.get(symbol)
        if position is None or position.quantity == 0 or position.avg_price <= 0:
            return None

        if position.quantity > 0:
            activation_price = position.avg_price * (1 + self.trailing_stop_activation_pct)
            if price < activation_price:
                return self._trailing_stops.get(symbol)
            high = self._trailing_highs.get(symbol)
            high = price if high is None else max(high, price)
            self._trailing_highs[symbol] = high
            stop = high * (1 - self.trailing_stop_pct)
        else:
            activation_price = position.avg_price * (1 - self.trailing_stop_activation_pct)
            if price > activation_price:
                return self._trailing_stops.get(symbol)
            low = self._trailing_lows.get(symbol)
            low = price if low is None else min(low, price)
            self._trailing_lows[symbol] = low
            stop = low * (1 + self.trailing_stop_pct)

        existing = self._trailing_stops.get(symbol)
        if existing is not None:
            if position.quantity > 0:
                stop = max(stop, existing)
            else:
                stop = min(stop, existing)

        self._trailing_stops[symbol] = stop
        return stop

    def _tracked_trailing_symbols(self) -> set[str]:
        """Symbols that currently carry trailing stop state.

        Returns:
            Set of symbols present in any of the trailing stop state
            dictionaries.

        """
        return set(self._trailing_stops) | set(self._trailing_highs) | set(self._trailing_lows)

    def _clear_trailing_state(self, symbol: str) -> None:
        """Drop the trailing stop state of a symbol.

        Args:
            symbol: Symbol whose trailing stop state is discarded.

        Returns:
            None.

        """
        self._trailing_stops.pop(symbol, None)
        self._trailing_highs.pop(symbol, None)
        self._trailing_lows.pop(symbol, None)

    def get_position_take_profit(self, symbol: str) -> float | None:
        """Get take profit price for a position.

        The level is direction aware. For a long position the target sits
        above the average entry price (``avg_price * (1 + take_profit_pct)``);
        for a short position it sits below it
        (``avg_price * (1 - take_profit_pct)``), because a short profits when
        the price falls.

        Args:
            symbol: Symbol to query.

        Returns:
            Take profit price, or None if no position/invalid price.

        """
        position = self.positions.get(symbol)
        if position is None or position.avg_price <= 0:
            return None
        if position.quantity < 0:
            return position.avg_price * (1 - self.position_limit.take_profit_pct)
        return position.avg_price * (1 + self.position_limit.take_profit_pct)

    def should_stop_loss(self, symbol: str, current_price: float) -> bool:
        """Check if position should trigger stop loss.

        The comparison follows the direction of the position: the stop is
        hit when the price falls to (or below) the stop level for a long,
        and when it rises to (or above) the stop level for a short.

        Args:
            symbol: Symbol to query.
            current_price: Current market price.

        Returns:
            True if stop loss triggered.

        """
        stop = self.get_position_stop_loss(symbol)
        if stop is None:
            return False
        if self.is_short_position(symbol):
            return bool(current_price >= stop)
        return bool(current_price <= stop)

    def should_take_profit(self, symbol: str, current_price: float) -> bool:
        """Check if position should trigger take profit.

        The comparison follows the direction of the position: the target is
        hit when the price rises to (or above) the target level for a long,
        and when it falls to (or below) the target level for a short.

        Args:
            symbol: Symbol to query.
            current_price: Current market price.

        Returns:
            True if take profit triggered.

        """
        tp = self.get_position_take_profit(symbol)
        if tp is None:
            return False
        if self.is_short_position(symbol):
            return bool(current_price <= tp)
        return bool(current_price >= tp)

    def reset(self) -> None:
        """Reset risk manager state.

        The portfolio state, the equity curve, the peak, the history and the
        last computed risk metrics are all cleared, so no value from the
        discarded run is left behind.

        Returns:
            None.

        """
        self.portfolio_risk = PortfolioRisk(
            total_market_value=self.initial_capital,
            cash=self.initial_capital,
            peak_value=self.initial_capital,
        )
        self.positions = {}
        self.equity_curve = [self.initial_capital]
        self.peak_value = self.initial_capital
        self.risk_metrics = None
        self.history = []
        for symbol in self._tracked_trailing_symbols():
            self._clear_trailing_state(symbol)

    def enable(self) -> None:
        """Enable risk management.

        Returns:
            None.

        """
        self.risk_enabled = True

    def disable(self) -> None:
        """Disable risk management.

        Returns:
            None.

        """
        self.risk_enabled = False
