"""Seeded, randomized invariant tests for the portfolio's position accounting.

``Portfolio.add_holding`` and ``Portfolio.remove_holding`` are the only two
public ways to change a position, and both are used by the backtest engine.
They must agree on what a reduction does: sell only what is held, leave the
remaining cost basis untouched, drop a position that is fully offset, and move
cash by exactly the trade's value net of the fees.

These tests drive a portfolio with pseudo-random but fully deterministic
scenarios (fixed seeds, no network, no unseeded randomness) and assert the
properties that must hold for *every* run:

1. The reported total value is cash plus the market value of the open positions.
2. A trade executed at the market price changes the total value by the fees and
   nothing else. This is the property that catches phantom cash: a trade that
   credits more cash than it sells leaks value into the portfolio, and a trade
   that credits less loses it.
3. The position moves by exactly the executed quantity, and a trade against an
   open position is capped at the size of that position.
4. A reduction never changes the cost basis of the remaining position.
5. ``add_holding`` with a negative quantity and ``remove_holding`` with the
   mirrored positive quantity leave the same position, the same basis and the
   same cash.
6. A fully offset position disappears from the portfolio; no zero-quantity
   leftovers are kept.
7. The reported position count matches the number of open positions.
"""

import numpy as np
import pytest

from quant_trading.portfolio.portfolio import Portfolio

SYMBOLS = ("AAA", "BBB", "CCC")
INITIAL_CASH = 1_000_000.0


def _assert_portfolio_invariants(portfolio: Portfolio) -> None:
    """Assert the self-consistency invariants that hold after every mutation."""
    market_value = sum(holding.market_value for holding in portfolio.holdings.values())

    # 1. The reported total value is cash plus the market value of the positions.
    assert portfolio.cash + market_value == pytest.approx(portfolio.total_value, rel=1e-9, abs=1e-9)

    # 6. No zero-quantity leftovers survive a trade.
    for holding in portfolio.holdings.values():
        assert holding.quantity != 0
        assert holding.market_value == pytest.approx(
            holding.quantity * holding.current_price, rel=1e-9, abs=1e-9
        )

    # 7. The reported position count matches the number of open positions.
    open_positions = [holding for holding in portfolio.holdings.values() if holding.quantity != 0]
    assert len(open_positions) == len(portfolio.holdings)
    assert portfolio.summary()["num_positions"] == len(open_positions)
    assert set(portfolio.get_positions()) == set(portfolio.holdings)


def _executed_quantity(position: float, requested: float) -> float:
    """Units actually traded by ``add_holding``, per its documented contract.

    A trade in the direction of the open position is executed in full, while a
    trade against it is capped at the size of the position.
    """
    if position == 0 or (position > 0) == (requested > 0):
        return abs(requested)
    return min(abs(requested), abs(position))


def _removed_quantity(position: float, requested: float) -> float:
    """Units actually traded by ``remove_holding``, per its documented contract.

    ``remove_holding`` always reduces the position, so it is capped at the size
    of the position and does nothing when the symbol is not held.
    """
    if position == 0:
        return 0.0
    return min(abs(requested), abs(position))


def _position_of(portfolio: Portfolio, symbol: str) -> float:
    """Signed quantity currently held in a symbol (0.0 when it is not held)."""
    holding = portfolio.holdings.get(symbol)
    return holding.quantity if holding is not None else 0.0


def _positions(portfolio: Portfolio) -> dict[str, tuple[float, float, float]]:
    """Snapshot of the per-symbol quantity, cost basis and current price."""
    return {
        symbol: (holding.quantity, holding.avg_cost, holding.current_price)
        for symbol, holding in portfolio.holdings.items()
    }


def _assert_positions_match(
    actual: dict[str, tuple[float, float, float]],
    expected: dict[str, tuple[float, float, float]],
) -> None:
    """Compare two per-symbol position snapshots element-wise with tolerance.

    ``pytest.approx`` on a dict whose values are tuples raises a ``TypeError``
    on pytest 9+ (it no longer descends into non-container values), so the
    comparison is done explicitly. This is at least as strict as the original
    ``_positions(a) == pytest.approx(_positions(b))``: every key and every
    component of every tuple must agree within the same tolerance.
    """
    assert set(actual) == set(expected), f"position keys differ: {set(actual)} != {set(expected)}"
    for symbol, actual_tuple in actual.items():
        expected_tuple = expected[symbol]
        for actual_value, expected_value in zip(actual_tuple, expected_tuple):
            assert actual_value == pytest.approx(
                expected_value, rel=1e-9, abs=1e-9
            ), f"{symbol}: {actual_value} != {expected_value}"


@pytest.mark.parametrize("seed", range(20))
def test_randomized_trade_sequence_invariants(seed: int):
    """A random sequence of trades keeps every portfolio invariant intact."""
    rng = np.random.default_rng(seed)
    commission = float(rng.uniform(0.0, 0.02))
    slippage = float(rng.uniform(0.0, 0.01))
    portfolio = Portfolio(cash=INITIAL_CASH, initial_capital=INITIAL_CASH)
    prices = {symbol: float(rng.uniform(20.0, 200.0)) for symbol in SYMBOLS}

    for _ in range(int(rng.integers(10, 40))):
        symbol = SYMBOLS[int(rng.integers(0, len(SYMBOLS)))]
        action = int(rng.integers(0, 10))
        price = prices[symbol]
        position_before = _position_of(portfolio, symbol)
        total_before = portfolio.total_value

        if action < 4:
            # Buy: open a long or add to the one already held.
            requested = float(rng.integers(1, 60))
            portfolio.add_holding(symbol, requested, price, commission, slippage)
            executed = _executed_quantity(position_before, requested)
        elif action < 7:
            # Sell: reduce a long, cover a short or open a short.
            requested = -float(rng.integers(1, 60))
            portfolio.add_holding(symbol, requested, price, commission, slippage)
            executed = _executed_quantity(position_before, requested)
        elif action < 9:
            # Explicit removal of part or all of a position.
            requested = float(rng.integers(1, 60))
            portfolio.remove_holding(symbol, requested, price, commission, slippage)
            executed = _removed_quantity(position_before, requested)
        else:
            # Mark to market; this moves the value and is not a trade.
            prices[symbol] = price * float(rng.uniform(0.9, 1.1))
            portfolio.update_prices({symbol: prices[symbol]})
            _assert_portfolio_invariants(portfolio)
            continue

        position_after = _position_of(portfolio, symbol)

        # 3. The position moved by exactly the executed quantity.
        assert abs(position_after - position_before) == pytest.approx(executed, rel=1e-9, abs=1e-9)

        # 2. Only the fees moved the total value.
        assert portfolio.total_value == pytest.approx(
            total_before - executed * price * (commission + slippage), rel=1e-9, abs=1e-6
        )

        _assert_portfolio_invariants(portfolio)


@pytest.mark.parametrize("seed", range(20))
def test_reduction_never_changes_the_remaining_basis(seed: int):
    """Reducing a long leaves the cost basis of the remaining position alone."""
    rng = np.random.default_rng(seed)
    commission = float(rng.uniform(0.0, 0.02))
    slippage = float(rng.uniform(0.0, 0.01))
    price = float(rng.uniform(20.0, 200.0))
    opened = float(rng.integers(10, 200))
    sold = float(rng.integers(1, int(opened)))

    portfolio = Portfolio(cash=INITIAL_CASH, initial_capital=INITIAL_CASH)
    portfolio.add_holding("AAA", opened, price, commission, slippage)
    basis = portfolio.holdings["AAA"].avg_cost

    portfolio.add_holding("AAA", -sold, price, commission, slippage)

    holding = portfolio.holdings["AAA"]
    assert holding.quantity == pytest.approx(opened - sold)
    assert holding.avg_cost == pytest.approx(basis)
    assert portfolio.cash == pytest.approx(
        INITIAL_CASH
        - opened * price * (1 + commission + slippage)
        + sold * price * (1 - commission - slippage)
    )
    _assert_portfolio_invariants(portfolio)


@pytest.mark.parametrize("seed", range(20))
def test_add_holding_reduction_matches_remove_holding(seed: int):
    """Both public ways of selling a position leave the same portfolio."""
    rng = np.random.default_rng(seed)
    commission = float(rng.uniform(0.0, 0.02))
    slippage = float(rng.uniform(0.0, 0.01))
    price = float(rng.uniform(20.0, 200.0))
    opened = float(rng.integers(10, 200))
    # Half of the runs sell more than is held, which both APIs must cap.
    sold = float(rng.integers(1, int(opened) * 2))

    reduced = Portfolio(cash=INITIAL_CASH, initial_capital=INITIAL_CASH)
    removed = Portfolio(cash=INITIAL_CASH, initial_capital=INITIAL_CASH)
    for portfolio in (reduced, removed):
        portfolio.add_holding("AAA", opened, price, commission, slippage)

    reduced.add_holding("AAA", -sold, price, commission, slippage)
    cash_effect = removed.remove_holding("AAA", sold, price, commission, slippage)

    assert reduced.cash == pytest.approx(removed.cash)
    assert reduced.total_value == pytest.approx(removed.total_value)
    _assert_positions_match(_positions(reduced), _positions(removed))
    # The cash that moved in the add_holding reduction is the cash that
    # remove_holding reported.
    assert reduced.cash - (INITIAL_CASH - opened * price * (1 + commission + slippage)) == (
        pytest.approx(cash_effect)
    )
    _assert_portfolio_invariants(reduced)
    _assert_portfolio_invariants(removed)


@pytest.mark.parametrize("seed", range(20))
def test_covering_a_short_matches_remove_holding(seed: int):
    """Buying back a short leaves the same portfolio as removing it."""
    rng = np.random.default_rng(seed)
    commission = float(rng.uniform(0.0, 0.02))
    slippage = float(rng.uniform(0.0, 0.01))
    price = float(rng.uniform(20.0, 200.0))
    opened = float(rng.integers(10, 200))
    covered = float(rng.integers(1, int(opened) * 2))

    covered_portfolio = Portfolio(cash=INITIAL_CASH, initial_capital=INITIAL_CASH)
    removed_portfolio = Portfolio(cash=INITIAL_CASH, initial_capital=INITIAL_CASH)
    for portfolio in (covered_portfolio, removed_portfolio):
        portfolio.add_holding("AAA", -opened, price, commission, slippage)

    covered_portfolio.add_holding("AAA", covered, price, commission, slippage)
    cash_effect = removed_portfolio.remove_holding("AAA", covered, price, commission, slippage)

    assert covered_portfolio.cash == pytest.approx(removed_portfolio.cash)
    assert covered_portfolio.total_value == pytest.approx(removed_portfolio.total_value)
    _assert_positions_match(_positions(covered_portfolio), _positions(removed_portfolio))
    assert covered_portfolio.cash - (
        INITIAL_CASH + opened * price * (1 - commission - slippage)
    ) == (pytest.approx(cash_effect))
    _assert_portfolio_invariants(covered_portfolio)
    _assert_portfolio_invariants(removed_portfolio)


@pytest.mark.parametrize("seed", range(10))
def test_adding_to_a_short_keeps_the_position(seed: int):
    """Selling more of an open short grows it instead of replacing it."""
    rng = np.random.default_rng(seed)
    commission = float(rng.uniform(0.0, 0.02))
    slippage = float(rng.uniform(0.0, 0.01))
    price = float(rng.uniform(20.0, 200.0))
    opened = float(rng.integers(10, 200))
    extra = float(rng.integers(1, 100))
    extra_price = float(rng.uniform(20.0, 200.0))

    portfolio = Portfolio(cash=INITIAL_CASH, initial_capital=INITIAL_CASH)
    portfolio.add_holding("AAA", -opened, price, commission, slippage)
    portfolio.add_holding("AAA", -extra, extra_price, commission, slippage)

    holding = portfolio.holdings["AAA"]
    assert holding.quantity == pytest.approx(-(opened + extra))
    assert holding.avg_cost == pytest.approx(
        (price * opened + extra_price * extra) / (opened + extra)
    )
    _assert_portfolio_invariants(portfolio)


def test_fully_offset_position_is_removed():
    """A position that is fully offset disappears from the portfolio."""
    portfolio = Portfolio(cash=INITIAL_CASH, initial_capital=INITIAL_CASH)
    portfolio.add_holding("AAA", 100, 50.0)
    portfolio.add_holding("AAA", -100, 50.0)

    assert "AAA" not in portfolio.holdings
    assert portfolio.get_positions() == {}
    assert portfolio.summary()["num_positions"] == 0
    _assert_portfolio_invariants(portfolio)


def test_fully_covered_short_is_removed():
    """A short that is fully covered disappears from the portfolio."""
    portfolio = Portfolio(cash=INITIAL_CASH, initial_capital=INITIAL_CASH)
    portfolio.add_holding("AAA", -100, 50.0)
    portfolio.add_holding("AAA", 100, 50.0)

    assert "AAA" not in portfolio.holdings
    assert portfolio.summary()["num_positions"] == 0
    _assert_portfolio_invariants(portfolio)


def test_zero_quantity_trade_creates_no_position():
    """A zero-sized trade must not leave a position behind."""
    portfolio = Portfolio(cash=INITIAL_CASH, initial_capital=INITIAL_CASH)
    portfolio.add_holding("AAA", 0, 50.0)

    assert portfolio.holdings == {}
    assert portfolio.summary()["num_positions"] == 0
    assert portfolio.cash == INITIAL_CASH
    _assert_portfolio_invariants(portfolio)


def test_reduction_larger_than_the_position_sells_only_what_is_held():
    """A reduction is capped at the size of the position."""
    portfolio = Portfolio(cash=INITIAL_CASH, initial_capital=INITIAL_CASH)
    portfolio.add_holding("AAA", 100, 50.0)
    portfolio.add_holding("AAA", -150, 60.0)

    assert "AAA" not in portfolio.holdings
    assert portfolio.cash == pytest.approx(INITIAL_CASH - 100 * 50.0 + 100 * 60.0)
    _assert_portfolio_invariants(portfolio)
