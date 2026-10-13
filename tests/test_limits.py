"""Tests for risk limits."""

import pytest

from quant_trading.risk.limits import CheckResult, PortfolioLimit, PositionLimit
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
        limit = PortfolioLimit(max_positions=10, max_position_size=0.1)
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
