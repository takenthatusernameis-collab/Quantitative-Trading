"""Tests for input validation in WalkForwardOptimizer.__init__."""

import pytest

from quant_trading.optimization.base import (
    ParameterGrid,
    ParameterSpace,
    maximize_sharpe,
)
from quant_trading.optimization.walk_forward import WalkForwardOptimizer


def _minimal_kwargs():
    """Return a minimal valid set of WalkForwardOptimizer constructor kwargs."""
    grid = ParameterGrid().add(
        ParameterSpace("fast_period", values=[5], param_type=int)
    )
    return {
        "strategy_cls": None,
        "param_grid": grid,
        "objective": maximize_sharpe,
        "start": None,
        "end": None,
    }


class TestWalkForwardInitValidation:
    """Tests for input validation in WalkForwardOptimizer.__init__."""

    @pytest.mark.parametrize("initial_capital", [0.0, -1000.0, -1.0])
    def test_rejects_invalid_initial_capital(self, initial_capital):
        with pytest.raises(ValueError, match="invalid initial_capital"):
            WalkForwardOptimizer(**_minimal_kwargs(), initial_capital=initial_capital)

    @pytest.mark.parametrize("n_windows", [0, -1, -5])
    def test_rejects_invalid_n_windows(self, n_windows):
        with pytest.raises(ValueError, match="invalid n_windows"):
            WalkForwardOptimizer(**_minimal_kwargs(), n_windows=n_windows)

    @pytest.mark.parametrize("train_size", [0.0, -0.1, 1.5])
    def test_rejects_invalid_train_size(self, train_size):
        with pytest.raises(ValueError, match="invalid train_size"):
            WalkForwardOptimizer(**_minimal_kwargs(), train_size=train_size)

    @pytest.mark.parametrize("train_size", [1.0])
    def test_accepts_train_size_upper_boundary(self, train_size):
        optimizer = WalkForwardOptimizer(**_minimal_kwargs(), train_size=train_size)
        assert optimizer.train_size == train_size

    @pytest.mark.parametrize("step_size", [0.0, -0.1, 1.5])
    def test_rejects_invalid_step_size(self, step_size):
        with pytest.raises(ValueError, match="invalid step_size"):
            WalkForwardOptimizer(**_minimal_kwargs(), step_size=step_size)

    @pytest.mark.parametrize("step_size", [1.0])
    def test_accepts_step_size_upper_boundary(self, step_size):
        optimizer = WalkForwardOptimizer(**_minimal_kwargs(), step_size=step_size)
        assert optimizer.step_size == step_size

    @pytest.mark.parametrize("periods_per_year", [0, -1, -252])
    def test_rejects_invalid_periods_per_year(self, periods_per_year):
        with pytest.raises(ValueError, match="invalid periods_per_year"):
            WalkForwardOptimizer(
                **_minimal_kwargs(), periods_per_year=periods_per_year
            )

    @pytest.mark.parametrize("periods_per_year", [1])
    def test_accepts_minimal_periods_per_year(self, periods_per_year):
        optimizer = WalkForwardOptimizer(
            **_minimal_kwargs(), periods_per_year=periods_per_year
        )
        assert optimizer.periods_per_year == periods_per_year

    @pytest.mark.parametrize("commission", [-0.1, 1.5])
    def test_rejects_invalid_commission(self, commission):
        with pytest.raises(ValueError, match="invalid commission"):
            WalkForwardOptimizer(**_minimal_kwargs(), commission=commission)

    @pytest.mark.parametrize("commission", [0.0, 1.0])
    def test_accepts_commission_boundaries(self, commission):
        optimizer = WalkForwardOptimizer(**_minimal_kwargs(), commission=commission)
        assert optimizer.commission == commission

    @pytest.mark.parametrize("slippage", [-0.1, 1.5])
    def test_rejects_invalid_slippage(self, slippage):
        with pytest.raises(ValueError, match="invalid slippage"):
            WalkForwardOptimizer(**_minimal_kwargs(), slippage=slippage)

    @pytest.mark.parametrize("slippage", [0.0, 1.0])
    def test_accepts_slippage_boundaries(self, slippage):
        optimizer = WalkForwardOptimizer(**_minimal_kwargs(), slippage=slippage)
        assert optimizer.slippage == slippage

    def test_accepts_all_boundary_valid_values(self):
        optimizer = WalkForwardOptimizer(
            **_minimal_kwargs(),
            initial_capital=1.0,
            n_windows=1,
            train_size=1.0,
            step_size=1.0,
            periods_per_year=1,
            commission=0.0,
            slippage=0.0,
        )
        assert optimizer.initial_capital == 1.0
        assert optimizer.n_windows == 1
        assert optimizer.train_size == 1.0
        assert optimizer.step_size == 1.0
        assert optimizer.periods_per_year == 1
        assert optimizer.commission == 0.0
        assert optimizer.slippage == 0.0
