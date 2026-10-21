"""Invariant tests for the trade sizes the rebalancer plans.

The rebalancer turns a portfolio and a set of signals into a batch of
:class:`~quant_trading.portfolio.rebalancer.RebalanceAction` objects. The
batch has to satisfy two invariants:

1. **One price space.** The quantity of a trade is derived from the price the
   trade happens at, and the deviation it closes is measured at that same
   price. A trade therefore releases exactly the dollars the deviation
   measured, and the position it leaves behind is worth its target.
2. **One target per symbol.** A symbol that is bought twice in the same batch
   is topped up to the target of the batch, not bought twice. The batch's own
   trades count towards the current value of the symbol.

The scenarios are pseudo-random but fully deterministic (fixed seeds, no
network, no unseeded randomness).
"""

import numpy as np
import pytest

from quant_trading.portfolio.portfolio import Portfolio
from quant_trading.portfolio.rebalancer import Rebalancer
from quant_trading.risk.manager import RiskManager
from quant_trading.strategies.base import Signal

SEEDS = (20240611, 20240612, 20240613, 20240614, 20240615)
SYMBOLS = ("AAA", "BBB", "CCC")


def _portfolio_with_aapl(quantity: float = 100.0, price: float = 100.0) -> Portfolio:
    """Portfolio with $10,000 of cash and one AAPL lot marked at ``price``."""
    portfolio = Portfolio(cash=10000.0, initial_capital=10000.0)
    portfolio.add_holding("AAPL", quantity, price)
    return portfolio


def test_a_sell_releases_exactly_the_dollars_the_deviation_measured():
    """A sell is sized at the price it trades at, not at the holding's mark."""
    portfolio = _portfolio_with_aapl()  # 100 AAPL marked at $100
    rebalancer = Rebalancer(portfolio, target_allocation={"AAPL": 0.25, "MSFT": 0.75})
    # The market price the trade happens at is twice the mark of the holding.
    prices = {"AAPL": 200.0}

    actions = rebalancer.generate_rebalance_actions(prices=prices)

    assert len(actions) == 1
    action = actions[0]
    assert action.action == "sell"
    # The position is worth $20,000 at the price it trades at and the target
    # is 25% of the $20,000 portfolio, so $15,000 is sold: 75 shares at $200.
    assert action.quantity == pytest.approx(75.0)

    executions = rebalancer.execute_actions(actions, prices=prices)
    assert executions[0].executed_quantity == pytest.approx(75.0)
    assert executions[0].price == pytest.approx(200.0)
    # The trade released exactly the dollars the deviation measured.
    assert executions[0].cash_effect == pytest.approx(15000.0)


def test_a_rebalance_lands_the_position_on_its_target():
    """After the batch is executed the position is worth its target."""
    portfolio = _portfolio_with_aapl()  # 100 AAPL marked at $100
    rebalancer = Rebalancer(portfolio, target_allocation={"AAPL": 0.25, "MSFT": 0.75})
    prices = {"AAPL": 200.0}

    actions = rebalancer.generate_rebalance_actions(prices=prices)
    rebalancer.execute_actions(actions, prices=prices)

    # The portfolio is worth $20,000 at the trade price, so AAPL is worth
    # 25% of it, which is $5,000, or 25 shares at $200.
    holding = portfolio.holdings["AAPL"]
    assert holding.quantity == pytest.approx(25.0)
    assert holding.quantity * prices["AAPL"] == pytest.approx(5000.0)


def test_a_buy_lands_the_position_on_its_target():
    """A buy that closes a gap leaves the position worth its target."""
    portfolio = _portfolio_with_aapl(quantity=50.0)  # 50 AAPL marked at $100
    rebalancer = Rebalancer(portfolio, target_allocation={"AAPL": 0.75, "MSFT": 0.25})
    prices = {"AAPL": 200.0}

    actions = rebalancer.generate_rebalance_actions(prices=prices)
    rebalancer.execute_actions(actions, prices=prices)

    # The portfolio is worth $15,000 at the trade price ($5,000 of cash and
    # $10,000 of AAPL), so AAPL is worth 75% of it, which is $11,250, or
    # 56.25 shares at $200.
    holding = portfolio.holdings["AAPL"]
    assert holding.quantity == pytest.approx(56.25)
    assert holding.quantity * prices["AAPL"] == pytest.approx(11250.0)


def test_two_buy_signals_for_the_same_symbol_buy_one_slice():
    """The second signal tops the position up instead of buying another slice."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio)
    signals = [
        Signal(symbol="GOOGL", action="buy", strength=1.0, price=100.0),
        Signal(symbol="GOOGL", action="buy", strength=1.0, price=100.0),
    ]

    actions = rebalancer.generate_rebalance_actions(signals, prices={"GOOGL": 100.0})

    # A single buy of 5% of the portfolio value, not two of them.
    assert len(actions) == 1
    assert actions[0].action == "buy"
    assert actions[0].quantity == pytest.approx(50.0)  # 5% of $100,000


def test_a_stronger_signal_tops_the_position_up_to_its_own_target():
    """A stronger signal raises the target of the symbol it tops up."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio)
    signals = [
        Signal(symbol="GOOGL", action="buy", strength=1.0, price=100.0),
        Signal(symbol="GOOGL", action="buy", strength=2.0, price=100.0),
    ]

    actions = rebalancer.generate_rebalance_actions(signals, prices={"GOOGL": 100.0})

    # The first signal buys 5% of the portfolio, the second one tops the
    # position up to 10% of it, so 50 shares are bought in total.
    assert len(actions) == 2
    assert sum(action.quantity for action in actions) == pytest.approx(100.0)


def test_a_signal_buy_counts_the_position_the_portfolio_already_holds():
    """A position that is already at the signal's target is not topped up."""
    portfolio = Portfolio(cash=95000.0, initial_capital=100000.0)
    portfolio.add_holding("GOOGL", 50, 100.0)  # $5,000 of a $95,000 portfolio
    rebalancer = Rebalancer(portfolio)
    signal = Signal(symbol="GOOGL", action="buy", strength=1.0, price=100.0)

    actions = rebalancer.generate_rebalance_actions([signal], prices={"GOOGL": 100.0})

    # The position is already worth more than 5% of the portfolio value.
    assert actions == []


def test_a_buy_that_cannot_be_funded_is_dropped():
    """A buy the portfolio cannot pay for produces no action."""
    portfolio = Portfolio(cash=10000.0, initial_capital=10000.0)
    portfolio.add_holding("AAPL", 100, 100.0)  # the cash is spent, AAPL is held
    rebalancer = Rebalancer(portfolio, target_allocation={"MSFT": 1.0, "AAPL": 0.0})
    prices = {"MSFT": 50.0, "AAPL": 100.0}

    actions = rebalancer.generate_rebalance_actions(prices=prices)

    # MSFT is bought first and there is no cash to buy it with, so the buy is
    # dropped. The sell of AAPL comes after it and is planned.
    assert [a.action for a in actions] == ["sell"]
    assert actions[0].symbol == "AAPL"


def test_a_sell_for_a_symbol_that_is_not_held_produces_no_action():
    """A negative target for a symbol the portfolio does not hold is not traded."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio, target_allocation={"AAPL": -0.5})

    actions = rebalancer.generate_rebalance_actions(prices={"AAPL": 100.0})

    assert actions == []


def test_a_signal_buy_the_position_limit_blocks_produces_no_action():
    """A signal buy for a position that is already at its limit is dropped."""
    portfolio = Portfolio(cash=99000.0, initial_capital=100000.0)
    portfolio.add_holding("GOOGL", 10, 100.0)  # $1,000, the position limit
    risk_manager = RiskManager(initial_capital=100000.0, max_position_size=0.01)
    rebalancer = Rebalancer(portfolio, risk_manager=risk_manager)
    signal = Signal(symbol="GOOGL", action="buy", strength=1.0, price=100.0)

    actions = rebalancer.generate_rebalance_actions([signal], prices={"GOOGL": 100.0})

    assert actions == []


def test_resolve_sell_quantity_falls_back_to_the_holding_price():
    """Without a planned price the current price of the holding is used."""
    rebalancer = Rebalancer(_portfolio_with_aapl())  # 100 AAPL marked at $100

    assert rebalancer._resolve_sell_quantity("AAPL", 1000.0) == pytest.approx(10.0)


def test_set_target_allocation_rejects_a_zero_sum():
    """Fractions that sum to zero cannot be normalized and are reported."""
    rebalancer = Rebalancer(Portfolio(cash=100000.0, initial_capital=100000.0))

    with pytest.raises(ValueError, match="must not sum to zero"):
        rebalancer.set_target_allocation({"AAPL": 0.0})


def test_set_target_allocation_accepts_an_empty_allocation():
    """An empty allocation clears the targets."""
    rebalancer = Rebalancer(
        Portfolio(cash=100000.0, initial_capital=100000.0),
        target_allocation={"AAPL": 1.0},
    )

    rebalancer.set_target_allocation({})

    assert rebalancer.target_allocation == {}


@pytest.mark.parametrize("seed", SEEDS)
def test_randomized_rebalance_sizes_every_trade_at_the_trade_price(seed: int):
    """Every planned trade is sized at the price the trade happens at.

    The portfolio holds its positions at marks that differ from the prices
    the trades are planned at, which is the case in which a trade used to be
    sized at the wrong price.
    """
    rng = np.random.default_rng(seed)
    prices = {symbol: float(rng.uniform(20.0, 200.0)) for symbol in SYMBOLS}
    raw = rng.uniform(0.05, 1.0, size=len(SYMBOLS))
    target_allocation = {s: float(v / raw.sum()) for s, v in zip(SYMBOLS, raw)}

    portfolio = Portfolio(cash=500_000.0, initial_capital=500_000.0)
    for symbol in SYMBOLS:
        if rng.random() < 0.8:
            mark = float(rng.uniform(20.0, 200.0))
            portfolio.add_holding(symbol, float(rng.integers(10, 100)), mark)

    rebalancer = Rebalancer(portfolio, target_allocation=target_allocation, rebalance_threshold=0.0)

    total_value = portfolio.cash + sum(
        (portfolio.holdings[s].quantity if s in portfolio.holdings else 0.0) * prices[s]
        for s in SYMBOLS
    )
    targets = {s: total_value * pct for s, pct in target_allocation.items()}

    actions = rebalancer.generate_rebalance_actions(prices=prices)

    for action in actions:
        price = prices[action.symbol]
        holding = portfolio.holdings.get(action.symbol)
        quantity_before = holding.quantity if holding is not None else 0.0
        deviation = abs(targets[action.symbol] - quantity_before * price)
        traded = action.quantity * price
        # A trade never moves more than the deviation it closes.
        assert traded <= deviation + 1e-6
        if action.action == "sell":
            # A sell is not limited by the cash, so it moves exactly the
            # deviation it closes.
            assert traded == pytest.approx(deviation, rel=1e-9, abs=1e-6)


@pytest.mark.parametrize("seed", SEEDS)
def test_randomized_signals_never_buy_a_symbol_beyond_its_target(seed: int):
    """Repeated buy signals for one symbol buy it up to its target, not beyond."""
    rng = np.random.default_rng(seed)
    prices = {symbol: float(rng.uniform(20.0, 200.0)) for symbol in SYMBOLS}

    portfolio = Portfolio(cash=1_000_000.0, initial_capital=1_000_000.0)
    rebalancer = Rebalancer(portfolio)

    signals = [
        Signal(
            symbol=symbol, action="buy", strength=float(rng.uniform(0.2, 2.0)), price=prices[symbol]
        )
        for symbol in SYMBOLS
        for _ in range(3)
    ]

    actions = rebalancer.generate_rebalance_actions(signals, prices=prices)

    bought: dict[str, float] = {}
    for action in actions:
        bought[action.symbol] = (
            bought.get(action.symbol, 0.0) + action.quantity * prices[action.symbol]
        )

    total_value = portfolio.cash + sum(
        (portfolio.holdings[s].quantity if s in portfolio.holdings else 0.0) * prices[s]
        for s in SYMBOLS
    )
    for symbol, value in bought.items():
        strongest = max(signal.strength for signal in signals if signal.symbol == symbol)
        # The symbol is never worth more than the strongest signal's target.
        assert value <= total_value * 0.05 * strongest + 1e-6
