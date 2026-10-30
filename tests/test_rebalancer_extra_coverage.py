import pytest

from quant_trading.portfolio.portfolio import Portfolio
from quant_trading.portfolio.rebalancer import RebalanceAction, Rebalancer
from quant_trading.risk.manager import RiskManager
from quant_trading.strategies.base import Signal


def test_execute_actions_unknown_action_raises():
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio)
    with pytest.raises(ValueError):
        rebalancer.execute_actions([RebalanceAction(symbol="AAPL", action="short", quantity=10)], prices={"AAPL": 100.0})


def test_execute_actions_hold_and_zero_quantity():
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", 10, 100.0)
    rebalancer = Rebalancer(portfolio)
    # hold action
    results = rebalancer.execute_actions([RebalanceAction(symbol="AAPL", action="hold", quantity=0)], prices={"AAPL": 100.0})
    assert results[0].executed_quantity == 0.0
    # zero quantity buy/sell
    results = rebalancer.execute_actions([RebalanceAction(symbol="AAPL", action="buy", quantity=0)], prices={"AAPL": 100.0})
    assert results[0].executed_quantity == 0.0


def test_risk_adjust_buy_no_room_left():
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rm = RiskManager(initial_capital=100000.0, max_position_size=0.01)
    rebalancer = Rebalancer(portfolio, risk_manager=rm)
    # position at limit already
    from quant_trading.portfolio.rebalancer import _RebalancePlan
    plan = _RebalancePlan(cash=50000, fee_rate=0.0, positions={"AAPL": 100.0})  # already has position
    # max position value = min(0.01*100000, max_value) but need to look up limits
    # try to buy more - should return 0 if room <= 0
    result = rebalancer._risk_adjust_buy(plan, "AAPL", 10.0, 100.0, 100000.0)
    assert result == 0.0
