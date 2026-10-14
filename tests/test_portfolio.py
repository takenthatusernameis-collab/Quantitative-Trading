"""Tests for the portfolio data structures."""

import pytest

from quant_trading.portfolio.portfolio import Holding, Portfolio


class TestHolding:
    """Tests for the Holding dataclass."""

    def test_unrealized_pnl_zero_quantity(self):
        """unrealized_pnl returns 0 when quantity is zero."""
        holding = Holding(symbol="AAPL", quantity=0, avg_cost=100.0, current_price=150.0)
        assert holding.unrealized_pnl == 0.0

    def test_unrealized_pnl_zero_cost(self):
        """unrealized_pnl returns 0 when avg_cost is zero."""
        holding = Holding(symbol="AAPL", quantity=100, avg_cost=0.0, current_price=150.0)
        assert holding.unrealized_pnl == 0.0

    def test_unrealized_pnl_positive(self):
        """unrealized_pnl computes for a profitable holding."""
        holding = Holding(symbol="AAPL", quantity=100, avg_cost=100.0, current_price=150.0)
        assert holding.unrealized_pnl == 5000.0

    def test_unrealized_pnl_pct_zero_cost(self):
        """unrealized_pnl_pct returns 0 when avg_cost is zero."""
        holding = Holding(symbol="AAPL", quantity=100, avg_cost=0.0, current_price=150.0)
        assert holding.unrealized_pnl_pct == 0.0

    def test_unrealized_pnl_pct(self):
        """unrealized_pnl_pct computes the percentage gain."""
        holding = Holding(symbol="AAPL", quantity=100, avg_cost=100.0, current_price=150.0)
        assert holding.unrealized_pnl_pct == pytest.approx(0.5)

    def test_to_position(self):
        """to_position converts a Holding to a Position."""
        holding = Holding(
            symbol="AAPL", quantity=100, avg_cost=100.0, current_price=150.0, market_value=15000.0
        )
        position = holding.to_position()
        assert position.symbol == "AAPL"
        assert position.quantity == 100
        assert position.avg_price == 100.0
        assert position.current_price == 150.0
        assert position.unrealized_pnl == 5000.0

    def test_update_price(self):
        """update_price recalculates market value."""
        holding = Holding(symbol="AAPL", quantity=100, avg_cost=100.0, current_price=100.0)
        holding.update_price(120.0)
        assert holding.current_price == 120.0
        assert holding.market_value == 12000.0


class TestPortfolio:
    """Tests for the Portfolio dataclass."""

    def test_portfolio_default_init(self):
        """Portfolio with no cash sets initial_capital to 0.0."""
        portfolio = Portfolio()
        assert portfolio.initial_capital == 0.0
        assert portfolio.cash == 0.0

    def test_portfolio_cash_only_init(self):
        """Portfolio infers initial_capital from cash when cash provided."""
        portfolio = Portfolio(cash=100000.0)
        assert portfolio.initial_capital == 100000.0

    def test_get_position_value_missing_symbol(self):
        """get_position_value returns 0 for unknown symbols."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        assert portfolio.get_position_value("MISSING") == 0.0

    def test_get_position_pct_zero_value(self):
        """get_position_pct returns 0 when total_value is non-positive."""
        portfolio = Portfolio()
        assert portfolio.get_position_pct("AAPL") == 0.0

    def test_get_position_pct(self):
        """get_position_pct computes percentage allocation."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 50.0)
        assert portfolio.get_position_pct("AAPL") == pytest.approx(5000.0 / portfolio.total_value)

    def test_get_allocation_zero_value(self):
        """get_allocation returns empty dict when total_value is non-positive."""
        portfolio = Portfolio()
        assert portfolio.get_allocation() == {}

    def test_add_holding_net_zero(self):
        """Adding an opposite position that nets to zero resets avg_cost to 0."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        # Short to exactly offset the long position
        portfolio.add_holding("AAPL", -100, 100.0)
        assert portfolio.holdings["AAPL"].quantity == 0
        assert portfolio.holdings["AAPL"].avg_cost == 0.0

    def test_remove_holding_no_symbol(self):
        """remove_holding returns 0.0 for an unknown symbol."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        assert portfolio.remove_holding("MISSING", 10, 100.0) == 0.0

    def test_remove_holding_full(self):
        """remove_holding deletes the holding when fully sold."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        proceeds = portfolio.remove_holding("AAPL", 100, 110.0)
        assert "AAPL" not in portfolio.holdings
        assert proceeds == 11000.0

    def test_remove_holding_partial_keeps_pos(self):
        """remove_holding keeps the holding when partially sold."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        portfolio.remove_holding("AAPL", 40, 110.0)
        assert "AAPL" in portfolio.holdings
        assert portfolio.holdings["AAPL"].quantity == 60

    def test_add_holding_existing_averaging(self):
        """add_holding to an existing holding averages the cost basis."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        portfolio.add_holding("AAPL", 50, 120.0)
        assert portfolio.holdings["AAPL"].quantity == 150
        assert portfolio.holdings["AAPL"].avg_cost == pytest.approx((10000.0 + 6000.0) / 150)

    def test_update_prices_existing(self):
        """update_prices recalculates market value for held symbols."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        portfolio.update_prices({"AAPL": 120.0})
        assert portfolio.holdings["AAPL"].current_price == 120.0
        assert portfolio.holdings["AAPL"].market_value == 12000.0

    def test_update_prices_unknown_symbol(self):
        """update_prices ignores unknown symbols in the price dict."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        portfolio.update_prices({"UNKNOWN": 99.0})
        assert portfolio.holdings["AAPL"].current_price == 100.0

    def test_get_positions(self):
        """get_positions returns Position objects for all holdings."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        positions = portfolio.get_positions()
        assert "AAPL" in positions
        assert positions["AAPL"].quantity == 100

    def test_reset(self):
        """reset clears the portfolio back to a single cash balance."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        portfolio.reset(200000.0)
        assert portfolio.cash == 200000.0
        assert len(portfolio.holdings) == 0
        assert portfolio.total_value == 200000.0
        assert portfolio.initial_capital == 200000.0
        assert portfolio.last_rebalance is None

    def test_summary(self):
        """summary returns a populated summary dict."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)

        summary = portfolio.summary()
        assert "total_value" in summary
        assert summary["total_value"] == portfolio.total_value
        assert summary["cash"] == portfolio.cash
        assert summary["holdings_value"] == portfolio.get_holdings_value()
        assert summary["num_positions"] == 1
        assert "AAPL" in summary["allocation"]
        assert summary["pnl"] == pytest.approx(portfolio.total_value - 100000.0)
        assert summary["pnl_pct"] == pytest.approx(
            (portfolio.total_value - 100000.0) / 100000.0 * 100
        )

    def test_summary_zero_capital(self):
        """summary pnls are 0 when initial_capital is 0."""
        portfolio = Portfolio()
        summary = portfolio.summary()
        assert summary["pnl_pct"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
