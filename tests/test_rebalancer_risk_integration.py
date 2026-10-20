"""End-to-end solvency tests for a risk-managed Rebalancer + execute_actions."""

import pytest

from quant_trading.portfolio.portfolio import Portfolio
from quant_trading.portfolio.rebalancer import Rebalancer
from quant_trading.risk.manager import RiskManager


def _risk_manager():
    return RiskManager(initial_capital=100000.0, max_position_size=0.1, max_drawdown=0.20)


def _total_holdings_value(portfolio):
    return sum(holding.market_value for holding in portfolio.holdings.values())


def _assert_solvency(portfolio, risk_manager):
    total_value = portfolio.total_value
    assert portfolio.cash >= 0
    assert portfolio.cash + _total_holdings_value(portfolio) == pytest.approx(total_value)
    cap = risk_manager.position_limit.max_value
    for holding in portfolio.holdings.values():
        assert abs(holding.market_value) <= cap + 1e-3


def test_multi_round_solvency():
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", 100, 100.0)
    rm = _risk_manager()
    rebalancer = Rebalancer(
        portfolio, target_allocation={"AAPL": 0.5, "MSFT": 0.3}, risk_manager=rm
    )
    prices = {"AAPL": 100.0, "MSFT": 50.0}
    for _ in range(5):
        actions = rebalancer.generate_rebalance_actions(
            prices=prices, commission=0.001, slippage=0.0005
        )
        rebalancer.execute_actions(actions, prices=prices, commission=0.001, slippage=0.0005)
        _assert_solvency(portfolio, rm)


def test_drawdown_breach_stops_buys_allows_sells():
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", 100, 200.0)  # deep loss -> drawdown
    rm = RiskManager(initial_capital=100000.0, max_position_size=0.1, max_drawdown=0.05)
    rm.portfolio_risk.current_drawdown = -0.5
    rebalancer = Rebalancer(portfolio, target_allocation={"AAPL": 0.5}, risk_manager=rm)
    prices = {"AAPL": 50.0}
    actions = rebalancer.generate_rebalance_actions(prices=prices)
    buys = [a for a in actions if a.action == "buy"]
    assert buys == []
