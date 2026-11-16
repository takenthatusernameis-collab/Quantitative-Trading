"""Regression tests for generation/execution parity of risk-managed rebalancing.

The rebalancer sizes buys at generation time in
``Rebalancer.generate_rebalance_actions`` (via ``_risk_adjust_buy`` /
``_risk_adjust_planned_exposure``) and re-sizes them at execution time in
``Rebalancer.execute_actions`` (via ``_risk_adjust_execution_buy`` /
``_risk_adjust_execution_exposure``).

These tests assert that, given identical prices, fees, and portfolio state, the
quantity a risk-managed rebalancer plans to buy equals the quantity it executes,
for both the leverage cap (``max_leverage < 1.0``) and the portfolio risk budget
(tight ``max_portfolio_risk`` with ``stop_loss_pct > 0``), including multi-symbol
batches where planned gross exposure and open risk accumulate across actions.
Every scenario also asserts the portfolio stays solvent.
"""

import pytest

from quant_trading.portfolio.portfolio import Portfolio
from quant_trading.portfolio.rebalancer import Rebalancer
from quant_trading.risk.manager import RiskManager


def _risk_manager(
    *,
    max_leverage: float,
    max_portfolio_risk: float,
    stop_loss_pct: float,
    max_drawdown: float = 0.0,
    max_position_size: float = 1.0,
) -> RiskManager:
    """Risk manager with drawdown disabled so only the cap under test binds."""
    return RiskManager(
        initial_capital=100000.0,
        max_position_size=max_position_size,
        max_portfolio_risk=max_portfolio_risk,
        max_drawdown=max_drawdown,
        stop_loss_pct=stop_loss_pct,
        max_leverage=max_leverage,
    )


def _assert_parity(actions: list, executions: list, portfolio: Portfolio) -> None:
    """Every planned action executes in full and the portfolio stays solvent."""
    assert len(executions) == len(actions)
    for action, execution in zip(actions, executions):
        assert execution.symbol == action.symbol
        assert execution.action == action.action
        assert execution.requested_quantity == pytest.approx(action.quantity)
        assert execution.executed_quantity == pytest.approx(action.quantity)
    total_value = portfolio.total_value
    assert portfolio.cash >= 0.0
    holdings_value = sum(holding.market_value for holding in portfolio.holdings.values())
    assert portfolio.cash + holdings_value == pytest.approx(total_value)


def test_generation_execution_parity_under_leverage_cap() -> None:
    """A leverage cap of 0.5 crowds the second symbol out at generation, and
    execution reproduces the planned quantity exactly."""
    rm = _risk_manager(max_leverage=0.5, max_portfolio_risk=1.0, stop_loss_pct=0.0)
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(
        portfolio,
        frequency="monthly",
        target_allocation={"AAPL": 0.6, "MSFT": 0.6},
        risk_manager=rm,
    )
    prices = {"AAPL": 100.0, "MSFT": 100.0}
    portfolio.update_prices(prices)

    actions = rebalancer.generate_rebalance_actions(prices=prices, commission=0.0, slippage=0.0)
    executions = rebalancer.execute_actions(actions, prices=prices, commission=0.0, slippage=0.0)

    assert [a.symbol for a in actions] == ["AAPL"]
    assert actions[0].quantity == pytest.approx(500.0)
    _assert_parity(actions, executions, portfolio)
    assert executions[0].executed_quantity == pytest.approx(500.0)
    assert portfolio.cash == pytest.approx(50000.0)


def test_generation_execution_parity_under_risk_budget_accumulates() -> None:
    """A tight portfolio risk budget splits across a multi-symbol batch: the
    first buy consumes most of the budget and the second buy receives the
    remainder, with generation and execution agreeing on both quantities."""
    rm = _risk_manager(max_leverage=10.0, max_portfolio_risk=0.04, stop_loss_pct=0.05)
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(
        portfolio,
        frequency="monthly",
        target_allocation={"AAPL": 0.6, "MSFT": 0.6},
        risk_manager=rm,
    )
    prices = {"AAPL": 100.0, "MSFT": 100.0}
    portfolio.update_prices(prices)

    actions = rebalancer.generate_rebalance_actions(prices=prices, commission=0.0, slippage=0.0)
    executions = rebalancer.execute_actions(actions, prices=prices, commission=0.0, slippage=0.0)

    assert [a.symbol for a in actions] == ["AAPL", "MSFT"]
    assert actions[0].quantity == pytest.approx(600.0)
    assert actions[1].quantity == pytest.approx(200.0)
    _assert_parity(actions, executions, portfolio)
    assert executions[0].executed_quantity == pytest.approx(600.0)
    assert executions[1].executed_quantity == pytest.approx(200.0)
    assert portfolio.cash == pytest.approx(20000.0)


def test_generation_execution_parity_when_both_caps_bind() -> None:
    """The leverage cap binds first and leaves no room for any further buy."""
    rm = _risk_manager(max_leverage=0.5, max_portfolio_risk=0.04, stop_loss_pct=0.05)
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(
        portfolio,
        frequency="monthly",
        target_allocation={"AAPL": 0.6, "MSFT": 0.6},
        risk_manager=rm,
    )
    prices = {"AAPL": 100.0, "MSFT": 100.0}
    portfolio.update_prices(prices)

    actions = rebalancer.generate_rebalance_actions(prices=prices, commission=0.0, slippage=0.0)
    executions = rebalancer.execute_actions(actions, prices=prices, commission=0.0, slippage=0.0)

    assert [a.symbol for a in actions] == ["AAPL"]
    assert actions[0].quantity == pytest.approx(500.0)
    _assert_parity(actions, executions, portfolio)
    assert executions[0].executed_quantity == pytest.approx(500.0)
    assert portfolio.cash == pytest.approx(50000.0)


def test_generation_execution_parity_without_risk_manager() -> None:
    """Without a risk manager no caps apply, so planned quantities execute in
    full and cash-constraint planning still matches execution."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(
        portfolio,
        frequency="monthly",
        target_allocation={"AAPL": 0.6, "MSFT": 0.6},
    )
    prices = {"AAPL": 100.0, "MSFT": 100.0}
    portfolio.update_prices(prices)

    actions = rebalancer.generate_rebalance_actions(prices=prices, commission=0.0, slippage=0.0)
    executions = rebalancer.execute_actions(actions, prices=prices, commission=0.0, slippage=0.0)

    assert [a.symbol for a in actions] == ["AAPL", "MSFT"]
    assert actions[0].quantity == pytest.approx(600.0)
    assert actions[1].quantity == pytest.approx(400.0)
    _assert_parity(actions, executions, portfolio)
    assert executions[0].executed_quantity == pytest.approx(600.0)
    assert executions[1].executed_quantity == pytest.approx(400.0)
    # The cash safety margin in _plan_buy leaves a negligible residue.
    assert portfolio.cash < 1e-4
