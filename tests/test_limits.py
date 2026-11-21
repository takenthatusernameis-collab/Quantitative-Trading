"""Tests for risk limits."""

import pytest

from quant_trading.risk.limits import (
    CheckResult,
    PortfolioLimit,
    PositionLimit,
    _finite,
    gross_exposure,
)
from quant_trading.strategies.base import Position


class TestPositionLimit:
    """Tests for PositionLimit class."""

    def test_initialization_defaults(self) -> None:
        """Test default initialization."""
        limit = PositionLimit()
        assert limit.max_size == 0.1
        assert limit.max_value == 50000.0
        assert limit.stop_loss_pct == 0.05
        assert limit.take_profit_pct == 0.15

    def test_initialization_custom(self) -> None:
        """Test custom initialization."""
        limit = PositionLimit(
            max_size=0.2,
            max_value=100000.0,
            stop_loss_pct=0.10,
            take_profit_pct=0.20,
        )
        assert limit.max_size == 0.2
        assert limit.max_value == 100000.0
        assert limit.stop_loss_pct == 0.10
        assert limit.take_profit_pct == 0.20

    def test_check_no_position(self) -> None:
        """Test check with zero quantity position."""
        limit = PositionLimit()
        position = Position(symbol="AAPL", quantity=0.0, avg_price=150.0, current_price=155.0)
        violations = limit.check(position, 100000.0)
        assert violations == []

    def test_check_position_size_violation(self) -> None:
        """Test check detects position size violation."""
        limit = PositionLimit(max_size=0.1, max_value=50000.0)
        # Position worth 20% of portfolio
        position = Position(symbol="AAPL", quantity=200, avg_price=150.0, current_price=100.0)
        violations = limit.check(position, 100000.0)
        assert len(violations) == 1
        assert "exceeds max" in violations[0]
        assert "20.00%" in violations[0] or "20%" in violations[0]

    def test_check_position_value_violation(self) -> None:
        """Test check detects position value violation."""
        limit = PositionLimit(max_size=0.5, max_value=10000.0)
        # Position worth $15,000, max is $10,000
        position = Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=150.0)
        violations = limit.check(position, 100000.0)
        assert len(violations) == 1
        assert "exceeds max" in violations[0]
        assert "$15,000.00" in violations[0]

    def test_check_both_violations(self) -> None:
        """Test check detects both violations."""
        limit = PositionLimit(max_size=0.1, max_value=10000.0)
        # Position worth $20,000 (20% of portfolio), max size 10%, max value $10,000
        position = Position(symbol="AAPL", quantity=200, avg_price=100.0, current_price=100.0)
        violations = limit.check(position, 100000.0)
        assert len(violations) == 2

    def test_check_ok(self) -> None:
        """Test check passes for valid position."""
        limit = PositionLimit(max_size=0.2, max_value=50000.0)
        position = Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=155.0)
        violations = limit.check(position, 100000.0)
        assert violations == []


class TestPortfolioLimit:
    """Tests for PortfolioLimit class."""

    def test_initialization_defaults(self) -> None:
        """Test default initialization."""
        limit = PortfolioLimit()
        assert limit.max_positions == 20
        assert limit.max_position_size == 0.1
        assert limit.max_portfolio_risk == 0.02
        assert limit.max_drawdown == 0.20
        assert limit.max_leverage == 1.0

    def test_initialization_custom(self) -> None:
        """Test custom initialization."""
        limit = PortfolioLimit(
            max_positions=10,
            max_position_size=0.15,
            max_portfolio_risk=0.05,
            max_drawdown=0.15,
            max_leverage=2.0,
        )
        assert limit.max_positions == 10
        assert limit.max_position_size == 0.15
        assert limit.max_portfolio_risk == 0.05
        assert limit.max_drawdown == 0.15
        assert limit.max_leverage == 2.0

    def test_check_too_many_positions(self) -> None:
        """Test check detects too many positions."""
        limit = PortfolioLimit(max_positions=2, max_position_size=1.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=155.0),
            "MSFT": Position(symbol="MSFT", quantity=50, avg_price=300.0, current_price=310.0),
            "GOOGL": Position(symbol="GOOGL", quantity=20, avg_price=140.0, current_price=145.0),
        }
        violations = limit.check(positions, 100000.0, 100000.0)
        assert len(violations) == 1
        assert "exceeds max" in violations[0]
        assert "3" in violations[0]

    def test_check_position_size_violation(self) -> None:
        """Test check detects individual position size violation."""
        # The risk budget is raised so this test isolates the position size
        # check; the portfolio risk limit has its own tests below.
        limit = PortfolioLimit(max_positions=10, max_position_size=0.1, max_portfolio_risk=0.05)
        # AAPL is 31% of portfolio, MSFT is 15.5%
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=200, avg_price=150.0, current_price=155.0),
            "MSFT": Position(symbol="MSFT", quantity=50, avg_price=300.0, current_price=310.0),
        }
        violations = limit.check(positions, 100000.0, 100000.0)
        assert len(violations) == 2
        assert any("AAPL" in v for v in violations)
        assert any("MSFT" in v for v in violations)
        assert all("exceeds max" in v for v in violations)

    def test_check_drawdown_violation(self) -> None:
        """Test check detects drawdown violation."""
        limit = PortfolioLimit(max_drawdown=0.10)  # 10% max drawdown
        positions: dict[str, Position] = {}
        # Portfolio dropped from 100k to 85k = 15% drawdown
        violations = limit.check(positions, 85000.0, 100000.0)
        assert len(violations) == 1
        assert "Drawdown" in violations[0]
        assert "exceeds max" in violations[0]

    def test_check_no_drawdown_violation(self) -> None:
        """Test check passes when drawdown within limits."""
        limit = PortfolioLimit(max_drawdown=0.20)
        positions: dict[str, Position] = {}
        # Portfolio dropped from 100k to 90k = 10% drawdown
        violations = limit.check(positions, 90000.0, 100000.0)
        assert violations == []

    def test_check_drawdown_limit_of_zero_is_disabled(self) -> None:
        """A max_drawdown of 0.0 disables the drawdown limit (README)."""
        limit = PortfolioLimit(max_drawdown=0.0)
        # A 90% drawdown must not be reported when the limit is disabled.
        violations = limit.check({}, 10000.0, 100000.0)
        assert violations == []

    def test_check_skips_drawdown_when_peak_zero(self) -> None:
        """The drawdown check is skipped when peak_value <= 0 (72->77)."""
        limit = PortfolioLimit(max_drawdown=0.10)
        positions: dict[str, Position] = {}
        violations = limit.check(positions, 85000.0, 0.0)
        assert violations == []

    def test_check_no_positions_with_peak(self) -> None:
        """With no positions and a positive peak, the loop body is skipped and
        the drawdown check is still evaluated (covers the peak>0 branch)."""
        limit = PortfolioLimit(max_drawdown=0.20)
        violations = limit.check({}, 90000.0, 100000.0)
        assert violations == []

    def test_check_ok(self) -> None:
        """Test check passes for valid portfolio."""
        limit = PortfolioLimit()
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=50, avg_price=150.0, current_price=155.0),
            "MSFT": Position(symbol="MSFT", quantity=30, avg_price=300.0, current_price=310.0),
        }
        violations = limit.check(positions, 100000.0, 100000.0)
        assert violations == []

    def test_check_skips_zero_quantity_position(self) -> None:
        """Test check skips positions with zero quantity."""
        limit = PortfolioLimit(max_position_size=0.1)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=50, avg_price=150.0, current_price=155.0),
            "MSFT": Position(symbol="MSFT", quantity=0, avg_price=300.0, current_price=310.0),
        }
        violations = limit.check(positions, 100000.0, 100000.0)
        assert violations == []

    def test_check_zero_quantity_with_other_violations(self) -> None:
        """Test check handles zero quantity position alongside violations."""
        limit = PortfolioLimit(max_positions=2, max_position_size=0.1)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=200, avg_price=150.0, current_price=155.0),
            "MSFT": Position(symbol="MSFT", quantity=0, avg_price=300.0, current_price=310.0),
            "GOOGL": Position(symbol="GOOGL", quantity=50, avg_price=140.0, current_price=145.0),
        }
        violations = limit.check(positions, 100000.0, 100000.0)
        assert len(violations) == 2
        assert any("exceeds max" in v and "positions" in v for v in violations)
        assert any("AAPL" in v for v in violations)


class TestPortfolioLimitPortfolioRisk:
    """Tests for the portfolio risk limit (total open risk at once)."""

    def test_defaults_include_stop_loss_pct(self) -> None:
        """The stop loss distance used to size position risk has a default."""
        assert PortfolioLimit().stop_loss_pct == 0.05

    def test_risk_within_limit(self) -> None:
        """Open risk below the budget produces no violation."""
        limit = PortfolioLimit(max_portfolio_risk=0.02, max_position_size=1.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=150.0),
        }
        # 100 shares * $150 entry * 5% stop = $750 at risk = 0.75% of portfolio
        assert limit.portfolio_risk(positions) == pytest.approx(750.0)
        assert limit.portfolio_risk_pct(positions, 100000.0) == pytest.approx(0.0075)
        assert limit.check(positions, 100000.0, 100000.0) == []

    def test_risk_violation(self) -> None:
        """Open risk above the budget is reported."""
        limit = PortfolioLimit(max_portfolio_risk=0.02, max_position_size=1.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=400, avg_price=150.0, current_price=150.0),
        }
        # 400 shares * $150 entry * 5% stop = $3000 at risk = 3% of portfolio
        violations = limit.check(positions, 100000.0, 100000.0)
        assert len(violations) == 1
        assert "Portfolio risk 3.00%" in violations[0]
        assert "exceeds max 2.00%" in violations[0]

    def test_risk_sums_across_positions(self) -> None:
        """The risk of several positions is summed."""
        limit = PortfolioLimit(max_portfolio_risk=1.0, max_position_size=1.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=150.0),
            "MSFT": Position(symbol="MSFT", quantity=50, avg_price=300.0, current_price=300.0),
        }
        # 100 * 150 * 5% + 50 * 300 * 5% = $1500
        assert limit.portfolio_risk(positions) == pytest.approx(1500.0)

    def test_risk_measured_from_entry_price(self) -> None:
        """The risk committed to a trade does not drift with the market price."""
        limit = PortfolioLimit(max_portfolio_risk=1.0, max_position_size=1.0)
        position = Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=300.0)
        assert limit.position_risk(position) == pytest.approx(750.0)

    def test_risk_of_short_position(self) -> None:
        """A short risks the same amount as a long of equal size."""
        limit = PortfolioLimit(max_portfolio_risk=1.0, max_position_size=1.0)
        long_pos = Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=150.0)
        short_pos = Position(symbol="AAPL", quantity=-100, avg_price=150.0, current_price=150.0)
        assert limit.position_risk(short_pos) == pytest.approx(limit.position_risk(long_pos))

    def test_risk_ignores_flat_positions(self) -> None:
        """Flat positions contribute no risk."""
        limit = PortfolioLimit(max_portfolio_risk=0.0, max_position_size=1.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=0, avg_price=150.0, current_price=150.0),
        }
        assert limit.portfolio_risk(positions) == 0.0
        assert limit.check(positions, 100000.0, 100000.0) == []

    def test_risk_falls_back_to_current_price(self) -> None:
        """A position without an entry price is sized from its current price."""
        limit = PortfolioLimit(max_portfolio_risk=1.0, max_position_size=1.0)
        position = Position(symbol="AAPL", quantity=100, avg_price=0.0, current_price=200.0)
        assert limit.position_risk(position) == pytest.approx(1000.0)

    def test_position_risk_zero_basis_returns_zero(self) -> None:
        """A position with no usable entry or current price commits no risk."""
        limit = PortfolioLimit(max_portfolio_risk=1.0, max_position_size=1.0)
        position = Position(symbol="AAPL", quantity=100, avg_price=0.0, current_price=0.0)
        assert limit.position_risk(position) == pytest.approx(0.0)

    def test_risk_with_zero_portfolio_value(self) -> None:
        """A non-positive portfolio value is handled without dividing by zero."""
        limit = PortfolioLimit(max_portfolio_risk=0.0, max_position_size=1.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=150.0),
        }
        assert limit.portfolio_risk_pct(positions, 0.0) == 0.0
        assert limit.check(positions, 0.0, 0.0) == []


class TestPortfolioLimitLeverage:
    """Tests for the leverage limit (gross exposure)."""

    def test_leverage_within_limit(self) -> None:
        """Gross exposure below the limit produces no violation."""
        limit = PortfolioLimit(max_leverage=1.0, max_position_size=1.0, max_portfolio_risk=1.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=400, avg_price=150.0, current_price=150.0),
        }
        assert limit.leverage(positions, 100000.0) == pytest.approx(0.6)
        assert limit.check(positions, 100000.0, 100000.0) == []

    def test_leverage_violation(self) -> None:
        """Gross exposure above the limit is reported."""
        limit = PortfolioLimit(max_leverage=1.0, max_position_size=1.0, max_portfolio_risk=1.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=400, avg_price=150.0, current_price=150.0),
            "MSFT": Position(symbol="MSFT", quantity=200, avg_price=300.0, current_price=300.0),
        }
        assert limit.leverage(positions, 100000.0) == pytest.approx(1.2)
        violations = limit.check(positions, 100000.0, 100000.0)
        assert len(violations) == 1
        assert "Portfolio leverage 1.20x" in violations[0]
        assert "exceeds max 1.00x" in violations[0]

    def test_leverage_is_gross_not_net(self) -> None:
        """An offsetting short does not cancel the long for leverage purposes."""
        limit = PortfolioLimit(max_leverage=1.0, max_position_size=10.0, max_portfolio_risk=1.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=400, avg_price=150.0, current_price=150.0),
            "MSFT": Position(symbol="MSFT", quantity=-400, avg_price=150.0, current_price=150.0),
        }
        # Net exposure is zero, but gross exposure is 120% of the portfolio
        assert limit.leverage(positions, 100000.0) == pytest.approx(1.2)
        violations = limit.check(positions, 100000.0, 100000.0)
        assert any("Portfolio leverage 1.20x" in v for v in violations)

    def test_higher_leverage_limit_allows_exposure(self) -> None:
        """A leverage limit above the exposure allows the same portfolio."""
        limit = PortfolioLimit(max_leverage=2.0, max_position_size=1.0, max_portfolio_risk=1.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=400, avg_price=150.0, current_price=150.0),
            "MSFT": Position(symbol="MSFT", quantity=200, avg_price=300.0, current_price=300.0),
        }
        assert limit.check(positions, 100000.0, 100000.0) == []

    def test_leverage_with_zero_portfolio_value(self) -> None:
        """A non-positive portfolio value is handled without dividing by zero."""
        limit = PortfolioLimit(max_leverage=0.0, max_position_size=1.0, max_portfolio_risk=1.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=150.0),
        }
        assert limit.leverage(positions, 0.0) == 0.0
        assert limit.check(positions, 0.0, 0.0) == []


class TestPositionLimitGrossExposure:
    """Tests that position limits are measured on gross exposure."""

    def test_short_position_size_violation(self) -> None:
        """A short position is limited like a long position of the same size."""
        limit = PositionLimit(max_size=0.1, max_value=50000.0)
        short = Position(symbol="AAPL", quantity=-200, avg_price=100.0, current_price=100.0)
        violations = limit.check(short, 100000.0)
        assert len(violations) == 1
        assert "20.00%" in violations[0]
        assert "exceeds max" in violations[0]

    def test_short_position_value_violation(self) -> None:
        """The dollar value limit applies to a short position as well."""
        limit = PositionLimit(max_size=0.5, max_value=10000.0)
        short = Position(symbol="AAPL", quantity=-100, avg_price=150.0, current_price=150.0)
        violations = limit.check(short, 100000.0)
        assert len(violations) == 1
        assert "$15,000.00" in violations[0]
        assert "exceeds max" in violations[0]

    def test_short_position_within_limits(self) -> None:
        """A small short position produces no violation."""
        limit = PositionLimit(max_size=0.1, max_value=50000.0)
        short = Position(symbol="AAPL", quantity=-50, avg_price=150.0, current_price=150.0)
        assert limit.check(short, 100000.0) == []

    def test_long_and_short_of_equal_size_are_equivalent(self) -> None:
        """The same limits apply to a long and a short of the same size."""
        limit = PositionLimit(max_size=0.1, max_value=50000.0)
        long = Position(symbol="AAPL", quantity=200, avg_price=100.0, current_price=100.0)
        short = Position(symbol="AAPL", quantity=-200, avg_price=100.0, current_price=100.0)
        assert limit.check(long, 100000.0) == limit.check(short, 100000.0)

    def test_gross_exposure_helper(self) -> None:
        """The gross exposure of a position is its absolute market value."""
        long = Position(symbol="AAPL", quantity=200, avg_price=100.0, current_price=100.0)
        short = Position(symbol="AAPL", quantity=-200, avg_price=100.0, current_price=100.0)
        assert gross_exposure(long) == pytest.approx(20000.0)
        assert gross_exposure(short) == pytest.approx(20000.0)


class TestPortfolioLimitGrossExposure:
    """Tests that the portfolio position size limit uses gross exposure."""

    def test_short_position_size_violation(self) -> None:
        """An oversized short is reported like an oversized long."""
        limit = PortfolioLimit(
            max_position_size=0.1,
            max_portfolio_risk=1.0,
            max_leverage=10.0,
        )
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=-400, avg_price=150.0, current_price=150.0),
        }
        violations = limit.check(positions, 100000.0, 100000.0)
        assert len(violations) == 1
        assert "AAPL" in violations[0]
        assert "60.00%" in violations[0]

    def test_short_position_within_limits(self) -> None:
        """A small short position produces no violation."""
        limit = PortfolioLimit(
            max_position_size=0.1,
            max_portfolio_risk=1.0,
            max_leverage=10.0,
        )
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=-50, avg_price=150.0, current_price=150.0),
        }
        assert limit.check(positions, 100000.0, 100000.0) == []

    def test_offsetting_short_does_not_hide_the_long(self) -> None:
        """A short does not offset a long for the per-position size limit."""
        limit = PortfolioLimit(
            max_position_size=0.1,
            max_portfolio_risk=1.0,
            max_leverage=10.0,
        )
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=400, avg_price=150.0, current_price=150.0),
            "MSFT": Position(symbol="MSFT", quantity=-400, avg_price=150.0, current_price=150.0),
        }
        violations = limit.check(positions, 100000.0, 100000.0)
        assert len(violations) == 2
        assert any("AAPL" in v for v in violations)
        assert any("MSFT" in v for v in violations)


class TestCheckResult:
    """Tests for CheckResult class."""

    def test_initialization_passed(self) -> None:
        """Test initialization with passed=True."""
        result = CheckResult(passed=True)
        assert result.passed is True
        assert result.violations == []
        assert result.ok is True
        assert result.timestamp is not None

    def test_initialization_failed(self) -> None:
        """Test initialization with passed=False."""
        result = CheckResult(passed=False, violations=["Error 1", "Error 2"])
        assert result.passed is False
        assert result.violations == ["Error 1", "Error 2"]
        assert result.ok is False

    def test_add_violation(self) -> None:
        """Test add_violation sets passed to False."""
        result = CheckResult(passed=True)
        result.add_violation("New violation")
        assert result.passed is False
        assert result.violations == ["New violation"]
        assert result.ok is False

    def test_add_multiple_violations(self) -> None:
        """Test adding multiple violations."""
        result = CheckResult(passed=True)
        result.add_violation("Violation 1")
        result.add_violation("Violation 2")
        assert result.passed is False
        assert result.violations == ["Violation 1", "Violation 2"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestPortfolioLimitEdgeCases:
    def test_portfolio_value_nonpositive_returns_zero_risk_and_leverage(self) -> None:
        pl = PortfolioLimit()
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=10, avg_price=100.0, current_price=100.0)
        }
        assert pl.portfolio_risk_pct(positions, 0.0) == 0.0
        assert pl.leverage(positions, -5.0) == 0.0

    def test_position_risk_zero_basis_returns_zero(self) -> None:
        pl = PortfolioLimit()
        pos = Position(symbol="AAPL", quantity=10, avg_price=0.0, current_price=0.0)
        assert pl.position_risk(pos) == 0.0

    def test_check_flat_position_skipped(self) -> None:
        pl = PortfolioLimit()
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=0, avg_price=100.0, current_price=100.0)
        }
        assert pl.check(positions, 100000.0, 100000.0) == []

    def test_gross_exposure_short(self) -> None:
        pos = Position(symbol="AAPL", quantity=-5, avg_price=100.0, current_price=100.0)
        assert gross_exposure(pos) == 500.0


class TestPositionLimitEdgeCases:
    def test_check_with_zero_portfolio_value_still_checks_max_value(self) -> None:
        limit = PositionLimit(max_size=0.1, max_value=10000.0)
        position = Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=150.0)
        violations = limit.check(position, 0.0)
        assert len(violations) == 1
        assert "exceeds max" in violations[0]
        assert "$15,000.00" in violations[0]

    def test_check_with_negative_portfolio_value_still_checks_max_value(self) -> None:
        limit = PositionLimit(max_size=0.1, max_value=10000.0)
        position = Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=150.0)
        violations = limit.check(position, -1000.0)
        assert len(violations) == 1
        assert "exceeds max" in violations[0]


class TestPortfolioLimitAdditionalEdgeCases:
    def test_position_risk_with_avg_price_zero_uses_current_price_positive(self) -> None:
        pl = PortfolioLimit(stop_loss_pct=0.05)
        pos = Position(symbol="AAPL", quantity=100, avg_price=0.0, current_price=200.0)
        assert pl.position_risk(pos) == 1000.0

    def test_position_risk_with_avg_price_positive_uses_avg_price(self) -> None:
        pl = PortfolioLimit(stop_loss_pct=0.05)
        pos = Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=300.0)
        assert pl.position_risk(pos) == 750.0

    def test_portfolio_risk_pct_with_zero_portfolio_value(self) -> None:
        pl = PortfolioLimit(max_portfolio_risk=0.02)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=150.0)
        }
        assert pl.portfolio_risk_pct(positions, 0.0) == 0.0

    def test_leverage_with_zero_portfolio_value(self) -> None:
        pl = PortfolioLimit(max_leverage=1.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=150.0)
        }
        assert pl.leverage(positions, 0.0) == 0.0

    def test_check_skips_zero_quantity_in_portfolio_loop(self) -> None:
        pl = PortfolioLimit(max_position_size=0.1, max_portfolio_risk=1.0, max_leverage=10.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=200, avg_price=150.0, current_price=155.0),
            "MSFT": Position(symbol="MSFT", quantity=0, avg_price=300.0, current_price=310.0),
        }
        violations = pl.check(positions, 100000.0, 100000.0)
        assert any("AAPL" in v for v in violations)

    def test_check_position_size_violation_in_portfolio_loop(self) -> None:
        pl = PortfolioLimit(max_position_size=0.1, max_portfolio_risk=1.0, max_leverage=10.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=200, avg_price=150.0, current_price=155.0),
        }
        violations = pl.check(positions, 100000.0, 100000.0)
        assert len(violations) == 1
        assert "AAPL" in violations[0]
        assert "exceeds max" in violations[0]

    def test_check_result_ok_property(self) -> None:
        result = CheckResult(passed=True)
        assert result.ok is True
        result2 = CheckResult(passed=False)
        assert result2.ok is False


class TestLimitsCoverageGaps:
    """Additional tests to cover specific lines."""

    def test_position_limit_check_zero_quantity_returns_empty(self) -> None:
        """Covers line ~90 in PositionLimit.check."""
        limit = PositionLimit()
        pos = Position(symbol="AAPL", quantity=0, avg_price=100, current_price=100)
        violations = limit.check(pos, 100000)
        assert violations == []

    def test_position_limit_check_portfolio_value_zero_skips_pct_violation_but_checks_value(
        self,
    ) -> None:
        """Covers branch where portfolio_value > 0 is false."""
        limit = PositionLimit(max_size=0.01, max_value=5000)
        pos = Position(symbol="AAPL", quantity=100, avg_price=100, current_price=100)  # value 10000
        violations = limit.check(pos, 0)
        # position_pct becomes 0, so size violation won't trigger; value violation will
        assert any("exceeds max" in v and "$" in v for v in violations)

    def test_position_limit_check_portfolio_value_negative_skips_pct_violation_but_checks_value(
        self,
    ) -> None:
        """Covers branch where portfolio_value > 0 is false (negative)."""
        limit = PositionLimit(max_size=0.01, max_value=5000)
        pos = Position(symbol="AAPL", quantity=100, avg_price=100, current_price=100)
        violations = limit.check(pos, -1000)
        assert any("exceeds max" in v for v in violations)

    def test_portfolio_limit_position_risk_quantity_zero(self) -> None:
        """Covers line ~196."""
        pl = PortfolioLimit()
        pos = Position(symbol="AAPL", quantity=0, avg_price=100, current_price=100)
        assert pl.position_risk(pos) == 0.0

    def test_portfolio_limit_position_risk_basis_zero(self) -> None:
        """Covers line ~200."""
        pl = PortfolioLimit()
        pos = Position(symbol="AAPL", quantity=10, avg_price=0, current_price=0)
        assert pl.position_risk(pos) == 0.0

    def test_portfolio_limit_portfolio_risk_pct_zero_portfolio(self) -> None:
        """Covers line ~229."""
        pl = PortfolioLimit()
        positions = {"AAPL": Position(symbol="AAPL", quantity=10, avg_price=100, current_price=100)}
        assert pl.portfolio_risk_pct(positions, 0) == 0.0

    def test_portfolio_limit_leverage_zero_portfolio(self) -> None:
        """Covers line ~248."""
        pl = PortfolioLimit()
        positions = {"AAPL": Position(symbol="AAPL", quantity=10, avg_price=100, current_price=100)}
        assert pl.leverage(positions, 0) == 0.0

    def test_portfolio_limit_check_skips_zero_quantity(self) -> None:
        """Covers line ~278."""
        pl = PortfolioLimit(max_position_size=0.05, max_portfolio_risk=1.0, max_leverage=10.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=200, avg_price=150, current_price=155),
            "MSFT": Position(symbol="MSFT", quantity=0, avg_price=100, current_price=100),
        }
        violations = pl.check(positions, 100000, 100000)
        assert any("AAPL" in v for v in violations)

    def test_portfolio_limit_check_position_size_violation_message(self) -> None:
        """Covers line ~281."""
        pl = PortfolioLimit(max_position_size=0.05)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=100, current_price=100)
        }  # 10% of 100k
        violations = pl.check(positions, 100000, 100000)
        assert any("exceeds max" in v and "AAPL" in v for v in violations)

    def test_check_result_ok_property(self) -> None:
        """Covers line ~337."""
        result = CheckResult(passed=True)
        assert result.ok is True
        result2 = CheckResult(passed=False)
        assert result2.ok is False

    def test_position_limit_both_violations_exact(self) -> None:
        """Ensure both violations are reported."""
        limit = PositionLimit(max_size=0.1, max_value=10000.0)
        position = Position(symbol="AAPL", quantity=200, avg_price=100.0, current_price=100.0)
        violations = limit.check(position, 100000.0)
        assert len(violations) == 2

    def test_portfolio_risk_pct_with_positive_portfolio(self) -> None:
        """Cover portfolio_risk_pct when portfolio_value > 0."""
        pl = PortfolioLimit(max_portfolio_risk=0.05)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150, current_price=150)
        }
        pct = pl.portfolio_risk_pct(positions, 100000.0)
        assert pct > 0

    def test_leverage_with_positive_portfolio(self) -> None:
        """Cover leverage when portfolio_value > 0."""
        pl = PortfolioLimit(max_leverage=2.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150, current_price=150)
        }
        lev = pl.leverage(positions, 100000.0)
        assert lev > 0


class TestFiniteHelper:
    """Tests for the _finite helper used in deserialization."""

    @pytest.mark.parametrize("value", [1.5, 0, -3.14, 42, 0.0])
    def test_finite_numbers_pass_through(self, value: float) -> None:
        assert _finite(value) == float(value)

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_numbers_return_default(self, value: float) -> None:
        assert _finite(value) == 0.0
        assert _finite(value, default=99.0) == 99.0

    @pytest.mark.parametrize("value", ["not a number", None, [], {}, object()])
    def test_non_numeric_values_return_default(self, value: object) -> None:
        assert _finite(value) == 0.0
        assert _finite(value, default=77.0) == 77.0

    def test_numeric_strings_are_parsed(self) -> None:
        assert _finite("3.14") == 3.14
        assert _finite("-2.5") == -2.5
        assert _finite("0") == 0.0

    def test_bool_is_not_treated_as_number(self) -> None:
        # bool is a subclass of int, but we explicitly exclude it
        assert _finite(True) == 0.0
        assert _finite(False) == 0.0


class TestCheckResultSerialization:
    """Tests for CheckResult.to_dict/from_dict branches."""

    def test_to_dict_serializes_timestamp(self) -> None:
        from datetime import datetime

        dt = datetime(2024, 1, 2, 3, 4, 5)
        res = CheckResult(passed=False, violations=["x"], timestamp=dt)
        d = res.to_dict()
        assert d["passed"] is False
        assert d["violations"] == ["x"]
        assert d["timestamp"] == "2024-01-02T03:04:05"

    def test_from_dict_missing_keys_use_defaults(self) -> None:
        from datetime import datetime

        res = CheckResult.from_dict({})
        assert res.passed is True
        assert res.violations == []
        assert isinstance(res.timestamp, datetime)

    def test_from_dict_coerces_iso_timestamp(self) -> None:
        from datetime import datetime

        res = CheckResult.from_dict(
            {"passed": False, "violations": ["v"], "timestamp": "2024-01-02T03:04:05"}
        )
        assert res.passed is False
        assert res.violations == ["v"]
        assert res.timestamp == datetime(2024, 1, 2, 3, 4, 5)

    def test_from_dict_invalid_timestamp_type_falls_back_to_now(self) -> None:
        from datetime import datetime

        res = CheckResult.from_dict({"passed": True, "timestamp": 12345})
        assert isinstance(res.timestamp, datetime)

    def test_add_violation_marks_failed(self) -> None:
        res = CheckResult(passed=True)
        assert res.ok is True
        res.add_violation("boom")
        assert res.passed is False
        assert res.ok is False
        assert res.violations == ["boom"]


class TestPositionLimitValidation:
    """Tests that PositionLimit rejects non-finite constructor values."""

    @pytest.mark.parametrize(
        "field",
        ["max_size", "max_value", "stop_loss_pct", "take_profit_pct"],
    )
    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_rejects_non_finite_values(self, field: str, value: float) -> None:
        with pytest.raises(ValueError, match="invalid "):
            PositionLimit(**{field: value})

    def test_accepts_finite_values(self) -> None:
        limit = PositionLimit(
            max_size=0.5,
            max_value=10000.0,
            stop_loss_pct=0.0,
            take_profit_pct=1.0,
        )
        assert limit.max_size == 0.5
        assert limit.max_value == 10000.0


class TestPortfolioLimitValidation:
    """Tests that PortfolioLimit rejects non-finite constructor values."""

    @pytest.mark.parametrize(
        "field",
        [
            "max_positions",
            "max_position_size",
            "max_portfolio_risk",
            "max_drawdown",
            "max_leverage",
            "stop_loss_pct",
        ],
    )
    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_rejects_non_finite_values(self, field: str, value: float) -> None:
        with pytest.raises(ValueError, match="invalid "):
            PortfolioLimit(**{field: value})  # type: ignore[arg-type]

    @pytest.mark.parametrize("max_positions", [-1, -5, float("nan"), float("inf"), float("-inf")])
    def test_rejects_invalid_max_positions(self, max_positions: int) -> None:
        with pytest.raises(ValueError, match="invalid max_positions"):
            PortfolioLimit(max_positions=max_positions)

    def test_accepts_zero_max_positions(self) -> None:
        # Zero means no positions may be opened; it must remain constructible.
        limit = PortfolioLimit(max_positions=0)
        assert limit.max_positions == 0

    @pytest.mark.parametrize(
        "field,value",
        [
            ("max_leverage", 0.0),
            ("max_portfolio_risk", 0.0),
            ("max_drawdown", 0.0),
        ],
    )
    def test_accepts_disabled_limits(self, field: str, value: float) -> None:
        # Zero disables some limits and must remain constructible.
        limit = PortfolioLimit(**{field: value})  # type: ignore[arg-type]
        assert getattr(limit, field) == value


class TestPositionLimitSerialization:
    """Tests for PositionLimit.to_dict/from_dict branches."""

    def test_to_dict_returns_all_fields(self) -> None:
        limit = PositionLimit(
            max_size=0.2,
            max_value=100000.0,
            stop_loss_pct=0.10,
            take_profit_pct=0.20,
        )
        d = limit.to_dict()
        assert d["max_size"] == 0.2
        assert d["max_value"] == 100000.0
        assert d["stop_loss_pct"] == 0.10
        assert d["take_profit_pct"] == 0.20

    def test_from_dict_restores_all_fields(self) -> None:
        limit = PositionLimit.from_dict(
            {
                "max_size": 0.2,
                "max_value": 100000.0,
                "stop_loss_pct": 0.10,
                "take_profit_pct": 0.20,
            }
        )
        assert limit.max_size == 0.2
        assert limit.max_value == 100000.0
        assert limit.stop_loss_pct == 0.10
        assert limit.take_profit_pct == 0.20

    def test_from_dict_defaults_missing_fields(self) -> None:
        limit = PositionLimit.from_dict({})
        assert limit.max_size == 0.1
        assert limit.max_value == 50000.0
        assert limit.stop_loss_pct == 0.05
        assert limit.take_profit_pct == 0.15

    def test_from_dict_partial_restores_with_defaults(self) -> None:
        limit = PositionLimit.from_dict({"max_size": 0.3})
        assert limit.max_size == 0.3
        assert limit.max_value == 50000.0
        assert limit.stop_loss_pct == 0.05
        assert limit.take_profit_pct == 0.15

    def test_round_trip_preserves_values(self) -> None:
        original = PositionLimit(
            max_size=0.15,
            max_value=75000.0,
            stop_loss_pct=0.08,
            take_profit_pct=0.25,
        )
        restored = PositionLimit.from_dict(original.to_dict())
        assert restored.max_size == original.max_size
        assert restored.max_value == original.max_value
        assert restored.stop_loss_pct == original.stop_loss_pct
        assert restored.take_profit_pct == original.take_profit_pct


class TestPortfolioLimitSerialization:
    """Tests for PortfolioLimit.to_dict/from_dict branches."""

    def test_to_dict_returns_all_fields(self) -> None:
        limit = PortfolioLimit(
            max_positions=10,
            max_position_size=0.15,
            max_portfolio_risk=0.05,
            max_drawdown=0.15,
            max_leverage=2.0,
            stop_loss_pct=0.08,
        )
        d = limit.to_dict()
        assert d["max_positions"] == 10
        assert d["max_position_size"] == 0.15
        assert d["max_portfolio_risk"] == 0.05
        assert d["max_drawdown"] == 0.15
        assert d["max_leverage"] == 2.0
        assert d["stop_loss_pct"] == 0.08

    def test_from_dict_restores_all_fields(self) -> None:
        limit = PortfolioLimit.from_dict(
            {
                "max_positions": 10,
                "max_position_size": 0.15,
                "max_portfolio_risk": 0.05,
                "max_drawdown": 0.15,
                "max_leverage": 2.0,
                "stop_loss_pct": 0.08,
            }
        )
        assert limit.max_positions == 10
        assert limit.max_position_size == 0.15
        assert limit.max_portfolio_risk == 0.05
        assert limit.max_drawdown == 0.15
        assert limit.max_leverage == 2.0
        assert limit.stop_loss_pct == 0.08

    def test_from_dict_defaults_missing_fields(self) -> None:
        limit = PortfolioLimit.from_dict({})
        assert limit.max_positions == 20
        assert limit.max_position_size == 0.1
        assert limit.max_portfolio_risk == 0.02
        assert limit.max_drawdown == 0.20
        assert limit.max_leverage == 1.0
        assert limit.stop_loss_pct == 0.05

    def test_from_dict_partial_restores_with_defaults(self) -> None:
        limit = PortfolioLimit.from_dict({"max_positions": 5, "max_leverage": 3.0})
        assert limit.max_positions == 5
        assert limit.max_leverage == 3.0
        assert limit.max_position_size == 0.1
        assert limit.max_portfolio_risk == 0.02
        assert limit.max_drawdown == 0.20
        assert limit.stop_loss_pct == 0.05

    def test_round_trip_preserves_values(self) -> None:
        original = PortfolioLimit(
            max_positions=15,
            max_position_size=0.12,
            max_portfolio_risk=0.03,
            max_drawdown=0.18,
            max_leverage=1.5,
            stop_loss_pct=0.07,
        )
        restored = PortfolioLimit.from_dict(original.to_dict())
        assert restored.max_positions == original.max_positions
        assert restored.max_position_size == original.max_position_size
        assert restored.max_portfolio_risk == original.max_portfolio_risk
        assert restored.max_drawdown == original.max_drawdown
        assert restored.max_leverage == original.max_leverage
        assert restored.stop_loss_pct == original.stop_loss_pct


class TestPositionLimitSerializationHardening:
    """Regression tests for PositionLimit.from_dict non-finite/non-numeric handling."""

    @pytest.mark.parametrize(
        "field,value",
        [
            ("max_size", float("nan")),
            ("max_size", float("inf")),
            ("max_size", float("-inf")),
            ("max_value", float("nan")),
            ("max_value", float("inf")),
            ("max_value", float("-inf")),
            ("stop_loss_pct", float("nan")),
            ("stop_loss_pct", float("inf")),
            ("stop_loss_pct", float("-inf")),
            ("take_profit_pct", float("nan")),
            ("take_profit_pct", float("inf")),
            ("take_profit_pct", float("-inf")),
        ],
    )
    def test_from_dict_sanitizes_non_finite_values(self, field: str, value: float) -> None:
        data = {field: value}
        limit = PositionLimit.from_dict(data)
        # The field should fall back to its default
        expected_default = {
            "max_size": 0.1,
            "max_value": 50000.0,
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.15,
        }[field]
        assert getattr(limit, field) == expected_default

    @pytest.mark.parametrize(
        "field,value",
        [
            ("max_size", "not a number"),
            ("max_value", "not a number"),
            ("stop_loss_pct", "not a number"),
            ("take_profit_pct", "not a number"),
            ("max_size", None),
            ("max_value", None),
            ("stop_loss_pct", None),
            ("take_profit_pct", None),
            ("max_size", []),
            ("max_value", {}),
        ],
    )
    def test_from_dict_sanitizes_non_numeric_values(self, field: str, value: object) -> None:
        data = {field: value}
        limit = PositionLimit.from_dict(data)
        expected_default = {
            "max_size": 0.1,
            "max_value": 50000.0,
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.15,
        }[field]
        assert getattr(limit, field) == expected_default

    def test_from_dict_accepts_numeric_strings(self) -> None:
        limit = PositionLimit.from_dict(
            {
                "max_size": "0.25",
                "max_value": "75000.0",
                "stop_loss_pct": "0.12",
                "take_profit_pct": "0.30",
            }
        )
        assert limit.max_size == 0.25
        assert limit.max_value == 75000.0
        assert limit.stop_loss_pct == 0.12
        assert limit.take_profit_pct == 0.30

    def test_from_dict_missing_fields_use_defaults(self) -> None:
        limit = PositionLimit.from_dict({})
        assert limit.max_size == 0.1
        assert limit.max_value == 50000.0
        assert limit.stop_loss_pct == 0.05
        assert limit.take_profit_pct == 0.15


class TestPortfolioLimitSerializationHardening:
    """Regression tests for PortfolioLimit.from_dict non-finite/non-numeric handling."""

    @pytest.mark.parametrize(
        "field,value",
        [
            ("max_position_size", float("nan")),
            ("max_position_size", float("inf")),
            ("max_position_size", float("-inf")),
            ("max_portfolio_risk", float("nan")),
            ("max_portfolio_risk", float("inf")),
            ("max_portfolio_risk", float("-inf")),
            ("max_drawdown", float("nan")),
            ("max_drawdown", float("inf")),
            ("max_drawdown", float("-inf")),
            ("max_leverage", float("nan")),
            ("max_leverage", float("inf")),
            ("max_leverage", float("-inf")),
            ("stop_loss_pct", float("nan")),
            ("stop_loss_pct", float("inf")),
            ("stop_loss_pct", float("-inf")),
        ],
    )
    def test_from_dict_sanitizes_non_finite_values(self, field: str, value: float) -> None:
        data = {field: value}
        limit = PortfolioLimit.from_dict(data)
        expected_default = {
            "max_position_size": 0.1,
            "max_portfolio_risk": 0.02,
            "max_drawdown": 0.20,
            "max_leverage": 1.0,
            "stop_loss_pct": 0.05,
        }[field]
        assert getattr(limit, field) == expected_default

    def test_from_dict_sanitizes_non_finite_max_positions(self) -> None:
        limit = PortfolioLimit.from_dict({"max_positions": float("nan")})
        assert limit.max_positions == 20
        limit = PortfolioLimit.from_dict({"max_positions": float("inf")})
        assert limit.max_positions == 20
        limit = PortfolioLimit.from_dict({"max_positions": float("-inf")})
        assert limit.max_positions == 20

    @pytest.mark.parametrize(
        "field,value",
        [
            ("max_position_size", "not a number"),
            ("max_portfolio_risk", "not a number"),
            ("max_drawdown", "not a number"),
            ("max_leverage", "not a number"),
            ("stop_loss_pct", "not a number"),
            ("max_position_size", None),
            ("max_portfolio_risk", None),
            ("max_drawdown", None),
            ("max_leverage", None),
            ("stop_loss_pct", None),
            ("max_position_size", []),
            ("max_portfolio_risk", {}),
        ],
    )
    def test_from_dict_sanitizes_non_numeric_values(self, field: str, value: object) -> None:
        data = {field: value}
        limit = PortfolioLimit.from_dict(data)
        expected_default = {
            "max_position_size": 0.1,
            "max_portfolio_risk": 0.02,
            "max_drawdown": 0.20,
            "max_leverage": 1.0,
            "stop_loss_pct": 0.05,
        }[field]
        assert getattr(limit, field) == expected_default

    def test_from_dict_sanitizes_non_numeric_max_positions(self) -> None:
        limit = PortfolioLimit.from_dict({"max_positions": "not a number"})
        assert limit.max_positions == 20
        limit = PortfolioLimit.from_dict({"max_positions": None})
        assert limit.max_positions == 20

    def test_from_dict_accepts_numeric_strings(self) -> None:
        limit = PortfolioLimit.from_dict(
            {
                "max_positions": "15",
                "max_position_size": "0.18",
                "max_portfolio_risk": "0.04",
                "max_drawdown": "0.25",
                "max_leverage": "2.5",
                "stop_loss_pct": "0.08",
            }
        )
        assert limit.max_positions == 15
        assert limit.max_position_size == 0.18
        assert limit.max_portfolio_risk == 0.04
        assert limit.max_drawdown == 0.25
        assert limit.max_leverage == 2.5
        assert limit.stop_loss_pct == 0.08

    def test_from_dict_missing_fields_use_defaults(self) -> None:
        limit = PortfolioLimit.from_dict({})
        assert limit.max_positions == 20
        assert limit.max_position_size == 0.1
        assert limit.max_portfolio_risk == 0.02
        assert limit.max_drawdown == 0.20
        assert limit.max_leverage == 1.0
        assert limit.stop_loss_pct == 0.05


class TestCheckResultSerializationHardening:
    """Regression tests for CheckResult.from_dict edge cases."""

    def test_from_dict_sanitizes_non_finite_numeric_fields(self) -> None:
        # CheckResult doesn't have float fields in from_dict, but test that
        # the pattern is consistent (passed is bool, violations is list)
        res = CheckResult.from_dict({"passed": float("nan")})  # bool() of nan is True
        assert res.passed is True
        res = CheckResult.from_dict({"passed": float("inf")})
        assert res.passed is True
        res = CheckResult.from_dict({"violations": "not a list"})  # list() of str iterates chars
        assert isinstance(res.violations, list)
