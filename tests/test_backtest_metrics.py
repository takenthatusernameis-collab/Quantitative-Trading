"""Tests for backtest metrics calculation."""

import numpy as np
import pandas as pd

from quant_trading.backtest.metrics import BacktestMetrics, calculate_backtest_metrics


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
    assert metrics.num_trades == 3
    assert metrics.num_winning_trades == 1  # Only > 0
    assert metrics.num_losing_trades == 1  # Only < 0
    assert metrics.win_rate == 1 / 3  # 1 winning out of 3
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
