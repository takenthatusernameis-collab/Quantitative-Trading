"""Tests for the portfolio data structures."""

from datetime import datetime

import pytest

from quant_trading.portfolio.portfolio import Holding, Portfolio


class TestHolding:
    """Tests for the Holding dataclass."""

    def test_unrealized_pnl_zero_quantity(self) -> None:
        """unrealized_pnl returns 0 when quantity is zero."""
        holding = Holding(symbol="AAPL", quantity=0, avg_cost=100.0, current_price=150.0)
        assert holding.unrealized_pnl == 0.0

    def test_unrealized_pnl_zero_cost(self) -> None:
        """unrealized_pnl returns 0 when avg_cost is zero."""
        holding = Holding(symbol="AAPL", quantity=100, avg_cost=0.0, current_price=150.0)
        assert holding.unrealized_pnl == 0.0

    def test_unrealized_pnl_positive(self) -> None:
        """unrealized_pnl computes for a profitable holding."""
        holding = Holding(symbol="AAPL", quantity=100, avg_cost=100.0, current_price=150.0)
        assert holding.unrealized_pnl == 5000.0

    def test_unrealized_pnl_pct_zero_cost(self) -> None:
        """unrealized_pnl_pct returns 0 when avg_cost is zero."""
        holding = Holding(symbol="AAPL", quantity=100, avg_cost=0.0, current_price=150.0)
        assert holding.unrealized_pnl_pct == 0.0

    def test_unrealized_pnl_pct(self) -> None:
        """unrealized_pnl_pct computes the percentage gain."""
        holding = Holding(symbol="AAPL", quantity=100, avg_cost=100.0, current_price=150.0)
        assert holding.unrealized_pnl_pct == pytest.approx(0.5)

    def test_unrealized_pnl_pct_short(self) -> None:
        """unrealized_pnl_pct is the negation of the long's for a short."""
        holding = Holding(symbol="AAPL", quantity=-100, avg_cost=100.0, current_price=150.0)
        assert holding.unrealized_pnl == pytest.approx(-5000.0)
        assert holding.unrealized_pnl_pct == pytest.approx(-0.5)

    def test_unrealized_pnl_pct_zero_quantity(self) -> None:
        """unrealized_pnl_pct returns 0 when quantity is zero."""
        holding = Holding(symbol="AAPL", quantity=0, avg_cost=100.0, current_price=150.0)
        assert holding.unrealized_pnl_pct == 0.0

    def test_to_position(self) -> None:
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

    def test_update_price(self) -> None:
        """update_price recalculates market value."""
        holding = Holding(symbol="AAPL", quantity=100, avg_cost=100.0, current_price=100.0)
        holding.update_price(120.0)
        assert holding.current_price == 120.0
        assert holding.market_value == 12000.0

    def test_update_price_non_finite_price(self) -> None:
        """update_price with a non-finite price keeps current_price and zeroes market value."""
        holding = Holding(symbol="AAPL", quantity=100, avg_cost=100.0, current_price=100.0)
        holding.update_price(float("nan"))
        assert holding.current_price == 100.0
        assert holding.market_value == 0.0
        holding.update_price(float("inf"))
        assert holding.current_price == 100.0
        assert holding.market_value == 0.0


class TestPortfolio:
    """Tests for the Portfolio dataclass."""

    def test_portfolio_default_init(self) -> None:
        """Portfolio with no cash sets initial_capital to 0.0."""
        portfolio = Portfolio()
        assert portfolio.initial_capital == 0.0
        assert portfolio.cash == 0.0

    def test_portfolio_total_value_already_set(self) -> None:
        """When total_value is non-zero, __post_init__ skips the auto-derivation
        (the `if self.total_value == 0` False branch, 67->exit)."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0, total_value=250000.0)
        assert portfolio.total_value == 250000.0

    def test_portfolio_cash_only_init(self) -> None:
        """Portfolio infers initial_capital from cash when cash provided."""
        portfolio = Portfolio(cash=100000.0)
        assert portfolio.initial_capital == 100000.0

    def test_get_position_value_missing_symbol(self) -> None:
        """get_position_value returns 0 for unknown symbols."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        assert portfolio.get_position_value("MISSING") == 0.0

    def test_get_position_pct_zero_value(self) -> None:
        """get_position_pct returns 0 when total_value is non-positive."""
        portfolio = Portfolio()
        assert portfolio.get_position_pct("AAPL") == 0.0

    def test_get_position_pct(self) -> None:
        """get_position_pct computes percentage allocation."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 50.0)
        assert portfolio.get_position_pct("AAPL") == pytest.approx(5000.0 / portfolio.total_value)

    def test_get_allocation_zero_value(self) -> None:
        """get_allocation returns empty dict when total_value is non-positive."""
        portfolio = Portfolio()
        assert portfolio.get_allocation() == {}

    def test_add_holding_net_zero(self) -> None:
        """A position that is fully offset is removed from the portfolio."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        # Short to exactly offset the long position
        portfolio.add_holding("AAPL", -100, 100.0)
        assert "AAPL" not in portfolio.holdings

    def test_remove_holding_no_symbol(self) -> None:
        """remove_holding returns 0.0 for an unknown symbol."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        assert portfolio.remove_holding("MISSING", 10, 100.0) == 0.0

    def test_remove_holding_full(self) -> None:
        """remove_holding deletes the holding when fully sold."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        proceeds = portfolio.remove_holding("AAPL", 100, 110.0)
        assert "AAPL" not in portfolio.holdings
        assert proceeds == 11000.0

    def test_remove_holding_partial_keeps_pos(self) -> None:
        """remove_holding keeps the holding when partially sold."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        portfolio.remove_holding("AAPL", 40, 110.0)
        assert "AAPL" in portfolio.holdings
        assert portfolio.holdings["AAPL"].quantity == 60

    def test_add_holding_existing_averaging(self) -> None:
        """add_holding to an existing holding averages the cost basis."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        portfolio.add_holding("AAPL", 50, 120.0)
        assert portfolio.holdings["AAPL"].quantity == 150
        assert portfolio.holdings["AAPL"].avg_cost == pytest.approx((10000.0 + 6000.0) / 150)

    def test_add_holding_capitalizes_entry_fees(self) -> None:
        """A new long position costs at price including commission and slippage."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 10, 100.0, commission=0.001, slippage=0.0005)
        assert portfolio.holdings["AAPL"].quantity == 10
        assert portfolio.holdings["AAPL"].avg_cost == pytest.approx(100.0 * (1 + 0.001 + 0.0005))
        assert portfolio.cash == pytest.approx(100000.0 - 10 * 100.0 * (1 + 0.001 + 0.0005))

    def test_add_holding_averaging_includes_entry_fees(self) -> None:
        """Lots added to a long are averaged at their fee-inclusive cost."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0, commission=0.001, slippage=0.0005)
        portfolio.add_holding("AAPL", 50, 120.0, commission=0.001, slippage=0.0005)
        assert portfolio.holdings["AAPL"].quantity == 150
        expected = (100 * 100.0 * 1.0015 + 50 * 120.0 * 1.0015) / 150
        assert portfolio.holdings["AAPL"].avg_cost == pytest.approx(expected)

    def test_short_position_keeps_execution_price_as_basis(self) -> None:
        """A new short position keeps the execution price as its basis."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", -100, 100.0, commission=0.001, slippage=0.0005)
        assert portfolio.holdings["AAPL"].quantity == -100
        assert portfolio.holdings["AAPL"].avg_cost == pytest.approx(100.0)

    def test_add_holding_partial_reduction_keeps_basis(self) -> None:
        """Reducing a long leaves the remaining basis untouched."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        portfolio.add_holding("AAPL", -40, 110.0)
        holding = portfolio.holdings["AAPL"]
        assert holding.quantity == 60
        assert holding.avg_cost == pytest.approx(100.0)
        # Cash is credited with the net proceeds of the reduction.
        assert portfolio.cash == pytest.approx(100000.0 - 100 * 100.0 + 40 * 110.0)

    def test_add_holding_reduction_larger_than_position_is_capped(self) -> None:
        """A reduction sells only what is held and credits only that much cash."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        portfolio.add_holding("AAPL", -150, 110.0)
        assert "AAPL" not in portfolio.holdings
        assert portfolio.cash == pytest.approx(100000.0 - 100 * 100.0 + 100 * 110.0)

    def test_add_holding_grows_an_existing_short(self) -> None:
        """Selling more of an open short grows it instead of replacing it."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", -100, 100.0)
        portfolio.add_holding("AAPL", -50, 120.0)
        holding = portfolio.holdings["AAPL"]
        assert holding.quantity == -150
        assert holding.avg_cost == pytest.approx((100 * 100.0 + 120 * 50.0) / 150)
        assert portfolio.cash == pytest.approx(100000.0 + 100 * 100.0 + 50 * 120.0)

    def test_add_holding_reduces_an_existing_short(self) -> None:
        """Buying back an open short reduces it instead of flipping the sign."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", -100, 100.0)
        portfolio.add_holding("AAPL", 40, 90.0)
        holding = portfolio.holdings["AAPL"]
        assert holding.quantity == -60
        assert holding.avg_cost == pytest.approx(100.0)
        assert portfolio.cash == pytest.approx(100000.0 + 100 * 100.0 - 40 * 90.0)

    def test_add_holding_zero_quantity_creates_no_position(self) -> None:
        """A zero-sized trade does not create a position."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 0, 100.0)
        assert "AAPL" not in portfolio.holdings
        assert portfolio.cash == 100000.0

    def test_remove_holding_covers_a_short(self) -> None:
        """remove_holding buys back a short position."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", -100, 100.0)
        cash_effect = portfolio.remove_holding("AAPL", 40, 90.0)
        holding = portfolio.holdings["AAPL"]
        assert holding.quantity == -60
        assert holding.avg_cost == pytest.approx(100.0)
        assert cash_effect == pytest.approx(-40 * 90.0)
        assert portfolio.cash == pytest.approx(100000.0 + 100 * 100.0 - 40 * 90.0)

    def test_remove_holding_fully_covers_a_short(self) -> None:
        """remove_holding deletes the position when the short is fully covered."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", -100, 100.0)
        portfolio.remove_holding("AAPL", 100, 90.0)
        assert "AAPL" not in portfolio.holdings
        assert portfolio.cash == pytest.approx(100000.0 + 100 * 100.0 - 100 * 90.0)

    def test_update_prices_existing(self) -> None:
        """update_prices recalculates market value for held symbols."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        portfolio.update_prices({"AAPL": 120.0})
        assert portfolio.holdings["AAPL"].current_price == 120.0
        assert portfolio.holdings["AAPL"].market_value == 12000.0

    def test_update_prices_unknown_symbol(self) -> None:
        """update_prices ignores unknown symbols in the price dict."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        portfolio.update_prices({"UNKNOWN": 99.0})
        assert portfolio.holdings["AAPL"].current_price == 100.0

    def test_get_positions(self) -> None:
        """get_positions returns Position objects for all holdings."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        positions = portfolio.get_positions()
        assert "AAPL" in positions
        assert positions["AAPL"].quantity == 100

    def test_get_position(self) -> None:
        """get_position returns the Position of a single held symbol."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 150.0)
        position = portfolio.get_position("AAPL")
        assert position is not None
        assert position.symbol == "AAPL"
        assert position.quantity == 100
        assert position.avg_price == 150.0

    def test_get_position_missing_symbol(self) -> None:
        """get_position returns None for a symbol that is not held."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        assert portfolio.get_position("AAPL") is None

    def test_reset(self) -> None:
        """reset clears the portfolio back to a single cash balance."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        portfolio.reset(200000.0)
        assert portfolio.cash == 200000.0
        assert len(portfolio.holdings) == 0
        assert portfolio.total_value == 200000.0
        assert portfolio.initial_capital == 200000.0
        assert portfolio.last_rebalance is None

    def test_summary(self) -> None:
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

    def test_summary_zero_capital(self) -> None:
        """summary pnls are 0 when initial_capital is 0."""
        portfolio = Portfolio()
        summary = portfolio.summary()
        assert summary["pnl_pct"] == 0

    def test_get_allocation_short_positions_signed(self) -> None:
        """get_allocation with use_absolute=False returns signed weights for shorts."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", -100, 100.0)  # Short position
        allocation = portfolio.get_allocation(use_absolute=False)
        # Short position has negative market value
        assert "AAPL" in allocation
        assert allocation["AAPL"] < 0

    def test_get_allocation_short_positions_absolute(self) -> None:
        """get_allocation with use_absolute=True returns positive weights for shorts."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", -100, 100.0)  # Short position
        allocation = portfolio.get_allocation(use_absolute=True)
        assert "AAPL" in allocation
        assert allocation["AAPL"] > 0

    def test_get_net_allocation_short_positions(self) -> None:
        """get_net_allocation returns signed weights with shorts negative."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", -100, 100.0)
        net_alloc = portfolio.get_net_allocation()
        assert net_alloc["AAPL"] < 0
        assert net_alloc == portfolio.get_allocation(use_absolute=False)

    def test_get_gross_allocation_short_positions(self) -> None:
        """get_gross_allocation returns absolute weights with shorts positive."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", -100, 100.0)
        gross_alloc = portfolio.get_gross_allocation()
        assert gross_alloc["AAPL"] > 0
        assert gross_alloc == portfolio.get_allocation(use_absolute=True)

    def test_allocation_invariants_mixed_long_short(self) -> None:
        """Test allocation invariants with mixed long and short positions."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)  # Long
        portfolio.add_holding("GOOG", -50, 200.0)  # Short

        net_alloc = portfolio.get_net_allocation()
        gross_alloc = portfolio.get_gross_allocation()

        # Net allocation: long positive, short negative
        assert net_alloc["AAPL"] > 0
        assert net_alloc["GOOG"] < 0

        # Gross allocation: both positive
        assert gross_alloc["AAPL"] > 0
        assert gross_alloc["GOOG"] > 0

        # Invariants
        # Sum of absolute values for gross should equal sum of abs for all
        assert sum(gross_alloc.values()) == pytest.approx(sum(abs(v) for v in net_alloc.values()))
        # Net and gross should have same magnitude per position
        for sym in net_alloc:
            assert abs(net_alloc[sym]) == pytest.approx(abs(gross_alloc[sym]))

    def test_allocation_invariants_long_only(self) -> None:
        """Test allocation invariants for long-only portfolio."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)

        net_alloc = portfolio.get_net_allocation()
        gross_alloc = portfolio.get_gross_allocation()

        # For long positions, net and gross should be identical
        assert net_alloc["AAPL"] == pytest.approx(gross_alloc["AAPL"])
        assert net_alloc["AAPL"] > 0

    # -- Exact-value short position tests -----------------------------------

    def test_get_allocation_short_exact_values(self) -> None:
        """get_allocation computes exact signed weights for a short."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        # Shorting credits cash equal to market value, so total_value is unchanged.
        portfolio.add_holding("AAPL", -100, 100.0)
        alloc = portfolio.get_allocation(use_absolute=False)
        assert alloc["AAPL"] == pytest.approx(-10000.0 / 100000.0)

    def test_get_gross_allocation_short_exact_values(self) -> None:
        """get_gross_allocation computes exact absolute weights for a short."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", -100, 100.0)
        gross = portfolio.get_gross_allocation()
        assert gross["AAPL"] == pytest.approx(10000.0 / 100000.0)

    def test_get_net_allocation_equals_signed_allocation(self) -> None:
        """get_net_allocation is identical to get_allocation(use_absolute=False)."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", -100, 100.0)
        assert portfolio.get_net_allocation() == portfolio.get_allocation(use_absolute=False)

    def test_get_gross_allocation_equals_absolute_allocation(self) -> None:
        """get_gross_allocation is identical to get_allocation(use_absolute=True)."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", -100, 100.0)
        assert portfolio.get_gross_allocation() == portfolio.get_allocation(use_absolute=True)

    def test_allocation_invariants_short_only(self) -> None:
        """Invariants hold for a short-only portfolio."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", -100, 100.0)
        portfolio.add_holding("GOOG", -50, 200.0)

        net = portfolio.get_net_allocation()
        gross = portfolio.get_gross_allocation()

        # Shorts are negative in net, positive in gross
        assert net["AAPL"] < 0
        assert net["GOOG"] < 0
        assert gross["AAPL"] > 0
        assert gross["GOOG"] > 0

        # Magnitudes match per position
        for sym in net:
            assert abs(net[sym]) == pytest.approx(abs(gross[sym]))

        # Gross sum equals sum of absolute net values
        assert sum(gross.values()) == pytest.approx(sum(abs(v) for v in net.values()))

    def test_allocation_invariants_net_sum_equals_position_pct_sum(self) -> None:
        """Net allocation sums to (holdings_value / total_value)."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        portfolio.add_holding("GOOG", -50, 200.0)
        net = portfolio.get_net_allocation()
        expected = portfolio.get_holdings_value() / portfolio.total_value
        assert sum(net.values()) == pytest.approx(expected)

    def test_allocation_invariants_gross_sum_exceeds_one_when_leveraged(self) -> None:
        """Gross exposure exceeds 100% when longs and shorts are both present."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)  # +10000
        portfolio.add_holding("GOOG", -50, 200.0)  # -10000
        gross = portfolio.get_gross_allocation()
        # total_value = 100000 + 10000 - 10000 = 100000; gross = (10000+10000)/100000 = 0.2
        assert sum(gross.values()) == pytest.approx(0.2)
        assert sum(gross.values()) > abs(sum(portfolio.get_net_allocation().values()))

    def test_remove_holding_non_finite_quantity(self) -> None:
        """remove_holding with a non-finite quantity does not mutate the portfolio."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        cash_before = portfolio.cash
        total_before = portfolio.total_value

        portfolio.remove_holding("AAPL", float("nan"), 100.0)

        assert "AAPL" in portfolio.holdings
        assert portfolio.holdings["AAPL"].quantity == pytest.approx(100.0)
        assert portfolio.cash == pytest.approx(cash_before)
        assert portfolio.total_value == pytest.approx(total_before)

    def test_remove_holding_non_finite_price(self) -> None:
        """remove_holding with a non-finite price does not mutate the portfolio."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        cash_before = portfolio.cash

        portfolio.remove_holding("AAPL", 50, float("nan"))

        assert "AAPL" in portfolio.holdings
        assert portfolio.holdings["AAPL"].quantity == pytest.approx(100.0)
        assert portfolio.cash == pytest.approx(cash_before)

    def test_reset_non_finite_capital(self) -> None:
        """reset with a non-finite capital sanitizes it to 0.0."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)

        portfolio.reset(float("nan"))

        assert portfolio.cash == 0.0
        assert portfolio.total_value == 0.0
        assert portfolio.initial_capital == 0.0
        assert portfolio.holdings == {}

        portfolio.reset(float("inf"))
        assert portfolio.cash == 0.0
        assert portfolio.total_value == 0.0
        assert portfolio.initial_capital == 0.0

    def test_add_holding_non_finite_commission(self) -> None:
        """add_holding with a non-finite commission is a no-op."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        cash_before = portfolio.cash

        portfolio.add_holding("AAPL", 10, 100.0, commission=float("nan"))

        assert "AAPL" not in portfolio.holdings
        assert portfolio.cash == pytest.approx(cash_before)

    def test_add_holding_non_finite_slippage(self) -> None:
        """add_holding with a non-finite slippage is a no-op."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        cash_before = portfolio.cash

        portfolio.add_holding("AAPL", 10, 100.0, slippage=float("inf"))

        assert "AAPL" not in portfolio.holdings
        assert portfolio.cash == pytest.approx(cash_before)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestHoldingMarketValue:
    """Tests for the market value derived when a holding is created."""

    def test_market_value_derived_for_long_position(self) -> None:
        """A long holding is worth quantity times its current price."""
        holding = Holding(symbol="AAPL", quantity=100, avg_cost=100.0, current_price=150.0)
        assert holding.market_value == pytest.approx(15000.0)

    def test_market_value_derived_for_short_position(self) -> None:
        """A short holding is worth the negative of quantity times its price."""
        holding = Holding(symbol="AAPL", quantity=-100, avg_cost=100.0, current_price=150.0)
        assert holding.market_value == pytest.approx(-15000.0)

    def test_market_value_derived_for_zero_cost_position(self) -> None:
        """A zero cost basis does not stop the market value from being derived."""
        holding = Holding(symbol="AAPL", quantity=100, avg_cost=0.0, current_price=150.0)
        assert holding.market_value == pytest.approx(15000.0)

    def test_market_value_is_zero_for_zero_quantity(self) -> None:
        """A holding without units has no market value."""
        holding = Holding(symbol="AAPL", quantity=0, avg_cost=100.0, current_price=150.0)
        assert holding.market_value == 0.0


class TestHoldingSerialization:
    """Tests for Holding.to_dict / Holding.from_dict."""

    def test_to_dict_contains_all_fields(self) -> None:
        """to_dict exposes every field the holding carries."""
        holding = Holding(symbol="AAPL", quantity=100, avg_cost=100.0, current_price=150.0)
        data = holding.to_dict()
        assert set(data) == {"symbol", "quantity", "avg_cost", "current_price", "market_value"}
        assert data["symbol"] == "AAPL"
        assert data["quantity"] == 100
        assert data["avg_cost"] == 100.0
        assert data["current_price"] == 150.0
        assert data["market_value"] == 15000.0

    def test_to_dict_short_position(self) -> None:
        """to_dict carries the signed values of a short holding."""
        holding = Holding(symbol="GOOG", quantity=-50, avg_cost=200.0, current_price=210.0)
        data = holding.to_dict()
        assert data["quantity"] == -50
        assert data["market_value"] == -10500.0

    def test_from_dict_round_trip_long(self) -> None:
        """from_dict(to_dict(holding)) restores the holding exactly."""
        holding = Holding(symbol="AAPL", quantity=100, avg_cost=100.0, current_price=150.0)
        restored = Holding.from_dict(holding.to_dict())
        assert restored.symbol == holding.symbol
        assert restored.quantity == holding.quantity
        assert restored.avg_cost == holding.avg_cost
        assert restored.current_price == holding.current_price
        assert restored.market_value == holding.market_value

    def test_from_dict_round_trip_short(self) -> None:
        """from_dict(to_dict(holding)) restores a short holding exactly."""
        holding = Holding(symbol="GOOG", quantity=-50, avg_cost=200.0, current_price=210.0)
        restored = Holding.from_dict(holding.to_dict())
        assert restored.quantity == -50
        assert restored.market_value == -10500.0

    def test_from_dict_defaults_missing_fields(self) -> None:
        """from_dict tolerates a dict that omits optional fields."""
        restored = Holding.from_dict({"symbol": "AAPL"})
        assert restored.symbol == "AAPL"
        assert restored.quantity == 0.0
        assert restored.avg_cost == 0.0
        assert restored.current_price == 0.0

    def test_from_dict_sanitizes_non_finite_values(self) -> None:
        """from_dict replaces non-finite numeric fields with 0.0."""
        restored = Holding.from_dict(
            {
                "symbol": "AAPL",
                "quantity": float("nan"),
                "avg_cost": float("inf"),
                "current_price": -float("inf"),
                "market_value": float("nan"),
            }
        )
        assert restored.quantity == 0.0
        assert restored.avg_cost == 0.0
        assert restored.current_price == 0.0
        assert restored.market_value == 0.0

    def test_from_dict_rejects_non_numeric_values(self) -> None:
        """from_dict replaces non-numeric values with 0.0."""
        restored = Holding.from_dict(
            {
                "symbol": "AAPL",
                "quantity": "not-a-number",
                "avg_cost": None,
                "current_price": [1, 2],
                "market_value": object(),
            }
        )
        assert restored.quantity == 0.0
        assert restored.avg_cost == 0.0
        assert restored.current_price == 0.0
        assert restored.market_value == 0.0

    def test_from_dict_converts_numeric_strings(self) -> None:
        """from_dict converts numeric strings to floats."""
        restored = Holding.from_dict(
            {
                "symbol": "AAPL",
                "quantity": "100",
                "avg_cost": "100.0",
                "current_price": "150.0",
                "market_value": "15000.0",
            }
        )
        assert restored.quantity == 100.0
        assert restored.avg_cost == 100.0
        assert restored.current_price == 150.0
        assert restored.market_value == 15000.0


class TestPortfolioSerialization:
    """Tests for Portfolio.to_dict / Portfolio.from_dict."""

    def test_to_dict_contains_all_fields(self) -> None:
        """to_dict exposes cash, holdings, total_value, initial_capital and last_rebalance."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        data = portfolio.to_dict()
        assert set(data) == {"cash", "holdings", "total_value", "initial_capital", "last_rebalance"}
        # Buying 100 shares at $100 debits $10,000 from cash.
        assert data["cash"] == 90000.0
        assert data["total_value"] == portfolio.total_value
        assert data["initial_capital"] == 100000.0
        assert data["last_rebalance"] is None
        assert set(data["holdings"]) == {"AAPL"}

    def test_to_dict_serializes_holdings_recursively(self) -> None:
        """Each holding in the dict is itself a serialized holding dict."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        data = portfolio.to_dict()
        holding_data = data["holdings"]["AAPL"]
        assert holding_data["symbol"] == "AAPL"
        assert holding_data["quantity"] == 100
        assert holding_data["market_value"] == 10000.0

    def test_to_dict_serializes_last_rebalance_isoformat(self) -> None:
        """last_rebalance is rendered as an ISO-8601 string when set."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.last_rebalance = datetime(2024, 1, 15, 9, 30)
        data = portfolio.to_dict()
        assert data["last_rebalance"] == "2024-01-15T09:30:00"

    def test_from_dict_round_trip_with_holdings_and_rebalance(self) -> None:
        """from_dict(to_dict(portfolio)) restores cash, holdings and the rebalance date."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        portfolio.add_holding("GOOG", -50, 200.0)
        portfolio.last_rebalance = datetime(2024, 1, 15)

        restored = Portfolio.from_dict(portfolio.to_dict())
        assert restored.cash == portfolio.cash
        assert restored.initial_capital == portfolio.initial_capital
        assert restored.total_value == portfolio.total_value
        assert restored.last_rebalance == datetime(2024, 1, 15)
        assert set(restored.holdings) == {"AAPL", "GOOG"}
        assert restored.holdings["AAPL"].quantity == 100
        assert restored.holdings["GOOG"].quantity == -50

    def test_from_dict_round_trip_empty_portfolio(self) -> None:
        """from_dict(to_dict(portfolio)) works for a cash-only portfolio."""
        portfolio = Portfolio(cash=50000.0, initial_capital=50000.0)
        restored = Portfolio.from_dict(portfolio.to_dict())
        assert restored.cash == 50000.0
        assert restored.initial_capital == 50000.0
        assert restored.holdings == {}

    def test_from_dict_none_last_rebalance(self) -> None:
        """A missing or null last_rebalance restores to None."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        restored = Portfolio.from_dict(portfolio.to_dict())
        assert restored.last_rebalance is None

    def test_from_dict_invalid_last_rebalance_string(self) -> None:
        """An unparseable last_rebalance string is treated as None."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.last_rebalance = "not-a-date"  # type: ignore[assignment]
        restored = Portfolio.from_dict(portfolio.to_dict())
        assert restored.last_rebalance is None

    def test_from_dict_accepts_last_rebalance_as_datetime(self) -> None:
        """from_dict passes through datetime objects (branch at line 517)."""
        dt = datetime(2024, 2, 3, 10, 11, 12)
        data = {
            "cash": 1000.0,
            "holdings": {},
            "total_value": 1000.0,
            "initial_capital": 1000.0,
            "last_rebalance": dt,
        }
        restored = Portfolio.from_dict(data)
        assert restored.last_rebalance == dt

    def test_from_dict_sanitizes_non_finite_portfolio_fields(self) -> None:
        """from_dict replaces non-finite portfolio-level numerics with 0.0."""
        restored = Portfolio.from_dict(
            {
                "cash": float("nan"),
                "initial_capital": float("inf"),
                "total_value": -float("inf"),
                "holdings": {},
            }
        )
        assert restored.cash == 0.0
        assert restored.initial_capital == 0.0
        assert restored.total_value == 0.0

    def test_from_dict_sanitizes_non_finite_holdings(self) -> None:
        """from_dict sanitizes every holding's numeric fields."""
        restored = Portfolio.from_dict(
            {
                "cash": 100000.0,
                "initial_capital": 100000.0,
                "total_value": 100000.0,
                "holdings": {
                    "AAPL": {
                        "symbol": "AAPL",
                        "quantity": float("nan"),
                        "avg_cost": float("inf"),
                        "current_price": -float("inf"),
                        "market_value": float("nan"),
                    }
                },
            }
        )
        assert "AAPL" in restored.holdings
        holding = restored.holdings["AAPL"]
        assert holding.quantity == 0.0
        assert holding.avg_cost == 0.0
        assert holding.current_price == 0.0
        assert holding.market_value == 0.0

    def test_from_dict_rejects_non_numeric_portfolio_fields(self) -> None:
        """from_dict replaces non-numeric portfolio-level fields with 0.0."""
        restored = Portfolio.from_dict(
            {
                "cash": "not-a-number",
                "initial_capital": None,
                "total_value": object(),
                "holdings": {},
            }
        )
        assert restored.cash == 0.0
        assert restored.initial_capital == 0.0
        assert restored.total_value == 0.0


class TestHoldingNonFiniteSanitization:
    """Direct construction sanitizes non-finite numeric fields to 0.0.

    ``Holding.from_dict`` sanitizes before construction, so these tests exercise
    the ``__post_init__`` guards that protect a directly constructed holding from
    NaN/inf propagation.
    """

    def test_non_finite_quantity_is_zeroed(self) -> None:
        """A NaN quantity is replaced with 0.0 and yields no market value."""
        holding = Holding(symbol="AAPL", quantity=float("nan"), avg_cost=100.0, current_price=150.0)
        assert holding.quantity == 0.0
        assert holding.market_value == 0.0

    def test_non_finite_avg_cost_is_zeroed(self) -> None:
        """A non-finite average cost is replaced with 0.0; market value is unaffected."""
        holding = Holding(symbol="AAPL", quantity=10, avg_cost=float("inf"), current_price=150.0)
        assert holding.avg_cost == 0.0
        assert holding.market_value == pytest.approx(1500.0)

    def test_non_finite_current_price_is_zeroed(self) -> None:
        """A non-finite current price is replaced with 0.0 and zeroes market value."""
        holding = Holding(symbol="AAPL", quantity=10, avg_cost=100.0, current_price=float("nan"))
        assert holding.current_price == 0.0
        assert holding.market_value == 0.0

    def test_pnl_and_pct_zero_when_price_becomes_non_finite(self) -> None:
        """PnL and PnL% report 0.0 if the price is mutated to a non-finite value."""
        holding = Holding(symbol="AAPL", quantity=10, avg_cost=100.0, current_price=150.0)
        holding.current_price = float("inf")
        assert holding.unrealized_pnl == 0.0
        assert holding.unrealized_pnl_pct == 0.0


class TestPortfolioNonFiniteSanitization:
    """Construction and operations keep every portfolio numeric field finite."""

    def test_non_finite_cash_is_zeroed(self) -> None:
        """A NaN cash balance is replaced with 0.0 at construction."""
        portfolio = Portfolio(cash=float("nan"))
        assert portfolio.cash == 0.0
        assert portfolio.total_value == 0.0

    def test_non_finite_initial_capital_is_sanitized(self) -> None:
        """A non-finite initial capital is sanitized, then inferred from cash."""
        portfolio = Portfolio(cash=1000.0, initial_capital=float("inf"))
        assert portfolio.initial_capital == 1000.0
        assert portfolio.total_value == 1000.0

    def test_non_finite_total_value_falls_back_to_cash(self) -> None:
        """A non-finite total value falls back to the (finite) cash balance."""
        portfolio = Portfolio(cash=1000.0, total_value=float("inf"))
        assert portfolio.total_value == 1000.0

    def test_get_position_pct_zero_when_value_non_finite(self) -> None:
        """get_position_pct returns 0.0 when the position value is non-finite."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        portfolio.holdings["AAPL"].market_value = float("nan")
        assert portfolio.get_position_pct("AAPL") == 0.0

    def test_add_holding_zero_quantity_falls_back_when_cash_non_finite(self) -> None:
        """A no-op trade still recomputes a finite total value from non-finite cash."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.cash = float("inf")
        portfolio.add_holding("AAPL", 0, 100.0)
        assert portfolio.total_value == 0.0

    def test_add_holding_overflow_keeps_total_value_finite(self) -> None:
        """An overflowing buy leaves total_value finite (0.0) rather than inf."""
        portfolio = Portfolio(cash=1e308, initial_capital=1e308)
        portfolio.add_holding("AAPL", 1e308, 1e308)
        assert portfolio.total_value == 0.0

    def test_remove_holding_overflow_keeps_total_value_finite(self) -> None:
        """An overflowing sale leaves total_value finite (0.0) rather than inf."""
        portfolio = Portfolio(cash=0.0, initial_capital=0.0)
        portfolio.add_holding("AAPL", 100, 100.0)
        portfolio.remove_holding("AAPL", 1e308, 1e308)
        assert portfolio.total_value == 0.0

    def test_update_prices_falls_back_when_cash_non_finite(self) -> None:
        """update_prices recomputes a finite total value from non-finite cash."""
        portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
        portfolio.cash = float("inf")
        portfolio.update_prices({})
        assert portfolio.total_value == 0.0
