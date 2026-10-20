"""Tests for portfolio rebalancing logic."""

from datetime import datetime, timedelta

import pytest

from quant_trading.portfolio.portfolio import Portfolio
from quant_trading.portfolio.rebalancer import RebalanceAction, Rebalancer
from quant_trading.risk.manager import RiskManager
from quant_trading.strategies.base import Signal


def _portfolio_with_aapl():
    """Portfolio with $100k cash and one AAPL lot worth $10k (total $100k)."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", 100, 100.0)
    return portfolio


def _empty_portfolio():
    return Portfolio(cash=100000.0, initial_capital=100000.0)


class TestRebalanceAction:
    """Tests for the RebalanceAction dataclass."""

    def test_defaults(self):
        """Action defaults to a hold with zero quantity and empty reason."""
        action = RebalanceAction(symbol="AAPL", action="hold")
        assert action.symbol == "AAPL"
        assert action.action == "hold"
        assert action.quantity == 0.0
        assert action.reason == ""
        assert isinstance(action.timestamp, datetime)

    def test_explicit_values(self):
        """All fields are set when provided."""
        timestamp = datetime(2026, 1, 1, 12, 0, 0)
        action = RebalanceAction(
            symbol="MSFT",
            action="sell",
            quantity=25.0,
            reason="target_allocation",
            timestamp=timestamp,
        )
        assert action.quantity == 25.0
        assert action.reason == "target_allocation"
        assert action.timestamp == timestamp


class TestRebalancerInit:
    """Tests for Rebalancer initialization."""

    def test_defaults(self):
        """Default frequency, empty target allocation, and no prior rebalance."""
        portfolio = _empty_portfolio()
        rebalancer = Rebalancer(portfolio)
        assert rebalancer.frequency == "monthly"
        assert rebalancer.target_allocation == {}
        assert rebalancer.rebalance_threshold == pytest.approx(0.05)
        assert rebalancer.last_rebalance is None
        assert rebalancer.rebalance_history == []

    def test_custom_values(self):
        """Constructor arguments are stored as given."""
        portfolio = _empty_portfolio()
        rebalancer = Rebalancer(
            portfolio,
            frequency="daily",
            target_allocation={"AAPL": 0.6, "MSFT": 0.4},
            rebalance_threshold=0.10,
        )
        assert rebalancer.frequency == "daily"
        assert rebalancer.target_allocation == {"AAPL": 0.6, "MSFT": 0.4}
        assert rebalancer.rebalance_threshold == 0.10

    def test_target_allocation_none_defaults_empty(self):
        """A None target allocation normalizes to an empty dict."""
        portfolio = _empty_portfolio()
        rebalancer = Rebalancer(portfolio, target_allocation=None)
        assert rebalancer.target_allocation == {}


class TestShouldRebalance:
    """Tests for the frequency-based should_rebalance trigger."""

    def test_first_call_always_true(self):
        """With no prior rebalance, the first call always triggers."""
        rebalancer = Rebalancer(_empty_portfolio())
        assert rebalancer.should_rebalance() is True

    def test_daily_new_day(self):
        """A daily rebalancer triggers when the last run was a previous day."""
        rebalancer = Rebalancer(_empty_portfolio(), frequency="daily")
        rebalancer.last_rebalance = datetime.now() - timedelta(days=1)
        assert rebalancer.should_rebalance() is True

    def test_daily_same_day(self):
        """A daily rebalancer does not trigger within the same day."""
        rebalancer = Rebalancer(_empty_portfolio(), frequency="daily")
        rebalancer.last_rebalance = datetime.now()
        assert rebalancer.should_rebalance() is False

    def test_weekly_enough_elapsed(self):
        """A weekly rebalancer triggers after 7 or more days."""
        rebalancer = Rebalancer(_empty_portfolio(), frequency="weekly")
        rebalancer.last_rebalance = datetime.now() - timedelta(days=8)
        assert rebalancer.should_rebalance() is True

    def test_weekly_not_enough_elapsed(self):
        """A weekly rebalancer does not trigger before 7 days."""
        rebalancer = Rebalancer(_empty_portfolio(), frequency="weekly")
        rebalancer.last_rebalance = datetime.now() - timedelta(days=3)
        assert rebalancer.should_rebalance() is False

    def test_monthly_different_month(self):
        """A monthly rebalancer triggers in a different month/year."""
        rebalancer = Rebalancer(_empty_portfolio(), frequency="monthly")
        rebalancer.last_rebalance = datetime(2020, 1, 15)
        assert rebalancer.should_rebalance() is True

    def test_monthly_same_month(self):
        """A monthly rebalancer does not trigger within the same month."""
        rebalancer = Rebalancer(_empty_portfolio(), frequency="monthly")
        rebalancer.last_rebalance = datetime.now()
        assert rebalancer.should_rebalance() is False

    def test_quarterly_enough_elapsed(self):
        """A quarterly rebalancer triggers after 90 or more days."""
        rebalancer = Rebalancer(_empty_portfolio(), frequency="quarterly")
        rebalancer.last_rebalance = datetime.now() - timedelta(days=100)
        assert rebalancer.should_rebalance() is True

    def test_quarterly_not_enough_elapsed(self):
        """A quarterly rebalancer does not trigger before 90 days."""
        rebalancer = Rebalancer(_empty_portfolio(), frequency="quarterly")
        rebalancer.last_rebalance = datetime.now() - timedelta(days=30)
        assert rebalancer.should_rebalance() is False

    def test_unrecognized_frequency(self):
        """An unknown frequency never triggers a rebalance."""
        rebalancer = Rebalancer(_empty_portfolio(), frequency="yearly")
        rebalancer.last_rebalance = datetime(2020, 1, 1)
        assert rebalancer.should_rebalance() is False


class TestCalculateTargetValues:
    """Tests for target market value computation."""

    def test_empty_with_no_targets(self):
        """No target allocation yields an empty target map."""
        portfolio = _empty_portfolio()
        rebalancer = Rebalancer(portfolio)
        assert rebalancer.calculate_target_values() == {}

    def test_computes_target_values(self):
        """Each target is total portfolio value times the target fraction."""
        portfolio = _portfolio_with_aapl()  # total value stays 100000
        rebalancer = Rebalancer(portfolio, target_allocation={"AAPL": 0.5, "MSFT": 0.5})
        targets = rebalancer.calculate_target_values()
        assert targets == pytest.approx({"AAPL": 50000.0, "MSFT": 50000.0})


class TestGenerateRebalanceActions:
    """Tests for action generation from targets and signals."""

    def test_buy_below_target_allocation(self):
        """A position below target emits a buy sized to close the gap."""
        portfolio = _portfolio_with_aapl()
        rebalancer = Rebalancer(
            portfolio, target_allocation={"AAPL": 0.5}, rebalance_threshold=0.05
        )
        actions = rebalancer.generate_rebalance_actions()
        assert len(actions) == 1
        action = actions[0]
        assert action.symbol == "AAPL"
        assert action.action == "buy"
        assert action.quantity == pytest.approx(400.0)  # (50000 - 10000) / 100
        assert action.reason == "target_allocation"

    def test_sell_above_target_allocation(self):
        """A position above target emits a sell sized to close the gap."""
        portfolio = _portfolio_with_aapl()
        rebalancer = Rebalancer(
            portfolio, target_allocation={"AAPL": 0.0}, rebalance_threshold=0.05
        )
        actions = rebalancer.generate_rebalance_actions()
        assert len(actions) == 1
        action = actions[0]
        assert action.action == "sell"
        assert action.quantity == pytest.approx(100.0)  # 10000 / 100
        assert action.reason == "target_allocation"

    def test_no_action_within_threshold(self):
        """Deviations below the threshold produce no actions."""
        portfolio = _portfolio_with_aapl()
        rebalancer = Rebalancer(
            portfolio, target_allocation={"AAPL": 0.11}, rebalance_threshold=0.05
        )
        actions = rebalancer.generate_rebalance_actions()
        assert actions == []

    def test_no_action_at_exact_threshold(self):
        """A deviation exactly equal to the threshold does not trigger."""
        portfolio = _empty_portfolio()
        rebalancer = Rebalancer(
            portfolio, target_allocation={"AAPL": 0.05}, rebalance_threshold=0.05
        )
        actions = rebalancer.generate_rebalance_actions()
        assert actions == []  # diff/total == 0.05, not strictly greater

    def test_skip_when_total_value_non_positive(self):
        """No target-allocation actions are generated with zero portfolio value."""
        portfolio = Portfolio()
        rebalancer = Rebalancer(portfolio, target_allocation={"AAPL": 0.5})
        actions = rebalancer.generate_rebalance_actions()
        assert actions == []

    def test_buy_uses_prices_map_for_unheld_symbol(self):
        """Buy quantity falls back to the provided prices map."""
        portfolio = _empty_portfolio()
        rebalancer = Rebalancer(
            portfolio,
            target_allocation={"GOOGL": 0.5},
            rebalance_threshold=0.05,
        )
        actions = rebalancer.generate_rebalance_actions(prices={"GOOGL": 200.0})
        assert len(actions) == 1
        assert actions[0].action == "buy"
        assert actions[0].quantity == pytest.approx(250.0)  # 50000 / 200

    def test_buy_with_unresolvable_price_yields_no_action(self):
        """A buy with no available price produces no action."""
        portfolio = _empty_portfolio()
        rebalancer = Rebalancer(
            portfolio, target_allocation={"GOOGL": 0.5}, rebalance_threshold=0.05
        )
        actions = rebalancer.generate_rebalance_actions()
        assert actions == []

    def test_buy_target_with_holding_zero_price_yields_no_action(self):
        """A buy target for a holding with a non-positive price resolves to no action."""
        portfolio = _empty_portfolio()
        portfolio.add_holding("GOOGL", 100, 100.0)
        portfolio.holdings["GOOGL"].update_price(0.0)
        rebalancer = Rebalancer(
            portfolio, target_allocation={"GOOGL": 1.0}, rebalance_threshold=0.05
        )
        actions = rebalancer.generate_rebalance_actions()
        assert actions == []

    def test_buy_target_via_signal_with_zero_price_yields_no_action(self):
        """A buy target sized from a signal with a non-positive price resolves to no action."""
        portfolio = _empty_portfolio()
        rebalancer = Rebalancer(
            portfolio, target_allocation={"GOOGL": 0.5}, rebalance_threshold=0.05
        )
        signal = Signal(symbol="GOOGL", action="buy", strength=1.0, price=0.0)
        actions = rebalancer.generate_rebalance_actions(signals=[signal])
        assert actions == []

    def test_signal_buy_outside_allocation(self):
        """A buy signal for an untracked symbol is sized at 5% of value times strength."""
        portfolio = _empty_portfolio()
        rebalancer = Rebalancer(portfolio, target_allocation={})
        signal = Signal(symbol="GOOGL", action="buy", strength=1.0, price=100.0)
        actions = rebalancer.generate_rebalance_actions(signals=[signal])
        assert len(actions) == 1
        action = actions[0]
        assert action.symbol == "GOOGL"
        assert action.action == "buy"
        assert action.quantity == pytest.approx(50.0)  # 100000 * 0.05 * 1.0 / 100
        assert action.reason == "signal_unknown"

    def test_signal_buy_scaled_by_strength(self):
        """Signal strength scales the signal-sized target value."""
        portfolio = _empty_portfolio()
        rebalancer = Rebalancer(portfolio, target_allocation={})
        signal = Signal(symbol="GOOGL", action="buy", strength=0.5, price=100.0)
        actions = rebalancer.generate_rebalance_actions(signals=[signal])
        assert len(actions) == 1
        assert actions[0].quantity == pytest.approx(25.0)  # half strength

    def test_signal_buy_with_no_price_yields_no_action(self):
        """A buy signal without a price cannot be sized and produces no action."""
        portfolio = _empty_portfolio()
        rebalancer = Rebalancer(portfolio, target_allocation={})
        signal = Signal(symbol="GOOGL", action="buy", strength=1.0, price=None)
        actions = rebalancer.generate_rebalance_actions(signals=[signal])
        assert actions == []

    def test_signal_sell_liquidates_holding(self):
        """A sell signal emits a sell for the full held quantity."""
        portfolio = _portfolio_with_aapl()
        rebalancer = Rebalancer(portfolio, target_allocation={})
        signal = Signal(symbol="AAPL", action="sell", strength=1.0, price=100.0)
        actions = rebalancer.generate_rebalance_actions(signals=[signal])
        assert len(actions) == 1
        assert actions[0].action == "sell"
        assert actions[0].quantity == pytest.approx(100.0)
        assert actions[0].reason == "signal_sell"

    def test_signal_sell_no_holding_yields_no_action(self):
        """A sell signal for an unheld symbol produces no action."""
        portfolio = _empty_portfolio()
        rebalancer = Rebalancer(portfolio, target_allocation={})
        signal = Signal(symbol="AAPL", action="sell", strength=1.0, price=100.0)
        actions = rebalancer.generate_rebalance_actions(signals=[signal])
        assert actions == []

    def test_signal_for_tracked_symbol_is_ignored(self):
        """Signals for symbols in the target allocation are not signal-sized."""
        portfolio = _portfolio_with_aapl()
        rebalancer = Rebalancer(
            portfolio, target_allocation={"AAPL": 0.5}, rebalance_threshold=0.05
        )
        signal = Signal(symbol="AAPL", action="buy", strength=1.0, price=100.0)
        actions = rebalancer.generate_rebalance_actions(signals=[signal])
        assert len(actions) == 1
        assert actions[0].reason == "target_allocation"

    def test_records_history_and_updates_last_rebalance(self):
        """Each run records history and stamps last_rebalance."""
        portfolio = _portfolio_with_aapl()
        rebalancer = Rebalancer(
            portfolio, target_allocation={"AAPL": 0.0}, rebalance_threshold=0.05
        )
        assert rebalancer.last_rebalance is None
        assert rebalancer.rebalance_history == []
        rebalancer.generate_rebalance_actions()
        assert rebalancer.last_rebalance is not None
        assert isinstance(rebalancer.last_rebalance, datetime)
        assert len(rebalancer.rebalance_history) == 1
        entry = rebalancer.rebalance_history[0]
        assert "timestamp" in entry
        assert entry["actions"] == ["AAPL"]
        assert entry["portfolio_value"] == pytest.approx(portfolio.total_value)


class TestRebalancerRiskLimits:
    """Tests for risk-manager-aware action generation."""

    def _risk_manager(self, **kwargs):
        defaults = {
            "initial_capital": 100000.0,
            "max_position_size": 0.1,
            "max_drawdown": 0.20,
        }
        defaults.update(kwargs)
        return RiskManager(**defaults)

    def test_risk_manager_parameter_defaults_to_none(self):
        """The risk manager defaults to None when not supplied."""
        rebalancer = Rebalancer(_empty_portfolio())
        assert rebalancer.risk_manager is None

    def test_risk_manager_parameter_is_stored(self):
        """A supplied risk manager is stored on the rebalancer."""
        portfolio = _empty_portfolio()
        risk_manager = self._risk_manager()
        rebalancer = Rebalancer(portfolio, risk_manager=risk_manager)
        assert rebalancer.risk_manager is risk_manager

    def test_without_risk_manager_behavior_unchanged(self):
        """No risk manager means buys are generated exactly as before."""
        portfolio = _empty_portfolio()
        rebalancer = Rebalancer(
            portfolio, target_allocation={"AAPL": 1.0}, rebalance_threshold=0.05
        )
        actions = rebalancer.generate_rebalance_actions(prices={"AAPL": 100.0})
        assert len(actions) == 1
        assert actions[0].quantity == pytest.approx(1000.0)  # 100000 / 100

    def test_position_limit_sizes_buy_down(self):
        """A buy is reduced to the largest position the limits allow."""
        portfolio = _empty_portfolio()
        risk_manager = self._risk_manager(max_position_size=0.05)  # max $5,000
        rebalancer = Rebalancer(
            portfolio,
            target_allocation={"AAPL": 1.0},
            rebalance_threshold=0.05,
            risk_manager=risk_manager,
        )
        actions = rebalancer.generate_rebalance_actions(prices={"AAPL": 100.0})
        assert len(actions) == 1
        assert actions[0].quantity == pytest.approx(50.0)  # $5,000 / $100

    def test_position_limit_uses_smaller_of_fraction_and_dollar_cap(self):
        """The tighter of the size fraction and dollar value cap wins."""
        portfolio = _empty_portfolio()
        risk_manager = self._risk_manager(max_position_size=0.5)
        risk_manager.position_limit.max_value = 5000.0  # tighter than 50% of $100k
        rebalancer = Rebalancer(
            portfolio,
            target_allocation={"AAPL": 1.0},
            rebalance_threshold=0.05,
            risk_manager=risk_manager,
        )
        actions = rebalancer.generate_rebalance_actions(prices={"AAPL": 100.0})
        assert len(actions) == 1
        assert actions[0].quantity == pytest.approx(50.0)  # $5,000 / $100

    def test_position_limit_no_room_skips_buy(self):
        """A position already at its limit produces no further buy action."""
        portfolio = _portfolio_with_aapl()  # AAPL worth $10,000 of $100,000
        risk_manager = self._risk_manager(max_position_size=0.1)  # max $10,000
        rebalancer = Rebalancer(
            portfolio,
            target_allocation={"AAPL": 1.0},
            rebalance_threshold=0.05,
            risk_manager=risk_manager,
        )
        actions = rebalancer.generate_rebalance_actions(prices={"AAPL": 100.0})
        assert actions == []

    def test_drawdown_limit_halts_buys(self):
        """A breached drawdown (loss) limit drops all buy actions."""
        portfolio = _empty_portfolio()
        risk_manager = self._risk_manager(max_drawdown=0.10)
        risk_manager.update_portfolio_value({}, 90000.0)  # 10% drawdown breached
        rebalancer = Rebalancer(
            portfolio,
            target_allocation={"AAPL": 1.0},
            rebalance_threshold=0.05,
            risk_manager=risk_manager,
        )
        actions = rebalancer.generate_rebalance_actions(prices={"AAPL": 100.0})
        assert actions == []

    def test_drawdown_within_limit_still_buys(self):
        """A drawdown below the loss limit does not block buying."""
        portfolio = _empty_portfolio()
        risk_manager = self._risk_manager(max_drawdown=0.20, max_position_size=1.0)
        risk_manager.update_portfolio_value({}, 90000.0)  # 10% drawdown, below 20%
        rebalancer = Rebalancer(
            portfolio,
            target_allocation={"AAPL": 1.0},
            rebalance_threshold=0.05,
            risk_manager=risk_manager,
        )
        actions = rebalancer.generate_rebalance_actions(prices={"AAPL": 100.0})
        assert len(actions) == 1
        assert actions[0].quantity == pytest.approx(1000.0)

    def test_zero_drawdown_limit_skips_loss_check(self):
        """A zero drawdown limit skips the loss check; position limit still applies."""
        portfolio = _empty_portfolio()
        risk_manager = self._risk_manager(max_drawdown=0.0, max_position_size=0.05)
        rebalancer = Rebalancer(
            portfolio,
            target_allocation={"AAPL": 1.0},
            rebalance_threshold=0.05,
            risk_manager=risk_manager,
        )
        actions = rebalancer.generate_rebalance_actions(prices={"AAPL": 100.0})
        assert len(actions) == 1
        assert actions[0].quantity == pytest.approx(50.0)

    def test_disabled_risk_manager_buys_as_usual(self):
        """A disabled risk manager leaves buy generation unchanged."""
        portfolio = _empty_portfolio()
        risk_manager = self._risk_manager()
        risk_manager.disable()
        rebalancer = Rebalancer(
            portfolio,
            target_allocation={"AAPL": 1.0},
            rebalance_threshold=0.05,
            risk_manager=risk_manager,
        )
        actions = rebalancer.generate_rebalance_actions(prices={"AAPL": 100.0})
        assert len(actions) == 1
        assert actions[0].quantity == pytest.approx(1000.0)

    def test_signal_buy_respects_position_limit(self):
        """A signal-sized buy is reduced to the position limit."""
        portfolio = _empty_portfolio()
        risk_manager = self._risk_manager(max_position_size=0.01)  # max $1,000
        rebalancer = Rebalancer(
            portfolio,
            target_allocation={},
            risk_manager=risk_manager,
        )
        signal = Signal(symbol="GOOGL", action="buy", strength=1.0, price=100.0)
        actions = rebalancer.generate_rebalance_actions(signals=[signal], prices={"GOOGL": 100.0})
        assert len(actions) == 1
        assert actions[0].quantity == pytest.approx(10.0)  # $1,000 / $100

    def test_zero_quantity_signal_in_batch_skipped(self):
        """A signal that cannot be sized is skipped while later signals still trade."""
        portfolio = _empty_portfolio()
        rebalancer = Rebalancer(portfolio, target_allocation={})
        signals = [
            Signal(symbol="GOOGL", action="buy", strength=1.0, price=-10.0),
            Signal(symbol="AAPL", action="buy", strength=1.0, price=100.0),
        ]
        actions = rebalancer.generate_rebalance_actions(signals=signals, prices={"AAPL": 100.0})
        assert len(actions) == 1
        assert actions[0].symbol == "AAPL"
        assert actions[0].quantity == pytest.approx(50.0)

    def test_risk_limited_buy_executes_without_negative_cash(self):
        """A risk-limited buy executed through execute_actions keeps cash non-negative."""
        portfolio = _empty_portfolio()
        risk_manager = self._risk_manager(max_position_size=0.05)
        rebalancer = Rebalancer(
            portfolio,
            target_allocation={"AAPL": 1.0},
            rebalance_threshold=0.05,
            risk_manager=risk_manager,
        )
        actions = rebalancer.generate_rebalance_actions(
            prices={"AAPL": 100.0}, commission=0.001, slippage=0.0005
        )
        assert len(actions) == 1
        executions = rebalancer.execute_actions(
            actions, prices={"AAPL": 100.0}, commission=0.001, slippage=0.0005
        )
        assert executions[0].executed_quantity == pytest.approx(50.0)
        assert portfolio.cash >= 0.0


class TestSetTargetAllocation:
    """Tests for target allocation normalization."""

    def test_keeps_allocation_when_sum_near_one(self):
        """Allocations summing to 1.0 (within tolerance) are stored as-is."""
        portfolio = _empty_portfolio()
        rebalancer = Rebalancer(portfolio)
        rebalancer.set_target_allocation({"AAPL": 0.6, "MSFT": 0.4})
        assert rebalancer.target_allocation == {"AAPL": 0.6, "MSFT": 0.4}

    def test_normalizes_allocation_far_from_one(self):
        """Allocations not summing to 1.0 are rescaled to sum to 1.0."""
        portfolio = _empty_portfolio()
        rebalancer = Rebalancer(portfolio)
        rebalancer.set_target_allocation({"AAPL": 2, "MSFT": 3})
        assert rebalancer.target_allocation == pytest.approx({"AAPL": 0.4, "MSFT": 0.6})

    def test_single_symbol_normalizes_to_one(self):
        """A lone target is normalized to 100%."""
        portfolio = _empty_portfolio()
        rebalancer = Rebalancer(portfolio)
        rebalancer.set_target_allocation({"AAPL": 0.6})
        assert rebalancer.target_allocation == pytest.approx({"AAPL": 1.0})


class TestGetCurrentDeviation:
    """Tests for deviation-from-target computation."""

    def test_returns_current_minus_target(self):
        """Deviation is current allocation fraction minus target fraction."""
        portfolio = _portfolio_with_aapl()
        rebalancer = Rebalancer(portfolio, target_allocation={"AAPL": 0.5, "MSFT": 0.2})
        deviations = rebalancer.get_current_deviation()
        aapl_pct = 10000.0 / portfolio.total_value
        assert deviations["AAPL"] == pytest.approx(aapl_pct - 0.5)
        assert deviations["MSFT"] == pytest.approx(0.0 - 0.2)

    def test_missing_symbol_has_zero_current_allocation(self):
        """An unheld symbol reports a deviation of negative its target."""
        portfolio = _empty_portfolio()
        rebalancer = Rebalancer(portfolio, target_allocation={"GOOGL": 0.3})
        deviations = rebalancer.get_current_deviation()
        assert deviations == pytest.approx({"GOOGL": -0.3})


class TestNeedsRebalance:
    """Tests for deviation-based needs_rebalance."""

    def test_true_when_deviation_exceeds_threshold(self):
        """Any deviation above the threshold triggers needs_rebalance."""
        portfolio = _portfolio_with_aapl()
        rebalancer = Rebalancer(
            portfolio, target_allocation={"AAPL": 0.5}, rebalance_threshold=0.05
        )
        assert rebalancer.needs_rebalance() is True

    def test_false_within_threshold(self):
        """Deviations within the threshold do not trigger."""
        portfolio = _portfolio_with_aapl()
        rebalancer = Rebalancer(
            portfolio, target_allocation={"AAPL": 0.11}, rebalance_threshold=0.05
        )
        assert rebalancer.needs_rebalance() is False

    def test_false_when_no_target_allocation(self):
        """No target allocation means no rebalance is needed."""
        portfolio = _portfolio_with_aapl()
        rebalancer = Rebalancer(portfolio)
        assert rebalancer.needs_rebalance() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
