import pytest

from quant_trading.portfolio.portfolio import Portfolio
from quant_trading.portfolio.rebalancer import RebalanceAction, Rebalancer
from quant_trading.risk.manager import RiskManager


def test_execute_actions_unknown_action_raises():
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio)
    with pytest.raises(ValueError):
        rebalancer.execute_actions(
            [RebalanceAction(symbol="AAPL", action="short", quantity=10)], prices={"AAPL": 100.0}
        )


def test_execute_actions_hold_and_zero_quantity():
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", 10, 100.0)
    rebalancer = Rebalancer(portfolio)
    # hold action
    results = rebalancer.execute_actions(
        [RebalanceAction(symbol="AAPL", action="hold", quantity=0)], prices={"AAPL": 100.0}
    )
    assert results[0].executed_quantity == 0.0
    # zero quantity buy/sell
    results = rebalancer.execute_actions(
        [RebalanceAction(symbol="AAPL", action="buy", quantity=0)], prices={"AAPL": 100.0}
    )
    assert results[0].executed_quantity == 0.0


def test_risk_adjust_buy_no_room_left():
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rm = RiskManager(initial_capital=100000.0, max_position_size=0.01)
    rebalancer = Rebalancer(portfolio, risk_manager=rm)
    # position at limit already
    from quant_trading.portfolio.rebalancer import _RebalancePlan

    plan = _RebalancePlan(
        cash=50000, fee_rate=0.0, positions={"AAPL": 100.0}
    )  # already has position
    # max position value = min(0.01*100000, max_value) but need to look up limits
    # try to buy more - should return 0 if room <= 0
    result = rebalancer._risk_adjust_buy(plan, "AAPL", 10.0, 100.0, 100000.0)
    assert result == 0.0


def test_rebalancer_iso_none_returns_none():
    """_iso(None) returns None (rebalancer.py:43)."""
    from quant_trading.portfolio.rebalancer import _iso

    assert _iso(None) is None


def test_rebalancer_iso_datetime_returns_isoformat():
    """_iso(datetime) returns its ISO-8601 string (rebalancer.py:44)."""
    from datetime import datetime

    from quant_trading.portfolio.rebalancer import _iso

    dt = datetime(2024, 1, 2, 3, 4, 5)
    assert _iso(dt) == "2024-01-02T03:04:05"


def test_rebalancer_coerce_datetime_branches():
    """_coerce_datetime covers the None/datetime/str/fallback branches
    (rebalancer.py:50-55)."""
    from datetime import datetime

    from quant_trading.portfolio.rebalancer import _coerce_datetime

    assert _coerce_datetime(None) is None
    dt = datetime(2024, 1, 2, 3, 4, 5)
    assert _coerce_datetime(dt) is dt
    assert _coerce_datetime("2024-01-02T03:04:05") == dt
    assert _coerce_datetime(12345) is None
