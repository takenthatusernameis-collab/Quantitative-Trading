"""Tests for the strategy base classes."""

import pandas as pd
import pytest

from quant_trading.strategies.base import Position, Strategy, StrategyManager


class TestPosition:
    """Tests for Position dataclass."""

    def test_pnl_property(self):
        """Test Position.pnl returns sum of unrealized and realized PnL."""
        pos = Position(
            symbol="AAPL",
            quantity=100,
            avg_price=150.0,
            current_price=160.0,
            unrealized_pnl=1000.0,
            realized_pnl=500.0,
        )
        assert pos.pnl == 1500.0

    def test_pnl_property_zero(self):
        """Test Position.pnl returns 0 when both components are zero."""
        pos = Position(symbol="AAPL")
        assert pos.pnl == 0.0

    def test_pnl_property_negative_unrealized(self):
        """Test Position.pnl with negative unrealized PnL."""
        pos = Position(
            symbol="AAPL",
            unrealized_pnl=-200.0,
            realized_pnl=500.0,
        )
        assert pos.pnl == 300.0


class StrategyWithValidation(Strategy):
    """Concrete strategy with parameter validation for testing."""

    def __init__(self, name: str = "Validated", threshold: float = 10.0):
        super().__init__(name, {"threshold": threshold})
        self.threshold = threshold

    def validate_parameters(self) -> None:
        if self.threshold <= 0:
            raise ValueError("threshold must be positive")

    def generate_signals(self, data):
        return []


class TestStrategySetParameter:
    """Tests for Strategy.set_parameter with validation and rollback."""

    def test_set_parameter_success(self):
        """Test successful parameter update without validation error."""
        strategy = StrategyWithValidation(name="Test", threshold=10.0)
        strategy.set_parameter("threshold", 20.0)
        assert strategy.threshold == 20.0
        assert strategy.parameters["threshold"] == 20.0

    def test_set_parameter_rollback_on_validation_failure(self):
        """Test parameter rollback when validation raises ValueError."""
        strategy = StrategyWithValidation(name="Test", threshold=10.0)
        with pytest.raises(ValueError, match="threshold must be positive"):
            strategy.set_parameter("threshold", -5.0)
        # Verify rollback
        assert strategy.threshold == 10.0
        assert strategy.parameters["threshold"] == 10.0

    def test_set_parameter_rollback_removes_new_key(self):
        """Test rollback removes a newly added parameter key when validation fails."""
        strategy = StrategyWithValidation(name="Test", threshold=10.0)
        # Add a new parameter that will fail validation (threshold <= 0)
        with pytest.raises(ValueError):
            strategy.set_parameter("threshold", -5.0)
        # The parameter should be rolled back to original value
        assert strategy.parameters["threshold"] == 10.0
        assert strategy.threshold == 10.0

    def test_set_parameter_rollback_restores_attribute(self):
        """Test rollback restores the instance attribute value."""
        strategy = StrategyWithValidation(name="Test", threshold=10.0)
        with pytest.raises(ValueError):
            strategy.set_parameter("threshold", -5.0)
        # Attribute should be restored to original value
        assert strategy.threshold == 10.0


class TestStrategyManager:
    """Tests for StrategyManager class."""

    def test_init_empty(self):
        """Test StrategyManager initializes with empty strategies dict."""
        manager = StrategyManager()
        assert manager.strategies == {}

    def test_add_strategy(self):
        """Test adding a strategy to the manager."""
        manager = StrategyManager()
        strategy = StrategyWithValidation(name="Test1", threshold=5.0)
        manager.add_strategy(strategy)
        assert manager.strategies["Test1"] is strategy

    def test_add_strategy_overwrites(self):
        """Test adding a strategy with same name overwrites."""
        manager = StrategyManager()
        strategy1 = StrategyWithValidation(name="Test", threshold=5.0)
        strategy2 = StrategyWithValidation(name="Test", threshold=10.0)
        manager.add_strategy(strategy1)
        manager.add_strategy(strategy2)
        assert manager.strategies["Test"] is strategy2

    def test_remove_strategy(self):
        """Test removing a strategy by name."""
        manager = StrategyManager()
        strategy = StrategyWithValidation(name="Test", threshold=5.0)
        manager.add_strategy(strategy)
        manager.remove_strategy("Test")
        assert "Test" not in manager.strategies

    def test_remove_strategy_unknown_is_noop(self):
        """Test removing unknown strategy does not raise."""
        manager = StrategyManager()
        manager.remove_strategy("NonExistent")  # Should not raise
        assert manager.strategies == {}

    def test_get_strategy_existing(self):
        """Test getting an existing strategy by name."""
        manager = StrategyManager()
        strategy = StrategyWithValidation(name="Test", threshold=5.0)
        manager.add_strategy(strategy)
        retrieved = manager.get_strategy("Test")
        assert retrieved is strategy

    def test_get_strategy_unknown_returns_none(self):
        """Test getting unknown strategy returns None."""
        manager = StrategyManager()
        assert manager.get_strategy("NonExistent") is None

    def test_generate_all_signals(self):
        """Test generate_all_signals delegates to each strategy."""
        manager = StrategyManager()
        strategy1 = StrategyWithValidation(name="Strat1", threshold=5.0)
        strategy2 = StrategyWithValidation(name="Strat2", threshold=10.0)
        manager.add_strategy(strategy1)
        manager.add_strategy(strategy2)

        data = {"AAPL": pd.DataFrame({"close": [100, 101, 102]})}
        signals = manager.generate_all_signals(data)

        assert "Strat1" in signals
        assert "Strat2" in signals
        assert isinstance(signals["Strat1"], list)
        assert isinstance(signals["Strat2"], list)

    def test_generate_all_signals_empty_manager(self):
        """Test generate_all_signals with empty manager returns empty dict."""
        manager = StrategyManager()
        data = {"AAPL": pd.DataFrame({"close": [100, 101, 102]})}
        signals = manager.generate_all_signals(data)
        assert signals == {}

    def test_generate_all_signals_with_multiple_strategies(self):
        """Test generate_all_signals with multiple strategies returns all signals."""
        manager = StrategyManager()
        for i in range(3):
            strategy = StrategyWithValidation(name=f"Strat{i}", threshold=float(i))
            manager.add_strategy(strategy)

        data = {"AAPL": pd.DataFrame({"close": [100, 101, 102]})}
        signals = manager.generate_all_signals(data)

        assert len(signals) == 3
        for i in range(3):
            assert f"Strat{i}" in signals


class TestStrategyValidateParameters:
    """Tests for Strategy.validate_parameters."""

    def test_default_validate_parameters_does_nothing(self):
        """Test default validate_parameters does not raise."""

        class NoValidationStrategy(Strategy):
            def generate_signals(self, data):
                return []

        strategy = NoValidationStrategy(name="Test")
        # Should not raise
        strategy.validate_parameters()

    def test_validate_parameters_called_in_set_parameter(self):
        """Test validate_parameters is called during set_parameter."""

        class TrackingStrategy(Strategy):
            def __init__(self, name: str = "Tracking"):
                super().__init__(name)
                self.validate_called = False

            def validate_parameters(self) -> None:
                self.validate_called = True

            def generate_signals(self, data):
                return []

        strategy = TrackingStrategy(name="Test")
        strategy.set_parameter("any_key", "any_value")
        assert strategy.validate_called is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])