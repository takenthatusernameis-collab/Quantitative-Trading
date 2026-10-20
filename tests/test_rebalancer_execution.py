"""Seeded, randomized invariant tests for :meth:`Rebalancer.execute_actions`.

``Rebalancer.execute_actions`` is the bridge between the actions the rebalancer
plans and the portfolio that holds the positions. Applying an action must never
break the accounting the portfolio guarantees:

1. The reported total value stays cash plus the market value of the positions.
2. A trade moves the total value by exactly the fees and nothing else.
3. A trade against an open position is capped at the size of that position.
4. A position that is fully offset disappears from the portfolio.
5. A buy of a symbol that is already held averages the cost basis.
6. The reported position count matches the number of open positions.

The scenarios are pseudo-random but fully deterministic (fixed seeds, no
network, no unseeded randomness).
"""

import numpy as np
import pytest

from quant_trading.portfolio.portfolio import Portfolio
from quant_trading.portfolio.rebalancer import RebalanceAction, Rebalancer

SEEDS = (20240601, 20240602, 20240603, 20240604, 20240605)
SYMBOLS = ("AAA", "BBB", "CCC")
INITIAL_CASH = 5_000_000.0
STEPS = 40


def _position_of(portfolio: Portfolio, symbol: str) -> float:
    """Signed quantity currently held in a symbol (0.0 when it is not held)."""
    holding = portfolio.holdings.get(symbol)
    return holding.quantity if holding is not None else 0.0


def _market_value(portfolio: Portfolio) -> float:
    """Total market value of the open positions."""
    return sum(holding.market_value for holding in portfolio.holdings.values())


def _open_positions(portfolio: Portfolio) -> int:
    """Number of positions the portfolio actually holds."""
    return len([holding for holding in portfolio.holdings.values() if holding.quantity != 0])


@pytest.mark.parametrize("seed", SEEDS)
def test_randomized_execution_invariants(seed: int):
    """A random sequence of executed actions keeps every portfolio invariant."""
    rng = np.random.default_rng(seed)
    commission = float(rng.uniform(0.0, 0.01))
    slippage = float(rng.uniform(0.0, 0.005))
    prices = {symbol: float(rng.uniform(20.0, 200.0)) for symbol in SYMBOLS}

    portfolio = Portfolio(cash=INITIAL_CASH, initial_capital=INITIAL_CASH)
    rebalancer = Rebalancer(portfolio, frequency="monthly")

    # Seed the portfolio with a few random positions, longs and shorts alike.
    for symbol in SYMBOLS:
        if rng.random() < 0.5:
            quantity = float(rng.integers(5, 60))
            if rng.random() < 0.3:
                quantity = -quantity
            portfolio.add_holding(symbol, quantity, prices[symbol], commission, slippage)

    for _ in range(STEPS):
        symbol = SYMBOLS[int(rng.integers(0, len(SYMBOLS)))]
        direction = ("buy", "sell", "hold")[int(rng.integers(0, 3))]
        requested = float(rng.integers(1, 51))

        # Mark the symbol to market so the trade happens at its current price.
        price = float(rng.uniform(20.0, 200.0))
        prices[symbol] = price
        portfolio.update_prices({symbol: price})

        position_before = _position_of(portfolio, symbol)
        basis_before = portfolio.holdings[symbol].avg_cost if symbol in portfolio.holdings else 0.0
        total_before = portfolio.total_value
        cash_before = portfolio.cash

        action = RebalanceAction(
            symbol=symbol, action=direction, quantity=requested, reason="invariant_test"
        )
        executions = rebalancer.execute_actions(
            [action], prices=prices, commission=commission, slippage=slippage
        )

        assert len(executions) == 1
        execution = executions[0]
        assert execution.symbol == symbol
        assert execution.action == direction
        assert execution.requested_quantity == pytest.approx(requested, rel=1e-9, abs=1e-9)
        assert execution.price == pytest.approx(price, rel=1e-9, abs=1e-9)

        executed = execution.executed_quantity

        # The reported cash effect is the cash that actually moved.
        assert execution.cash_effect == pytest.approx(
            portfolio.cash - cash_before, rel=1e-9, abs=1e-9
        )

        # 1. The reported total value is cash plus the market value.
        assert portfolio.cash + _market_value(portfolio) == pytest.approx(
            portfolio.total_value, rel=1e-9, abs=1e-9
        )

        # 2. Only the fees moved the total value.
        assert portfolio.total_value == pytest.approx(
            total_before - executed * price * (commission + slippage), rel=1e-9, abs=1e-6
        )

        # 3. A trade against an open position is capped at the size of that
        #    position; a trade in the same direction is executed in full.
        if direction == "hold":
            assert executed == 0.0
        elif direction == "sell":
            assert executed == pytest.approx(
                min(requested, abs(position_before)), rel=1e-9, abs=1e-9
            )
        elif position_before < 0:
            # A buy against an open short covers it instead of flipping it.
            assert executed == pytest.approx(
                min(requested, abs(position_before)), rel=1e-9, abs=1e-9
            )
        else:
            assert executed == pytest.approx(requested, rel=1e-9, abs=1e-9)

        # 4. A fully offset position disappears from the portfolio. A sale
        #    always reduces the position and a buy against a short covers it,
        #    but a hold never touches the position.
        if abs(position_before) > 0 and requested >= abs(position_before):
            reduces_position = direction == "sell" or (direction == "buy" and position_before < 0)
            if reduces_position:
                assert symbol not in portfolio.holdings

        # 5. A buy of a symbol that is already held averages the cost basis.
        if direction == "buy" and position_before > 0:
            expected_basis = (
                basis_before * position_before + price * (1 + commission + slippage) * requested
            ) / (position_before + requested)
            assert portfolio.holdings[symbol].avg_cost == pytest.approx(
                expected_basis, rel=1e-9, abs=1e-9
            )

        # 6. The reported position count matches the number of open positions.
        assert portfolio.summary()["num_positions"] == _open_positions(portfolio)
        for holding in portfolio.holdings.values():
            assert holding.quantity != 0
            assert holding.market_value == pytest.approx(
                holding.quantity * holding.current_price, rel=1e-9, abs=1e-9
            )


@pytest.mark.parametrize("seed", SEEDS)
def test_randomized_execution_never_leaves_zero_quantity_positions(seed: int):
    """An executed action never leaves a zero-quantity position behind."""
    rng = np.random.default_rng(seed)
    prices = {symbol: float(rng.uniform(20.0, 200.0)) for symbol in SYMBOLS}

    portfolio = Portfolio(cash=INITIAL_CASH, initial_capital=INITIAL_CASH)
    rebalancer = Rebalancer(portfolio)

    for _ in range(STEPS):
        symbol = SYMBOLS[int(rng.integers(0, len(SYMBOLS)))]
        direction = ("buy", "sell")[int(rng.integers(0, 2))]
        requested = float(rng.integers(1, 51))
        portfolio.update_prices({symbol: prices[symbol]})

        rebalancer.execute_actions(
            [
                RebalanceAction(
                    symbol=symbol, action=direction, quantity=requested, reason="zero_qty_test"
                )
            ],
            prices=prices,
        )

        assert all(holding.quantity != 0 for holding in portfolio.holdings.values())
        assert portfolio.summary()["num_positions"] == len(portfolio.holdings)


def test_execute_actions_buy_opens_a_position():
    """A buy action buys the requested quantity."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio)

    executions = rebalancer.execute_actions(
        [RebalanceAction(symbol="AAPL", action="buy", quantity=10.0)], prices={"AAPL": 150.0}
    )

    assert len(executions) == 1
    assert executions[0].executed_quantity == pytest.approx(10.0)
    assert executions[0].cash_effect == pytest.approx(-1500.0)
    assert portfolio.holdings["AAPL"].quantity == pytest.approx(10.0)
    assert portfolio.holdings["AAPL"].avg_cost == pytest.approx(150.0)
    assert portfolio.cash == pytest.approx(98500.0)


def test_execute_actions_sell_reduces_a_position():
    """A sell action sells the requested quantity."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", 10, 100.0)
    rebalancer = Rebalancer(portfolio)

    executions = rebalancer.execute_actions(
        [RebalanceAction(symbol="AAPL", action="sell", quantity=4.0)], prices={"AAPL": 150.0}
    )

    assert executions[0].executed_quantity == pytest.approx(4.0)
    assert executions[0].cash_effect == pytest.approx(600.0)
    assert portfolio.holdings["AAPL"].quantity == pytest.approx(6.0)
    # The remaining basis is untouched.
    assert portfolio.holdings["AAPL"].avg_cost == pytest.approx(100.0)


def test_execute_actions_hold_is_a_noop():
    """A hold action changes nothing."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", 10, 100.0)
    rebalancer = Rebalancer(portfolio)
    before = portfolio.summary()

    executions = rebalancer.execute_actions(
        [RebalanceAction(symbol="AAPL", action="hold", quantity=5.0)], prices={"AAPL": 150.0}
    )

    assert executions[0].executed_quantity == 0.0
    assert executions[0].cash_effect == 0.0
    assert portfolio.summary() == before


def test_execute_actions_sell_is_capped_at_the_position_size():
    """A sell larger than the position only sells what is held."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", 10, 100.0)
    rebalancer = Rebalancer(portfolio)

    executions = rebalancer.execute_actions(
        [RebalanceAction(symbol="AAPL", action="sell", quantity=25.0)], prices={"AAPL": 150.0}
    )

    assert executions[0].requested_quantity == pytest.approx(25.0)
    assert executions[0].executed_quantity == pytest.approx(10.0)
    assert "AAPL" not in portfolio.holdings
    assert portfolio.summary()["num_positions"] == 0


def test_execute_actions_uses_the_prices_map_over_the_holding_price():
    """The prices map wins over the current price of the holding."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", 10, 100.0)
    rebalancer = Rebalancer(portfolio)

    executions = rebalancer.execute_actions(
        [RebalanceAction(symbol="AAPL", action="sell", quantity=5.0)], prices={"AAPL": 150.0}
    )

    assert executions[0].price == pytest.approx(150.0)
    assert executions[0].cash_effect == pytest.approx(750.0)


def test_execute_actions_falls_back_to_the_holding_price():
    """Without a price in the map the holding's current price is used."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", 10, 100.0)
    rebalancer = Rebalancer(portfolio)

    executions = rebalancer.execute_actions(
        [RebalanceAction(symbol="AAPL", action="sell", quantity=5.0)]
    )

    assert executions[0].price == pytest.approx(100.0)
    assert executions[0].executed_quantity == pytest.approx(5.0)


def test_execute_actions_skips_an_action_without_a_price():
    """An action with no resolvable price is skipped, not guessed."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio)

    executions = rebalancer.execute_actions(
        [RebalanceAction(symbol="AAPL", action="buy", quantity=10.0)]
    )

    assert executions[0].executed_quantity == 0.0
    assert executions[0].price == 0.0
    assert portfolio.holdings == {}
    assert portfolio.cash == pytest.approx(100000.0)


def test_execute_actions_rejects_an_unknown_action():
    """An unrecognized direction is a programming error and is reported."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio)

    with pytest.raises(ValueError, match="Unknown rebalance action"):
        rebalancer.execute_actions(
            [RebalanceAction(symbol="AAPL", action="short", quantity=10.0)],
            prices={"AAPL": 150.0},
        )


def test_execute_actions_sell_of_an_unheld_symbol_is_a_noop():
    """Selling a symbol that is not held does nothing."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio)

    executions = rebalancer.execute_actions(
        [RebalanceAction(symbol="AAPL", action="sell", quantity=10.0)], prices={"AAPL": 150.0}
    )

    assert executions[0].executed_quantity == 0.0
    assert executions[0].cash_effect == 0.0
    assert portfolio.holdings == {}
    assert portfolio.cash == pytest.approx(100000.0)


def test_execute_actions_zero_quantity_is_a_noop():
    """A zero-sized action does not open a position."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio)

    executions = rebalancer.execute_actions(
        [RebalanceAction(symbol="AAPL", action="buy", quantity=0.0)], prices={"AAPL": 150.0}
    )

    assert executions[0].executed_quantity == 0.0
    assert portfolio.holdings == {}


def test_execute_actions_buy_covers_an_open_short():
    """A buy against an open short covers it instead of flipping it."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    portfolio.add_holding("AAPL", -10, 100.0)
    rebalancer = Rebalancer(portfolio)

    executions = rebalancer.execute_actions(
        [RebalanceAction(symbol="AAPL", action="buy", quantity=10.0)],
        prices={"AAPL": 100.0},
        commission=0.001,
        slippage=0.0005,
    )

    assert executions[0].executed_quantity == pytest.approx(10.0)
    # Covering a short costs cash.
    assert executions[0].cash_effect == pytest.approx(-10 * 100.0 * (1 + 0.001 + 0.0005))
    assert "AAPL" not in portfolio.holdings


def test_execute_actions_applies_commission_and_slippage():
    """The fees are charged to cash and to the cost basis of a new position."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio)

    rebalancer.execute_actions(
        [RebalanceAction(symbol="AAPL", action="buy", quantity=10.0)],
        prices={"AAPL": 100.0},
        commission=0.001,
        slippage=0.0005,
    )

    fees = 0.001 + 0.0005
    assert portfolio.cash == pytest.approx(100000.0 - 10 * 100.0 * (1 + fees))
    assert portfolio.holdings["AAPL"].avg_cost == pytest.approx(100.0 * (1 + fees))
    # Only the fees changed the total value of the portfolio.
    assert portfolio.total_value == pytest.approx(100000.0 - 10 * 100.0 * fees)


def test_execute_actions_returns_one_execution_per_action():
    """The executions are reported in the order the actions were given."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio)

    executions = rebalancer.execute_actions(
        [
            RebalanceAction(symbol="AAPL", action="buy", quantity=10.0),
            RebalanceAction(symbol="MSFT", action="buy", quantity=5.0),
            RebalanceAction(symbol="AAPL", action="hold", quantity=3.0),
        ],
        prices={"AAPL": 100.0, "MSFT": 200.0},
    )

    assert [e.symbol for e in executions] == ["AAPL", "MSFT", "AAPL"]
    assert [e.action for e in executions] == ["buy", "buy", "hold"]
    assert [e.executed_quantity for e in executions] == [10.0, 5.0, 0.0]


def test_execute_actions_records_the_execution_in_the_history():
    """The run is recorded in the rebalance history."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio)

    rebalancer.execute_actions(
        [RebalanceAction(symbol="AAPL", action="buy", quantity=10.0)], prices={"AAPL": 150.0}
    )

    assert len(rebalancer.rebalance_history) == 1
    entry = rebalancer.rebalance_history[0]
    assert entry["actions"] == ["AAPL"]
    assert entry["portfolio_value"] == pytest.approx(portfolio.total_value)
    assert entry["executions"][0]["executed_quantity"] == pytest.approx(10.0)
    assert entry["executions"][0]["price"] == pytest.approx(150.0)
    assert entry["executions"][0]["cash_effect"] == pytest.approx(-1500.0)


def test_execute_actions_updates_last_rebalance():
    """Executing actions stamps the rebalancer and the portfolio."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(portfolio)

    assert rebalancer.last_rebalance is None
    assert portfolio.last_rebalance is None

    rebalancer.execute_actions(
        [RebalanceAction(symbol="AAPL", action="buy", quantity=10.0)], prices={"AAPL": 150.0}
    )

    assert rebalancer.last_rebalance is not None
    assert portfolio.last_rebalance == rebalancer.last_rebalance


def test_execute_actions_applies_the_generated_actions():
    """The actions the rebalancer generates can be executed end to end."""
    portfolio = Portfolio(cash=100000.0, initial_capital=100000.0)
    rebalancer = Rebalancer(
        portfolio, frequency="monthly", target_allocation={"AAPL": 0.5, "MSFT": 0.5}
    )
    prices = {"AAPL": 150.0, "MSFT": 300.0}

    actions = rebalancer.generate_rebalance_actions(prices=prices)
    assert actions

    deviations_before = rebalancer.get_current_deviation()
    executions = rebalancer.execute_actions(actions, prices=prices)

    assert len(executions) == len(actions)
    assert all(execution.executed_quantity > 0 for execution in executions)

    deviations_after = rebalancer.get_current_deviation()
    for symbol, deviation in deviations_before.items():
        assert abs(deviations_after[symbol]) < abs(deviation)

    assert portfolio.summary()["num_positions"] == 2
