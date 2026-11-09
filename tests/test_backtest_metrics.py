"""Tests for backtest metrics calculation."""

import warnings
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from quant_trading.backtest.engine import BacktestResult
from quant_trading.backtest.metrics import BacktestMetrics, calculate_backtest_metrics


def _result(metrics: Any) -> BacktestResult:
    """Build a BacktestResult carrying the given metrics object."""
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    equity = pd.Series([100000.0 + step * 10.0 for step in range(10)], index=dates)
    return BacktestResult(
        equity_curve=equity,
        trades=pd.DataFrame(),
        positions={},
        metrics=metrics,
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 10),
        initial_capital=100000.0,
        final_value=100090.0,
        total_return=90.0,
        total_return_pct=0.09,
    )


def test_calculate_metrics_no_trades_empty():
    """Test metrics when there are no trades."""
    equity_curve = pd.Series([100000, 110000, 105000, 115000])
    trades = pd.DataFrame()

    metrics = calculate_backtest_metrics(equity_curve, trades=trades)
    assert metrics.total_return > 0
    assert metrics.num_trades == 0


def test_calculate_metrics_no_trades_none():
    """Test metrics when trades is None."""
    equity_curve = pd.Series([100000, 110000, 105000, 115000])
    metrics = calculate_backtest_metrics(equity_curve, trades=None)
    assert metrics.num_trades == 0
    assert metrics.profit_factor == 0


def test_calculate_metrics_all_winning_trades():
    """Test metrics when all trades are winners."""
    equity_curve = pd.Series([100000, 110000])
    trades = pd.DataFrame(
        {
            "pnl": [1000, 2000, 1500],  # All positive
            "entry_date": pd.date_range("2023-01-01", periods=3),
            "exit_date": pd.date_range("2023-01-02", periods=3),
        }
    )

    metrics = calculate_backtest_metrics(equity_curve, trades=trades)
    assert metrics.num_trades == 3
    assert metrics.num_winning_trades == 3
    assert metrics.num_losing_trades == 0
    assert metrics.win_rate == 1.0
    assert metrics.profit_factor == 0  # gross_loss is 0
    assert metrics.avg_win == 1500
    assert metrics.largest_win == 2000


def test_calculate_metrics_all_losing_trades():
    """Test metrics when all trades are losers."""
    equity_curve = pd.Series([100000, 90000])
    trades = pd.DataFrame(
        {
            "pnl": [-1000, -2000, -500],  # All negative
            "entry_date": pd.date_range("2023-01-01", periods=3),
            "exit_date": pd.date_range("2023-01-02", periods=3),
        }
    )

    metrics = calculate_backtest_metrics(equity_curve, trades=trades)
    assert metrics.num_trades == 3
    assert metrics.num_winning_trades == 0
    assert metrics.num_losing_trades == 3
    assert metrics.win_rate == 0.0
    assert metrics.avg_loss == -1166.6666666666667  # Mean of negative values
    assert metrics.largest_loss == -2000
    assert metrics.profit_factor == 0  # gross_profit is 0


def test_calculate_metrics_mixed_trades():
    """Test metrics when trades are mixed (winners and losers)."""
    equity_curve = pd.Series([100000, 105000])
    trades = pd.DataFrame(
        {
            "pnl": [3000, -1000, 2000, -500],  # Mixed
            "entry_date": pd.date_range("2023-01-01", periods=4),
            "exit_date": pd.date_range("2023-01-02", periods=4),
        }
    )

    metrics = calculate_backtest_metrics(equity_curve, trades=trades)
    assert metrics.num_trades == 4
    assert metrics.num_winning_trades == 2  # +3000, +2000
    assert metrics.num_losing_trades == 2  # -1000, -500
    assert metrics.win_rate == 0.5
    gross_profit = 5000
    gross_loss = 1500
    assert metrics.profit_factor == gross_profit / gross_loss
    assert metrics.avg_win == 2500
    assert metrics.avg_loss == -750
    assert metrics.largest_win == 3000
    assert metrics.largest_loss == -1000


def test_calculate_metrics_zero_pnl_trades():
    """Test metrics when there are zero PnL trades."""
    equity_curve = pd.Series([100000, 100000])
    trades = pd.DataFrame(
        {
            "pnl": [1000, 0, -500],  # Zero is neither winning nor losing (> 0 or < 0)
            "entry_date": pd.date_range("2023-01-01", periods=3),
            "exit_date": pd.date_range("2023-01-02", periods=3),
        }
    )

    metrics = calculate_backtest_metrics(equity_curve, trades=trades)
    assert metrics.num_trades == 2
    assert metrics.num_winning_trades == 1  # Only > 0
    assert metrics.num_losing_trades == 1  # Only < 0
    assert metrics.win_rate == 1 / 2  # 1 winning out of 2
    assert metrics.profit_factor == 1000 / 500  # gross_profit / gross_loss


def test_calculate_metrics_short_equity_curve():
    """Test metrics when equity curve has less than 2 points."""
    equity_curve = pd.Series([100000])
    trades = pd.DataFrame({"pnl": [1000, -500]})

    metrics = calculate_backtest_metrics(equity_curve, trades=trades)
    assert metrics.total_return == 0.0
    assert metrics.num_trades == 0


def test_backtest_metrics_to_dict():
    """Test BacktestMetrics to_dict method."""
    metrics = BacktestMetrics(
        total_return=1000,
        total_return_pct=1.0,
        sharpe_ratio=1.5,
        num_trades=10,
    )
    result = metrics.to_dict()
    assert result["total_return"] == 1000
    assert result["total_return_pct"] == 1.0
    assert result["sharpe_ratio"] == 1.5
    assert result["num_trades"] == 10


class TestBacktestMetricsNanHandling:
    """Test NaN handling in backtest metrics."""

    def test_calculate_backtest_metrics_with_nan_equity(self):
        """Test backtest metrics with NaN in equity curve."""
        equity_curve = pd.Series([100000, np.nan, 105000, np.nan, 110000])
        metrics = calculate_backtest_metrics(equity_curve)
        # After dropna in calculations, should still produce valid results
        assert isinstance(metrics.total_return, (int, float))
        assert isinstance(metrics.sharpe_ratio, (int, float))

    def test_calculate_backtest_metrics_with_nan_in_trades(self):
        """Test backtest metrics with NaN in trades."""
        equity_curve = pd.Series([100000, 105000, 110000])
        trades = pd.DataFrame({"pnl": [1000, np.nan, -500]})
        metrics = calculate_backtest_metrics(equity_curve, trades=trades)
        # NaN values in pnl don't affect the calculation logic as written
        assert metrics.num_trades == 3

    def test_calculate_backtest_metrics_with_all_zeros_trades(self):
        """Test backtest metrics when all trades have pnl == 0."""
        equity_curve = pd.Series([100000, 100000, 100000])
        trades = pd.DataFrame({"pnl": [0, 0, 0]})
        metrics = calculate_backtest_metrics(equity_curve, trades=trades)
        assert metrics.num_trades == 0
        assert metrics.num_winning_trades == 0
        assert metrics.num_losing_trades == 0
        assert metrics.win_rate == 0
        assert metrics.profit_factor == 0

    def test_calculate_backtest_metrics_with_all_positive_trades(self):
        """Test backtest metrics when all trades are profitable."""
        equity_curve = pd.Series([100000, 105000, 110000])
        trades = pd.DataFrame({"pnl": [1000, 500, 2000]})
        metrics = calculate_backtest_metrics(equity_curve, trades=trades)
        assert metrics.num_winning_trades == 3
        assert metrics.num_losing_trades == 0
        assert metrics.win_rate == 1.0
        assert metrics.profit_factor == 0  # gross_loss is 0, so division gives 0 as implemented

    def test_calculate_backtest_metrics_with_all_negative_trades(self):
        """Test backtest metrics when all trades are losing."""
        equity_curve = pd.Series([100000, 95000, 90000])
        trades = pd.DataFrame({"pnl": [-1000, -500, -2000]})
        metrics = calculate_backtest_metrics(equity_curve, trades=trades)
        assert metrics.num_winning_trades == 0
        assert metrics.num_losing_trades == 3
        assert metrics.win_rate == 0.0
        assert metrics.profit_factor == 0  # gross_profit is 0

    def test_calculate_backtest_metrics_short_equity_curve_all_zeros(self):
        """Test edge cases with short equity curve."""
        # Less than 2 points
        equity_curve = pd.Series([0])
        metrics = calculate_backtest_metrics(equity_curve)
        assert metrics.total_return == 0.0

    def test_calculate_backtest_metrics_zero_initial_value(self):
        """Test when initial equity is zero."""
        equity_curve = pd.Series([0, 1000, 2000])
        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            metrics = calculate_backtest_metrics(equity_curve)
        # Division by zero is avoided; pct return is defined as 0.0
        assert metrics.total_return == 2000.0
        assert metrics.total_return_pct == 0.0
        # No "divide by zero" RuntimeWarning should be raised
        assert not any(
            issubclass(w.category, RuntimeWarning) and "divide by zero" in str(w.message)
            for w in recorded
        )

    def test_calculate_backtest_metrics_single_return_no_nan(self):
        """A two-point equity curve yields a single return with undefined std.

        The Sharpe ratio must be 0.0 rather than NaN.
        """
        equity_curve = pd.Series([100000, 101000])
        metrics = calculate_backtest_metrics(equity_curve)
        assert not np.isnan(metrics.sharpe_ratio)
        assert metrics.sharpe_ratio == pytest.approx(0.0)


class TestBacktestMetricsPeriodsPerYear:
    """Test the ``periods_per_year`` annualization parameter."""

    EQUITY = pd.Series([100.0, 102.0, 101.0, 104.0, 103.0, 106.0, 108.0])

    def _returns(self):
        return self.EQUITY.pct_change().dropna()

    def test_periods_per_year_applies_to_every_annualized_metric(self):
        """All annualized metrics must use the same periods_per_year value."""
        returns = self._returns()
        metrics = calculate_backtest_metrics(self.EQUITY, risk_free_rate=0.02, periods_per_year=12)

        assert metrics.annual_return == pytest.approx(returns.mean() * 12)
        assert metrics.annual_return_pct == pytest.approx(returns.mean() * 12 * 100)
        assert metrics.volatility == pytest.approx(returns.std() * np.sqrt(12))
        assert metrics.sharpe_ratio == pytest.approx(
            (returns.mean() - 0.02 / 12) / returns.std() * np.sqrt(12)
        )
        shortfalls = np.minimum(returns.to_numpy(dtype=float) - 0.02 / 12, 0.0)
        downside_dev = np.sqrt(np.mean(shortfalls**2))
        assert metrics.sortino_ratio == pytest.approx(
            (returns.mean() - 0.02 / 12) / downside_dev * np.sqrt(12)
        )
        running_max = self.EQUITY.cummax()
        max_dd = ((self.EQUITY - running_max) / running_max).min()
        assert metrics.calmar_ratio == pytest.approx((returns.mean() * 12) / abs(max_dd))

    def test_default_is_daily_annualization(self):
        """The default periods_per_year (252) reproduces daily annualization."""
        returns = self._returns()
        metrics = calculate_backtest_metrics(self.EQUITY, risk_free_rate=0.02)

        assert metrics.annual_return == pytest.approx(returns.mean() * 252)
        assert metrics.volatility == pytest.approx(returns.std() * np.sqrt(252))
        assert metrics.sharpe_ratio == pytest.approx(
            (returns.mean() - 0.02 / 252) / returns.std() * np.sqrt(252)
        )

    def test_metrics_are_internally_consistent_across_periods(self):
        """Changing only periods_per_year must not desynchronize the metrics."""
        for periods in (12, 52, 252):
            metrics = calculate_backtest_metrics(self.EQUITY, periods_per_year=periods)
            returns = self._returns()
            assert metrics.volatility == pytest.approx(returns.std() * np.sqrt(periods))
            assert metrics.sharpe_ratio == pytest.approx(
                (returns.mean() - 0.02 / periods) / returns.std() * np.sqrt(periods)
            )


class TestBacktestMetricsUnrealizedPnl:
    """Test the ``unrealized_pnl`` field of the backtest metrics."""

    EQUITY = pd.Series([100.0, 102.0, 101.0, 104.0])

    def test_the_field_defaults_to_zero(self):
        """A metrics object that nobody filled in reports no unrealized PnL."""
        metrics = BacktestMetrics()

        assert metrics.unrealized_pnl == 0.0
        assert metrics.to_dict()["unrealized_pnl"] == 0.0

    def test_the_function_cannot_derive_the_unrealized_pnl(self):
        """The metrics function only sees an equity curve and a trade log.

        Neither of them carries the market value of a position that is still
        open, so the field stays at zero when the function is called
        directly. Only the engine, which knows the open positions, fills it
        in.
        """
        trades = pd.DataFrame({"pnl": [100.0, -50.0]})
        metrics = calculate_backtest_metrics(self.EQUITY, trades=trades)

        assert metrics.unrealized_pnl == 0.0

    def test_the_field_is_reported_in_the_dictionary(self):
        """The unrealized PnL is part of the reported metrics."""
        metrics = BacktestMetrics(total_pnl=100.0, unrealized_pnl=-25.0)

        assert metrics.to_dict()["unrealized_pnl"] == -25.0
        assert metrics.to_dict()["total_pnl"] == 100.0

    def test_function_accepts_unrealized_pnl_parameter(self):
        """Passing ``unrealized_pnl`` to the function populates the field.

        Covers the branch where ``unrealized_pnl is not None``.
        """
        trades = pd.DataFrame({"pnl": [100.0, -50.0]})
        metrics = calculate_backtest_metrics(self.EQUITY, trades=trades, unrealized_pnl=42.5)

        assert metrics.unrealized_pnl == pytest.approx(42.5)

    def test_function_falls_back_to_zero_when_positions_raise(self):
        """When summing position unrealized PnL raises, the field stays 0.0.

        Covers the defensive ``except Exception`` branch.
        """

        class BadPosition:
            @property
            def unrealized_pnl(self):
                raise RuntimeError("boom")

        positions = {"AAPL": BadPosition()}
        metrics = calculate_backtest_metrics(self.EQUITY, positions=positions)

        assert metrics.unrealized_pnl == 0.0


class TestBacktestResultMetricPassthrough:
    """``BacktestResult`` exposes metrics through ``getattr``-guarded properties.

    The properties fall back to ``0`` when the wrapped ``metrics`` object does
    not carry the attribute, so a result built from a partial metrics object
    never raises ``AttributeError``. The fallback also tolerates falsy values
    such as ``None``.
    """

    def test_defaults_when_metrics_is_empty(self):
        """A bare ``BacktestMetrics()`` reports zero for every passthrough."""
        result = _result(BacktestMetrics())

        assert result.num_trades == 0
        assert result.trade_count == 0
        assert result.win_rate == 0.0
        assert result.sharpe_ratio == 0.0
        assert result.max_drawdown_pct == 0.0

    def test_passes_through_real_values(self):
        """The properties forward the values stored on ``metrics``."""
        metrics = BacktestMetrics(
            num_trades=7,
            win_rate=0.5714285714285714,
            sharpe_ratio=1.25,
            max_drawdown_pct=-12.5,
        )
        result = _result(metrics)

        assert result.num_trades == 7
        assert result.trade_count == 7
        assert result.win_rate == pytest.approx(0.5714285714285714)
        assert result.sharpe_ratio == 1.25
        assert result.max_drawdown_pct == -12.5

    def test_falls_back_when_metrics_lacks_the_attribute(self):
        """A metrics object missing an attribute is treated as zero."""
        partial = SimpleNamespace(num_trades=4, win_rate=0.5)
        result = _result(partial)

        assert result.num_trades == 4
        assert result.win_rate == 0.5
        assert result.sharpe_ratio == 0.0
        assert result.max_drawdown_pct == 0.0

    def test_tolerates_falsy_attribute_values(self):
        """``None`` and ``0`` on the metrics object both map to zero."""
        partial = SimpleNamespace(
            num_trades=None,
            win_rate=None,
            sharpe_ratio=None,
            max_drawdown_pct=None,
        )
        result = _result(partial)

        assert result.num_trades == 0
        assert result.win_rate == 0.0
        assert result.sharpe_ratio == 0.0
        assert result.max_drawdown_pct == 0.0

    def test_trade_count_aliases_num_trades(self):
        """``trade_count`` mirrors ``num_trades`` even when the source is missing."""
        result = _result(SimpleNamespace())

        assert result.trade_count == result.num_trades == 0


def test_backtest_result_metric_passthrough_fallback():
    """BacktestResult metric passthrough returns 0 when metrics lacks attrs."""
    result = _result(SimpleNamespace())
    assert result.num_trades == 0
    assert result.trade_count == 0
    assert result.win_rate == 0.0
    assert result.sharpe_ratio == 0.0
    assert result.max_drawdown_pct == 0.0


def test_backtest_result_metric_passthrough_zero_values():
    """Fallback also covers falsy attribute values."""
    result = _result(
        SimpleNamespace(num_trades=0, win_rate=0.0, sharpe_ratio=0.0, max_drawdown_pct=0.0)
    )
    assert result.num_trades == 0
    assert result.win_rate == 0.0
    assert result.sharpe_ratio == 0.0
    assert result.max_drawdown_pct == 0.0


def test_backtest_result_metric_passthrough_remaining_attrs():
    """Remaining metric passthrough properties fall back when missing."""
    result = _result(SimpleNamespace())
    assert result.sortino_ratio == 0.0
    assert result.calmar_ratio == 0.0
    assert result.profit_factor == 0.0
    assert result.max_drawdown == 0.0
    assert result.total_pnl == 0.0
    assert result.unrealized_pnl == 0.0


class TestBacktestMetricsNewRiskMetrics:
    """Test new risk metrics added to BacktestMetrics."""

    EQUITY = pd.Series([100.0, 102.0, 101.0, 104.0, 103.0, 106.0, 108.0])

    def test_var_cvar_metrics_populated(self):
        """Test that VaR and CVaR metrics are calculated."""
        metrics = calculate_backtest_metrics(self.EQUITY)

        assert metrics.var_95 != 0.0
        assert metrics.var_99 != 0.0
        assert metrics.cvar_95 != 0.0
        assert metrics.cvar_99 != 0.0
        # VaR 99 should be more negative (worse) than VaR 95
        assert metrics.var_99 <= metrics.var_95
        # CVaR should be more negative than corresponding VaR
        assert metrics.cvar_95 <= metrics.var_95
        assert metrics.cvar_99 <= metrics.var_99

    def test_omega_ratio_populated(self):
        """Test that Omega ratio is calculated."""
        metrics = calculate_backtest_metrics(self.EQUITY)
        assert metrics.omega_ratio != 0.0
        assert isinstance(metrics.omega_ratio, float)

    def test_market_relative_metrics_populated_when_market_returns_provided(self):
        """Test that beta, alpha, treynor, information_ratio are calculated when market_returns provided."""
        market_returns = pd.Series([0.01, 0.015, -0.005, 0.012, -0.003, 0.008, 0.01])
        metrics = calculate_backtest_metrics(self.EQUITY, market_returns=market_returns)

        assert metrics.beta != 0.0
        assert metrics.alpha != 0.0
        assert metrics.treynor_ratio != 0.0
        assert metrics.information_ratio != 0.0

    def test_market_relative_metrics_zero_when_no_market_returns(self):
        """Test that market-relative metrics remain zero when market_returns not provided."""
        metrics = calculate_backtest_metrics(self.EQUITY)

        assert metrics.beta == 0.0
        assert metrics.alpha == 0.0
        assert metrics.treynor_ratio == 0.0
        assert metrics.information_ratio == 0.0

    def test_new_metrics_in_to_dict(self):
        """Test that new metrics are included in to_dict output."""
        metrics = calculate_backtest_metrics(self.EQUITY)
        d = metrics.to_dict()

        assert "var_99" in d
        assert "cvar_95" in d
        assert "cvar_99" in d
        assert "beta" in d
        assert "alpha" in d
        assert "treynor_ratio" in d
        assert "information_ratio" in d
        assert "omega_ratio" in d

    def test_new_metrics_default_to_zero_in_dataclass(self):
        """Test that new metrics default to zero in BacktestMetrics constructor."""
        metrics = BacktestMetrics()

        assert metrics.var_99 == 0.0
        assert metrics.cvar_95 == 0.0
        assert metrics.cvar_99 == 0.0
        assert metrics.beta == 0.0
        assert metrics.alpha == 0.0
        assert metrics.treynor_ratio == 0.0
        assert metrics.information_ratio == 0.0
        assert metrics.omega_ratio == 0.0


class TestBacktestMetricsFromDict:
    """Test BacktestMetrics.from_dict deserialization."""

    def test_from_dict_round_trips_to_dict(self):
        """from_dict must reconstruct a metrics object equal to its to_dict output."""
        metrics = BacktestMetrics(
            total_return=15000.0,
            total_pnl=12000.0,
            total_return_pct=15.0,
            annual_return=0.12,
            annual_return_pct=12.0,
            volatility=0.2,
            max_drawdown=-0.08,
            max_drawdown_pct=-8.0,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            calmar_ratio=1.5,
            win_rate=0.6,
            profit_factor=1.4,
            num_trades=10,
            num_winning_trades=6,
            num_losing_trades=4,
            avg_win=500.0,
            avg_loss=-250.0,
            largest_win=1200.0,
            largest_loss=-900.0,
            var_95=-0.03,
            var_99=-0.05,
            cvar_95=-0.04,
            cvar_99=-0.06,
            beta=1.1,
            alpha=0.02,
            treynor_ratio=0.09,
            information_ratio=0.4,
            omega_ratio=1.25,
            unrealized_pnl=300.0,
        )
        reconstructed = BacktestMetrics.from_dict(metrics.to_dict())
        assert reconstructed == metrics

    def test_from_dict_defaults_missing_keys_to_zero(self):
        """Missing keys must fall back to the dataclass defaults."""
        metrics = BacktestMetrics.from_dict({"sharpe_ratio": 1.5, "num_trades": 3})

        assert metrics.total_return == 0.0
        assert metrics.total_pnl == 0.0
        assert metrics.total_return_pct == 0.0
        assert metrics.annual_return == 0.0
        assert metrics.annual_return_pct == 0.0
        assert metrics.volatility == 0.0
        assert metrics.max_drawdown == 0.0
        assert metrics.max_drawdown_pct == 0.0
        assert metrics.sharpe_ratio == 1.5
        assert metrics.sortino_ratio == 0.0
        assert metrics.calmar_ratio == 0.0
        assert metrics.win_rate == 0.0
        assert metrics.profit_factor == 0.0
        assert metrics.num_trades == 3
        assert metrics.num_winning_trades == 0
        assert metrics.num_losing_trades == 0
        assert metrics.avg_win == 0.0
        assert metrics.avg_loss == 0.0
        assert metrics.largest_win == 0.0
        assert metrics.largest_loss == 0.0
        assert metrics.var_95 == 0.0
        assert metrics.var_99 == 0.0
        assert metrics.cvar_95 == 0.0
        assert metrics.cvar_99 == 0.0
        assert metrics.beta == 0.0
        assert metrics.alpha == 0.0
        assert metrics.treynor_ratio == 0.0
        assert metrics.information_ratio == 0.0
        assert metrics.omega_ratio == 0.0
        assert metrics.unrealized_pnl == 0.0

    def test_from_dict_ignores_extra_keys(self):
        """Extra keys in the dictionary must not raise."""
        data = BacktestMetrics(total_return=100.0).to_dict()
        data["unknown_metric"] = 42.0
        data["another_extra"] = "not-a-number"
        metrics = BacktestMetrics.from_dict(data)
        assert metrics.total_return == 100.0
        assert metrics.num_trades == 0

    def test_from_dict_preserves_integer_trade_counts(self):
        """Integer trade-count fields must survive a dictionary round-trip."""
        metrics = BacktestMetrics(num_trades=7, num_winning_trades=4, num_losing_trades=3)
        reconstructed = BacktestMetrics.from_dict(metrics.to_dict())
        assert reconstructed.num_trades == 7
        assert reconstructed.num_winning_trades == 4
        assert reconstructed.num_losing_trades == 3
        assert isinstance(reconstructed.num_trades, int)
