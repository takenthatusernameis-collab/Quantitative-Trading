"""Position and portfolio risk limits."""

from dataclasses import dataclass, field
from datetime import datetime

from quant_trading.strategies.base import Position


@dataclass
class PositionLimit:
    """Limits for a single position."""

    max_size: float = 0.1  # Max fraction of portfolio
    max_value: float = 50000.0  # Max dollar value
    stop_loss_pct: float = 0.05  # Stop loss percentage
    take_profit_pct: float = 0.15  # Take profit percentage

    def check(self, position: Position, portfolio_value: float) -> list[str]:
        """Check if position violates limits. Returns list of violations."""
        violations: list[str] = []

        if position.quantity == 0:
            return violations

        position_value = position.market_value
        position_pct = position_value / portfolio_value if portfolio_value > 0 else 0

        if position_pct > self.max_size:
            violations.append(
                f"Position size {position_pct:.2%} exceeds max {self.max_size:.2%}"
            )

        if position_value > self.max_value:
            violations.append(
                f"Position value ${position_value:,.2f} exceeds max ${self.max_value:,.2f}"
            )

        return violations


@dataclass
class PortfolioLimit:
    """Limits for the entire portfolio."""

    max_positions: int = 20
    max_position_size: float = 0.1  # Max single position as fraction
    max_portfolio_risk: float = 0.02  # Max risk per trade as fraction
    max_drawdown: float = 0.20  # Max drawdown before halt
    max_leverage: float = 1.0  # Max leverage

    def check(
        self,
        positions: dict[str, Position],
        portfolio_value: float,
        peak_value: float,
    ) -> list[str]:
        """Check if portfolio violates limits. Returns list of violations."""
        violations = []

        if len(positions) > self.max_positions:
            violations.append(
                f"Number of positions {len(positions)} exceeds max {self.max_positions}"
            )

        for symbol, pos in positions.items():
            if pos.quantity == 0:
                continue
            pos_pct = pos.market_value / portfolio_value if portfolio_value > 0 else 0
            if pos_pct > self.max_position_size:
                violations.append(
                    f"Position {symbol} size {pos_pct:.2%} exceeds max {self.max_position_size:.2%}"
                )

        if peak_value > 0:
            drawdown = (portfolio_value - peak_value) / peak_value
            if drawdown < -self.max_drawdown:
                violations.append(
                    f"Drawdown {drawdown:.2%} exceeds max {self.max_drawdown:.2%}"
                )

        return violations


@dataclass
class CheckResult:
    """Result of a risk check."""

    passed: bool
    violations: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def ok(self) -> bool:
        return self.passed

    def add_violation(self, message: str) -> None:
        self.violations.append(message)
        self.passed = False