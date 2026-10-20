"""Tests for Rebalancer.execute_actions with seeded randomized invariants."""

import random

import numpy as np
import pytest

from quant_trading.portfolio.portfolio import Portfolio
from quant_trading.portfolio.rebalancer import RebalanceAction, Rebalancer


def test_execute_actions_buy_and_sell_basic():
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio)
    actions = [
        RebalanceAction(symbol="AAPL", action="buy", quantity=100, reason="target"),
        RebalanceAction(symbol="MSFT", action="buy", quantity=50, reason="target"),
    ]
    executed = rebalancer.execute_actions(actions, prices={"AAPL": 100.0, "MSFT": 200.0})
    assert executed == actions
    assert portfolio.cash == 100000.0 - 10000.0 - 10000.0
    assert portfolio.get_position_value("AAPL") == 10000.0
    assert portfolio.get_position_value("MSFT") == 10000.0
    assert abs(portfolio.cash + portfolio.get_holdings_value() - portfolio.total_value) < 1e-9


def test_execute_actions_sell_reduces_position():
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", 100, 100.0)
    rebalancer = Rebalancer(portfolio)
    actions = [RebalanceAction(symbol="AAPL", action="sell", quantity=40, reason="rebalance")]
    rebalancer.execute_actions(actions, prices={"AAPL": 110.0})
    assert "AAPL" in portfolio.holdings
    assert portfolio.holdings["AAPL"].quantity == 60
    # bought for 10000, sold 40*110 = 4400
    assert pytest.approx(portfolio.cash) == 100000.0 - 10000.0 + 4400.0


def test_execute_actions_sell_capped_and_removed():
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", 50, 100.0)
    rebalancer = Rebalancer(portfolio)
    # sell more than held
    actions = [RebalanceAction(symbol="AAPL", action="sell", quantity=100, reason="rebalance")]
    rebalancer.execute_actions(actions, prices={"AAPL": 120.0})
    # fully offset -> removed
    assert "AAPL" not in portfolio.holdings
    assert pytest.approx(portfolio.cash) == 100000.0 - 50 * 100.0 + 50 * 120.0


def test_execute_actions_hold_is_noop():
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio)
    actions = [RebalanceAction(symbol="AAPL", action="hold", quantity=0, reason="hold")]
    rebalancer.execute_actions(actions, prices={"AAPL": 100.0})
    assert portfolio.cash == 100000.0
    assert len(portfolio.holdings) == 0


def test_execute_actions_updates_history():
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio)
    actions = [RebalanceAction(symbol="AAPL", action="buy", quantity=10, reason="target")]
    rebalancer.execute_actions(actions, prices={"AAPL": 50.0})
    assert len(rebalancer.rebalance_history) == 1
    assert rebalancer.last_rebalance is not None
    assert rebalancer.rebalance_history[0].get("executed") is True


@pytest.mark.parametrize("seed", [101, 202, 303, 404, 505])
def test_rebalancer_execution_invariants_randomized(seed):
    rng = random.Random(seed)
    np.random.default_rng(seed)

    portfolio = Portfolio(cash=100000.0 + rng.uniform(-1000, 1000), initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio, target_allocation={}, rebalance_threshold=0.0)
    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]

    # Start with some random holdings
    prices = {s: rng.uniform(50, 300) for s in symbols}
    for s in symbols:
        if rng.random() < 0.6:
            qty = rng.uniform(10, 200)
            commission = rng.uniform(0, 0.001)
            slippage = rng.uniform(0, 0.0005)
            portfolio.add_holding(s, qty, prices[s], commission=commission, slippage=slippage)
            prices[s] = prices[s] * rng.uniform(0.9, 1.1)
            portfolio.update_prices({s: prices[s]})

    # Execute random actions
    for _ in range(rng.randint(5, 20)):
        action_type = rng.choice(["buy", "sell", "hold"])
        sym = rng.choice(symbols)
        qty = rng.uniform(1, 50) if action_type != "hold" else 0.0
        action = RebalanceAction(symbol=sym, action=action_type, quantity=qty, reason="test")
        # update price slightly
        prices[sym] = prices[sym] * rng.uniform(0.99, 1.01)
        commission = rng.uniform(0, 0.001)
        slippage = rng.uniform(0, 0.0005)
        rebalancer.execute_actions(
            [action], prices=prices, commission=commission, slippage=slippage
        )
        # Invariants after each step
        holdings_val = portfolio.get_holdings_value()
        total = portfolio.cash + holdings_val
        assert pytest.approx(total, rel=1e-9, abs=1e-9) == portfolio.total_value
        # All holdings have non-zero quantity
        for h in portfolio.holdings.values():
            assert h.quantity != 0
        # num_positions matches
        summary = portfolio.summary()
        assert summary["num_positions"] == len(portfolio.holdings)


@pytest.mark.parametrize("seed", [111, 222, 333, 444, 555])
def test_rebalancer_execution_buy_averages_basis(seed):
    rng = random.Random(seed)
    portfolio = Portfolio(cash=10_000_000.0, initial_capital=10_000_000.0)
    rebalancer = Rebalancer(portfolio)
    sym = "AAPL"
    # first buy
    rebalancer.execute_actions(
        [RebalanceAction(symbol=sym, action="buy", quantity=100, reason="t")], prices={sym: 100.0}
    )
    h1 = portfolio.holdings[sym]
    basis1 = h1.avg_cost
    # second buy at different price
    price2 = rng.uniform(80, 120)
    qty2 = rng.uniform(10, 90)
    rebalancer.execute_actions(
        [RebalanceAction(symbol=sym, action="buy", quantity=qty2, reason="t")], prices={sym: price2}
    )
    h = portfolio.holdings[sym]
    # quantity increased
    assert pytest.approx(h.quantity) == 100 + qty2
    # basis is weighted average (with fees 0)
    expected_basis = (basis1 * 100 + price2 * qty2) / (100 + qty2)
    assert pytest.approx(h.avg_cost, rel=1e-9) == expected_basis


def test_execute_actions_sell_covers_short():
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    # open short: sell short means add_holding with negative quantity
    portfolio.add_holding("AAPL", -10, 100.0)
    rebalancer = Rebalancer(portfolio)
    actions = [RebalanceAction(symbol="AAPL", action="sell", quantity=5, reason="cover")]
    rebalancer.execute_actions(actions, prices={"AAPL": 90.0})
    # short reduced
    assert portfolio.holdings["AAPL"].quantity == -5


def test_execute_actions_sell_no_position_creates_short_via_fallback():
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio)
    actions = [RebalanceAction(symbol="AAPL", action="sell", quantity=10, reason="short")]
    rebalancer.execute_actions(actions, prices={"AAPL": 100.0})
    assert "AAPL" in portfolio.holdings
    assert portfolio.holdings["AAPL"].quantity < 0


def test_execute_actions_falls_back_to_holding_price():
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", 10, 100.0)
    rebalancer = Rebalancer(portfolio)
    actions = [RebalanceAction(symbol="AAPL", action="buy", quantity=5, reason="t")]
    rebalancer.execute_actions(actions)  # no prices
    assert portfolio.holdings["AAPL"].quantity == 15


def test_execute_actions_zero_or_negative_quantity_skipped():
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio)
    actions = [RebalanceAction(symbol="AAPL", action="buy", quantity=0, reason="t")]
    rebalancer.execute_actions(actions, prices={"AAPL": 100.0})
    assert len(portfolio.holdings) == 0


def test_execute_actions_invalid_price_skipped():
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio)
    actions = [RebalanceAction(symbol="AAPL", action="buy", quantity=5, reason="t")]
    rebalancer.execute_actions(actions, prices={"AAPL": 0})  # zero price
    assert len(portfolio.holdings) == 0


def test_execute_actions_sell_with_no_position_and_no_price_fallback_uses_add_holding():
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio)
    actions = [RebalanceAction(symbol="AAPL", action="sell", quantity=3, reason="t")]
    # price comes from action context? but we pass via prices; test when no holding and try to get price from holding (none)
    rebalancer.execute_actions(actions, prices={"AAPL": 50.0})
    # no existing holding -> goes to else branch adding negative
    assert portfolio.holdings["AAPL"].quantity == -3


def test_execute_actions_buy_falls_back_to_holding_when_no_prices_map():
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", 10, 100.0)
    # update price on holding
    portfolio.holdings["AAPL"].current_price = 120.0
    rebalancer = Rebalancer(portfolio)
    actions = [RebalanceAction(symbol="AAPL", action="buy", quantity=5, reason="t")]
    rebalancer.execute_actions(actions)  # no prices dict
    assert portfolio.holdings["AAPL"].quantity == 15


def test_execute_actions_no_price_available_skipped():
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio)
    actions = [RebalanceAction(symbol="AAPL", action="buy", quantity=5, reason="t")]
    rebalancer.execute_actions(actions)  # no prices, no holding
    assert len(portfolio.holdings) == 0
