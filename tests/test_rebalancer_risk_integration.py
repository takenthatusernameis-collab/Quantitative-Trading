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
    """Repeated risk-managed rebalance rounds keep the portfolio solvent.

    Prices move deterministically between rounds so the portfolio drifts away
    from its targets and each round produces real rebalancing activity. After
    every round the portfolio must stay solvent (cash non-negative), the
    cash-plus-holdings identity must hold, and no position may exceed the
    risk manager's position-value cap.
    """
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rm = RiskManager(initial_capital=100000.0, max_position_size=0.5, max_drawdown=0.20)
    rebalancer = Rebalancer(
        portfolio,
        target_allocation={"AAPL": 0.4, "MSFT": 0.3, "GOOGL": 0.3},
        rebalance_threshold=0.01,
        risk_manager=rm,
    )
    price_scenarios = [
        {"AAPL": 100.0, "MSFT": 100.0, "GOOGL": 100.0},
        {"AAPL": 105.0, "MSFT": 95.0, "GOOGL": 100.0},
        {"AAPL": 95.0, "MSFT": 105.0, "GOOGL": 105.0},
        {"AAPL": 110.0, "MSFT": 90.0, "GOOGL": 95.0},
        {"AAPL": 100.0, "MSFT": 110.0, "GOOGL": 90.0},
        {"AAPL": 105.0, "MSFT": 105.0, "GOOGL": 110.0},
    ]
    for prices in price_scenarios:
        portfolio.update_prices(prices)
        actions = rebalancer.generate_rebalance_actions(
            prices=prices, commission=0.001, slippage=0.0005
        )
        rebalancer.execute_actions(actions, prices=prices, commission=0.001, slippage=0.0005)
        _assert_solvency(portfolio, rm)


def test_drawdown_breach_stops_buys_allows_sells():
    """A breached drawdown limit blocks buys but still permits sells."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", 100, 100.0)
    rm = RiskManager(initial_capital=100000.0, max_position_size=0.1, max_drawdown=0.05)
    rm.portfolio_risk.current_drawdown = -0.5  # breach the loss limit
    rebalancer = Rebalancer(portfolio, target_allocation={"AAPL": 0.0}, risk_manager=rm)
    prices = {"AAPL": 50.0}
    actions = rebalancer.generate_rebalance_actions(prices=prices)
    buys = [a for a in actions if a.action == "buy"]
    sells = [a for a in actions if a.action == "sell"]
    assert buys == []  # drawdown halt blocks all buying
    assert len(sells) == 1  # selling still works despite the breach
    assert sells[0].symbol == "AAPL"
    assert sells[0].quantity == pytest.approx(100.0)

    executions = rebalancer.execute_actions(actions, prices=prices)
    assert len(executions) == 1
    assert executions[0].action == "sell"
    assert executions[0].executed_quantity == pytest.approx(100.0)
    assert portfolio.cash >= 0.0
    assert "AAPL" not in portfolio.holdings
    _assert_solvency(portfolio, rm)
