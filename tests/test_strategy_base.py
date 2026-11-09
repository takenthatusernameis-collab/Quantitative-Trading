"""Tests for the strategy base classes."""

from datetime import datetime

import pandas as pd
import pytest

from quant_trading.strategies.base import Position, Signal, Strategy, StrategyManager


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

    def test_market_value_property(self):
        """Test Position.market_value returns quantity times current price."""
        pos = Position(symbol="AAPL", quantity=100, current_price=160.0)
        assert pos.market_value == 16000.0

    def test_market_value_property_zero(self):
        """Test Position.market_value returns 0 when quantity is zero."""
        pos = Position(symbol="AAPL", quantity=0, current_price=160.0)
        assert pos.market_value == 0.0


class TestSignal:
    """Tests for the Signal dataclass."""

    def test_timestamp_defaults_to_now(self):
        """A signal created without a timestamp gets the current time."""
        signal = Signal(symbol="AAPL", action="buy", price=150.0)
        assert signal.timestamp is not None

    def test_explicit_timestamp_is_preserved(self):
        """An explicitly given timestamp is not overridden by __post_init__."""
        fixed = datetime(2024, 1, 1, 12, 0, 0)
        signal = Signal(symbol="AAPL", action="buy", price=150.0, timestamp=fixed)
        assert signal.timestamp == fixed


class TestPositionSerialization:
    """Tests for Position.to_dict/from_dict serialization."""

    def test_to_dict_exposes_all_fields(self):
        pos = Position(
            symbol="AAPL",
            quantity=100,
            avg_price=150.0,
            current_price=160.0,
            unrealized_pnl=1000.0,
            realized_pnl=500.0,
        )
        assert pos.to_dict() == {
            "symbol": "AAPL",
            "quantity": 100,
            "avg_price": 150.0,
            "current_price": 160.0,
            "unrealized_pnl": 1000.0,
            "realized_pnl": 500.0,
        }

    def test_to_dict_defaults(self):
        pos = Position(symbol="MSFT")
        assert pos.to_dict() == {
            "symbol": "MSFT",
            "quantity": 0.0,
            "avg_price": 0.0,
            "current_price": 0.0,
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
        }

    def test_from_dict_round_trips(self):
        pos = Position("AAPL", 100, 150.0, 160.0, 1000.0, 500.0)
        assert Position.from_dict(pos.to_dict()) == pos

    def test_from_dict_json_round_trip(self):
        import json

        pos = Position("AAPL", 100, 150.0, 160.0)
        decoded = json.loads(json.dumps(pos.to_dict()))
        restored = Position.from_dict(decoded)
        assert restored == pos

    def test_from_dict_defaults_missing_keys(self):
        restored = Position.from_dict({})
        assert restored == Position(symbol="")

    def test_from_dict_ignores_extra_keys(self):
        data = Position("AAPL", 10, 100.0).to_dict()
        data["unknown"] = 123
        restored = Position.from_dict(data)
        assert restored == Position("AAPL", 10, 100.0)


class TestSignalSerialization:
    """Tests for Signal.to_dict/from_dict serialization."""

    def test_to_dict_exposes_all_fields(self):
        ts = datetime(2024, 1, 1, 12, 0, 0)
        signal = Signal(
            symbol="AAPL",
            action="buy",
            strength=0.5,
            price=150.0,
            timestamp=ts,
            metadata={"key": "value"},
        )
        assert signal.to_dict() == {
            "symbol": "AAPL",
            "action": "buy",
            "strength": 0.5,
            "price": 150.0,
            "timestamp": "2024-01-01T12:00:00",
            "metadata": {"key": "value"},
        }

    def test_to_dict_serializes_timestamp_as_iso_string(self):
        """A signal created without a timestamp serializes it as an ISO string."""
        signal = Signal(symbol="AAPL", action="hold")
        d = signal.to_dict()
        assert d["timestamp"] is not None
        assert d["metadata"] == {}
        assert datetime.fromisoformat(d["timestamp"]) == signal.timestamp

    def test_to_dict_metadata_is_copied(self):
        metadata = {"key": "value"}
        signal = Signal(symbol="AAPL", action="buy", metadata=metadata)
        d = signal.to_dict()
        assert d["metadata"] == metadata
        d["metadata"]["mutated"] = True
        assert signal.metadata == {"key": "value"}

    def test_from_dict_round_trips(self):
        ts = datetime(2024, 1, 1, 12, 0, 0)
        signal = Signal("AAPL", "sell", 0.25, 150.0, ts, {"k": "v"})
        assert Signal.from_dict(signal.to_dict()) == signal

    def test_from_dict_json_round_trip(self):
        import json

        ts = datetime(2024, 1, 1, 12, 0, 0)
        signal = Signal("AAPL", "buy", timestamp=ts)
        decoded = json.loads(json.dumps(signal.to_dict()))
        restored = Signal.from_dict(decoded)
        assert restored.timestamp == ts

    def test_from_dict_defaults_missing_keys(self):
        restored = Signal.from_dict({})
        assert restored.symbol == ""
        assert restored.action == "hold"
        assert restored.strength == 1.0
        assert restored.price is None
        assert restored.metadata == {}

    def test_from_dict_ignores_extra_keys(self):
        data = Signal("AAPL", "buy").to_dict()
        data["extra"] = 123
        restored = Signal.from_dict(data)
        assert restored.symbol == "AAPL"
        assert restored.action == "buy"
        assert restored.strength == 1.0
        assert restored.price is None
        assert restored.metadata == {}
        assert restored.timestamp is not None


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


class StrictlyInvalidStrategy(Strategy):
    """Strategy whose validation always fails."""

    def __init__(self, name: str = "StrictlyInvalid"):
        super().__init__(name, {"threshold": 10.0})
        self.threshold = 10.0

    def validate_parameters(self) -> None:
        raise ValueError("always invalid")

    def generate_signals(self, data):
        return []


class NoneAttributeStrategy(Strategy):
    """Strategy with a parameter key whose instance attribute is None."""

    def __init__(self, name: str = "NoneAttribute"):
        super().__init__(name, {"flag": "original"})
        self.flag = None

    def validate_parameters(self) -> None:
        raise ValueError("always invalid")

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

    def test_set_parameter_rollback_pops_new_parameter_key(self):
        """Test rollback removes a parameter key that did not exist before.

        The key was absent from parameters (old value None), so the
        tentative insertion is rolled back by removing the key.
        """
        strategy = StrictlyInvalidStrategy(name="Test")
        with pytest.raises(ValueError, match="always invalid"):
            strategy.set_parameter("new_key", "value")
        assert "new_key" not in strategy.parameters
        assert strategy.parameters == {"threshold": 10.0}
        assert strategy.threshold == 10.0

    def test_set_parameter_rollback_deletes_none_attribute(self):
        """Test rollback deletes an attribute whose old value was None.

        The attribute exists but holds None, so there is no old value
        to restore; the tentative update is rolled back by deleting
        the attribute. The parameter entry itself is restored.
        """
        strategy = NoneAttributeStrategy(name="Test")
        with pytest.raises(ValueError, match="always invalid"):
            strategy.set_parameter("flag", "new")
        assert strategy.parameters["flag"] == "original"
        assert not hasattr(strategy, "flag")

    def test_set_parameter_rollback_restores_none_value_in_real_strategy(self):
        """Test rollback restores a parameter key whose value was None.

        A parameter entry that legitimately holds None must be restored
        to None, not removed. Distinguishing "key absent" from "key
        present with value None" is the whole point of the rollback:
        some strategies store None in their parameters dict (e.g. an
        optional exit period that defaults to the entry period).
        """
        from quant_trading.strategies.examples import DonchianChannelStrategy

        strategy = DonchianChannelStrategy(name="Test")
        assert strategy.parameters["exit_period"] is None
        with pytest.raises(ValueError, match="exit_period must be positive"):
            strategy.set_parameter("exit_period", -5)
        assert strategy.parameters["exit_period"] is None
        assert strategy.exit_period == 20


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


class TestStrategyDescriptionDerivation:
    """Tests for Strategy.__init_subclass__ description derivation.

    A subclass that does not declare an explicit ``description`` derives it
    from the first line of its docstring, so a misplaced (dead) docstring
    silently leaves ``description`` at ``None``.
    """

    def test_description_is_derived_from_docstring_first_line(self):
        """A subclass without an explicit description derives it from its docstring."""

        class DocstringStrategy(Strategy):
            """Mean reversion strategy based on RSI levels.

            It buys when RSI is oversold and sells when overbought.
            """

            def generate_signals(self, data):
                return []

        strategy = DocstringStrategy(name="Test")
        assert strategy.description == "Mean reversion strategy based on RSI levels"

    def test_explicit_description_is_preserved(self):
        """An explicit description attribute is not overridden by the docstring."""

        class ExplicitDescriptionStrategy(Strategy):
            """Some docstring."""

            description = "Explicitly set description"

            def generate_signals(self, data):
                return []

        strategy = ExplicitDescriptionStrategy(name="Test")
        assert strategy.description == "Explicitly set description"

    def test_description_is_none_without_docstring(self):
        """A subclass with no docstring and no description keeps description None."""

        class NoDocstringStrategy(Strategy):
            def generate_signals(self, data):
                return []

        strategy = NoDocstringStrategy(name="Test")
        assert strategy.description is None


class TestStrategyUpdatePositions:
    """Tests for Strategy.update_positions."""

    def test_update_positions_replaces_tracking(self):
        """update_positions stores the supplied positions dict."""
        strategy = StrategyWithValidation(name="Test", threshold=10.0)
        positions = {
            "AAPL": Position(symbol="AAPL", quantity=100, avg_price=150.0, current_price=160.0),
        }
        strategy.update_positions(positions)
        assert strategy.positions is positions
        assert strategy.positions["AAPL"].quantity == 100


class TestStrategyGetParameters:
    """Tests for Strategy.get_parameters."""

    def test_get_parameters_returns_a_copy(self):
        """get_parameters returns a shallow copy of the parameters dict."""
        strategy = StrategyWithValidation(name="Test", threshold=10.0)
        params = strategy.get_parameters()
        assert params == {"threshold": 10.0}
        assert params is not strategy.parameters
        params["threshold"] = 999.0
        assert strategy.parameters["threshold"] == 10.0


class TestStrategyFromConfig:
    """Tests for Strategy.from_config."""

    def test_from_config_creates_strategy(self):
        """from_config builds a registered strategy from name, type, parameters."""
        strategy = Strategy.from_config(
            {
                "type": "ma",
                "name": "MyMA",
                "parameters": {"fast_period": 5, "slow_period": 20},
            }
        )
        from quant_trading.strategies.examples import MovingAverageCrossover

        assert isinstance(strategy, MovingAverageCrossover)
        assert strategy.name == "MyMA"
        assert strategy.fast_period == 5
        assert strategy.slow_period == 20

    def test_from_config_without_type_raises(self):
        """from_config raises ValueError when the config lacks a 'type' key."""
        with pytest.raises(ValueError, match="must contain 'type' key"):
            Strategy.from_config({"name": "NoType", "parameters": {}})


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
