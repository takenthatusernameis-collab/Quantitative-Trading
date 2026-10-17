"""Tests for backtest metrics edge cases.

Covers ``calculate_backtest_metrics`` behaviour with no trades, all winning
trades, all losing trades, mixed trades, zero-PnL trades, and short equity
curves.
"""

import pandas as pd
import pytest

from quant_trading.backtest.metrics import BacktestMetrics, calculate_backtest_metrics


def _equity(values: list[float]) -> pd.Series:
    return pd.Series(
        values,
        index=pd.date_range("2024-01-01", periods=len(values), freq="D"),
    )


def test_short_equity_curve_returns_default_metrics():
    metrics = calculate_backtest_metrics(_equity([100_000.0]))
    assert metrics == BacktestMetrics()
    assert metrics.total_return == 0.0
    assert metrics.num_trades == 0


def test_no_trades_returns_equity_only_metrics():
    equity = _equity([100_000.0, 101_000.0, 102_000.0])
    metrics = calculate_backtest_metrics(equity, trades=None)

    assert metrics.num_trades == 0
    assert metrics.num_winning_trades == 0
    assert metrics.num_losing_trades == 0
    assert metrics.win_rate == 0.0
    assert metrics.profit_factor == 0.0
    assert metrics.avg_win == 0.0
    assert metrics.avg_loss == 0.0
    assert metrics.largest_win == 0.0
    assert metrics.largest_loss == 0.0
    assert metrics.total_return == 2_000.0
    assert metrics.total_return_pct == pytest.approx(2.0)


def test_empty_trades_dataframe():
    equity = _equity([100_000.0, 101_000.0])
    trades = pd.DataFrame(columns=["pnl"])
    metrics = calculate_backtest_metrics(equity, trades=trades)

    assert metrics.num_trades == 0
    assert metrics.num_winning_trades == 0
    assert metrics.num_losing_trades == 0
    assert metrics.win_rate == 0.0
    assert metrics.profit_factor == 0.0


def test_all_winning_trades_profit_factor_zero():
    equity = _equity([100_000.0, 101_000.0])
    trades = pd.DataFrame({"pnl": [100.0, 200.0]})
    metrics = calculate_backtest_metrics(equity, trades=trades)

    assert metrics.num_trades == 2
    assert metrics.num_winning_trades == 2
    assert metrics.num_losing_trades == 0
    assert metrics.win_rate == 1.0
    # No losing trades → gross_loss == 0 → profit factor defined as 0.
    assert metrics.profit_factor == 0.0
    assert metrics.avg_win == pytest.approx(150.0)
    assert metrics.largest_win == 200.0
    assert metrics.avg_loss == 0.0
    assert metrics.largest_loss == 0.0


def test_all_losing_trades_profit_factor_zero():
    equity = _equity([100_000.0, 101_000.0])
    trades = pd.DataFrame({"pnl": [-100.0, -200.0]})
    metrics = calculate_backtest_metrics(equity, trades=trades)

    assert metrics.num_trades == 2
    assert metrics.num_winning_trades == 0
    assert metrics.num_losing_trades == 2
    assert metrics.win_rate == 0.0
    # No winning trades → gross_profit == 0 → profit factor == 0.
    assert metrics.profit_factor == 0.0
    assert metrics.avg_win == 0.0
    assert metrics.avg_loss == pytest.approx(-150.0)
    assert metrics.largest_win == 0.0
    assert metrics.largest_loss == -200.0


def test_mixed_trades_profit_factor():
    equity = _equity([100_000.0, 101_000.0])
    trades = pd.DataFrame({"pnl": [100.0, -50.0, 200.0, -100.0]})
    metrics = calculate_backtest_metrics(equity, trades=trades)

    assert metrics.num_trades == 4
    assert metrics.num_winning_trades == 2
    assert metrics.num_losing_trades == 2
    assert metrics.win_rate == 0.5
    # gross_profit = 300, gross_loss = 150 → profit factor == 2.
    assert metrics.profit_factor == pytest.approx(2.0)
    assert metrics.avg_win == pytest.approx(150.0)
    assert metrics.avg_loss == pytest.approx(-75.0)
    assert metrics.largest_win == 200.0
    assert metrics.largest_loss == -100.0


def test_zero_pnl_trades_not_counted_as_win_or_loss():
    equity = _equity([100_000.0, 101_000.0])
    trades = pd.DataFrame({"pnl": [100.0, -50.0, 0.0]})
    metrics = calculate_backtest_metrics(equity, trades=trades)

    assert metrics.num_trades == 3
    assert metrics.num_winning_trades == 1
    assert metrics.num_losing_trades == 1
    assert metrics.win_rate == pytest.approx(1 / 3)
    assert metrics.profit_factor == pytest.approx(2.0)
