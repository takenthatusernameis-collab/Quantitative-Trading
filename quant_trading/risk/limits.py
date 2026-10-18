"""Position and portfolio risk limits.

Examples:
    Check a single position against limits::

        from quant_trading.risk.limits import PositionLimit
        from quant_trading.strategies.base import Position

        limit = PositionLimit(max_size=0.1, max_value=10000.0)
        pos = Position(symbol="AAPL", quantity=100, entry_price=150.0)
        violations = limit.check(pos, portfolio_value=50000.0)
        assert len(violations) == 0

"""

from dataclasses import dataclass, field
from datetime import datetime

from quant_trading.strategies.base import Position


@dataclass
class PositionLimit:
    """Limits for a single position.

    Attributes:
        max_size: Maximum position size as fraction of portfolio (e.g., 0.1 = 10%).
        max_value: Maximum dollar value allowed for the position.
        stop_loss_pct: Default stop loss percentage (fraction).
        take_profit_pct: Default take profit percentage (fraction).

    Examples:
        Create position limits and check for violations::

            from quant_trading.risk.limits import PositionLimit
            from quant_trading.strategies.base import Position

            pl = PositionLimit(max_size=0.1, max_value=50000.0)
            pos = Position(symbol="AAPL", quantity=200, entry_price=100.0)
            violations = pl.check(pos, portfolio_value=100000.0)
            print(violations)

    """

    max_size: float = 0.1  # Max fraction of portfolio
    max_value: float = 50000.0  # Max dollar value
    stop_loss_pct: float = 0.05  # Stop loss percentage
    take_profit_pct: float = 0.15  # Take profit percentage

    def check(self, position: Position, portfolio_value: float) -> list[str]:
        """Check if position violates limits.

        Args:
            position: Position to evaluate for violations.
            portfolio_value: Total portfolio value used for percentage checks.

        Returns:
            List of violation messages (empty if none).

        """
        violations: list[str] = []

        if position.quantity == 0:
            return violations

        position_value = position.market_value
        position_pct = position_value / portfolio_value if portfolio_value > 0 else 0

        if position_pct > self.max_size:
            violations.append(f"Position size {position_pct:.2%} exceeds max {self.max_size:.2%}")

        if position_value > self.max_value:
            violations.append(
                f"Position value ${position_value:,.2f} exceeds max ${self.max_value:,.2f}"
            )

        return violations


@dataclass
class PortfolioLimit:
    """Limits for the entire portfolio.

    Attributes:
        max_positions: Maximum number of open positions allowed.
        max_position_size: Maximum single position size as fraction of portfolio.
        max_portfolio_risk: Maximum portfolio risk per trade as fraction.
        max_drawdown: Maximum drawdown before halt (fraction, e.g., 0.20 = 20%).
        max_leverage: Maximum portfolio leverage allowed.

    Examples:
        Check portfolio-level constraints::

            from quant_trading.risk.limits import PortfolioLimit
            from quant_trading.strategies.base import Position

            pl = PortfolioLimit(max_positions=20, max_drawdown=0.20)
            positions = {"AAPL": Position(symbol="AAPL", quantity=10, entry_price=150.0)}
            violations = pl.check(positions, portfolio_value=100000.0, peak_value=105000.0)
            print(violations)

    """

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
        """Check if portfolio violates limits.

        Args:
            positions: Dictionary mapping symbol to current position.
            portfolio_value: Current total portfolio value.
            peak_value: Peak portfolio value for drawdown calculation.

        Returns:
            List of violation messages (empty if none).

        """
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
                violations.append(f"Drawdown {drawdown:.2%} exceeds max {self.max_drawdown:.2%}")

        return violations


@dataclass
class CheckResult:
    """Result of a risk check.

    Attributes:
        passed: True if no violations occurred, False otherwise.
        violations: List of violation messages collected during checks.
        timestamp: Time at which the check result was created.

    Examples:
        Create a passing check result and add violations::

            from quant_trading.risk.limits import CheckResult

            res = CheckResult(passed=True)
            print(res.ok)
            res.add_violation("Position too large")
            assert not res.passed

    """

    passed: bool
    violations: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def ok(self) -> bool:
        """Check if result passed.

        Returns:
            True if passed, False otherwise.

        """
        return self.passed

    def add_violation(self, message: str) -> None:
        """Add a violation and mark result as failed.

        Args:
            message: Description of the violation.

        """
        self.violations.append(message)
        self.passed = False
