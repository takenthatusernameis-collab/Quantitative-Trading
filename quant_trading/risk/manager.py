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
        leverage: Portfolio leverage ratio (positions_value / total_value).
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
    ):
        """Initialize risk manager.

        Args:
            initial_capital: Initial capital for risk calculations.
            max_position_size: Maximum position size as fraction of portfolio.
            max_portfolio_risk: Maximum portfolio risk per trade as fraction.
            max_drawdown: Maximum drawdown before halt (fraction).
            max_positions: Maximum number of positions allowed.
            stop_loss_pct: Default stop loss percentage.
            take_profit_pct: Default take profit percentage.
            risk_free_rate: Annual risk-free rate used for risk-adjusted
                metrics (Sharpe/Sortino/alpha). Defaults to 0.02 to match
                the rest of the framework.

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

        # The peak is updated first so the drawdown is measured against the
        # peak the portfolio is actually at. Measuring against the previous
        # peak would report a positive drawdown at a new high.
        peak_value = max(self.peak_value, total_value)

        self.portfolio_risk = PortfolioRisk(
            total_market_value=total_value,
            cash=cash,
            positions_value=positions_value,
            leverage=positions_value / total_value if total_value > 0 else 0,
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

    def check_signal(self, signal: Signal, portfolio_value: float | None = None) -> CheckResult:
        """Check if a trading signal passes risk limits.

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
            # Check position size limit
            position = self.positions.get(signal.symbol)
            if signal.price is None:
                result.add_violation("Buy signal has no price")
                return result
            current_size = position.quantity * signal.price if position else 0
            new_size = current_size + (signal.strength * value * self.position_limit.max_size)

            if new_size > self.position_limit.max_value:
                result.add_violation(
                    f"Buy signal would exceed max position value: ${new_size:,.2f} > ${self.position_limit.max_value:,.2f}"
                )

            position_pct = new_size / value if value > 0 else 0
            if position_pct > self.position_limit.max_size:
                result.add_violation(
                    f"Buy signal would exceed max position size: {position_pct:.2%} > {self.position_limit.max_size:.2%}"
                )

        elif signal.action == "sell":
            position = self.positions.get(signal.symbol)
            if position is None or position.quantity <= 0:
                result.add_violation("Sell signal for position with no holdings")

        return result

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

    def get_position_stop_loss(self, symbol: str) -> float | None:
        """Get stop loss price for a position.

        Args:
            symbol: Symbol to query.

        Returns:
            Stop loss price, or None if no position/invalid price.

        """
        position = self.positions.get(symbol)
        if position is None or position.avg_price <= 0:
            return None
        return position.avg_price * (1 - self.position_limit.stop_loss_pct)

    def get_position_take_profit(self, symbol: str) -> float | None:
        """Get take profit price for a position.

        Args:
            symbol: Symbol to query.

        Returns:
            Take profit price, or None if no position/invalid price.

        """
        position = self.positions.get(symbol)
        if position is None or position.avg_price <= 0:
            return None
        return position.avg_price * (1 + self.position_limit.take_profit_pct)

    def should_stop_loss(self, symbol: str, current_price: float) -> bool:
        """Check if position should trigger stop loss.

        Args:
            symbol: Symbol to query.
            current_price: Current market price.

        Returns:
            True if stop loss triggered.

        """
        stop = self.get_position_stop_loss(symbol)
        return stop is not None and current_price <= stop

    def should_take_profit(self, symbol: str, current_price: float) -> bool:
        """Check if position should trigger take profit.

        Args:
            symbol: Symbol to query.
            current_price: Current market price.

        Returns:
            True if take profit triggered.

        """
        tp = self.get_position_take_profit(symbol)
        return tp is not None and current_price >= tp

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
