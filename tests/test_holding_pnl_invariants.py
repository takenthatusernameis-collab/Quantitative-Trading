"""Seeded, randomized invariant tests for Holding.unrealized_pnl_pct.

``unrealized_pnl_pct`` must be the position's unrealized PnL as a fraction of
its cost basis, so that it carries the sign of the PnL: a long and a short
with the same prices are mirror images, and a zero-quantity holding reports
0.0.

The scenarios are pseudo-random but fully deterministic (fixed seeds, no
network, no unseeded randomness).
"""

import numpy as np
import pytest

from quant_trading.portfolio.portfolio import Holding

SEEDS = (20240101, 20240202, 20240303, 20240404, 20240505)
HOLDINGS_PER_SEED = 200


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


def _random_holding(rng: np.random.Generator) -> Holding:
    """Build a random holding, sometimes on a zero-quantity or zero-cost path."""
    quantity = float(rng.integers(-1000, 1001))
    avg_cost = float(rng.uniform(1.0, 500.0))
    current_price = float(rng.uniform(1.0, 500.0))
    if rng.random() < 0.1:
        quantity = 0.0
    if rng.random() < 0.1:
        avg_cost = 0.0
    return Holding(symbol="AAPL", quantity=quantity, avg_cost=avg_cost, current_price=current_price)


@pytest.mark.parametrize("seed", SEEDS)
def test_unrealized_pnl_pct_is_cost_basis_fraction(seed):
    """unrealized_pnl_pct is the PnL as a fraction of the cost basis."""
    rng = np.random.default_rng(seed)
    for _ in range(HOLDINGS_PER_SEED):
        holding = _random_holding(rng)

        if holding.quantity == 0 or holding.avg_cost == 0:
            assert holding.unrealized_pnl_pct == 0.0
            assert holding.unrealized_pnl == 0.0
            continue

        expected = holding.unrealized_pnl / (abs(holding.quantity) * abs(holding.avg_cost))
        assert holding.unrealized_pnl_pct == pytest.approx(expected, rel=1e-9, abs=1e-12)
        assert holding.unrealized_pnl == pytest.approx(
            abs(holding.quantity) * abs(holding.avg_cost) * holding.unrealized_pnl_pct,
            rel=1e-9,
            abs=1e-12,
        )


@pytest.mark.parametrize("seed", SEEDS)
def test_unrealized_pnl_pct_sign_matches_pnl(seed):
    """The sign of unrealized_pnl_pct matches the sign of unrealized_pnl."""
    rng = np.random.default_rng(seed)
    for _ in range(HOLDINGS_PER_SEED):
        holding = _random_holding(rng)
        pnl = holding.unrealized_pnl
        pct = holding.unrealized_pnl_pct
        if pnl == 0.0 or pct == 0.0:
            continue
        assert _sign(pnl) == _sign(pct)


@pytest.mark.parametrize("seed", SEEDS)
def test_unrealized_pnl_pct_long_short_are_mirror_images(seed):
    """A long and a short with the same prices are mirror images."""
    rng = np.random.default_rng(seed)
    for _ in range(HOLDINGS_PER_SEED):
        quantity = float(rng.integers(1, 1001))
        avg_cost = float(rng.uniform(1.0, 500.0))
        current_price = float(rng.uniform(1.0, 500.0))

        long_holding = Holding(
            symbol="AAPL", quantity=quantity, avg_cost=avg_cost, current_price=current_price
        )
        short_holding = Holding(
            symbol="AAPL", quantity=-quantity, avg_cost=avg_cost, current_price=current_price
        )

        assert short_holding.unrealized_pnl == pytest.approx(
            -long_holding.unrealized_pnl, rel=1e-9, abs=1e-12
        )
        assert short_holding.unrealized_pnl_pct == pytest.approx(
            -long_holding.unrealized_pnl_pct, rel=1e-9, abs=1e-12
        )
