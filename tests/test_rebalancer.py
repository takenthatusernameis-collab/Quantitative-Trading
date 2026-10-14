"""Tests for the portfolio rebalancer."""

from datetime import datetime

import pytest

from quant_trading.portfolio.portfolio import Portfolio
from quant_trading.portfolio.rebalancer import RebalanceAction, Rebalancer
from quant_trading.strategies.base import Signal


class TestRebalanceAction:
    """Tests for RebalanceAction dataclass."""

    def test_rebalance_action_creation(self):
        """Test creating a RebalanceAction."""
        action = RebalanceAction(
            symbol="AAPL",
            action="buy",
            quantity=10.0,
            reason="target_allocation",
        )
        assert action.symbol == "AAPL"
        assert action.action == "buy"
        assert action.quantity == 10.0
        assert action.reason == "target_allocation"
        assert action.timestamp is not None


class TestRebalancer:
    """Tests for Rebalancer class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        self.rebalancer = Rebalancer(
            portfolio=self.portfolio,
            frequency="monthly",
            target_allocation={"AAPL": 0.4, "MSFT": 0.6},
            rebalance_threshold=0.05,
        )

    def test_rebalancer_initialization(self):
        """Test Rebalancer initialization."""
        assert self.rebalancer.portfolio is self.portfolio
        assert self.rebalancer.frequency == "monthly"
        assert self.rebalancer.target_allocation == {"AAPL": 0.4, "MSFT": 0.6}
        assert self.rebalancer.rebalance_threshold == 0.05
        assert self.rebalancer.last_rebalance is None
        assert self.rebalancer.rebalance_history == []

    def test_should_rebalance_first_time(self):
        """Test should_rebalance returns True on first call."""
        assert self.rebalancer.should_rebalance() is True

    def test_should_rebalance_daily(self):
        """Test should_rebalance with daily frequency."""
        rebalancer = Rebalancer(self.portfolio, frequency="daily")
        rebalancer.last_rebalance = datetime.now()
        assert rebalancer.should_rebalance() is False

    def test_should_rebalance_weekly(self):
        """Test should_rebalance with weekly frequency."""
        from datetime import timedelta

        rebalancer = Rebalancer(self.portfolio, frequency="weekly")
        rebalancer.last_rebalance = datetime.now() - timedelta(days=3)
        assert rebalancer.should_rebalance() is False
        rebalancer.last_rebalance = datetime.now() - timedelta(days=8)
        assert rebalancer.should_rebalance() is True

    def test_calculate_target_values(self):
        """Test calculate_target_values."""
        self.portfolio.cash = 100000.0
        self.portfolio.total_value = 100000.0
        targets = self.rebalancer.calculate_target_values()
        assert targets["AAPL"] == 40000.0
        assert targets["MSFT"] == 60000.0

    def test_generate_rebalance_actions_no_holdings(self):
        """Test generate_rebalance_actions with no current holdings."""
        self.portfolio.cash = 100000.0
        self.portfolio.total_value = 100000.0
        actions = self.rebalancer.generate_rebalance_actions(prices={"AAPL": 150.0, "MSFT": 300.0})
        assert len(actions) == 2
        buy_actions = [a for a in actions if a.action == "buy"]
        assert len(buy_actions) == 2

    def test_generate_rebalance_actions_with_holdings(self):
        """Test generate_rebalance_actions with existing holdings."""
        self.portfolio.add_holding("AAPL", 200, 150.0)  # $30,000
        self.portfolio.add_holding("MSFT", 100, 300.0)  # $30,000
        self.portfolio.total_value = self.portfolio.cash + self.portfolio.get_holdings_value()

        actions = self.rebalancer.generate_rebalance_actions()
        # AAPL: target 40% of 100k = 40k, current 30k -> buy 10k worth
        # MSFT: target 60% of 100k = 60k, current 30k -> buy 30k worth
        buy_actions = [a for a in actions if a.action == "buy"]
        assert len(buy_actions) == 2

    def test_generate_rebalance_actions_sell(self):
        """Test generate_rebalance_actions generates sell when over-allocated."""
        # Set up portfolio with too much AAPL
        self.portfolio.add_holding("AAPL", 500, 150.0)  # $75,000 (75%)
        self.portfolio.add_holding("MSFT", 100, 300.0)  # $30,000 (30%)
        self.portfolio.total_value = self.portfolio.cash + self.portfolio.get_holdings_value()

        actions = self.rebalancer.generate_rebalance_actions()
        sell_actions = [a for a in actions if a.action == "sell"]
        assert len(sell_actions) == 1
        assert sell_actions[0].symbol == "AAPL"

    def test_generate_rebalance_actions_with_signals(self):
        """Test generate_rebalance_actions processes signals."""
        self.portfolio.cash = 100000.0
        self.portfolio.total_value = 100000.0

        signals = [
            Signal(symbol="GOOGL", action="buy", strength=0.8, price=140.0),
        ]
        actions = self.rebalancer.generate_rebalance_actions(
            signals=signals, prices={"AAPL": 150.0, "MSFT": 300.0}
        )

        # Should have actions for AAPL, MSFT (target) + GOOGL (signal)
        assert len(actions) >= 3
        signal_actions = [a for a in actions if a.reason.startswith("signal_")]
        assert len(signal_actions) == 1
        assert signal_actions[0].symbol == "GOOGL"

    def test_generate_rebalance_actions_sell_signal(self):
        """Test generate_rebalance_actions processes sell signals."""
        self.portfolio.add_holding("AAPL", 100, 150.0)
        self.portfolio.total_value = self.portfolio.cash + self.portfolio.get_holdings_value()

        signals = [
            Signal(symbol="AAPL", action="sell", strength=1.0, price=150.0),
        ]
        actions = self.rebalancer.generate_rebalance_actions(signals=signals)

        sell_actions = [a for a in actions if a.action == "sell" and a.symbol == "AAPL"]
        assert len(sell_actions) == 1

    def test_generate_rebalance_actions_zero_price_holdings(self):
        """Test generate_rebalance_actions guards against zero prices in holdings."""
        self.portfolio.add_holding("AAPL", 100, 150.0)  # $15,000
        # Force the holding's current_price to 0 (e.g. stale quote)
        self.portfolio.holdings["AAPL"].current_price = 0.0
        self.portfolio.total_value = self.portfolio.cash + self.portfolio.get_holdings_value()

        actions = self.rebalancer.generate_rebalance_actions(prices={"AAPL": 150.0, "MSFT": 300.0})
        # AAPL target 40% of 100k = 40k, current 15k -> buy 25k worth.
        # With a zero holding price, the prices dict should be used.
        aapl_buys = [a for a in actions if a.symbol == "AAPL" and a.action == "buy"]
        assert len(aapl_buys) == 1
        assert aapl_buys[0].quantity > 0

    def test_generate_rebalance_actions_zero_price_no_prices(self):
        """Test generate_rebalance_actions produces no buy when no price source exists."""
        self.portfolio.cash = 100000.0
        self.portfolio.total_value = 100000.0
        actions = self.rebalancer.generate_rebalance_actions()
        # No holdings, no prices, no signals -> no actionable buys.
        buy_actions = [a for a in actions if a.action == "buy"]
        assert buy_actions == []

    def test_generate_rebalance_actions_zero_total_value(self):
        """Test generate_rebalance_actions is a no-op when total_value is zero."""
        self.portfolio.cash = 0.0
        self.portfolio.total_value = 0.0
        actions = self.rebalancer.generate_rebalance_actions(prices={"AAPL": 150.0})
        assert actions == []

    def test_resolve_sell_quantity_zero_price(self):
        """_resolve_sell_quantity returns 0 when the holding price is zero."""
        self.portfolio.add_holding("AAPL", 100, 150.0)
        self.portfolio.holdings["AAPL"].current_price = 0.0
        assert self.rebalancer._resolve_sell_quantity("AAPL", 1000.0) == 0.0

    def test_resolve_buy_quantity_no_price_source(self):
        """_resolve_buy_quantity returns 0 when no usable price is available."""
        self.portfolio.cash = 100000.0
        self.portfolio.total_value = 100000.0
        assert self.rebalancer._resolve_buy_quantity("AAPL", 1000.0, None, {}) == 0.0

    def test_generate_rebalance_actions_sell_zero_price(self):
        """Test sell actions are skipped when the holding price is zero."""
        self.portfolio.add_holding("AAPL", 500, 150.0)  # $75,000 (75%)
        self.portfolio.add_holding("MSFT", 100, 300.0)  # $30,000 (30%)
        self.portfolio.holdings["AAPL"].current_price = 0.0
        self.portfolio.total_value = self.portfolio.cash + self.portfolio.get_holdings_value()

        actions = self.rebalancer.generate_rebalance_actions()
        aapl_sells = [a for a in actions if a.symbol == "AAPL" and a.action == "sell"]
        assert aapl_sells == []

    def test_set_target_allocation(self):
        """Test set_target_allocation normalizes values."""
        self.rebalancer.set_target_allocation({"AAPL": 0.3, "MSFT": 0.3, "GOOGL": 0.3})
        # Should normalize to sum = 1.0
        total = sum(self.rebalancer.target_allocation.values())
        assert abs(total - 1.0) < 0.01

    def test_get_current_deviation(self):
        """Test get_current_deviation."""
        self.portfolio.add_holding("AAPL", 200, 150.0)  # $30,000
        self.portfolio.total_value = self.portfolio.cash + self.portfolio.get_holdings_value()

        deviations = self.rebalancer.get_current_deviation()
        # AAPL target 40%, actual 30% -> deviation -10%
        assert "AAPL" in deviations
        assert abs(deviations["AAPL"] - (-0.10)) < 0.02  # Approximately -10%

    def test_needs_rebalance(self):
        """Test needs_rebalance."""
        # No target allocation -> False
        rebalancer = Rebalancer(self.portfolio)
        assert rebalancer.needs_rebalance() is False

        # With target but no holdings -> True (0% vs target)
        rebalancer = Rebalancer(
            self.portfolio,
            target_allocation={"AAPL": 0.5},
            rebalance_threshold=0.05,
        )
        assert rebalancer.needs_rebalance() is True

        # With target and matching holdings -> False
        self.portfolio.add_holding("AAPL", 500, 100.0)  # $50,000 out of $100,000 = 50%
        self.portfolio.total_value = self.portfolio.cash + self.portfolio.get_holdings_value()
        assert rebalancer.needs_rebalance() is False

    def test_rebalance_history_tracking(self):
        """Test that rebalance history is tracked."""
        self.portfolio.cash = 100000.0
        self.portfolio.total_value = 100000.0
        self.rebalancer.generate_rebalance_actions()

        assert len(self.rebalancer.rebalance_history) == 1
        history_entry = self.rebalancer.rebalance_history[0]
        assert "timestamp" in history_entry
        assert "actions" in history_entry
        assert "portfolio_value" in history_entry

    def test_should_rebalance_monthly(self):
        """Test should_rebalance with monthly frequency triggers across month boundaries."""
        from datetime import timedelta

        rebalancer = Rebalancer(self.portfolio, frequency="monthly")
        # Same month -> False
        rebalancer.last_rebalance = datetime.now().replace(day=1)
        assert rebalancer.should_rebalance() is False
        # Previous month -> True
        rebalancer.last_rebalance = datetime.now() - timedelta(days=40)
        assert rebalancer.should_rebalance() is True

    def test_should_rebalance_quarterly(self):
        """Test should_rebalance with quarterly frequency."""
        from datetime import timedelta

        rebalancer = Rebalancer(self.portfolio, frequency="quarterly")
        # Less than 90 days -> False
        rebalancer.last_rebalance = datetime.now() - timedelta(days=30)
        assert rebalancer.should_rebalance() is False
        # >= 90 days -> True
        rebalancer.last_rebalance = datetime.now() - timedelta(days=95)
        assert rebalancer.should_rebalance() is True

    def test_should_rebalance_unknown_frequency(self):
        """Test should_rebalance returns False for an unknown frequency."""
        from datetime import timedelta

        rebalancer = Rebalancer(self.portfolio, frequency="yearly")
        rebalancer.last_rebalance = datetime.now() - timedelta(days=30)
        assert rebalancer.should_rebalance() is False

    def test_resolve_buy_quantity_from_signals(self):
        """_resolve_buy_quantity derives a price from matching signals when no
        holding or price dict is available."""
        self.portfolio.cash = 100000.0
        self.portfolio.total_value = 100000.0
        # No AAPL holding and no AAPL price in the prices dict, but a buy signal
        # provides a price. The average of matching signal prices is used.
        signals = [
            Signal(symbol="AAPL", action="buy", strength=1.0, price=150.0),
            Signal(symbol="AAPL", action="buy", strength=1.0, price=160.0),
        ]
        quantity = self.rebalancer._resolve_buy_quantity("AAPL", 1000.0, signals, {})
        assert quantity == pytest.approx(1000.0 / 155.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
