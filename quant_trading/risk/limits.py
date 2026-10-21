"""Position and portfolio risk limits.

Examples:
    Check a single position against limits::

        >>> from quant_trading.risk.limits import PositionLimit
        >>> from quant_trading.strategies.base import Position
        >>> limit = PositionLimit(max_size=0.1, max_value=10000.0)
        >>> pos = Position(symbol="AAPL", quantity=10, avg_price=150.0, current_price=150.0)
        >>> limit.check(pos, portfolio_value=50000.0)
        []

"""

from dataclasses import dataclass, field
from datetime import datetime

from quant_trading.strategies.base import Position


def gross_exposure(position: Position) -> float:
    """Compute the gross exposure of a single position.

    Gross exposure is the absolute market value of a position, so a short
    position counts as a commitment of the same size as a long position of
    equal size. Concentration limits are measured on this gross figure: a
    signed market value would let a short position pass the limit simply
    because its market value is negative.

    Args:
        position: Position to measure.

    Returns:
        Absolute market value of the position.

    """
    return abs(position.market_value)


@dataclass
class PositionLimit:
    """Limits for a single position.

    Limits are measured on the gross exposure of the position, so a short
    position is limited exactly like a long position of the same size.

    Attributes:
        max_size: Maximum position size as fraction of portfolio (e.g., 0.1 = 10%).
        max_value: Maximum dollar value allowed for the position.
        stop_loss_pct: Default stop loss percentage (fraction).
        take_profit_pct: Default take profit percentage (fraction).

    Examples:
        Create position limits and check for violations::

            >>> from quant_trading.risk.limits import PositionLimit
            >>> from quant_trading.strategies.base import Position
            >>> pl = PositionLimit(max_size=0.1, max_value=50000.0)
            >>> pos = Position(symbol="AAPL", quantity=200, avg_price=100.0, current_price=110.0)
            >>> pl.check(pos, portfolio_value=100000.0)
            ['Position size 22.00% exceeds max 10.00%']

        A short position is limited on its gross exposure too::

            >>> short = Position(symbol="AAPL", quantity=-200, avg_price=100.0, current_price=100.0)
            >>> pl.check(short, portfolio_value=100000.0)
            ['Position size 20.00% exceeds max 10.00%']

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

        position_value = gross_exposure(position)
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

    The per-position size limit is measured on the gross exposure of each
    position, so a short position is limited exactly like a long position of
    the same size.

    Attributes:
        max_positions: Maximum number of open positions allowed.
        max_position_size: Maximum single position size as fraction of portfolio.
        max_portfolio_risk: Maximum fraction of the portfolio value that may
            be at risk at any time. The risk of a position is the loss that
            would be realised if its planned stop loss were hit; the portfolio
            risk is the sum of that risk over all open positions.
        max_drawdown: Maximum drawdown before new positions are stopped (fraction,
            e.g., 0.20 = 20%). A signal that adds exposure is rejected while the
            portfolio is in a breach of it.
        max_leverage: Maximum gross exposure as a multiple of the portfolio
            value (1.0 = fully invested with no borrowing).
        stop_loss_pct: Stop loss distance used to size the risk of each open
            position (fraction, e.g., 0.05 = 5%).

    Examples:
        Check portfolio-level constraints::

            >>> from quant_trading.risk.limits import PortfolioLimit
            >>> from quant_trading.strategies.base import Position
            >>> pl = PortfolioLimit(max_positions=20, max_drawdown=0.20)
            >>> positions = {
            ...     "AAPL": Position(symbol="AAPL", quantity=10, avg_price=150.0, current_price=150.0)
            ... }
            >>> pl.check(positions, portfolio_value=100000.0, peak_value=105000.0)
            []

        Too much open risk at once is reported::

            >>> pl = PortfolioLimit(max_portfolio_risk=0.02, max_position_size=1.0)
            >>> positions = {
            ...     "AAPL": Position(symbol="AAPL", quantity=400, avg_price=150.0, current_price=150.0)
            ... }
            >>> pl.check(positions, portfolio_value=100000.0, peak_value=100000.0)
            ['Portfolio risk 3.00% exceeds max 2.00%']

        Gross exposure above the leverage limit is reported::

            >>> pl = PortfolioLimit(max_position_size=1.0, max_portfolio_risk=0.10, max_leverage=1.0)
            >>> positions = {
            ...     "AAPL": Position(symbol="AAPL", quantity=400, avg_price=150.0, current_price=150.0),
            ...     "MSFT": Position(symbol="MSFT", quantity=200, avg_price=300.0, current_price=300.0),
            ... }
            >>> pl.check(positions, portfolio_value=100000.0, peak_value=100000.0)
            ['Portfolio leverage 1.20x exceeds max 1.00x']

        A short position is limited on its gross exposure, like a long::

            >>> pl = PortfolioLimit(max_position_size=0.1, max_portfolio_risk=1.0, max_leverage=1.0)
            >>> positions = {
            ...     "AAPL": Position(symbol="AAPL", quantity=-400, avg_price=150.0, current_price=150.0)
            ... }
            >>> pl.check(positions, portfolio_value=100000.0, peak_value=100000.0)
            ['Position AAPL size 60.00% exceeds max 10.00%']

    """

    max_positions: int = 20
    max_position_size: float = 0.1  # Max single position as fraction
    max_portfolio_risk: float = 0.02  # Max open risk as fraction of portfolio
    max_drawdown: float = 0.20  # Max drawdown before new positions are stopped
    max_leverage: float = 1.0  # Max gross exposure as multiple of portfolio value
    stop_loss_pct: float = 0.05  # Stop loss distance used to size position risk

    def position_risk(self, position: Position) -> float:
        """Compute the risk committed by a single position.

        The risk of a position is the loss that would be realised if its
        planned stop loss were hit: the position size multiplied by the entry
        price and by the stop loss distance. Measuring from the entry price
        keeps the risk committed to a trade stable while the market moves.
        Positions without a usable entry price fall back to the current price.

        Args:
            position: Position to size the risk of.

        Returns:
            Dollar amount at risk for the position (0.0 for flat positions).

        """
        quantity = position.quantity
        if quantity == 0:
            return 0.0

        basis = position.avg_price if position.avg_price > 0 else position.current_price
        if basis <= 0:
            return 0.0

        return abs(quantity) * basis * self.stop_loss_pct

    def portfolio_risk(self, positions: dict[str, Position]) -> float:
        """Compute the total open risk of the portfolio.

        Args:
            positions: Dictionary mapping symbol to current position.

        Returns:
            Sum of the risk of every open position, in dollars.

        """
        return sum(self.position_risk(pos) for pos in positions.values())

    def portfolio_risk_pct(self, positions: dict[str, Position], portfolio_value: float) -> float:
        """Compute the total open risk as a fraction of the portfolio value.

        Args:
            positions: Dictionary mapping symbol to current position.
            portfolio_value: Current total portfolio value.

        Returns:
            Open risk as a fraction of the portfolio value (0.0 when the
            portfolio value is not positive).

        """
        if portfolio_value <= 0:
            return 0.0
        return self.portfolio_risk(positions) / portfolio_value

    def leverage(self, positions: dict[str, Position], portfolio_value: float) -> float:
        """Compute the gross exposure of the portfolio.

        Gross exposure sums the absolute market value of every open position,
        so an equally sized long and short do not cancel each other out.

        Args:
            positions: Dictionary mapping symbol to current position.
            portfolio_value: Current total portfolio value.

        Returns:
            Gross exposure as a multiple of the portfolio value (0.0 when the
            portfolio value is not positive).

        """
        if portfolio_value <= 0:
            return 0.0
        gross = sum(gross_exposure(pos) for pos in positions.values())
        return gross / portfolio_value

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
        violations: list[str] = []

        if len(positions) > self.max_positions:
            violations.append(
                f"Number of positions {len(positions)} exceeds max {self.max_positions}"
            )

        for symbol, pos in positions.items():
            if pos.quantity == 0:
                continue
            pos_pct = gross_exposure(pos) / portfolio_value if portfolio_value > 0 else 0
            if pos_pct > self.max_position_size:
                violations.append(
                    f"Position {symbol} size {pos_pct:.2%} exceeds max {self.max_position_size:.2%}"
                )

        if peak_value > 0:
            drawdown = (portfolio_value - peak_value) / peak_value
            if drawdown < -self.max_drawdown:
                violations.append(f"Drawdown {drawdown:.2%} exceeds max {self.max_drawdown:.2%}")

        risk_pct = self.portfolio_risk_pct(positions, portfolio_value)
        if risk_pct > self.max_portfolio_risk:
            violations.append(
                f"Portfolio risk {risk_pct:.2%} exceeds max {self.max_portfolio_risk:.2%}"
            )

        leverage = self.leverage(positions, portfolio_value)
        if leverage > self.max_leverage:
            violations.append(
                f"Portfolio leverage {leverage:.2f}x exceeds max {self.max_leverage:.2f}x"
            )

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
