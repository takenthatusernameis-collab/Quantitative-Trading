"""Tests for risk limits."""

import pytest

from quant_trading.risk.limits import CheckResult, PortfolioLimit, PositionLimit, gross_exposure
from quant_trading.strategies.base import Position


class TestPositionLimit:
    """Tests for PositionLimit class."""

    def test_initialization_defaults(self):
        """Test default initialization."""
        limit = PositionLimit()
        assert limit.max_size == 0.1
        assert limit.max_value == 50000.0
        assert limit.stop_loss_pct == 0.05
        assert limit.take_profit_pct == 0.15

    def test_initialization_custom(self):
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

    def test_check_no_position(self):
        """Test check with zero quantity position."""
        limit = PositionLimit()
        position = Position(symbol="AAPL", quantity=0.0, avg_price=150.0, current_price=155.0)
        violations = limit.check(position, 100000.0)
        assert violations == []

    def test_check_position_size_violation(self):
        """Test check detects position size violation."""
        limit = PositionLimit(max_size=0.1, max_value=50000.0)
        # Position worth 20% of portfolio
        position = Position(symbol="AAPL", quantity=200, avg_price=150.0, current_price=100.0)
        violations = limit.check(position, 100000.0)
        assert len(violations) == 1
        assert "exceeds max" in violations[0]
        assert "20.00%" in violations[0] or "20%" in violations[0]

    def test_check_position_value_violation(self):
        """Test check detects position value violation."""
        limit = PositionLimit(max_size=0.5, max_value=10000.0)
        # Position worth $15,000, max is $10,000
        position = Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=150.0)
        violations = limit.check(position, 100000.0)
        assert len(violations) == 1
        assert "exceeds max" in violations[0]
        assert "$15,000.00" in violations[0]

    def test_check_both_violations(self):
        """Test check detects both violations."""
        limit = PositionLimit(max_size=0.1, max_value=10000.0)
        # Position worth $20,000 (20% of portfolio), max size 10%, max value $10,000
        position = Position(symbol="AAPL", quantity=200, avg_price=100.0, current_price=100.0)
        violations = limit.check(position, 100000.0)
        assert len(violations) == 2

    def test_check_ok(self):
        """Test check passes for valid position."""
        limit = PositionLimit(max_size=0.2, max_value=50000.0)
        position = Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=155.0)
        violations = limit.check(position, 100000.0)
        assert violations == []


class TestPortfolioLimit:
    """Tests for PortfolioLimit class."""

    def test_initialization_defaults(self):
        """Test default initialization."""
        limit = PortfolioLimit()
        assert limit.max_positions == 20
        assert limit.max_position_size == 0.1
        assert limit.max_portfolio_risk == 0.02
        assert limit.max_drawdown == 0.20
        assert limit.max_leverage == 1.0

    def test_initialization_custom(self):
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

    def test_check_too_many_positions(self):
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

    def test_check_position_size_violation(self):
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

    def test_check_drawdown_violation(self):
        """Test check detects drawdown violation."""
        limit = PortfolioLimit(max_drawdown=0.10)  # 10% max drawdown
        positions = {}
        # Portfolio dropped from 100k to 85k = 15% drawdown
        violations = limit.check(positions, 85000.0, 100000.0)
        assert len(violations) == 1
        assert "Drawdown" in violations[0]
        assert "exceeds max" in violations[0]

    def test_check_no_drawdown_violation(self):
        """Test check passes when drawdown within limits."""
        limit = PortfolioLimit(max_drawdown=0.20)
        positions = {}
        # Portfolio dropped from 100k to 90k = 10% drawdown
        violations = limit.check(positions, 90000.0, 100000.0)
        assert violations == []

    def test_check_skips_drawdown_when_peak_zero(self):
        """The drawdown check is skipped when peak_value <= 0 (72->77)."""
        limit = PortfolioLimit(max_drawdown=0.10)
        positions = {}
        violations = limit.check(positions, 85000.0, 0.0)
        assert violations == []

    def test_check_no_positions_with_peak(self):
        """With no positions and a positive peak, the loop body is skipped and
        the drawdown check is still evaluated (covers the peak>0 branch)."""
        limit = PortfolioLimit(max_drawdown=0.20)
        violations = limit.check({}, 90000.0, 100000.0)
        assert violations == []

    def test_check_ok(self):
        """Test check passes for valid portfolio."""
        limit = PortfolioLimit()
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=50, avg_price=150.0, current_price=155.0),
            "MSFT": Position(symbol="MSFT", quantity=30, avg_price=300.0, current_price=310.0),
        }
        violations = limit.check(positions, 100000.0, 100000.0)
        assert violations == []

    def test_check_skips_zero_quantity_position(self):
        """Test check skips positions with zero quantity."""
        limit = PortfolioLimit(max_position_size=0.1)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=50, avg_price=150.0, current_price=155.0),
            "MSFT": Position(symbol="MSFT", quantity=0, avg_price=300.0, current_price=310.0),
        }
        violations = limit.check(positions, 100000.0, 100000.0)
        assert violations == []

    def test_check_zero_quantity_with_other_violations(self):
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

    def test_defaults_include_stop_loss_pct(self):
        """The stop loss distance used to size position risk has a default."""
        assert PortfolioLimit().stop_loss_pct == 0.05

    def test_risk_within_limit(self):
        """Open risk below the budget produces no violation."""
        limit = PortfolioLimit(max_portfolio_risk=0.02, max_position_size=1.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=150.0),
        }
        # 100 shares * $150 entry * 5% stop = $750 at risk = 0.75% of portfolio
        assert limit.portfolio_risk(positions) == pytest.approx(750.0)
        assert limit.portfolio_risk_pct(positions, 100000.0) == pytest.approx(0.0075)
        assert limit.check(positions, 100000.0, 100000.0) == []

    def test_risk_violation(self):
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

    def test_risk_sums_across_positions(self):
        """The risk of several positions is summed."""
        limit = PortfolioLimit(max_portfolio_risk=1.0, max_position_size=1.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=150.0),
            "MSFT": Position(symbol="MSFT", quantity=50, avg_price=300.0, current_price=300.0),
        }
        # 100 * 150 * 5% + 50 * 300 * 5% = $1500
        assert limit.portfolio_risk(positions) == pytest.approx(1500.0)

    def test_risk_measured_from_entry_price(self):
        """The risk committed to a trade does not drift with the market price."""
        limit = PortfolioLimit(max_portfolio_risk=1.0, max_position_size=1.0)
        position = Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=300.0)
        assert limit.position_risk(position) == pytest.approx(750.0)

    def test_risk_of_short_position(self):
        """A short risks the same amount as a long of equal size."""
        limit = PortfolioLimit(max_portfolio_risk=1.0, max_position_size=1.0)
        long_pos = Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=150.0)
        short_pos = Position(symbol="AAPL", quantity=-100, avg_price=150.0, current_price=150.0)
        assert limit.position_risk(short_pos) == pytest.approx(limit.position_risk(long_pos))

    def test_risk_ignores_flat_positions(self):
        """Flat positions contribute no risk."""
        limit = PortfolioLimit(max_portfolio_risk=0.0, max_position_size=1.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=0, avg_price=150.0, current_price=150.0),
        }
        assert limit.portfolio_risk(positions) == 0.0
        assert limit.check(positions, 100000.0, 100000.0) == []

    def test_risk_falls_back_to_current_price(self):
        """A position without an entry price is sized from its current price."""
        limit = PortfolioLimit(max_portfolio_risk=1.0, max_position_size=1.0)
        position = Position(symbol="AAPL", quantity=100, avg_price=0.0, current_price=200.0)
        assert limit.position_risk(position) == pytest.approx(1000.0)

    def test_risk_with_zero_portfolio_value(self):
        """A non-positive portfolio value is handled without dividing by zero."""
        limit = PortfolioLimit(max_portfolio_risk=0.0, max_position_size=1.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=150.0),
        }
        assert limit.portfolio_risk_pct(positions, 0.0) == 0.0
        assert limit.check(positions, 0.0, 0.0) == []


class TestPortfolioLimitLeverage:
    """Tests for the leverage limit (gross exposure)."""

    def test_leverage_within_limit(self):
        """Gross exposure below the limit produces no violation."""
        limit = PortfolioLimit(max_leverage=1.0, max_position_size=1.0, max_portfolio_risk=1.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=400, avg_price=150.0, current_price=150.0),
        }
        assert limit.leverage(positions, 100000.0) == pytest.approx(0.6)
        assert limit.check(positions, 100000.0, 100000.0) == []

    def test_leverage_violation(self):
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

    def test_leverage_is_gross_not_net(self):
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

    def test_higher_leverage_limit_allows_exposure(self):
        """A leverage limit above the exposure allows the same portfolio."""
        limit = PortfolioLimit(max_leverage=2.0, max_position_size=1.0, max_portfolio_risk=1.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=400, avg_price=150.0, current_price=150.0),
            "MSFT": Position(symbol="MSFT", quantity=200, avg_price=300.0, current_price=300.0),
        }
        assert limit.check(positions, 100000.0, 100000.0) == []

    def test_leverage_with_zero_portfolio_value(self):
        """A non-positive portfolio value is handled without dividing by zero."""
        limit = PortfolioLimit(max_leverage=0.0, max_position_size=1.0, max_portfolio_risk=1.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=150.0),
        }
        assert limit.leverage(positions, 0.0) == 0.0
        assert limit.check(positions, 0.0, 0.0) == []


class TestPositionLimitGrossExposure:
    """Tests that position limits are measured on gross exposure."""

    def test_short_position_size_violation(self):
        """A short position is limited like a long position of the same size."""
        limit = PositionLimit(max_size=0.1, max_value=50000.0)
        short = Position(symbol="AAPL", quantity=-200, avg_price=100.0, current_price=100.0)
        violations = limit.check(short, 100000.0)
        assert len(violations) == 1
        assert "20.00%" in violations[0]
        assert "exceeds max" in violations[0]

    def test_short_position_value_violation(self):
        """The dollar value limit applies to a short position as well."""
        limit = PositionLimit(max_size=0.5, max_value=10000.0)
        short = Position(symbol="AAPL", quantity=-100, avg_price=150.0, current_price=150.0)
        violations = limit.check(short, 100000.0)
        assert len(violations) == 1
        assert "$15,000.00" in violations[0]
        assert "exceeds max" in violations[0]

    def test_short_position_within_limits(self):
        """A small short position produces no violation."""
        limit = PositionLimit(max_size=0.1, max_value=50000.0)
        short = Position(symbol="AAPL", quantity=-50, avg_price=150.0, current_price=150.0)
        assert limit.check(short, 100000.0) == []

    def test_long_and_short_of_equal_size_are_equivalent(self):
        """The same limits apply to a long and a short of the same size."""
        limit = PositionLimit(max_size=0.1, max_value=50000.0)
        long = Position(symbol="AAPL", quantity=200, avg_price=100.0, current_price=100.0)
        short = Position(symbol="AAPL", quantity=-200, avg_price=100.0, current_price=100.0)
        assert limit.check(long, 100000.0) == limit.check(short, 100000.0)

    def test_gross_exposure_helper(self):
        """The gross exposure of a position is its absolute market value."""
        long = Position(symbol="AAPL", quantity=200, avg_price=100.0, current_price=100.0)
        short = Position(symbol="AAPL", quantity=-200, avg_price=100.0, current_price=100.0)
        assert gross_exposure(long) == pytest.approx(20000.0)
        assert gross_exposure(short) == pytest.approx(20000.0)


class TestPortfolioLimitGrossExposure:
    """Tests that the portfolio position size limit uses gross exposure."""

    def test_short_position_size_violation(self):
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

    def test_short_position_within_limits(self):
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

    def test_offsetting_short_does_not_hide_the_long(self):
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

    def test_initialization_passed(self):
        """Test initialization with passed=True."""
        result = CheckResult(passed=True)
        assert result.passed is True
        assert result.violations == []
        assert result.ok is True
        assert result.timestamp is not None

    def test_initialization_failed(self):
        """Test initialization with passed=False."""
        result = CheckResult(passed=False, violations=["Error 1", "Error 2"])
        assert result.passed is False
        assert result.violations == ["Error 1", "Error 2"]
        assert result.ok is False

    def test_add_violation(self):
        """Test add_violation sets passed to False."""
        result = CheckResult(passed=True)
        result.add_violation("New violation")
        assert result.passed is False
        assert result.violations == ["New violation"]
        assert result.ok is False

    def test_add_multiple_violations(self):
        """Test adding multiple violations."""
        result = CheckResult(passed=True)
        result.add_violation("Violation 1")
        result.add_violation("Violation 2")
        assert result.passed is False
        assert result.violations == ["Violation 1", "Violation 2"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
