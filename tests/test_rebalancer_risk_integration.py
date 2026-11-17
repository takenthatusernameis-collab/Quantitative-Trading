"""End-to-end solvency tests for a risk-managed Rebalancer + execute_actions."""

import pytest

from quant_trading.portfolio.portfolio import Portfolio
from quant_trading.portfolio.rebalancer import Rebalancer
from quant_trading.risk.manager import RiskManager


def _risk_manager() -> RiskManager:
    return RiskManager(initial_capital=100000.0, max_position_size=0.1, max_drawdown=0.20)


def _total_holdings_value(portfolio: Portfolio) -> float:
    return sum(holding.market_value for holding in portfolio.holdings.values())


def _assert_solvency(portfolio: Portfolio, risk_manager: RiskManager) -> None:
    total_value = portfolio.total_value
    assert portfolio.cash >= 0
    assert portfolio.cash + _total_holdings_value(portfolio) == pytest.approx(total_value)
    cap = risk_manager.position_limit.max_value
    for holding in portfolio.holdings.values():
        assert abs(holding.market_value) <= cap + 1e-3


def test_multi_round_solvency() -> None:
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


def test_execute_explicit_buy_enforces_position_limit() -> None:
    """Execution of an explicitly constructed buy caps quantity at position limit.

    Without a drawdown breach, the drawdown gate is not triggered, but the
    position limit should still cap the buy at the maximum allowed position
    value.
    """
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("MSFT", 10, 100.0)  # existing long worth 1000
    rm = RiskManager(initial_capital=100000.0, max_position_size=0.1, max_drawdown=0.20)
    # No drawdown breach
    rebalancer = Rebalancer(
        portfolio,
        target_allocation={"MSFT": 0.5},
        risk_manager=rm,
    )
    prices = {"MSFT": 100.0}

    # Request a buy that would exceed the position limit
    # Max position value = 0.1 * 100000 = 10000
    # Current position value = 10 * 100 = 1000
    # Room = 9000, so max additional shares = 9000 / 100 = 90
    from quant_trading.portfolio.rebalancer import RebalanceAction

    explicit_buy = RebalanceAction(
        symbol="MSFT",
        action="buy",
        quantity=490.0,  # would exceed position limit
        reason="test_explicit",
    )

    executions = rebalancer.execute_actions(
        [explicit_buy], prices=prices, commission=0.001, slippage=0.0005
    )

    # The position limit caps the buy at ~90 shares (9000 / 100.0015 with fees)
    assert len(executions) == 1
    assert executions[0].symbol == "MSFT"
    assert executions[0].action == "buy"
    assert executions[0].executed_quantity == pytest.approx(
        90.0, rel=0.02
    )  # capped by position limit
    assert portfolio.cash >= 0.0
    # Position value should not exceed max_value (10000)
    msft_holding = portfolio.holdings["MSFT"]
    assert abs(msft_holding.market_value) <= rm.position_limit.max_value + 1e-3
    _assert_solvency(portfolio, rm)


def test_execute_short_covering_buy_allowed_during_drawdown_breach() -> None:
    """Execution of an explicitly constructed short-covering buy is allowed during
    a drawdown breach.

    Mirrors the generation-time behavior: a buy that covers an open short
    reduces gross exposure and is permitted even during a drawdown breach.
    """
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", -100, 100.0)  # open short
    rm = RiskManager(initial_capital=100000.0, max_position_size=0.1, max_drawdown=0.05)
    rm.portfolio_risk.current_drawdown = -0.5  # breach the loss limit
    rebalancer = Rebalancer(
        portfolio,
        target_allocation={"AAPL": 0.0},
        risk_manager=rm,
    )
    prices = {"AAPL": 100.0}

    from quant_trading.portfolio.rebalancer import RebalanceAction

    explicit_buy = RebalanceAction(
        symbol="AAPL",
        action="buy",
        quantity=100.0,  # exactly covers the short
        reason="test_explicit_short_cover",
    )

    executions = rebalancer.execute_actions(
        [explicit_buy], prices=prices, commission=0.001, slippage=0.0005
    )

    # Short-covering buy executes despite drawdown breach
    assert len(executions) == 1
    assert executions[0].symbol == "AAPL"
    assert executions[0].action == "buy"
    assert executions[0].executed_quantity == pytest.approx(100.0)
    assert "AAPL" not in portfolio.holdings  # short flattened
    assert portfolio.cash >= 0.0
    _assert_solvency(portfolio, rm)


def test_drawdown_breach_stops_buys_allows_sells() -> None:
    """A breached drawdown limit blocks buys but still permits sells."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", 100, 100.0)
    rm = RiskManager(
        initial_capital=100000.0,
        max_position_size=0.1,
        max_drawdown=0.05,
        max_portfolio_risk=1.0,
    )
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


def test_drawdown_breach_blocks_buys() -> None:
    """Drawdown breach blocks buys even when rebalancing requires increasing a position."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", 10, 100.0)
    rm = RiskManager(initial_capital=100000.0, max_position_size=0.5, max_drawdown=0.05)
    rm.portfolio_risk.current_drawdown = -0.5  # breach the loss limit
    rebalancer = Rebalancer(
        portfolio, target_allocation={"AAPL": 0.8, "MSFT": 0.2}, risk_manager=rm
    )
    prices = {"AAPL": 100.0, "MSFT": 100.0}
    actions = rebalancer.generate_rebalance_actions(prices=prices)
    buys = [a for a in actions if a.action == "buy"]
    assert buys == []  # drawdown halt blocks all buying
    _assert_solvency(portfolio, rm)


def test_drawdown_breach_allows_short_covering_buy_blocks_exposure_increasing_buy() -> None:
    """A breached drawdown limit blocks exposure-increasing buys but permits a
    buy that covers an open short, mirroring RiskManager.check_signal.

    RiskManager.check_signal returns before the drawdown gate for a buy that
    covers an open short (manager.py:882-885), so the rebalancer must not halt
    such a buy either; it only caps it at the short size in _plan_buy.
    """
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", -100, 100.0)  # open short to be covered
    portfolio.add_holding("MSFT", 10, 100.0)  # long the target wants to grow
    rm = RiskManager(initial_capital=100000.0, max_position_size=0.1, max_drawdown=0.05)
    rm.portfolio_risk.current_drawdown = -0.5  # breach the loss limit
    rebalancer = Rebalancer(
        portfolio,
        target_allocation={"AAPL": 0.0, "MSFT": 0.5},
        risk_manager=rm,
    )
    prices = {"AAPL": 100.0, "MSFT": 100.0}
    actions = rebalancer.generate_rebalance_actions(prices=prices)
    buys = [a for a in actions if a.action == "buy"]
    sells = [a for a in actions if a.action == "sell"]

    # The AAPL short is covered by an exposure-reducing buy despite the breach.
    aapl_buys = [a for a in buys if a.symbol == "AAPL"]
    assert len(aapl_buys) == 1
    assert aapl_buys[0].quantity == pytest.approx(100.0)

    # The MSFT buy that increases exposure is halted by the drawdown breach.
    assert [a for a in buys if a.symbol == "MSFT"] == []
    assert sells == []
    _assert_solvency(portfolio, rm)


def test_drawdown_breach_executes_short_covering_buy_but_not_exposure_increasing_buy() -> None:
    """Execution of drawdown-breach actions covers the short but drops an
    exposure-increasing buy.

    Extends generation coverage: the short-covering buy produced during a
    breach must execute and flatten the short, while an exposure-increasing
    buy that is planned during a breach is not executed.
    """
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", -100, 100.0)  # open short to be covered
    portfolio.add_holding("MSFT", 10, 100.0)  # long the target wants to grow
    rm = RiskManager(initial_capital=100000.0, max_position_size=0.1, max_drawdown=0.05)
    rm.portfolio_risk.current_drawdown = -0.5  # breach the loss limit
    rebalancer = Rebalancer(
        portfolio,
        target_allocation={"AAPL": 0.0, "MSFT": 0.5},
        risk_manager=rm,
    )
    prices = {"AAPL": 100.0, "MSFT": 100.0}

    actions = rebalancer.generate_rebalance_actions(prices=prices)
    executions = rebalancer.execute_actions(actions, prices=prices)

    # (a) The short-covering buy executes despite the drawdown breach.
    assert len(executions) == 1
    assert executions[0].symbol == "AAPL"
    assert executions[0].action == "buy"
    assert executions[0].executed_quantity == pytest.approx(100.0)
    assert "AAPL" not in portfolio.holdings  # short flattened to 0
    assert portfolio.cash >= 0.0
    _assert_solvency(portfolio, rm)

    # (b) An exposure-increasing buy planned during a breach is dropped at
    # execution: generation emits none, so executing the planned actions must
    # not increase the MSFT position.
    msft_before = portfolio.holdings["MSFT"].quantity
    msft_execs = [e for e in executions if e.symbol == "MSFT"]
    assert msft_execs == []
    assert portfolio.holdings["MSFT"].quantity == pytest.approx(msft_before)
    _assert_solvency(portfolio, rm)


def test_drawdown_breach_execute_explicit_exposure_increasing_buy_enforces_solvency() -> None:
    """Execution of an explicitly constructed exposure-increasing buy during a
    drawdown breach is blocked by the drawdown gate.

    The rebalancer's generate_rebalance_actions blocks exposure-increasing buys
    during a drawdown breach via _risk_adjust_buy. The execute_actions method
    now mirrors this behavior via _risk_adjust_execution_buy, ensuring that
    even explicitly constructed actions cannot bypass the drawdown gate.
    """
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("MSFT", 10, 100.0)  # existing long
    rm = RiskManager(initial_capital=100000.0, max_position_size=0.1, max_drawdown=0.05)
    rm.portfolio_risk.current_drawdown = -0.5  # breach the loss limit
    rebalancer = Rebalancer(
        portfolio,
        target_allocation={"MSFT": 0.5},
        risk_manager=rm,
    )
    prices = {"MSFT": 100.0}

    # Construct an explicit exposure-increasing buy action that would be
    # blocked by generate_rebalance_actions during a drawdown breach.
    from quant_trading.portfolio.rebalancer import RebalanceAction

    explicit_buy = RebalanceAction(
        symbol="MSFT",
        action="buy",
        quantity=490.0,
        reason="test_explicit",
    )

    executions = rebalancer.execute_actions(
        [explicit_buy], prices=prices, commission=0.001, slippage=0.0005
    )

    # The drawdown gate blocks the exposure-increasing buy entirely.
    assert len(executions) == 1
    assert executions[0].symbol == "MSFT"
    assert executions[0].action == "buy"
    assert executions[0].executed_quantity == 0.0
    assert executions[0].cash_effect == 0.0
    assert portfolio.cash >= 0.0
    assert portfolio.holdings["MSFT"].quantity == pytest.approx(10.0)
    _assert_solvency(portfolio, rm)


def test_execute_buy_at_position_limit_is_dropped() -> None:
    """An execution-time buy with no position-limit room is dropped.

    The position is already worth ``max_size * total_value`` (0.1 * 100000 =
    10000), so the position-limit room in ``_risk_adjust_execution_buy`` is
    zero and the buy must not change the portfolio.
    """
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", 100, 100.0)  # 10000 = max position value
    rm = RiskManager(initial_capital=100000.0, max_position_size=0.1, max_drawdown=0.20)
    rebalancer = Rebalancer(portfolio, target_allocation={"AAPL": 0.5}, risk_manager=rm)

    from quant_trading.portfolio.rebalancer import RebalanceAction

    buy = RebalanceAction(symbol="AAPL", action="buy", quantity=10.0, reason="test_position_limit")
    cash_before = portfolio.cash

    executions = rebalancer.execute_actions([buy], prices={"AAPL": 100.0})

    assert len(executions) == 1
    assert executions[0].executed_quantity == 0.0
    assert executions[0].cash_effect == 0.0
    assert portfolio.cash == pytest.approx(cash_before)
    assert portfolio.holdings["AAPL"].quantity == pytest.approx(100.0)
    _assert_solvency(portfolio, rm)


def test_execute_buy_at_leverage_limit_is_dropped() -> None:
    """An execution-time buy with no leverage room is dropped.

    Gross exposure is already ``max_leverage * total_value`` (0.8 * 100000 =
    80000), so ``_risk_adjust_execution_exposure`` returns 0 before the risk
    budget is consulted.
    """
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", 400, 100.0)  # 40000
    portfolio.add_holding("MSFT", 400, 100.0)  # 40000, gross = 80000
    rm = RiskManager(
        initial_capital=100000.0,
        max_position_size=1.0,
        max_leverage=0.8,
        max_drawdown=0.20,
    )
    rebalancer = Rebalancer(portfolio, target_allocation={"AAPL": 0.5}, risk_manager=rm)

    from quant_trading.portfolio.rebalancer import RebalanceAction

    buy = RebalanceAction(symbol="AAPL", action="buy", quantity=10.0, reason="test_leverage_limit")
    cash_before = portfolio.cash

    executions = rebalancer.execute_actions([buy], prices={"AAPL": 100.0})

    assert len(executions) == 1
    assert executions[0].executed_quantity == 0.0
    assert executions[0].cash_effect == 0.0
    assert portfolio.cash == pytest.approx(cash_before)
    assert portfolio.holdings["AAPL"].quantity == pytest.approx(400.0)
    _assert_solvency(portfolio, rm)


def test_execute_buy_at_portfolio_risk_limit_is_dropped() -> None:
    """An execution-time buy with no portfolio-risk room is dropped.

    The open risk of the 40000 position at a 5% stop is 2000, above the
    1% * 100000 = 1000 budget, so ``_risk_adjust_execution_exposure`` returns
    0 at the risk-budget guard.
    """
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", 400, 100.0)  # 40000, risk = 2000
    rm = RiskManager(
        initial_capital=100000.0,
        max_position_size=1.0,
        max_portfolio_risk=0.01,
        max_leverage=5.0,
        stop_loss_pct=0.05,
        max_drawdown=0.20,
    )
    rebalancer = Rebalancer(portfolio, target_allocation={"AAPL": 0.5}, risk_manager=rm)

    from quant_trading.portfolio.rebalancer import RebalanceAction

    buy = RebalanceAction(symbol="AAPL", action="buy", quantity=10.0, reason="test_risk_limit")
    cash_before = portfolio.cash

    executions = rebalancer.execute_actions([buy], prices={"AAPL": 100.0})

    assert len(executions) == 1
    assert executions[0].executed_quantity == 0.0
    assert executions[0].cash_effect == 0.0
    assert portfolio.cash == pytest.approx(cash_before)
    assert portfolio.holdings["AAPL"].quantity == pytest.approx(400.0)
    _assert_solvency(portfolio, rm)
