"""Risk management orchestration."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from quant_trading.risk.limits import CheckResult, PortfolioLimit, PositionLimit
from quant_trading.risk.metrics import RiskMetrics, calculate_all_metrics
from quant_trading.strategies.base import Position, Signal


@dataclass
class PortfolioRisk:
    """Current portfolio risk state."""

    total_market_value: float = 0.0
    cash: float = 0.0
    positions_value: float = 0.0
    leverage: float = 0.0
    current_drawdown: float = 0.0
    peak_value: float = 0.0

    @property
    def total_value(self) -> float:
        return self.total_market_value


class RiskManager:
    """Manages risk for trading operations."""

    def __init__(
        self,
        initial_capital: float = 100000.0,
        max_position_size: float = 0.1,
        max_portfolio_risk: float = 0.02,
        max_drawdown: float = 0.20,
        max_positions: int = 20,
        stop_loss_pct: float = 0.05,
        take_profit_pct: float = 0.15,
    ):
        self.initial_capital = initial_capital
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
        """Update portfolio value and track equity curve."""
        self.positions = positions
        positions_value = sum(p.market_value for p in positions.values())
        total_value = cash + positions_value

        self.portfolio_risk = PortfolioRisk(
            total_market_value=total_value,
            cash=cash,
            positions_value=positions_value,
            leverage=positions_value / total_value if total_value > 0 else 0,
            current_drawdown=(
                (total_value - self.peak_value) / self.peak_value if self.peak_value > 0 else 0
            ),
            peak_value=self.peak_value,
        )

        self.equity_curve.append(total_value)
        self.peak_value = max(self.peak_value, total_value)

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
        """Check if a trading signal passes risk limits."""
        result = CheckResult(passed=True)

        if not self.risk_enabled:
            return result

        value = portfolio_value or self.portfolio_risk.total_market_value
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
        """Check overall portfolio risk limits."""
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

    def calculate_metrics(self, market_returns: pd.Series | None = None) -> RiskMetrics:
        """Calculate current risk metrics from equity curve."""
        equity_series = pd.Series(self.equity_curve)
        self.risk_metrics = calculate_all_metrics(
            equity_series,
            market_returns=market_returns,
            risk_free_rate=0.02,
        )
        return self.risk_metrics

    def get_position_stop_loss(self, symbol: str) -> float | None:
        """Get stop loss price for a position."""
        position = self.positions.get(symbol)
        if position is None or position.avg_price <= 0:
            return None
        return position.avg_price * (1 - self.position_limit.stop_loss_pct)

    def get_position_take_profit(self, symbol: str) -> float | None:
        """Get take profit price for a position."""
        position = self.positions.get(symbol)
        if position is None or position.avg_price <= 0:
            return None
        return position.avg_price * (1 + self.position_limit.take_profit_pct)

    def should_stop_loss(self, symbol: str, current_price: float) -> bool:
        """Check if position should trigger stop loss."""
        stop = self.get_position_stop_loss(symbol)
        return stop is not None and current_price <= stop

    def should_take_profit(self, symbol: str, current_price: float) -> bool:
        """Check if position should trigger take profit."""
        tp = self.get_position_take_profit(symbol)
        return tp is not None and current_price >= tp

    def reset(self) -> None:
        """Reset risk manager state."""
        self.portfolio_risk = PortfolioRisk(
            total_market_value=self.initial_capital,
            cash=self.initial_capital,
            peak_value=self.initial_capital,
        )
        self.positions = {}
        self.equity_curve = [self.initial_capital]
        self.peak_value = self.initial_capital
        self.history = []

    def enable(self) -> None:
        """Enable risk management."""
        self.risk_enabled = True

    def disable(self) -> None:
        """Disable risk management."""
        self.risk_enabled = False
